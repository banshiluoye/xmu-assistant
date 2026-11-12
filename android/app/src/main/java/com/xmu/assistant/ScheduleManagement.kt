package com.xmu.assistant

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import java.time.LocalDate

@OptIn(ExperimentalMaterial3Api::class)
@Composable
internal fun ScheduleManagementSheet(
    mode: String, groups: List<XmuScheduleGroup>, monday: LocalDate?, store: ScheduleLocalChangeStore,
    onSaved: () -> Unit, onDismiss: () -> Unit,
) {
    var chosen by remember { mutableStateOf(groups.firstOrNull()) }
    var picker by remember { mutableStateOf(false) }
    var name by remember { mutableStateOf(if (mode == "新增课程") "" else chosen?.courseName.orEmpty()) }
    var target by remember { mutableStateOf((monday?.plusDays((chosen?.weekday ?: 1)-1L) ?: LocalDate.now()).toString()) }
    var holidaySource by remember { mutableStateOf("") }
    var start by remember { mutableStateOf((chosen?.startSection ?: 1).toString()) }
    var end by remember { mutableStateOf((chosen?.endSection ?: 2).toString()) }
    var room by remember { mutableStateOf(chosen?.rooms?.joinToString("、").orEmpty()) }
    var teacher by remember { mutableStateOf(chosen?.teachers?.joinToString("、").orEmpty()) }
    var cancelled by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf("") }
    var revision by remember { mutableIntStateOf(0) }
    val saved = remember(revision) { store.read() }
    ModalBottomSheet(onDismissRequest = onDismiss) {
        Column(Modifier.fillMaxWidth().verticalScroll(rememberScrollState()).imePadding().padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Text(mode, style = MaterialTheme.typography.titleLarge)
            Text(if (mode == "节假日调课") "选择实际日期，填写要采用的课表日期；来源留空表示当天放假。" else "只修改这一次上课。整学期的固定排课可从课程详情修改。",
                style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            if (mode == "临时调课") {
                Box {
                    OutlinedButton(onClick = { picker=true }, modifier=Modifier.fillMaxWidth()) {
                        Text(chosen?.let { "${it.courseName} · 周${xmuWeekdayShort(it.weekday)} ${it.startSection}—${it.endSection}节" } ?: "本周没有可调整课程")
                    }
                    DropdownMenu(expanded=picker, onDismissRequest={picker=false}, modifier=Modifier.heightIn(max=280.dp)) {
                        groups.forEach { group -> DropdownMenuItem(text={Text("${group.courseName} · 周${xmuWeekdayShort(group.weekday)} ${group.startSection}—${group.endSection}节")}, onClick={
                            chosen=group; name=group.courseName; start=group.startSection.toString(); end=group.endSection.toString()
                            room=group.rooms.joinToString("、"); teacher=group.teachers.joinToString("、")
                            target=(monday?.plusDays(group.weekday-1L) ?: LocalDate.now()).toString(); picker=false
                        }) }
                    }
                }
            }
            OutlinedTextField(target,{target=it},label={Text(if(mode=="节假日调课") "实际日期 YYYY-MM-DD" else "调整后的日期 YYYY-MM-DD")},singleLine=true,modifier=Modifier.fillMaxWidth())
            if (mode=="节假日调课") {
                OutlinedTextField(holidaySource,{holidaySource=it},label={Text("采用哪天的课表（留空为放假）")},singleLine=true,modifier=Modifier.fillMaxWidth())
            } else {
                if(mode=="新增课程") OutlinedTextField(name,{name=it},label={Text("课程名称")},modifier=Modifier.fillMaxWidth())
                Row(horizontalArrangement=Arrangement.spacedBy(8.dp)) {
                    OutlinedTextField(start,{start=it},label={Text("开始节次")},singleLine=true,modifier=Modifier.weight(1f))
                    OutlinedTextField(end,{end=it},label={Text("结束节次")},singleLine=true,modifier=Modifier.weight(1f))
                }
                OutlinedTextField(room,{room=it},label={Text("教室 / 地点")},modifier=Modifier.fillMaxWidth())
                OutlinedTextField(teacher,{teacher=it},label={Text("教师（可选）")},modifier=Modifier.fillMaxWidth())
                if(mode=="临时调课") Row { Checkbox(cancelled,{cancelled=it}); Text("本次停课",Modifier.padding(top=12.dp)) }
            }
            if(error.isNotBlank()) Text(error,color=MaterialTheme.colorScheme.error)
            Button(onClick={ runCatching {
                val date=LocalDate.parse(target.trim())
                if(mode=="节假日调课") store.saveDay(date,holidaySource.trim().takeIf { it.isNotBlank() }?.let(LocalDate::parse)) else {
                    val from=if(mode=="临时调课") requireNotNull(chosen){"请选择本周课程"} else null
                    val first=start.toInt(); val last=end.toInt()
                    val times=scheduleMovedTimes(first,last,from,groups)
                    val replacement=XmuScheduleGroup(date.dayOfWeek.value,first,last,times.first,times.second,
                        name.trim(),listOf(room.trim()).filter(String::isNotBlank),listOf(teacher.trim()).filter(String::isNotBlank),"临时安排")
                    val selectedDate=from?.let { requireNotNull(monday){"请先校准学期周次"}.plusDays(it.weekday-1L) }
                    val existing=from?.let { course -> store.read().occurrences.firstOrNull { !it.cancelled && it.targetDate==selectedDate && sameScheduleSlot(it.replacement,course) } }
                    store.saveOccurrence(existing?.copy(targetDate=date,replacement=replacement,cancelled=cancelled) ?: ScheduleOccurrenceChange(sourceDate=selectedDate,
                        original=from ?: replacement,targetDate=date,replacement=replacement,cancelled=cancelled))
                }
                revision++; onSaved(); onDismiss()
            }.onFailure { error=it.message ?: "日期或节次无效，请检查" } },modifier=Modifier.fillMaxWidth()) {Text("保存安排")}
            if(saved.occurrences.isNotEmpty() || saved.daySources.isNotEmpty()) {
                HorizontalDivider()
                Text("已保存的临时安排",style=MaterialTheme.typography.titleSmall)
                saved.occurrences.forEach { item -> Row(Modifier.fillMaxWidth()) {
                    Text("${item.original.courseName}\n${item.sourceDate ?: "新增"} → ${if(item.cancelled) "本次停课" else item.targetDate}",Modifier.weight(1f),style=MaterialTheme.typography.bodySmall)
                    TextButton(onClick={store.removeOccurrence(item.id); revision++; onSaved()}) {Text("撤销")}
                } }
                saved.daySources.forEach { (date,source) -> Row(Modifier.fillMaxWidth()) {
                    Text("$date · ${source?.let { "采用 $it 课表" } ?: "放假"}",Modifier.weight(1f),style=MaterialTheme.typography.bodySmall)
                    TextButton(onClick={store.removeDay(date);revision++;onSaved()}) {Text("撤销")}
                } }
            }
            Spacer(Modifier.height(20.dp))
        }
    }
}
