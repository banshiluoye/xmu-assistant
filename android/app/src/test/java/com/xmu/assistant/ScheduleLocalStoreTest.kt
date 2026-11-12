package com.xmu.assistant

import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config
import java.time.LocalDate

@RunWith(RobolectricTestRunner::class)
@Config(sdk=[34])
class ScheduleLocalStoreTest {
    @Test fun `confirmed homework status replaces the cached pending task and drafts can overwrite atomically`() {
        val store=LearningLocalStore(RuntimeEnvironment.getApplication(),"confirmed-status-test")
        val task=LearningTask("1","2","课程","作业","homework")
        LearningPoller.recordConfirmed(store,task,"未完成")
        LearningPoller.recordConfirmed(store,task,"已提交")
        assertEquals("已提交",store.tasks().single().status)
        store.write("draft-fixture",org.json.JSONObject().put("html","第一版"))
        store.write("draft-fixture",org.json.JSONObject().put("html","最终版"))
        assertEquals("最终版",store.read("draft-fixture").getString("html"))
    }
    @Test fun `date edits are isolated by account and term and repeated edits replace the same occurrence`() {
        val context=RuntimeEnvironment.getApplication()
        val store=ScheduleLocalChangeStore(context,"first","20261")
        val original=XmuScheduleGroup(1,1,2,800,935,"课程",listOf("A101"),emptyList(),"1-16周")
        val date=LocalDate.of(2026,9,7)
        val edit=ScheduleOccurrenceChange(sourceDate=date,original=original,targetDate=date.plusDays(1),replacement=original.copy(weekday=2))
        store.saveOccurrence(edit)
        store.saveOccurrence(edit.copy(targetDate=date.plusDays(2),replacement=original.copy(weekday=3)))
        assertEquals(1,store.read().occurrences.size)
        assertEquals(date.plusDays(2),store.read().occurrences.first().targetDate)
        assertTrue(ScheduleLocalChangeStore(context,"second","20261").read().occurrences.isEmpty())
        assertTrue(ScheduleLocalChangeStore(context,"first","20262").read().occurrences.isEmpty())
        store.saveDay(date,null);assertTrue(store.read().daySources.containsKey(date));assertNull(store.read().daySources[date])
        store.removeDay(date);assertFalse(store.read().daySources.containsKey(date))
        store.removeOccurrence(edit.id);assertTrue(store.read().occurrences.isEmpty())
    }
    @Test fun `generated radar suggestions stay unique and manual preference survives resync`() {
        val context=RuntimeEnvironment.getApplication()
        val store=RadarCoordinateStore(context);store.clear()
        val course=CourseSummary("1","示例课程")
        val a=RadarPreset("a","学武楼","主楼群",24.1,118.1,"high")
        val b=RadarPreset("b","坤銮楼","主楼群",24.2,118.2,"high")
        store.syncSchedulePlaces(course,listOf("学武楼 A101" to a,"坤銮楼 C304" to b))
        store.syncSchedulePlaces(course,listOf("学武楼 A101" to a,"坤銮楼 C304" to b))
        assertEquals(2,store.placesFor("1",course.title).size)
        val alternate=store.placesFor("1",course.title).last();store.setPreferred(alternate.id)
        store.syncSchedulePlaces(course,listOf("学武楼 A101" to a,"坤銮楼 C304" to b))
        assertEquals(2,store.placesFor("1",course.title).size)
        assertEquals(alternate.id,store.preferredFor("1",course.title)?.id)
    }
}
