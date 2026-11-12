package com.xmu.assistant

import androidx.compose.foundation.Image
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.state.ToggleableState
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp

internal fun safeCoursewareSegment(text:String)=text.replace(Regex("[\\\\/:*?\"<>|\\p{Cntrl}]"),"_").trim().trim('.').take(120).ifBlank {"未分组"}
internal fun coursewareRelativeDirectories(item:CoursewareUiItem):List<String> {
    val course=item.courseTitle.ifBlank {item.courseId}
    val chapter=listOf(item.moduleName,item.syllabusName).filter {it.isNotBlank()}.distinct().joinToString(" - ")
    return listOf(course,chapter.ifBlank {"未分组"}).map(::safeCoursewareSegment)
}
internal fun mobileFileIcon(filename:String):Int=when(filename.substringAfterLast('.',"").lowercase()) {
    "pdf"->R.drawable.file_pdf
    "doc","docx","odt"->R.drawable.file_word
    "xls","xlsx","csv"->R.drawable.file_table
    "ppt","pptx"->R.drawable.file_powerpoint
    "zip","rar","7z","gz"->R.drawable.file_zip
    "jpg","jpeg","png","gif","webp"->R.drawable.file_image
    "mp4","mov","mkv"->R.drawable.file_video
    "mp3","wav","m4a"->R.drawable.file_audio
    "py"->R.drawable.file_python
    "ipynb"->R.drawable.file_jupyter
    else->R.drawable.file_document
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
internal fun CoursewareMobilePage(
    courses:List<CourseSummary>,selectedCourse:CourseSummary?,coursewareItems:List<CoursewareUiItem>,selectedIds:Set<String>,
    onRefreshCourses:()->Unit,onCourseSelected:(CourseSummary)->Unit,onToggle:(String)->Unit,onToggleGroup:(Set<String>)->Unit,
    onSelectAll:()->Unit,onDownload:()->Unit,onRefreshCourseware:()->Unit,onOpenPlatform:()->Unit,
    downloadProgress:String,downloadLoading:Boolean,coursesLoading:Boolean,coursesRefreshError:String,
    coursewareLoading:Boolean,coursewareRefreshError:String,loggedIn:Boolean,
    owner:String="",
) {
    var picker by remember {mutableStateOf(false)}
    var query by rememberSaveable {mutableStateOf("")}
    var expanded by rememberSaveable(selectedCourse?.id) {mutableStateOf(listOf<String>())}
    val modules=remember(coursewareItems){coursewareItems.groupBy {it.moduleName.ifBlank {"未分组"}}}
    fun toggle(key:String){expanded=if(key in expanded) expanded-key else expanded+key}
    Column(Modifier.fillMaxSize(),verticalArrangement=Arrangement.spacedBy(8.dp)) {
        OutlinedButton(onClick={picker=true},modifier=Modifier.fillMaxWidth()){Text(selectedCourse?.displayName ?: "选择课程")}
        if(!loggedIn) EmptyState("请先登录","登录后即可读取课程课件。")
        if(coursesRefreshError.isNotBlank()) Text(coursesRefreshError,color=MaterialTheme.colorScheme.error)
        if(coursewareRefreshError.isNotBlank()) Text(coursewareRefreshError,color=MaterialTheme.colorScheme.error)
        if(selectedCourse!=null) {
            Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.spacedBy(8.dp)) {
                OutlinedButton(onClick=onSelectAll){Text(if(coursewareItems.isNotEmpty() && coursewareItems.all {it.id in selectedIds}) "取消全选" else "全选")}
                OutlinedButton(onClick=onRefreshCourseware,enabled=!coursewareLoading){Text(if(coursewareLoading) "读取中" else "刷新")}
                Button(onClick=onDownload,enabled=selectedIds.isNotEmpty() && !downloadLoading,modifier=Modifier.weight(1f)){Text("下载 ${selectedIds.size}")}
            }
            if(downloadProgress.isNotBlank()) Text(downloadProgress,style=MaterialTheme.typography.labelSmall)
            Text("按课程 / 章节 / 课件活动保存",style=MaterialTheme.typography.labelSmall,color=MaterialTheme.colorScheme.onSurfaceVariant)
        }
        LazyColumn(Modifier.weight(1f),verticalArrangement=Arrangement.spacedBy(2.dp)) {
            if(selectedCourse!=null && owner.isNotBlank()) item("local-materials") {
                LocalCourseMaterials(selectedCourse,owner,modules.keys.toList())
            }
            modules.forEach { (module,files) ->
                val key="module:$module"
                item(key) {CoursewareFolderRow(module,files.map {it.id}.toSet(),selectedIds,key in expanded,{toggle(key)},{onToggleGroup(files.map {it.id}.toSet())})}
                if(key in expanded) {
                    files.groupBy {it.activityId}.forEach { (activity,attachments) ->
                        val activityKey="$key:$activity"
                        item(activityKey) {Box(Modifier.padding(start=12.dp)) {CoursewareFolderRow(attachments.first().title,attachments.map {it.id}.toSet(),selectedIds,activityKey in expanded,{toggle(activityKey)},{onToggleGroup(attachments.map {it.id}.toSet())})}}
                        if(activityKey in expanded) items(attachments,key={"$activityKey:${it.id}"}) {file ->
                            Row(Modifier.fillMaxWidth().clickable {onToggle(file.id)}.padding(start=24.dp,top=6.dp,bottom=6.dp),verticalAlignment=Alignment.CenterVertically,horizontalArrangement=Arrangement.spacedBy(8.dp)) {
                                Checkbox(file.id in selectedIds,{onToggle(file.id)})
                                Image(painterResource(mobileFileIcon(file.filename)),null,Modifier.size(24.dp))
                                Column(Modifier.weight(1f)) {Text(file.filename.ifBlank {"平台入口"},style=MaterialTheme.typography.bodyMedium);Text(file.downloadStatus,style=MaterialTheme.typography.labelSmall,color=MaterialTheme.colorScheme.onSurfaceVariant)}
                            }
                        }
                    }
                }
            }
            if(selectedCourse!=null && coursewareItems.isEmpty() && !coursewareLoading) item{EmptyState("暂无课件","可以点击刷新重新读取。")}
            if(selectedCourse!=null) item {TextButton(onClick=onOpenPlatform,modifier=Modifier.fillMaxWidth()){Text("原平台打开")}}
        }
    }
    if(picker) ModalBottomSheet(onDismissRequest={picker=false}) {
        Column(Modifier.padding(16.dp),verticalArrangement=Arrangement.spacedBy(8.dp)) {
            Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.SpaceBetween){Text("选择课程",style=MaterialTheme.typography.titleLarge);TextButton(onClick=onRefreshCourses,enabled=!coursesLoading){Text("刷新课程")}}
            OutlinedTextField(query,{query=it},placeholder={Text("搜索课程或学期")},singleLine=true,modifier=Modifier.fillMaxWidth())
            LazyColumn(Modifier.heightIn(max=360.dp)) {items(courses.filter {it.displayName.contains(query,true)}) {course ->
                TextButton(onClick={onCourseSelected(course);picker=false},modifier=Modifier.fillMaxWidth()){Text(course.displayName)}
            }}
        }
    }
}

@Composable private fun CoursewareFolderRow(title:String,ids:Set<String>,selected:Set<String>,expanded:Boolean,onExpand:()->Unit,onCheck:()->Unit) {
    val count=ids.count {it in selected}
    Row(Modifier.fillMaxWidth(),verticalAlignment=Alignment.CenterVertically) {
        TriStateCheckbox(if(count==0)ToggleableState.Off else if(count==ids.size)ToggleableState.On else ToggleableState.Indeterminate,onCheck)
        Row(Modifier.weight(1f).clickable(onClick=onExpand).padding(vertical=12.dp),verticalAlignment=Alignment.CenterVertically,horizontalArrangement=Arrangement.spacedBy(8.dp)) {
            Icon(painterResource(if(expanded)R.drawable.ic_expand_less else R.drawable.ic_expand_more),contentDescription=if(expanded)"收起目录" else "展开目录",modifier=Modifier.size(18.dp))
            Image(painterResource(R.drawable.file_folder),null,Modifier.size(24.dp))
            Column(Modifier.weight(1f)){Text(title,style=MaterialTheme.typography.bodyMedium,fontWeight=FontWeight.Medium);Text("${ids.size} 项资料",style=MaterialTheme.typography.labelSmall,color=MaterialTheme.colorScheme.onSurfaceVariant)}
        }
    }
}
