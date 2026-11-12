package com.xmu.assistant

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject
import java.time.LocalDate
import java.util.UUID

internal data class ScheduleOccurrenceChange(
    val id: String = UUID.randomUUID().toString(),
    val sourceDate: LocalDate?,
    val original: XmuScheduleGroup,
    val targetDate: LocalDate,
    val replacement: XmuScheduleGroup,
    val cancelled: Boolean = false,
)

internal data class ScheduleLocalChanges(
    val occurrences: List<ScheduleOccurrenceChange> = emptyList(),
    // null means a holiday with no classes; otherwise use that date's lessons.
    val daySources: Map<LocalDate, LocalDate?> = emptyMap(),
)

/** A date-only move preserves the fetched clock times, including campus-specific breaks. */
internal fun scheduleMovedTimes(start:Int,end:Int,original:XmuScheduleGroup?,groups:List<XmuScheduleGroup>):Pair<Int,Int> {
    val first=original?.takeIf {it.startSection==start}?.startTime
        ?: groups.firstOrNull {it.startSection==start}?.startTime ?: scheduleSectionStartTime(start,800)
    val last=original?.takeIf {it.endSection==end}?.endTime
        ?: groups.firstOrNull {it.endSection==end}?.endTime ?: scheduleSectionEndTime(end,2240)
    return first to last
}

internal fun sameScheduleSlot(a: XmuScheduleGroup, b: XmuScheduleGroup): Boolean =
    normalizeCourseTitle(a.courseName) == normalizeCourseTitle(b.courseName) &&
        a.startSection == b.startSection && a.endSection == b.endSection && a.weekday == b.weekday

/** Local date edits never replace the official cache and never change a whole series implicitly. */
internal fun projectLocalScheduleWeek(
    entries: List<XmuScheduleEntry>, calendar: XmuAcademicCalendar?, week: Int,
    changes: ScheduleLocalChanges = ScheduleLocalChanges(),
    fixedOverride: (XmuScheduleGroup) -> XmuScheduleGroup = { it },
): List<XmuScheduleGroup> {
    val index = indexXmuScheduleByWeek(entries)
    val monday = xmuWeekStart(calendar, week)
    if (monday == null) return (index[week] ?: emptyList()).groupForDisplay().map(fixedOverride)
    val result = mutableListOf<XmuScheduleGroup>()
    for (day in 1..7) {
        val date = monday.plusDays(day - 1L)
        val source = if (changes.daySources.containsKey(date)) changes.daySources[date] else date
        if (source != null) {
            val sourceWeek = xmuAcademicWeekFor(calendar, source).week
            val groups = (index[sourceWeek] ?: emptyList()).groupForDisplay().map(fixedOverride)
                .filter { it.weekday == source.dayOfWeek.value }
            result += groups.filter { group ->
                changes.occurrences.none { it.sourceDate == date && sameScheduleSlot(it.original, group.copy(weekday = day)) }
            }.map { it.copy(weekday = day) }
        }
        result += changes.occurrences.filter { !it.cancelled && it.targetDate == date }
            .map { it.replacement.copy(weekday = day) }
    }
    return result.sortedWith(compareBy({ it.weekday }, { it.startSection }, { it.courseName }))
}

internal class ScheduleLocalChangeStore(context: Context, owner: String, private val term: String) {
    private val prefs = context.applicationContext.getSharedPreferences("schedule_date_edits", Context.MODE_PRIVATE)
    private val key = cookieFingerprint(owner) + ":" + term
    @Synchronized fun read(): ScheduleLocalChanges = runCatching {
        val root = JSONObject(prefs.getString(key, "{}").orEmpty())
        val items = root.optJSONArray("occurrences") ?: JSONArray()
        val days = root.optJSONObject("days") ?: JSONObject()
        ScheduleLocalChanges(
            (0 until items.length()).map { i ->
                val row = items.getJSONObject(i)
                ScheduleOccurrenceChange(row.getString("id"), row.optString("source").takeIf { it.isNotBlank() }?.let(LocalDate::parse),
                    groupFromJson(row.getJSONObject("original")), LocalDate.parse(row.getString("target")),
                    groupFromJson(row.getJSONObject("replacement")), row.optBoolean("cancelled"))
            },
            days.keys().asSequence().associate { date -> LocalDate.parse(date) to days.optString(date).takeIf { it.isNotBlank() }?.let(LocalDate::parse) },
        )
    }.getOrDefault(ScheduleLocalChanges())

    @Synchronized fun saveOccurrence(value: ScheduleOccurrenceChange) {
        require(value.replacement.courseName.isNotBlank()) { "请输入课程名称" }
        require(value.replacement.startSection in 1..12 && value.replacement.endSection in value.replacement.startSection..12) { "节次请输入 1—12，结束不能早于开始" }
        val current = read()
        val kept = current.occurrences.filterNot { it.id == value.id || (value.sourceDate != null && it.sourceDate == value.sourceDate && sameScheduleSlot(it.original, value.original)) }
        write(current.copy(occurrences = kept + value))
    }
    @Synchronized fun saveDay(date: LocalDate, source: LocalDate?) {
        require(date != source) { "补课来源应为其他日期" }
        write(read().let { it.copy(daySources = it.daySources + (date to source)) })
    }
    @Synchronized fun removeOccurrence(id: String) = write(read().let { it.copy(occurrences = it.occurrences.filterNot { row -> row.id == id }) })
    @Synchronized fun removeDay(date: LocalDate) = write(read().let { it.copy(daySources = it.daySources - date) })
    private fun write(value: ScheduleLocalChanges) {
        val days = JSONObject()
        value.daySources.forEach { (date, source) -> days.put(date.toString(), source?.toString().orEmpty()) }
        val rows = JSONArray()
        value.occurrences.forEach { row -> rows.put(JSONObject().put("id", row.id).put("source", row.sourceDate?.toString().orEmpty())
            .put("original", groupToJson(row.original)).put("target", row.targetDate.toString())
            .put("replacement", groupToJson(row.replacement)).put("cancelled", row.cancelled)) }
        check(prefs.edit().putString(key, JSONObject().put("days", days).put("occurrences", rows).toString()).commit()) { "本地安排保存失败" }
    }
}

private fun groupToJson(g: XmuScheduleGroup) = JSONObject().put("name", g.courseName).put("day", g.weekday)
    .put("start", g.startSection).put("end", g.endSection).put("startTime", g.startTime).put("endTime", g.endTime)
    .put("rooms", JSONArray(g.rooms)).put("teachers", JSONArray(g.teachers)).put("weeks", g.weeks)

private fun groupFromJson(o: JSONObject) = XmuScheduleGroup(o.getInt("day"), o.getInt("start"), o.getInt("end"),
    o.getInt("startTime"), o.getInt("endTime"), o.getString("name"),
    o.getJSONArray("rooms").let { a -> (0 until a.length()).map { a.getString(it) } },
    o.getJSONArray("teachers").let { a -> (0 until a.length()).map { a.getString(it) } }, o.optString("weeks"))
