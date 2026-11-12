package com.xmu.assistant

import android.content.Intent
import android.net.Uri
import androidx.activity.compose.BackHandler
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import org.json.JSONObject
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.time.temporal.ChronoUnit

internal fun filterLearningTasks(tasks: List<LearningTask>, course: String, kind: String, status: String, deadline: String, search: String, now: Instant = Instant.now()): List<LearningTask> =
    tasks.filter { t ->
        (course.isBlank() || t.courseId==course) && (kind.isBlank() || t.kind==kind) && (status=="全部状态" || t.status==status) &&
            (search.isBlank() || (t.courseName+t.title).contains(search,true)) && when(deadline) {
                "未过期" -> t.due?.isBefore(now)!=true
                "已逾期" -> t.due?.isBefore(now)==true
                "24 小时内" -> t.due?.let { !it.isBefore(now) && !it.isAfter(now.plus(1,ChronoUnit.DAYS)) }==true
                "7 天内" -> t.due?.let { !it.isBefore(now) && !it.isAfter(now.plus(7,ChronoUnit.DAYS)) }==true
                "无截止时间" -> t.due==null
                else -> true
            }
    }.sortedWith(compareBy<LearningTask> {it.due==null}.thenBy {it.due})

@OptIn(ExperimentalMaterial3Api::class)
@Composable
internal fun LearningHub(state: LearningInboxState, courses: List<CourseSummary>, loggedIn: Boolean, interval: Int) {
    val context=LocalContext.current
    var selected by rememberSaveable { mutableStateOf("") }
    var writing by rememberSaveable { mutableStateOf(false) }
    var search by rememberSaveable { mutableStateOf("") }
    var course by rememberSaveable { mutableStateOf("") }
    var kind by rememberSaveable { mutableStateOf("") }
    var status by rememberSaveable { mutableStateOf("全部状态") }
    var deadline by rememberSaveable { mutableStateOf("未过期") }
    var filter by remember { mutableStateOf(false) }
    var coursePicker by remember { mutableStateOf(false) }
    var courseSearch by remember { mutableStateOf("") }
    val task=remember(selected) { runCatching {parseLearningTask(JSONObject(selected))}.getOrNull() }
    BackHandler(enabled=task!=null) { if(writing) writing=false else selected="" }
    if(task!=null) {
        HomeworkFlow(state,task,writing,onWrite={writing=true},onBack={if(writing)writing=false else selected=""})
        return
    }
    val names=remember(courses,state.tasks) { linkedMapOf<String,String>().apply { courses.forEach {put(it.id,it.title)}; state.tasks.forEach {putIfAbsent(it.courseId,it.courseName)} } }
    val shown=filterLearningTasks(state.tasks,course,kind,status,deadline,search)
    Column(Modifier.fillMaxSize(),verticalArrangement=Arrangement.spacedBy(8.dp)) {
        Row(horizontalArrangement=Arrangement.spacedBy(8.dp)) {
            OutlinedTextField(search,{search=it},placeholder={Text("搜索待办 / 课程")},singleLine=true,modifier=Modifier.weight(1f))
            TextButton(onClick={state.refresh(interval,true)},enabled=loggedIn && !state.loading) {Text(if(state.loading) "刷新中" else "刷新")}
        }
        Row(horizontalArrangement=Arrangement.spacedBy(8.dp)) {
            OutlinedButton(onClick={coursePicker=true},modifier=Modifier.weight(1f)) {Text(names[course] ?: "全部课程",maxLines=1)}
            OutlinedButton(onClick={filter=true}) {Text(if(deadline=="未过期" && kind.isBlank() && status=="全部状态") "筛选" else "筛选中")}
        }
        Text("${shown.size} 项 · 默认隐藏已逾期 · 刷新间隔 $interval 秒",style=MaterialTheme.typography.labelSmall,color=MaterialTheme.colorScheme.onSurfaceVariant)
        if(state.error.isNotBlank()) Text(state.error,color=MaterialTheme.colorScheme.error,style=MaterialTheme.typography.bodySmall)
        if(!loggedIn) EmptyState("请先登录","到首页完成登录后即可查看待办。")
        else LazyColumn(Modifier.weight(1f),verticalArrangement=Arrangement.spacedBy(1.dp)) {
            if(shown.isEmpty()) item {EmptyState("当前没有待办","可在筛选中查看已逾期，或选择课程读取已提交作业。")}
            items(shown,key={it.key}) { item ->
                Column(Modifier.fillMaxWidth().clickable {
                    if(item.kind=="homework") {selected=item.toJson().toString();writing=false}
                    else context.startActivity(Intent(Intent.ACTION_VIEW,Uri.parse(item.url)))
                }.padding(vertical=13.dp,horizontal=4.dp),verticalArrangement=Arrangement.spacedBy(5.dp)) {
                    Text(item.courseName,style=MaterialTheme.typography.labelMedium,color=MaterialTheme.colorScheme.onSurfaceVariant)
                    Text(item.title,style=MaterialTheme.typography.titleSmall,fontWeight=FontWeight.Medium)
                    Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.SpaceBetween) {
                        Text(item.due?.atZone(ZoneId.of("Asia/Shanghai"))?.format(DateTimeFormatter.ofPattern("MM-dd HH:mm")) ?: "无截止时间",style=MaterialTheme.typography.bodySmall)
                        Text("${learningKinds[item.kind] ?: item.kind} · ${item.status}",style=MaterialTheme.typography.labelMedium,
                            color=if(item.status=="已提交") themeSuccess() else MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                }
                HorizontalDivider(color=MaterialTheme.colorScheme.outlineVariant.copy(alpha=.5f))
            }
        }
    }
    if(coursePicker) ModalBottomSheet(onDismissRequest={coursePicker=false}) {
        Column(Modifier.padding(16.dp),verticalArrangement=Arrangement.spacedBy(8.dp)) {
            Text("选择课程",style=MaterialTheme.typography.titleLarge)
            OutlinedTextField(courseSearch,{courseSearch=it},placeholder={Text("搜索课程")},singleLine=true,modifier=Modifier.fillMaxWidth())
            LazyColumn(Modifier.heightIn(max=340.dp)) {
                item {TextButton(onClick={course="";coursePicker=false},modifier=Modifier.fillMaxWidth()){Text("全部课程")}}
                items(names.entries.filter {it.value.contains(courseSearch,true)},key={it.key}) {entry ->
                    TextButton(onClick={course=entry.key;coursePicker=false},modifier=Modifier.fillMaxWidth()){Text(entry.value)}
                }
            }
            TextButton(onClick={courses.firstOrNull {it.id==course}?.let(state::loadHistory);coursePicker=false},enabled=course.isNotBlank()) {Text("读取这门课的全部作业状态")}
        }
    }
    if(filter) ModalBottomSheet(onDismissRequest={filter=false}) {
        Column(Modifier.verticalScroll(rememberScrollState()).padding(16.dp),verticalArrangement=Arrangement.spacedBy(10.dp)) {
            Text("待办筛选",style=MaterialTheme.typography.titleLarge)
            LearningChoice("截止时间",deadline,listOf("未过期","全部截止时间","24 小时内","7 天内","已逾期","无截止时间")){deadline=it}
            LearningChoice("类型",learningKinds[kind] ?: "全部类型",listOf("全部类型")+learningKinds.values){label->kind=learningKinds.entries.firstOrNull {it.value==label}?.key.orEmpty()}
            LearningChoice("状态",status,listOf("全部状态","未完成","已提交","草稿","待核实")){status=it}
            var reminder by remember {mutableStateOf(state.store.read("settings").optInt("reminderDays",3).toString())}
            OutlinedTextField(reminder,{reminder=it.filter(Char::isDigit).take(2)},label={Text("临期提醒提前天数（0—30，默认 3）")},modifier=Modifier.fillMaxWidth())
            Button(onClick={val days=reminder.toIntOrNull()?.coerceIn(0,30) ?: 3;state.store.write("settings",state.store.read("settings").put("reminderDays",days));filter=false},modifier=Modifier.fillMaxWidth()){Text("完成")}
            Spacer(Modifier.height(12.dp))
        }
    }
}

@Composable internal fun LearningChoice(label:String,value:String,values:List<String>,onChange:(String)->Unit) {
    var expanded by remember {mutableStateOf(false)}
    Box {
        OutlinedButton(onClick={expanded=true},modifier=Modifier.fillMaxWidth()){Text("$label · $value")}
        DropdownMenu(expanded,{expanded=false}) {values.forEach {item->DropdownMenuItem(text={Text(item)},onClick={onChange(item);expanded=false})}}
    }
}
