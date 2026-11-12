package com.xmu.assistant

import android.content.Context
import android.net.Uri
import android.provider.OpenableColumns
import androidx.compose.runtime.*
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.util.UUID
import java.util.concurrent.Executors

internal class HomeworkEditState(
    private val context: Context, val inbox: LearningInboxState, val task: LearningTask,
    initial: HomeworkSnapshot, private val scope: CoroutineScope,
) {
    var snapshot by mutableStateOf(initial)
    var html by mutableStateOf("")
    var uploads by mutableStateOf(emptyList<JSONObject>())
    var pending by mutableStateOf(emptyList<File>())
    var ready by mutableStateOf(false)
    var busy by mutableStateOf(false)
    var message by mutableStateOf("")
    var uncertain by mutableStateOf(false)
    private val mediaRoot=File(context.filesDir,"homework_uploads/${cookieFingerprint(inbox.owner)}")
    init {
        scope.launch {
            val draft=withContext(Dispatchers.IO){inbox.store.read(inbox.store.draftName(task))}
            inbox.assertCurrent()
            html=meaningfulLearningHtml(if(draft.has("html")) draft.optRealString("html") else initial.submission.optRealString("comment"))
            uploads=if(draft.has("uploads")) userLearningUploads(draft) else userLearningUploads(initial.submission)
            pending=draft.optJSONArray("pending")?.let {a->(0 until a.length()).map {File(a.getString(it))}.filter {it.isFile}}.orEmpty()
            ready=true
        }
    }
    fun saveLocal() {
        if(!ready) return
        val value=JSONObject().put("html",meaningfulLearningHtml(html)).put("uploads",JSONArray(uploads)).put("pending",JSONArray(pending.map {it.absolutePath}))
        val store=inbox.store;val name=store.draftName(task)
        writer.execute {runCatching {store.write(name,value)}.onFailure {error->scope.launch(Dispatchers.Main){message="本地草稿保存失败：${error.message}"}}}
    }
    fun newPhoto(): File {
        val directory=File(mediaRoot,UUID.randomUUID().toString()).apply {mkdirs()}
        return File(directory,"照片-${System.currentTimeMillis()}.jpg")
    }
    fun queuePhoto(file: File) {
        if(file.isFile && file.length()>0) {pending=pending+file;saveLocal();uploadPending()}
        else message="未拍摄照片"
    }
    fun importFiles(uris: List<Uri>) {
        if(busy) return
        busy=true
        scope.launch {
            try {
                val files=withContext(Dispatchers.IO) {uris.map {uri->
                    inbox.assertCurrent()
                    val raw=context.contentResolver.query(uri,arrayOf(OpenableColumns.DISPLAY_NAME),null,null,null)?.use {cursor->if(cursor.moveToFirst()) cursor.getString(0) else null}.orEmpty()
                    val name=raw.replace(Regex("[\\\\/:*?\"<>|\\p{Cntrl}]"),"_").trim('.').take(180).ifBlank {"附件-${System.currentTimeMillis()}"}
                    val dir=File(mediaRoot,UUID.randomUUID().toString()).apply {mkdirs()}
                    val file=File(dir,name)
                    requireNotNull(context.contentResolver.openInputStream(uri)){"无法读取所选文件"}.use {input->file.outputStream().use {output->input.copyTo(output)}}
                    require(file.length()>0){"附件为空：$name"};file
                }}
                inbox.assertCurrent();pending=pending+files;saveLocal()
            } catch(e:Exception){message=e.message.orEmpty()}
            finally {busy=false;uploadPending()}
        }
    }
    fun uploadPending() {
        if(busy || pending.isEmpty() || !ready) return
        busy=true;message="正在上传附件"
        scope.launch {
            try {
                while(pending.isNotEmpty()) {
                    val file=pending.first()
                    val uploaded=withContext(Dispatchers.IO) {inbox.client().upload(file)}
                    inbox.assertCurrent();uploads=uploads+uploaded;pending=pending.filterNot {it==file};saveLocal()
                }
                message="附件已上传，核对后交付作业"
            } catch(e:Exception) {message="上传未完成：${e.message}。可重试。";saveLocal()}
            finally {busy=false}
        }
    }
    fun remove(index:Int) {
        if(busy) return
        if(index<uploads.size) uploads=uploads.filterIndexed {i,_->i!=index} else pending=pending.filterIndexed {i,_->i!=index-uploads.size}
        saveLocal()
    }
    fun submit(draft:Boolean) {
        if(busy || uncertain || pending.isNotEmpty()) return
        if(meaningfulLearningHtml(html).isBlank() && uploads.isEmpty()) {message="请填写正文或添加附件";return}
        busy=true;saveLocal();message=if(draft) "正在保存平台草稿" else "正在交付并核实平台记录"
        scope.launch {
            try {
                val confirmed=withContext(Dispatchers.IO){inbox.client().submit(task,html,uploads,draft)}
                inbox.assertCurrent();snapshot=confirmed;uploads=userLearningUploads(confirmed.submission);html=meaningfulLearningHtml(confirmed.submission.optRealString("comment"))
                inbox.confirmSubmission(task,if(draft) "草稿" else "已提交")
                message=if(draft) "平台草稿已核实" else "已交付作业，平台记录已核实";saveLocal()
            } catch(e:Exception){uncertain=e is LearningSubmissionUncertain;message=e.message.orEmpty()}
            finally {busy=false}
        }
    }
    fun reload() {
        if(busy) return
        busy=true
        scope.launch {
            try {val current=withContext(Dispatchers.IO){inbox.client().homework(task)};inbox.assertCurrent();snapshot=current;uncertain=false
                message="平台记录：${if(current.submission.optBoolean("is_draft")) "草稿" else if(current.submission.has("id") && !current.submission.isNull("id")) "已提交" else "未提交"}。本地编辑内容已保留。"
            }catch(e:Exception){message=e.message.orEmpty()}finally{busy=false}
        }
    }
    companion object {private val writer=Executors.newSingleThreadExecutor {r->Thread(r,"learning-draft-writer").apply {isDaemon=true}}}
}
