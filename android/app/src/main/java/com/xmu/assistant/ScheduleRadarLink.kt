package com.xmu.assistant

import android.content.Context
import java.time.LocalDate

internal fun matchScheduleRoom(room: String, presets: List<RadarPreset>): RadarPreset? {
    var text = normalizeCourseTitle(room).replace("（", "(").replace("）", ")")
    // Names verified against XMU METC and School of Informatics public building notices.
    val aliases=mapOf("2" to "学信楼", "二" to "学信楼", "4" to "启信楼", "四" to "启信楼", "5" to "智信楼", "五" to "智信楼", "6" to "睿信楼", "六" to "睿信楼")
    text=Regex("西部片区([2二4四5五6六])(?:号|#)楼").replace(text) { aliases[it.groupValues[1]].orEmpty() }
    text=text.replace("西二教学楼","学信楼")
    // Match an explicit building name, never an arbitrary room number or nearest guessed building.
    val matches = presets.filter { preset ->
        val names = listOf(preset.name) + Regex("[（(]([^）)]+)[）)]").findAll(preset.name).map { it.groupValues[1] }.toList()
        names.any { name -> normalizeCourseTitle(name).length >= 3 && text.contains(normalizeCourseTitle(name)) }
    }
    return matches.singleOrNull()
}

internal fun syncScheduleRadarPlaces(
    context: Context, owner: String, courses: List<CourseSummary>, entries: List<XmuScheduleEntry>,
    term: String, calendar: XmuAcademicCalendar?, today: LocalDate = LocalDate.now(),
) {
    val week = xmuAcademicWeekFor(calendar, today).week ?: return
    val changes = ScheduleLocalChangeStore(context, owner, term).read()
    val fixed = ScheduleOverrideStore(context)
    val now=java.time.LocalTime.now().let {it.hour*100+it.minute}
    val occurrences = (week..week+1).flatMap { current ->
        val monday=xmuWeekStart(calendar,current) ?: return@flatMap emptyList()
        projectLocalScheduleWeek(entries, calendar, current, changes) { group -> fixed.apply(term, group) }
            .map { monday.plusDays(it.weekday-1L) to it }
    }.filter { (date,group) -> date>today || date==today && group.endTime>=now }
        .sortedWith(compareBy({it.first},{it.second.startTime}))
    val presets = loadXiangAnRadarPresets(context)
    val store = RadarCoordinateStore(context)
    courses.forEach { course ->
        val ordered = occurrences.map {it.second}.filter { normalizeCourseTitle(it.courseName) == normalizeCourseTitle(course.title) }
        val suggestions = ordered.flatMap { it.rooms }.distinct().mapNotNull { room -> matchScheduleRoom(room, presets)?.let { room to it } }
        store.syncSchedulePlaces(course, suggestions)
    }
}
