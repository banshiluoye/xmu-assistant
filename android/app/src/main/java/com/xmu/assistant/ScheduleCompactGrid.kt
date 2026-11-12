package com.xmu.assistant

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.layout.Layout
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.TextMeasurer
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.rememberTextMeasurer
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Constraints
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import java.time.LocalDate

/** Seven days share the available width, including overlapping classes. No horizontal scrolling. */
@Composable
internal fun ScheduleCompactWeekGrid(
    groups: List<XmuScheduleGroup>, weekStart: LocalDate?, selectedIsCurrent: Boolean,
    todayWeekday: Int, nowValue: Int, onCourseSelected: (XmuScheduleGroup) -> Unit,
    modifier: Modifier = Modifier,
) {
    val placements = remember(groups) { scheduleGridPlacements(groups.filter { it.weekday in 1..7 && it.startSection in 1..12 }) }
    val sections = maxOf(11, groups.maxOfOrNull { it.endSection.coerceAtMost(12) } ?: 11)
    val lanes = remember(placements) { buildMap<XmuScheduleGroup,Int> {
        scheduleGridClusters(placements.map {it.course}).forEach {cluster->
            val count=(placements.filter {it.course in cluster.courses}.maxOfOrNull {it.lane} ?: 0)+1
            cluster.courses.forEach {put(it,count)}
        }
    } }
    val line = MaterialTheme.colorScheme.outlineVariant.copy(alpha = .45f)
    val surface = MaterialTheme.colorScheme.surface
    val todayColor = themeTodayColumn()
    val textMeasurer = rememberTextMeasurer()
    BoxWithConstraints(modifier.fillMaxSize()) {
        val header = 34.dp
        val axis = 28.dp
        val day = (maxWidth - axis) / 7
        val row = ((maxHeight - header) / sections).coerceAtLeast(1.dp)
        Canvas(Modifier.fillMaxSize()) {
            drawRect(surface)
            if (selectedIsCurrent) drawRect(todayColor, Offset((axis + day * (todayWeekday-1)).toPx(), 0f), androidx.compose.ui.geometry.Size(day.toPx(), size.height))
            for (i in 0..7) {
                val x = (axis + day * i).toPx()
                drawLine(line, Offset(x, 0f), Offset(x, size.height), 1.dp.toPx())
            }
            for (i in 0..sections) {
                val y = (header + row * i).toPx()
                drawLine(line, Offset(0f, y), Offset(size.width, y), 1.dp.toPx())
            }
        }
        Layout(content = {
            Box(contentAlignment = Alignment.Center) { Text("节", style = MaterialTheme.typography.labelSmall) }
            for (dayIndex in 1..7) {
                Column(horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.Center) {
                    Text("周${xmuWeekdayShort(dayIndex)}", style = MaterialTheme.typography.labelMedium,
                        color = if (selectedIsCurrent && dayIndex == todayWeekday) themePrimary() else MaterialTheme.colorScheme.onSurface)
                    Text(weekStart?.plusDays(dayIndex - 1L)?.let { "${it.monthValue}/${it.dayOfMonth}" }.orEmpty(),
                        style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
            }
            for (section in 1..sections) {
                Column(horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.Center) {
                    Text("$section", style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    val fetchedStart=groups.firstOrNull {it.startSection==section}?.startTime
                    if (row >= 42.dp && fetchedStart!=null) Text(formatXmuTime(fetchedStart),
                        style = MaterialTheme.typography.labelSmall.copy(fontSize = 8.sp, lineHeight = 9.sp, letterSpacing = 0.sp),
                        maxLines = 1, color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
            }
            placements.forEach { placement ->
                val group = placement.course
                val base = scheduleCourseColor(group.courseName)
                val background = if (LocalXmuDarkTheme.current) base.copy(alpha = .32f) else base.copy(alpha = .30f)
                Surface(shape = RoundedCornerShape(5.dp), color = background,
                    border=if(selectedIsCurrent && group.weekday==todayWeekday && nowValue in group.startTime..group.endTime) androidx.compose.foundation.BorderStroke(1.dp,themePrimary()) else null,
                    modifier = Modifier.padding(2.dp).semantics {
                        contentDescription = "${weekdayName(group.weekday)}，${group.startSection}到${group.endSection}节，${group.courseName}，${scheduleLocationSummary(group)}"
                    }.clickable { onCourseSelected(group) }) {
                    ScheduleCardLabel(group.courseName, scheduleLocationSummary(group), textMeasurer)
                }
            }
        }, modifier = Modifier.fillMaxSize()) { measurables, constraints ->
            val axisPx = axis.roundToPx()
            val headPx = header.roundToPx()
            val rowPx = row.roundToPx()
            val available = constraints.maxWidth-axisPx
            fun x(day: Int) = axisPx + available * (day-1) / 7
            val labels = measurables.take(8).mapIndexed { i, m -> m.measure(Constraints.fixed(if (i == 0) axisPx else x(i+1)-x(i), headPx)) }
            val periods = measurables.drop(8).take(sections).map { it.measure(Constraints.fixed(axisPx, rowPx)) }
            val cards = placements.mapIndexed { i, p ->
                val width = (x(p.course.weekday+1)-x(p.course.weekday)) / lanes.getValue(p.course)
                val span = (p.course.endSection.coerceAtMost(sections)-p.course.startSection+1).coerceAtLeast(1)
                measurables[8+sections+i].measure(Constraints.fixed(width, rowPx*span))
            }
            layout(constraints.maxWidth, constraints.maxHeight) {
                labels[0].placeRelative(0,0)
                for(i in 1..7) labels[i].placeRelative(x(i),0)
                periods.forEachIndexed { i,p -> p.placeRelative(0,headPx+rowPx*i) }
                cards.forEachIndexed { i,p ->
                    val placement=placements[i]
                    p.placeRelative(x(placement.course.weekday)+placement.lane*p.width, headPx+(placement.course.startSection-1)*rowPx)
                }
            }
        }
    }
}

private val courseFontSizes = listOf(12 to 10, 11 to 9, 10 to 8, 9 to 8)
private val roomCode = Regex("""(?:[A-Za-z]{0,3}[-－]?)\d{2,5}[A-Za-z]?(?:室)?$""")

@Composable
private fun ScheduleCardLabel(title: String, location: String, measurer: TextMeasurer) {
    val density = LocalDensity.current
    val base = MaterialTheme.typography.labelSmall
    fun titleStyle(size: Int): TextStyle =
        base.copy(fontSize = size.sp, lineHeight = (size + 1).sp, fontWeight = FontWeight.SemiBold)
    fun locationStyle(size: Int): TextStyle =
        base.copy(fontSize = size.sp, lineHeight = (size + 1).sp)

    BoxWithConstraints(Modifier.fillMaxSize().padding(horizontal = 2.dp, vertical = 2.dp)) {
        val width = with(density) { maxWidth.roundToPx() }
        val height = with(density) { maxHeight.roundToPx() }
        val gap = with(density) { 1.dp.roundToPx() }
        val label = remember(title, location, width, height, gap, measurer, base, density) {
            fun fits(room: String, size: Pair<Int, Int>): Boolean {
                val constraints = Constraints(maxWidth = width, maxHeight = height)
                val name = measurer.measure(title, titleStyle(size.first), constraints = constraints)
                val place = measurer.measure(room, locationStyle(size.second), constraints = constraints)
                return !name.hasVisualOverflow && !place.hasVisualOverflow && name.size.height + place.size.height + gap <= height
            }
            val full = courseFontSizes.firstOrNull { fits(location, it) }
            if (full != null) Triple(full, location, false)
            else {
                val compact = location.lineSequence()
                    .map { roomCode.find(it.trim())?.value }
                    .filterNotNull().distinct().joinToString("/")
                    .ifBlank { location.lineSequence().first() }
                val size = courseFontSizes.firstOrNull { fits(compact, it) }
                Triple(size ?: courseFontSizes.last(), compact, size == null)
            }
        }
        val (size, room, clipped) = label
        Column(
            Modifier.fillMaxSize(),
            verticalArrangement = Arrangement.spacedBy(1.dp, Alignment.CenterVertically),
        ) {
            Text(title, style = titleStyle(size.first), overflow = TextOverflow.Ellipsis,
                modifier = if (clipped) Modifier.weight(1f, fill = false) else Modifier)
            Text(room, style = locationStyle(size.second), maxLines = if (clipped) 1 else Int.MAX_VALUE,
                color = MaterialTheme.colorScheme.onSurfaceVariant, overflow = TextOverflow.Ellipsis)
        }
    }
}
