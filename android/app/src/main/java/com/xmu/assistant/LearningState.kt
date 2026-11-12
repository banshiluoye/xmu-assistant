package com.xmu.assistant

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import androidx.compose.runtime.*
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.time.Instant
import java.time.temporal.ChronoUnit

internal class LearningLocalStore(context: Context, owner: String) {
    val directory = File(context.filesDir,"learning/${cookieFingerprint(owner)}").apply { mkdirs() }
    fun read(name: String): JSONObject = synchronized(lock) { runCatching { JSONObject(File(directory,"$name.json").readText()) }.getOrDefault(JSONObject()) }
    fun write(name: String, value: JSONObject, ensureCurrent: () -> Unit = {}) = synchronized(lock) {
        ensureCurrent()
        val file=File(directory,"$name.json")
        val temp=File(directory,"$name.tmp")
        temp.writeText(value.toString())
        ensureCurrent()
        try {
            java.nio.file.Files.move(temp.toPath(),file.toPath(),java.nio.file.StandardCopyOption.ATOMIC_MOVE,java.nio.file.StandardCopyOption.REPLACE_EXISTING)
        } catch(_:java.nio.file.AtomicMoveNotSupportedException) {
            java.nio.file.Files.move(temp.toPath(),file.toPath(),java.nio.file.StandardCopyOption.REPLACE_EXISTING)
        }
    }
    fun tasks()=read("tasks").optJSONArray("items")?.objects().orEmpty().mapNotNull { runCatching { parseLearningTask(it).let { task -> task.copy(status=it.optRealString("local_status").ifBlank { task.status }) } }.getOrNull() }
    fun draftName(task: LearningTask)="draft-${cookieFingerprint(task.key)}"
    companion object { private val lock=Any() }
}

/** Foreground and the existing monitor share one read, cache and notification deduplication gate. */
internal object LearningPoller {
    private val scheduled=java.util.concurrent.atomic.AtomicBoolean(false)
    private val executor=java.util.concurrent.Executors.newSingleThreadExecutor { r -> Thread(r,"learning-background-read").apply {isDaemon=true} }
    fun pollAsync(context:Context,owner:String,cookie:String,interval:Int,ensureCurrent:()->Unit) {
        if(!scheduled.compareAndSet(false,true)) return
        executor.execute {try {runCatching {poll(context.applicationContext,owner,cookie,interval,ensureCurrent=ensureCurrent)}} finally {scheduled.set(false)}}
    }
    private val lock=Any()
    private val next=mutableMapOf<String,Long>()
    private val verifiedAt=mutableMapOf<String,Long>()
    private const val VERIFY_RETRY_MS=30*60*1000L
    fun recordConfirmed(store:LearningLocalStore,task:LearningTask,status:String) = synchronized(lock) {
        val cached=store.read("tasks")
        val items=store.tasks().associateBy {it.key}.toMutableMap()
        items[task.key]=task.copy(status=status)
        cached.put("items",JSONArray(items.values.map {it.toJson().put("local_status",it.status)}))
        store.write("tasks",cached)
    }
    /** 待办只列未完成项；消失后先只读核对课程作业记录，再决定是否标「待核实」。 */
    private fun verifiedHomeworkStatuses(client:LearningClient,gate:String,missing:List<LearningTask>):Map<String,String> {
        val now=System.currentTimeMillis()
        val courses=missing.filter {it.kind=="homework"}.groupBy {it.courseId}
            .filterKeys {now-(verifiedAt["$gate:$it"]?:0L)>=VERIFY_RETRY_MS}
        if(courses.isEmpty()) return emptyMap()
        courses.keys.forEach {verifiedAt["$gate:$it"]=now}
        return courses.flatMap { (courseId,tasks) ->
            runCatching {client.homeworkList(CourseSummary(courseId,tasks.first().courseName))}
                .getOrElse {error->if(error is MainSessionExpiredException) throw error else emptyList()}
        }.associate {it.key to it.status}
    }
    fun poll(context: Context, owner: String, cookie: String, intervalSeconds: Int, force: Boolean=false, ensureCurrent: () -> Unit = {}): List<LearningTask> = synchronized(lock) {
        val store=LearningLocalStore(context,owner)
        val gate=cookieFingerprint(owner+cookie)
        if(!force && System.currentTimeMillis() < (next[gate] ?: 0L)) return@synchronized store.tasks()
        ensureCurrent()
        val client=LearningClient(cookie,ensureCurrent=ensureCurrent)
        val fresh=client.todos()
        val old=store.tasks().associateBy { it.key }
        val keys=fresh.map { it.key }.toSet()
        val missing=old.values.filter {it.key !in keys && it.status in setOf("未完成","待核实")}
        val verified=verifiedHomeworkStatuses(client,gate,missing)
        val merged=fresh.map { task ->
            val previous=old[task.key]
            // 待办响应不带完整提交记录，不能用「未完成」覆盖已经确认的提交/草稿。
            if(previous!=null && previous.status in setOf("已提交","草稿") && task.status=="未完成") previous else task
        } + old.values.filter { it.key !in keys }.map {task ->
            when {
                verified.containsKey(task.key) -> task.copy(status=verified.getValue(task.key))
                task.status=="未完成" -> task.copy(status="待核实")
                else -> task
            }
        }
        val previous=store.read("tasks")
        val notified=previous.optJSONArray("notified")?.let { a -> (0 until a.length()).map { a.getString(it) }.toMutableSet() } ?: mutableSetOf()
        val days=store.read("settings").optInt("reminderDays",3).coerceIn(0,30)
        val now=Instant.now()
        val messages=fresh.filter { task ->
            val soon=task.due?.let { it.isAfter(now) && it.isBefore(now.plus(days.toLong(),ChronoUnit.DAYS)) } ?: false
            val mark=task.key+if(soon) ":due:${task.deadline}" else ":new"
            (soon || task.key !in old) && task.status!="已提交" && task.due?.isBefore(now)!=true && notified.add(mark)
        }
        ensureCurrent()
        val rows=JSONArray(merged.map { it.toJson().put("local_status",it.status) })
        store.write("tasks",JSONObject().put("items",rows).put("notified",JSONArray(notified.toList().takeLast(2000))).put("updated",System.currentTimeMillis()),ensureCurrent)
        next.clear();next[gate]=System.currentTimeMillis()+intervalSeconds.coerceAtLeast(1)*1000L
        messages.take(5).forEach { task -> ensureCurrent(); notifyLearningTask(context,task) }
        merged
    }
}

private fun notifyLearningTask(context: Context, task: LearningTask) = runCatching {
    val manager=context.getSystemService(NotificationManager::class.java)
    manager.createNotificationChannel(NotificationChannel("learning_tasks","学习待办",NotificationManager.IMPORTANCE_DEFAULT))
    val intent=Intent(context,MainActivity::class.java).putExtra("open_page","学习待办")
    val pending=PendingIntent.getActivity(context,task.key.hashCode(),intent,PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
    manager.notify(task.key.hashCode(),Notification.Builder(context,"learning_tasks").setSmallIcon(R.drawable.ic_notification)
        .setContentTitle(task.title).setContentText(task.courseName+" · "+task.deadline.ifBlank { "新待办" }).setContentIntent(pending).setAutoCancel(true).build())
}

internal class LearningInboxState(
    private val context: Context, val owner: String, private val cookie: String,
    private val scope: CoroutineScope, private val ensureCurrent: () -> Unit,
    private val createClient: (() -> LearningClient)? = null,
) {
    val store=LearningLocalStore(context,owner)
    var tasks by mutableStateOf(emptyList<LearningTask>())
    var loading by mutableStateOf(false)
    var error by mutableStateOf("")
    var updated by mutableLongStateOf(0L)
    private var dataRevision=0L
    fun confirmSubmission(task:LearningTask,status:String) {
        dataRevision++
        tasks=(tasks.associateBy {it.key}+(task.key to task.copy(status=status))).values.toList()
        scope.launch(Dispatchers.IO) {runCatching {LearningPoller.recordConfirmed(store,task,status)}}
    }
    private val editors=mutableMapOf<String,HomeworkEditState>()
    fun editor(task:LearningTask,initial:HomeworkSnapshot):HomeworkEditState {
        val editor=editors.getOrPut(task.key) {HomeworkEditState(context,this,task,initial,scope)}
        if(editors.size>4) {
            val old=editors.entries.firstOrNull {it.key!=task.key && !it.value.busy}
            if(old!=null) {old.value.saveLocal();editors.remove(old.key)}
        }
        return editor
    }
    fun loadCached() {
        if(updated>0L) return
        scope.launch {
            val cached=withContext(Dispatchers.IO) {store.tasks() to store.read("tasks").optLong("updated")}
            runCatching {ensureCurrent();if(updated==0L && tasks.isEmpty()) {tasks=cached.first;updated=cached.second}}
        }
    }
    fun refresh(interval: Int, force: Boolean=false) {
        if(loading || cookie.isBlank()) return
        loading=true;error=""
        val revision=dataRevision
        scope.launch {
            try {
                val result=withContext(Dispatchers.IO) { LearningPoller.poll(context,owner,cookie,interval,force,ensureCurrent) }
                ensureCurrent()
                val current=tasks.associateBy {it.key}
                tasks=if(revision==dataRevision) result else result.map {task->current[task.key]?.takeIf {it.status in listOf("已提交","草稿")} ?: task}
                updated=System.currentTimeMillis()
            } catch(e: Exception) { runCatching {ensureCurrent();error=e.message.orEmpty()} }
            finally { loading=false }
        }
    }
    fun loadHistory(course: CourseSummary) {
        if(loading) return
        loading=true
        scope.launch {
            try {
                val rows=withContext(Dispatchers.IO) { LearningClient(cookie,ensureCurrent=ensureCurrent).homeworkList(course) }
                ensureCurrent();tasks=(tasks.associateBy {it.key}+rows.associateBy {it.key}).values.toList()
                withContext(Dispatchers.IO) { val cache=store.read("tasks");cache.put("items",JSONArray(tasks.map {it.toJson().put("local_status",it.status)}));store.write("tasks",cache,ensureCurrent) }
            } catch(e:Exception) {runCatching {ensureCurrent();error=e.message.orEmpty()}}
            finally {loading=false}
        }
    }
    fun client()=createClient?.invoke() ?: LearningClient(cookie,ensureCurrent=ensureCurrent)
    fun assertCurrent()=ensureCurrent()
}
