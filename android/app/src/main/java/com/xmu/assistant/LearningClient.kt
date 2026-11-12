package com.xmu.assistant

import okhttp3.MediaType.Companion.toMediaType
import okhttp3.MultipartBody
import okhttp3.Request
import okhttp3.RequestBody.Companion.asRequestBody
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.HttpUrl.Companion.toHttpUrl
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.time.Instant
import java.time.LocalDateTime
import java.time.OffsetDateTime
import java.time.ZoneId

internal val learningKinds = linkedMapOf("homework" to "作业", "exam" to "测验", "questionnaire" to "问卷", "discussion" to "讨论", "material" to "资料")
internal data class LearningTask(
    val id: String, val courseId: String, val courseName: String, val title: String,
    val kind: String, val deadline: String = "", val status: String = "未完成", val locked: Boolean = false,
) {
    val key get() = "$courseId:$kind:$id"
    val due: Instant? get() = parseLearningTime(deadline)
    val url get() = "https://lnt.xmu.edu.cn/course/$courseId/learning-activity#/" + when(kind) {
        "exam" -> "exam/$id"; "questionnaire" -> "questionnaire/$id"; else -> id
    }
    fun toJson() = JSONObject().put("id",id).put("course_id",courseId).put("course_name",courseName).put("title",title)
        .put("type",kind).put("end_time",deadline).put("submitted",status=="已提交").put("submitted_status",if(status=="草稿") "draft" else "").put("is_locked",locked)
}
internal fun parseLearningTime(text: String): Instant? = if(text.isBlank()) null else
    runCatching { OffsetDateTime.parse(text).toInstant() }.getOrElse {
        runCatching { LocalDateTime.parse(text).atZone(ZoneId.of("Asia/Shanghai")).toInstant() }.getOrNull()
    }
internal fun parseLearningTask(o: JSONObject, courseId: String="", courseName: String=""): LearningTask {
    val id=o.optRealString("id"); val course=o.optRealString("course_id").ifBlank { courseId }
    require(id.isNotBlank() && course.isNotBlank()) { "待办缺少课程或活动标识" }
    return LearningTask(id,course,o.optRealString("course_name").ifBlank { courseName },o.optRealString("title").ifBlank { "未命名活动" },
        o.optRealString("type").ifBlank { "homework" },o.optRealString("end_time").ifBlank { o.optRealString("deadline") },
        if(o.optBoolean("submitted")) "已提交" else if(o.optRealString("submitted_status") in listOf("draft","is_draft")) "草稿" else "未完成",o.optBoolean("is_locked"))
}
internal fun meaningfulLearningHtml(html: String): String {
    val body=html.replace(Regex("(?is)<(style|script)[^>]*>.*?</\\1>"), "")
    val text=body.replace(Regex("<[^>]+>"),"").replace(Regex("&(?:nbsp|#160|#x[aA]0);")," ")
        .replace(Regex("[\\s\\u00a0\\u200b\\ufeff]"),"")
    return if(text.isEmpty() && !Regex("(?i)<(?:img|video|audio|object|iframe)\\b").containsMatchIn(body)) "" else html.trim()
}
internal fun userLearningUploads(o: JSONObject): List<JSONObject> = (o.optJSONArray("uploads") ?: JSONArray()).objects()
    .filter { it.optRealString("source") != "auto-generated-pdf" }
internal fun JSONArray.objects(): List<JSONObject> = (0 until length()).mapNotNull { optJSONObject(it) }
internal data class HomeworkSnapshot(val detail: JSONObject, val submission: JSONObject, val history: List<JSONObject>, val group: Boolean)
internal class LearningSubmissionUncertain : IllegalStateException("提交结果待核实，已保留草稿和附件。请重读平台记录，避免直接重复提交。")

internal class LearningClient(
    private val cookie: String,
    private val transport: QueryHttpTransport = OkHttpQueryTransport(),
    private val ensureCurrent: () -> Unit = {},
    private val storageTransport: ((Request) -> String)? = null,
) {
    private val base="https://lnt.xmu.edu.cn"
    internal fun request(method: String, path: String, body: JSONObject? = null): JSONObject {
        ensureCurrent()
        val result=transport.execute(QueryHttpRequest(base+path,method,
            mapOf("Cookie" to cookie,"Accept" to "application/json","User-Agent" to "Mozilla/5.0 (Linux; Android) XMUAssistant"),
            if(body!=null) "application/json" else "",body?.toString().orEmpty(),oneShot=method!="GET"))
        if(result.code==401 || result.code in 300..399 && result.location.orEmpty().contains("login",true)) throw MainSessionExpiredException()
        check(result.code in 200..299) { "平台请求失败（${result.code}）" }
        if(result.code==204) return JSONObject()
        val json=runCatching { JSONObject(result.body) }.getOrElse { error("平台返回了网页，无法确认结果，请重新登录或在原平台查看") }
        check(!json.has("errors") || json.isNull("errors") || json.opt("errors")?.toString().orEmpty() in listOf("[]","{}","")) { "平台未接受操作，请检查作业要求" }
        return json
    }
    fun todos(): List<LearningTask> {
        val list=request("GET","/api/todos").optJSONArray("todo_list") ?: error("平台待办格式变化，保留上次结果")
        return list.objects().map { parseLearningTask(it) }
    }
    fun homeworkList(course: CourseSummary): List<LearningTask> = buildList {
        for(page in 1..100) {
            val response=request("GET","/api/courses/${course.id}/homework-activities?page=$page&page_size=100")
            val rows=response.optJSONArray("homework_activities") ?: error("作业列表格式变化")
            addAll(rows.objects().map { parseLearningTask(it,course.id,course.title) })
            if(page>=response.optInt("pages",1) || rows.length()==0) return@buildList
        }
        error("分页过多，请在原平台查询")
    }
    fun homework(task: LearningTask): HomeworkSnapshot {
        val detail=request("GET","/api/activities/${task.id}")
        require(detail.optRealString("course_id")==task.courseId && detail.optRealString("type")=="homework") { "课程或活动类型不匹配，请刷新待办" }
        if(detail.optBoolean("submit_by_group")) return HomeworkSnapshot(detail,JSONObject(),emptyList(),true)
        val user=request("GET","/api/profile").get("id").toString()
        return HomeworkSnapshot(detail,request("GET","/api/course/activities/${task.id}/students/$user/submission"),
            request("GET","/api/activities/${task.id}/students/$user/submission_list").optJSONArray("list")?.objects().orEmpty(),false)
    }
    fun upload(file: File): JSONObject {
        require(file.isFile && file.length()>0) { "附件不存在或为空" }
        val meta=request("POST","/api/uploads",JSONObject().put("name",file.name).put("size",file.length()).put("parent_type",JSONObject.NULL)
            .put("parent_id",0).put("is_scorm",false).put("is_wmpkg",false))
        val id=meta.get("id")
        val target=base.toHttpUrl().resolve(meta.getString("upload_url")) ?: error("上传地址无效")
        require(target.isHttps && target.username.isEmpty() && target.password.isEmpty()) { "上传地址必须为 HTTPS" }
        val sameOrigin=target.host==base.toHttpUrl().host && target.port==443
        // Storage never receives the school's Cookie; redirects and automatic replay are disabled.
        val client=XmuHttpClients.download.newBuilder().writeTimeout(120,java.util.concurrent.TimeUnit.SECONDS).followRedirects(false).followSslRedirects(false).retryOnConnectionFailure(false).build()
        fun send(request: Request): String {
            ensureCurrent()
            storageTransport?.let {return it(request)}
            return client.newCall(request).execute().use { response -> check(response.isSuccessful) { "上传失败（${response.code}）" }; response.body?.string().orEmpty() }
        }
        val source=LearningFileBody(file, java.net.URLConnection.guessContentTypeFromName(file.name) ?: "application/octet-stream", ensureCurrent)
        val storage=meta.optRealString("storage_type").uppercase()
        if(storage=="QINIU") {
            val token=request("GET","/api/uptoken?id=$id").getString("uptoken")
            val contexts=mutableListOf<String>()
            val total=file.length()
            var offset=0L
            // The storage protocol requires 4 MiB blocks, including for large camera photos.
            while(offset<total) {
                val size=minOf(4L*1024*1024,total-offset)
                val block=send(Request.Builder().url(target.toString().trimEnd('/')+"/mkblk/$size").header("Authorization","UpToken $token")
                    .post(LearningFileBody(file,"application/octet-stream",ensureCurrent,offset,size)).build())
                contexts+=JSONObject(block).getString("ctx");offset+=size
            }
            send(Request.Builder().url(target.toString().trimEnd('/')+"/mkfile/${file.length()}").header("Authorization","UpToken $token")
                .post(LearningOneShotBody(contexts.joinToString(",").toRequestBody("text/plain;charset=UTF-8".toMediaType()))).build())
        } else {
            val body=if(storage=="S3" && meta.optRealString("transcoder")=="WRPC") source else
                MultipartBody.Builder().setType(MultipartBody.FORM).addFormDataPart("file",file.name,source).build()
            val builder=Request.Builder().url(target).put(body)
            if(sameOrigin) builder.header("Cookie",cookie)
            send(builder.build())
        }
        if(storage=="S3") request("POST","/internal-api/upload/callback/$id",JSONObject().put("file_key",id))
        return JSONObject().put("id",id).put("name",file.name)
    }
    fun downloadAttachment(context: android.content.Context, upload: JSONObject): File {
        val ref=upload.optRealString("reference_id")
        var url=if(ref.isNotBlank()) request("GET","/api/uploads/reference/$ref/url").getString("url").toHttpUrl()
            else (base+"/api/uploads/${upload.get("id")}/blob").toHttpUrl()
        val client=XmuHttpClients.download.newBuilder().followRedirects(false).followSslRedirects(false).build()
        val raw=upload.optRealString("name").ifBlank {"作业附件"}
        val name=raw.replace(Regex("[\\\\/:*?\"<>|\\p{Cntrl}]"),"_").trim('.').take(180).ifBlank {"作业附件"}
        val directory=File(context.cacheDir,"exports/${java.util.UUID.randomUUID()}").apply {mkdirs()}
        for(hop in 0..5) {
            ensureCurrent();require(url.isHttps && url.username.isEmpty() && url.password.isEmpty()){ "下载地址无效" }
            val builder=Request.Builder().url(url)
            if(url.host==base.toHttpUrl().host && url.port==443) builder.header("Cookie",cookie)
            client.newCall(builder.build()).execute().use {response->
                if(response.code in 300..399) {url=url.resolve(response.header("Location").orEmpty()) ?: error("下载跳转无效")}
                else {
                    check(response.isSuccessful){"下载失败（${response.code}）"}
                    val target=File(directory,name)
                    requireNotNull(response.body).byteStream().use {input->target.outputStream().use {output->
                        val buffer=ByteArray(65536)
                        while(true){ensureCurrent();val count=input.read(buffer);if(count<0)break;output.write(buffer,0,count)}
                    }}
                    return target
                }
            }
        }
        error("下载跳转过多")
    }
    fun submit(task: LearningTask, html: String, uploads: List<JSONObject>, draft: Boolean): HomeworkSnapshot {
        val content=meaningfulLearningHtml(html)
        val files=uploads.filter { it.optRealString("source")!="auto-generated-pdf" }
        val expected=files.map { it.get("id").toString() }.toSet()
        fun matches(snapshot: HomeworkSnapshot): Boolean {
            val sub=snapshot.submission
            return sub.has("id") && !sub.isNull("id") && sub.optBoolean("is_draft")==draft && meaningfulLearningHtml(sub.optRealString("comment"))==content &&
                userLearningUploads(sub).map { it.get("id").toString() }.toSet()==expected &&
                (content.isNotBlank() || sub.optJSONArray("uploads")?.objects().orEmpty().none { it.optRealString("source")=="auto-generated-pdf" })
        }
        val before=homework(task)
        require(!before.group) { "分组作业请在原平台提交" }
        require(!before.detail.optBoolean("is_closed") && (!before.detail.has("is_started") || before.detail.optBoolean("is_started"))) { "作业当前不可提交" }
        if(matches(before)) return before
        ensureCurrent()
        try { request("POST","/api/course/activities/${task.id}/submissions",JSONObject().put("comment",content)
            .put("uploads",JSONArray(files.map { it.get("id") })).put("slides",JSONArray()).put("is_draft",draft))
        } catch(error: Exception) { ensureCurrent() /* Read back once; never repeat the write. */ }
        val after=try {homework(task)} catch(_:Exception) {throw LearningSubmissionUncertain()}
        if(!matches(after)) throw LearningSubmissionUncertain()
        return after
    }
}

private class LearningOneShotBody(private val delegate:okhttp3.RequestBody):okhttp3.RequestBody() {
    override fun contentType()=delegate.contentType()
    override fun contentLength()=delegate.contentLength()
    override fun isOneShot()=true
    override fun writeTo(sink:okio.BufferedSink)=delegate.writeTo(sink)
}

private class LearningFileBody(private val file:File,private val mime:String,private val guard:()->Unit,
    private val offset:Long=0,private val length:Long=file.length()):okhttp3.RequestBody() {
    override fun contentType()=mime.toMediaType()
    override fun contentLength()=length
    override fun isOneShot()=true
    override fun writeTo(sink:okio.BufferedSink) {
        file.inputStream().use {input->
            input.channel.position(offset)
            var remaining=length
            val buffer=ByteArray(65536)
            while(remaining>0){guard();val count=input.read(buffer,0,minOf(buffer.size.toLong(),remaining).toInt());check(count>=0){"附件在上传中发生变化"};sink.write(buffer,0,count);remaining-=count}
        }
    }
}
