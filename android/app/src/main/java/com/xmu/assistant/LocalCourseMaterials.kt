package com.xmu.assistant

import android.content.ContentValues
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.os.Environment
import android.provider.MediaStore
import android.provider.OpenableColumns
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.core.content.FileProvider
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.nio.file.Files
import java.nio.file.StandardCopyOption
import java.security.MessageDigest
import java.util.UUID

internal const val DEFAULT_LOCAL_REFERENCE_MIB=50L
internal fun shouldReferenceLocal(size:Long,thresholdMiB:Long,requestedReference:Boolean)=
    requestedReference || size<0 || size>thresholdMiB*1024*1024

internal class LocalCourseLibrary(private val context:Context,owner:String) {
    private val ownerKey=MessageDigest.getInstance("SHA-256").digest(owner.toByteArray()).joinToString(""){"%02x".format(it)}.take(24)
    private val directory=File(context.filesDir,"local_materials/$ownerKey").apply{mkdirs()}
    private val manifest=File(directory,"library.json")
    private fun read():JSONObject=if(manifest.exists()) {
        check(manifest.length()<=8*1024*1024){"本地资料清单过大"}
        JSONObject(manifest.readText()).also {check(it.optInt("schema")==1){"本地资料清单格式无效"}}
    } else JSONObject().put("schema",1).put("reference_threshold_mib",50).put("courses",JSONObject())
    private fun save(data:JSONObject) {
        val temp=File(directory,"manifest-${UUID.randomUUID()}.tmp")
        try {
            temp.writeText(data.toString())
            try {Files.move(temp.toPath(),manifest.toPath(),StandardCopyOption.REPLACE_EXISTING,StandardCopyOption.ATOMIC_MOVE)}
            catch(error:java.nio.file.AtomicMoveNotSupportedException){Files.move(temp.toPath(),manifest.toPath(),StandardCopyOption.REPLACE_EXISTING)}
        }
        finally {temp.delete()}
    }
    fun threshold()=read().optLong("reference_threshold_mib",50).coerceIn(1,2048)
    fun items(courseId:String):List<JSONObject> {
        val list=read().getJSONObject("courses").optJSONArray(courseId) ?: JSONArray()
        return (0 until list.length()).map{list.getJSONObject(it)}
    }
    fun remove(courseId:String,id:String) {synchronized(lock) {
        val data=read();val rows=items(courseId).filter{it.getString("resource_id")!=id}
        data.getJSONObject("courses").put(courseId,JSONArray(rows));save(data)
    }}
    fun add(uri:Uri,courseId:String,courseTitle:String,chapter:String,requestedReference:Boolean,thresholdMiB:Long,replaceId:String?=null):JSONObject {
        val resolver=context.contentResolver
        var name="资料";var size=-1L
        resolver.query(uri,arrayOf(OpenableColumns.DISPLAY_NAME,OpenableColumns.SIZE),null,null,null)?.use {cursor->
            if(cursor.moveToFirst()) {
                val n=cursor.getColumnIndex(OpenableColumns.DISPLAY_NAME);if(n>=0) name=cursor.getString(n) ?: name
                val s=cursor.getColumnIndex(OpenableColumns.SIZE);if(s>=0 && !cursor.isNull(s)) size=cursor.getLong(s)
            }
        }
        val reference=replaceId!=null || shouldReferenceLocal(size,thresholdMiB,requestedReference)
        var target=uri
        if(reference) {
            try {resolver.takePersistableUriPermission(uri,Intent.FLAG_GRANT_READ_URI_PERMISSION)}
            catch(error:SecurityException) {throw IllegalArgumentException("此来源不支持长期引用，请先保存到手机文件后重新选择")}
        } else {
            // A bounded stream also handles providers that under-report the size.
            val targetDirectory=listOf(courseTitle.ifBlank{courseId},chapter,"本地资料").map(::safeCoursewareSegment)
            val temp=File(directory,"import-${UUID.randomUUID()}.tmp")
            try {
                var copied=0L
                checkNotNull(resolver.openInputStream(uri)){"无法读取文件"}.use {input->temp.outputStream().use {output->
                    val buffer=ByteArray(64*1024)
                    while(true) {val n=input.read(buffer);if(n<0) break;copied+=n
                        if(copied>thresholdMiB*1024*1024) {
                            return add(uri,courseId,courseTitle,chapter,true,thresholdMiB,replaceId)
                        }
                        output.write(buffer,0,n)
                    }
                }}
                size=copied
                if(Build.VERSION.SDK_INT>=29) {
                    val values=ContentValues().apply {
                        put(MediaStore.Downloads.DISPLAY_NAME,name)
                        put(MediaStore.Downloads.MIME_TYPE,resolver.getType(uri) ?: "application/octet-stream")
                        put(MediaStore.Downloads.RELATIVE_PATH,Environment.DIRECTORY_DOWNLOADS+"/虾大助手/"+targetDirectory.joinToString("/")+"/")
                        put(MediaStore.Downloads.IS_PENDING,1)
                    }
                    val published=checkNotNull(resolver.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI,values)){"无法创建系统下载文件"}
                    try {
                        checkNotNull(resolver.openOutputStream(published)).use {output->temp.inputStream().use{it.copyTo(output)}}
                        check(resolver.update(published,ContentValues().apply{put(MediaStore.Downloads.IS_PENDING,0)},null,null)>0)
                        target=published
                    } catch(error:Exception) {resolver.delete(published,null,null);throw error}
                } else {
                    val base=File(context.getExternalFilesDir("course-materials"),ownerKey+"/"+courseId+"/"+targetDirectory.drop(1).joinToString("/"))
                    base.mkdirs();var file=File(base,safeCoursewareSegment(name));var counter=1
                    while(file.exists()){file=File(base,"${counter++}-"+safeCoursewareSegment(name))}
                    temp.copyTo(file)
                    target=FileProvider.getUriForFile(context,context.packageName+".fileprovider",file)
                }
            } finally {temp.delete()}
        }
        val row=JSONObject().put("resource_id",replaceId ?: UUID.randomUUID().toString()).put("course_id",courseId)
            .put("course_title",courseTitle).put("chapter",chapter).put("name",name).put("uri",target.toString())
            .put("bytes",size).put("mode",if(reference) "reference" else "copy")
        synchronized(lock) {
            val data=read();val old=items(courseId).filter{it.getString("resource_id")!=replaceId}
            data.getJSONObject("courses").put(courseId,JSONArray(old+row));data.put("reference_threshold_mib",thresholdMiB);save(data)
        }
        return row
    }
    companion object {private val lock=Any()}
}

/** Added inside the course list; no all-device scan, timer, OCR, or model. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
internal fun LocalCourseMaterials(course:CourseSummary,owner:String,chapters:List<String>) {
    val context=LocalContext.current
    val scope=rememberCoroutineScope()
    val library=remember(owner){LocalCourseLibrary(context,owner)}
    var rows by remember(owner,course.id){mutableStateOf(emptyList<JSONObject>())}
    var busy by remember{mutableStateOf(false)}
    var message by remember(owner,course.id){mutableStateOf("")}
    var showImport by remember{mutableStateOf(false)}
    var reference by remember{mutableStateOf(false)}
    var chapter by remember(course.id){mutableStateOf("补充资料")}
    var threshold by remember{mutableStateOf("50")}
    var selected by remember{mutableStateOf<JSONObject?>(null)}
    var showAll by remember{mutableStateOf(false)}
    fun refresh(){scope.launch {rows=withContext(Dispatchers.IO){library.items(course.id)}}}
    LaunchedEffect(owner,course.id) {try {rows=withContext(Dispatchers.IO){library.items(course.id)};threshold=withContext(Dispatchers.IO){library.threshold().toString()}} catch(error:Exception){message=error.message ?: "读取失败"}}
    val pick=rememberLauncherForActivityResult(ActivityResultContracts.OpenMultipleDocuments()){uris->
        if(uris.isNotEmpty()) scope.launch {
            busy=true
            val count=uris.size
            var success=0;var refs=0;val errors=mutableListOf<String>()
            withContext(Dispatchers.IO) {uris.forEach {uri->try {
                val row=library.add(uri,course.id,course.title,chapter,reference,threshold.toLongOrNull()?.coerceIn(1,2048) ?: 50)
                success++;if(row.getString("mode")=="reference") refs++
            } catch(error:Exception){errors+=error.message ?: "添加失败"}}}
            message="已添加 $success/$count 项，其中引用 $refs 项"+errors.take(2).joinToString("；",prefix=if(errors.isEmpty()) "" else "；")
            busy=false;refresh()
        }
    }
    val relocate=rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()){uri->
        val row=selected
        if(uri!=null && row!=null) scope.launch {try {
            withContext(Dispatchers.IO){library.add(uri,course.id,course.title,row.getString("chapter"),true,50,row.getString("resource_id"))}
            selected=null;refresh()
        } catch(error:Exception){message=error.message ?: "定位失败"}}
    }
    Column(Modifier.fillMaxWidth(),verticalArrangement=Arrangement.spacedBy(6.dp)) {
        Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.SpaceBetween) {
            Text("本地补充资料",style=MaterialTheme.typography.titleSmall)
            TextButton(onClick={showImport=true},enabled=!busy){Text(if(busy) "添加中…" else "添加资料")}
        }
        if(message.isNotBlank()) Text(message,style=MaterialTheme.typography.labelSmall)
        rows.take(3).forEach {row->
            ListItem(headlineContent={Text(row.getString("name"))},supportingContent={Text(row.getString("chapter")+" · "+if(row.getString("mode")=="reference") "引用原位置" else "本地副本")},
                modifier=Modifier.clickable{selected=row})
        }
        if(rows.size>3) TextButton(onClick={showAll=true}){Text("查看全部 ${rows.size} 项资料")}
    }
    if(showAll) ModalBottomSheet(onDismissRequest={showAll=false}) {
        androidx.compose.foundation.lazy.LazyColumn(Modifier.fillMaxWidth().heightIn(max=440.dp)) {
            items(rows.size,key={rows[it].getString("resource_id")}) {index->val row=rows[index]
                ListItem(headlineContent={Text(row.getString("name"))},supportingContent={Text(row.getString("chapter"))},modifier=Modifier.clickable{selected=row;showAll=false})
            }
        }
    }
    if(showImport) AlertDialog(onDismissRequest={showImport=false},title={Text("添加本地资料")},text={Column(verticalArrangement=Arrangement.spacedBy(8.dp)) {
        Text("仅保存本机。超过阈值或大小未知的文件自动引用原位置。")
        OutlinedTextField(chapter,{chapter=it},label={Text("归入章节")},singleLine=true)
        if(chapters.isNotEmpty()) Text("可用章节："+chapters.take(4).joinToString("、"),style=MaterialTheme.typography.labelSmall)
        OutlinedTextField(threshold,{threshold=it.filter(Char::isDigit)},label={Text("自动引用阈值（MiB，1–2048）")},singleLine=true)
        Row {Checkbox(reference,{reference=it});Text("全部引用原位置")}
    }},confirmButton={TextButton(onClick={showImport=false;pick.launch(arrayOf("*/*"))}){Text("选择文件")}},dismissButton={TextButton(onClick={showImport=false}){Text("取消")}})
    selected?.let {row->
        AlertDialog(
            onDismissRequest={selected=null},
            title={Text(row.getString("name"))},
            text={Text("移除只取消课程关联，保留文件。原文件移动或删除后可重新定位。")},
            confirmButton={
                TextButton(onClick={
                    try {
                        val uri=Uri.parse(row.getString("uri"))
                        context.startActivity(Intent(Intent.ACTION_VIEW).setDataAndType(uri,context.contentResolver.getType(uri) ?: "*/*")
                            .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION))
                        selected=null
                    } catch(error:Exception){message="文件暂不可用，请重新定位或安装对应查看器";selected=null}
                }){Text("打开")}
            },
            dismissButton={
                Row {
                    TextButton(onClick={relocate.launch(arrayOf("*/*"))}){Text("重新定位")}
                    TextButton(onClick={scope.launch {
                        withContext(Dispatchers.IO){library.remove(course.id,row.getString("resource_id"))}
                        selected=null;refresh()
                    }}){Text("移除")}
                }
            },
        )
    }
}
