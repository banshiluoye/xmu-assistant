package com.xmu.assistant

import android.content.Intent
import android.graphics.Typeface
import android.net.Uri
import android.text.Html
import android.text.Spanned
import android.text.TextWatcher
import android.text.Editable
import android.text.style.StyleSpan
import android.text.style.UnderlineSpan
import android.widget.EditText
import android.widget.TextView
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.core.content.FileProvider
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.io.File

@Composable
internal fun HomeworkFlow(inbox: LearningInboxState, task: LearningTask, writing: Boolean, onWrite:()->Unit, onBack:()->Unit) {
    var snapshot by remember(task.key) {mutableStateOf<HomeworkSnapshot?>(null)}
    var error by remember(task.key) {mutableStateOf("")}
    var revision by remember {mutableIntStateOf(0)}
    LaunchedEffect(task.key,revision) {
        error=""
        runCatching {withContext(Dispatchers.IO){inbox.client().homework(task)}}.onSuccess {inbox.assertCurrent();snapshot=it}.onFailure {error=it.message.orEmpty()}
    }
    Column(Modifier.fillMaxSize(),verticalArrangement=Arrangement.spacedBy(8.dp)) {
        Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.SpaceBetween) {
            TextButton(onClick=onBack){Text(if(writing) "返回作业要求" else "返回待办")}
            TextButton(onClick={revision++}){Text("重读记录")}
        }
        if(error.isNotBlank()) Text(error,color=MaterialTheme.colorScheme.error)
        if(snapshot==null) {if(error.isBlank()) LinearProgressIndicator(Modifier.fillMaxWidth());return@Column}
        val data=requireNotNull(snapshot)
        if(writing) {
            val editor=remember(task.key) {inbox.editor(task,data)}
            HomeworkComposer(editor)
        } else {
            val context=LocalContext.current
            LazyColumn(Modifier.weight(1f),verticalArrangement=Arrangement.spacedBy(12.dp)) {
                item {Text(task.courseName,style=MaterialTheme.typography.labelMedium,color=MaterialTheme.colorScheme.onSurfaceVariant)}
                item {Text(task.title,style=MaterialTheme.typography.headlineSmall,fontWeight=FontWeight.Bold)}
                item {Text("作业要求",style=MaterialTheme.typography.titleMedium)}
                item {HomeworkHtml(data.detail.optRealString("description").ifBlank {data.detail.optJSONObject("data")?.optRealString("description").orEmpty()})}
                item {Text("作业附件",style=MaterialTheme.typography.titleMedium)}
                val attachments=data.detail.optJSONArray("uploads")?.objects().orEmpty()
                if(attachments.isEmpty()) item {Text("没有作业附件",style=MaterialTheme.typography.bodySmall,color=MaterialTheme.colorScheme.onSurfaceVariant)}
                attachments.forEach {upload -> item {TeacherAttachment(inbox,upload)} }
                item {Text("平台记录：${if(data.submission.optBoolean("is_draft")) "草稿" else if(data.submission.has("id") && !data.submission.isNull("id")) "已提交" else "未提交"}",color=if(data.submission.has("id")) themeSuccess() else MaterialTheme.colorScheme.onSurfaceVariant)}
                item {TextButton(onClick={context.startActivity(Intent(Intent.ACTION_VIEW,Uri.parse(task.url)))}){Text("原平台打开")}}
            }
            Button(onClick=onWrite,enabled=!data.group && !task.locked,modifier=Modifier.fillMaxWidth()){Text("写作业")}
            if(data.group) Text("分组作业请从原平台进入对应小组提交。",style=MaterialTheme.typography.bodySmall)
        }
    }
}

@Composable internal fun HomeworkHtml(value:String) {
    val color=MaterialTheme.colorScheme.onSurface.toArgb()
    AndroidView(factory={context->TextView(context).apply {textSize=15f;setTextIsSelectable(true)}},modifier=Modifier.fillMaxWidth(),
        update={view->view.setTextColor(color);view.text=Html.fromHtml(value.ifBlank {"暂无文字要求"},Html.FROM_HTML_MODE_LEGACY)})
}

@Composable private fun TeacherAttachment(inbox:LearningInboxState,upload:JSONObject) {
    val context=LocalContext.current;val scope=rememberCoroutineScope()
    var message by remember {mutableStateOf("")};var busy by remember {mutableStateOf(false)}
    Column {
        OutlinedButton(onClick={busy=true;scope.launch {runCatching {withContext(Dispatchers.IO){inbox.client().downloadAttachment(context,upload)}}.onSuccess {file->
            val uri=FileProvider.getUriForFile(context,"${context.packageName}.fileprovider",file)
            runCatching {context.startActivity(Intent(Intent.ACTION_VIEW).setDataAndType(uri,context.contentResolver.getType(uri) ?: "application/octet-stream").addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION))}
                .onFailure {message="已下载；没有可打开此格式的应用，可从系统分享。"}
        }.onFailure {message=it.message.orEmpty()};busy=false}},enabled=!busy,modifier=Modifier.fillMaxWidth()) {Text(if(busy) "正在下载…" else upload.optRealString("name").ifBlank {"作业附件"})}
        if(message.isNotBlank()) Text(message,style=MaterialTheme.typography.bodySmall)
    }
}

@Composable private fun HomeworkComposer(editor:HomeworkEditState) {
    val context=LocalContext.current
    var confirm by remember {mutableStateOf(false)}
    var nativeEditor by remember {mutableStateOf<EditText?>(null)}
    var photoPath by rememberSaveable {mutableStateOf("")}
    val files=rememberLauncherForActivityResult(ActivityResultContracts.OpenMultipleDocuments()) {uris->if(uris.isNotEmpty()) editor.importFiles(uris)}
    val camera=rememberLauncherForActivityResult(ActivityResultContracts.TakePicture()) {success->if(success && photoPath.isNotBlank()) editor.queuePhoto(File(photoPath));photoPath=""}
    DisposableEffect(editor) {onDispose {editor.saveLocal()}}
    LaunchedEffect(editor.html) {delay(600);editor.saveLocal()}
    if(!editor.ready) {LinearProgressIndicator(Modifier.fillMaxWidth());return}
    val textColor=MaterialTheme.colorScheme.onSurface.toArgb()
    val hintColor=MaterialTheme.colorScheme.onSurfaceVariant.toArgb()
    Column(Modifier.fillMaxSize(),verticalArrangement=Arrangement.spacedBy(8.dp)) {
        Text(editor.task.title,style=MaterialTheme.typography.titleMedium,maxLines=2)
        LazyColumn(Modifier.weight(1f),verticalArrangement=Arrangement.spacedBy(10.dp)) {
            item {Text("正文（可选）",style=MaterialTheme.typography.titleSmall)}
            item {
                Row(Modifier.horizontalScroll(rememberScrollState()),horizontalArrangement=Arrangement.spacedBy(4.dp)) {
                    listOf("加粗","斜体","下划线","列表").forEach {label->TextButton(onClick={nativeEditor?.let {view->
                        val start=view.selectionStart.coerceAtLeast(0);val end=view.selectionEnd.coerceAtLeast(start)
                        if(label=="列表") view.text.insert(start,"• ") else if(end>start) {
                            val span=when(label){"加粗"->StyleSpan(Typeface.BOLD);"斜体"->StyleSpan(Typeface.ITALIC);else->UnderlineSpan()}
                            view.text.setSpan(span,start,end,Spanned.SPAN_EXCLUSIVE_EXCLUSIVE)
                            editor.html=meaningfulLearningHtml(Html.toHtml(view.text,Html.TO_HTML_PARAGRAPH_LINES_CONSECUTIVE))
                        }
                    }}){Text(label)}}
                }
            }
            item {
                AndroidView(factory={ctx->EditText(ctx).apply {
                    nativeEditor=this;minLines=4;maxLines=8;textSize=15f;gravity=android.view.Gravity.TOP
                    hint="填写答案，或直接上传附件";setText(Html.fromHtml(editor.html,Html.FROM_HTML_MODE_LEGACY))
                    addTextChangedListener(object:TextWatcher {
                        override fun beforeTextChanged(s:CharSequence?,start:Int,count:Int,after:Int){}
                        override fun onTextChanged(s:CharSequence?,start:Int,before:Int,count:Int){}
                        override fun afterTextChanged(s:Editable?){editor.html=meaningfulLearningHtml(Html.toHtml(s,Html.TO_HTML_PARAGRAPH_LINES_CONSECUTIVE))}
                    })
                }},modifier=Modifier.fillMaxWidth().heightIn(min=135.dp,max=240.dp),update={view->view.setTextColor(textColor);view.setHintTextColor(hintColor);view.isEnabled=!editor.busy})
            }
            item {Text("上传附件",style=MaterialTheme.typography.titleMedium,fontWeight=FontWeight.Bold)}
            item {
                Row(horizontalArrangement=Arrangement.spacedBy(8.dp)) {
                    OutlinedButton(onClick={files.launch(arrayOf("*/*"))},enabled=!editor.busy,modifier=Modifier.weight(1f)){Text("选择文件")}
                    OutlinedButton(onClick={
                        val file=editor.newPhoto();photoPath=file.absolutePath
                        runCatching {camera.launch(FileProvider.getUriForFile(context,"${context.packageName}.fileprovider",file))}.onFailure {editor.message="没有可用的相机应用"}
                    },enabled=!editor.busy,modifier=Modifier.weight(1f)){Text("拍照上传")}
                }
            }
            if(editor.uploads.isEmpty() && editor.pending.isEmpty()) item {Text("支持多个附件，拍照后作为图片附件上传。",style=MaterialTheme.typography.bodySmall,color=MaterialTheme.colorScheme.onSurfaceVariant)}
            (editor.uploads.map {it.optRealString("name")}+editor.pending.map {it.name}).forEachIndexed {index,name->item {
                Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.spacedBy(8.dp)) {
                    Column(Modifier.weight(1f)) {Text(name,style=MaterialTheme.typography.bodyMedium);Text(if(index<editor.uploads.size) "已上传" else "待上传 / 可重试",style=MaterialTheme.typography.labelSmall,color=if(index<editor.uploads.size)themeSuccess() else themeWarning())}
                    TextButton(onClick={editor.remove(index)},enabled=!editor.busy){Text("移除")}
                }
            }}
            if(editor.pending.isNotEmpty()) item {OutlinedButton(onClick=editor::uploadPending,enabled=!editor.busy,modifier=Modifier.fillMaxWidth()){Text("重试上传")}}
            if(editor.message.isNotBlank()) item {Text(editor.message,style=MaterialTheme.typography.bodySmall)}
            item {Row(horizontalArrangement=Arrangement.spacedBy(8.dp)) {
                TextButton(onClick={editor.saveLocal();editor.message="本地草稿已保存"}){Text("保存本地草稿")}
                TextButton(onClick=editor::reload,enabled=!editor.busy){Text("重读平台记录")}
            }}
        }
        if(editor.busy) LinearProgressIndicator(Modifier.fillMaxWidth())
        Row(horizontalArrangement=Arrangement.spacedBy(8.dp)) {
            OutlinedButton(onClick={editor.submit(true)},enabled=!editor.busy && !editor.uncertain && editor.pending.isEmpty(),modifier=Modifier.weight(1f)){Text("保存平台草稿")}
            Button(onClick={confirm=true},enabled=!editor.busy && !editor.uncertain && editor.pending.isEmpty(),modifier=Modifier.weight(1f)){Text("交付作业")}
        }
    }
    if(confirm) AlertDialog(onDismissRequest={confirm=false},title={Text("确认交付作业")},text={Text("${editor.task.title}\n${editor.uploads.size} 个附件。请确认内容与附件完整。")},
        confirmButton={TextButton(onClick={confirm=false;editor.submit(false)}){Text("确认交付")}},dismissButton={TextButton(onClick={confirm=false}){Text("继续检查")}})
}
