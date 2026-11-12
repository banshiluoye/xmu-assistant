package com.xmu.assistant

import java.time.LocalDate
import org.junit.Assert.*
import org.junit.Test

class ScheduleDateChangesTest {
    @Test fun `date only move preserves fetched times and section changes prefer known fetched slots`() {
        val original=XmuScheduleGroup(1,1,2,800,940,"课程",listOf("教室"),emptyList(),"1-16周")
        val other=original.copy(startSection=9,endSection=10,startTime=1910,endTime=2050)
        assertEquals(800 to 940,scheduleMovedTimes(1,2,original,listOf(original,other)))
        assertEquals(1910 to 2050,scheduleMovedTimes(9,10,original,listOf(original,other)))
    }
    private val monday=LocalDate.of(2026,9,7)
    private val calendar=XmuAcademicCalendar("20261","2026-2027","第一学期",monday,monday.plusWeeks(18))
    private val entry=XmuScheduleEntry(1,1,2,800,935,"课程", "学武楼 A101","老师","1-16周","20261")
    @Test fun `moving one occurrence across weeks preserves the recurring lessons`() {
        val original=listOf(entry).groupForDisplay().first()
        val change=ScheduleOccurrenceChange(sourceDate=monday,original=original,targetDate=monday.plusDays(9),replacement=original.copy(weekday=3))
        val edits=ScheduleLocalChanges(occurrences=listOf(change))
        assertTrue(projectLocalScheduleWeek(listOf(entry),calendar,1,edits).isEmpty())
        assertEquals(listOf(1,3),projectLocalScheduleWeek(listOf(entry),calendar,2,edits).map {it.weekday})
        assertEquals(listOf(1),projectLocalScheduleWeek(listOf(entry),calendar,3,edits).map {it.weekday})
    }
    @Test fun `holiday and replacement day can be represented without changing official data`() {
        val edits=ScheduleLocalChanges(daySources=mapOf(monday to null,monday.plusDays(5) to monday))
        val result=projectLocalScheduleWeek(listOf(entry),calendar,1,edits)
        assertEquals(listOf(6),result.map {it.weekday})
        assertEquals(1,entry.weekday)
    }
    @Test fun `room matching uses an explicit unambiguous building name`() {
        val presets=listOf(RadarPreset("1","学武楼","主楼群",24.0,118.0,"high"),RadarPreset("2","坤銮楼","主楼群",24.1,118.1,"high"))
        assertEquals("1",matchScheduleRoom("学武楼（1号楼）A404",presets)?.id)
        assertNull(matchScheduleRoom("西部片区4号楼301",presets))
        assertEquals("3",matchScheduleRoom("西部片区4号楼301",presets+RadarPreset("3","启信楼","西部片区",24.2,118.2,"high"))?.id)
        assertNull(matchScheduleRoom("学武楼 或 坤銮楼",presets))
    }
    @Test fun `navigation keeps todo second timetable center and scores in more`() {
        assertEquals(listOf("首页","学习待办","课表","签到情况","更多"),primaryDestinations.map {it.page})
        assertTrue(moreDestinations.any {it.page=="成绩"})
        assertEquals("更多",primaryPage("专业排名"))
    }
}
