package com.xmu.assistant

import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.ui.Modifier
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createComposeRule
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode
import java.time.LocalDate

@GraphicsMode(GraphicsMode.Mode.NATIVE)
@RunWith(RobolectricTestRunner::class)
@Config(sdk=[34],qualifiers="w360dp-h720dp")
class ScheduleCompactGridUiTest {
    @get:Rule val rule=createComposeRule()
    @Test fun `complete week including last period fits without horizontal scrolling`() {
        val course=XmuScheduleGroup(7,11,12,2040,2215,"周日末节课程",listOf("学武楼 A101"),emptyList(),"1-16周")
        rule.setContent {XmuMobileTheme {ScheduleCompactWeekGrid(listOf(course),LocalDate.of(2026,11,2),true,6,1200,{},Modifier.fillMaxSize())}}
        listOf("周一","周二","周三","周四","周五","周六","周日").forEach {rule.onNodeWithText(it).assertIsDisplayed()}
        val bounds=rule.onNode(hasClickAction() and hasText(course.courseName)).fetchSemanticsNode().boundsInRoot
        val root=rule.onRoot().fetchSemanticsNode().boundsInRoot
        assertTrue(bounds.right<=root.right+1);assertTrue(bounds.bottom<=root.bottom+1)
        rule.onAllNodes(hasScrollAction()).assertCountEquals(0)
    }
    @Test fun `overlap does not widen the day or hide the other course`() {
        val a=XmuScheduleGroup(1,1,2,800,935,"课程甲",listOf("A101"),emptyList(),"1-16周")
        var selected=""
        rule.setContent {XmuMobileTheme {ScheduleCompactWeekGrid(listOf(a,a.copy(courseName="课程乙")),null,false,1,0,{selected=it.courseName},Modifier.fillMaxSize())}}
        rule.onNode(hasClickAction() and hasText("课程乙")).assertIsDisplayed().performClick()
        assertEquals("课程乙",selected)
        rule.onNode(hasClickAction() and hasText("课程甲")).assertIsDisplayed().performClick()
        assertEquals("课程甲",selected)
    }
}
