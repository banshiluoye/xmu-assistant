package com.xmu.assistant

import org.junit.Assert.*
import org.junit.Test

class CoursewareDirectoryTest {
    @Test fun `download paths keep course and one combined chapter folder`() {
        val item=CoursewareUiItem("1","2","3","实验 / Redis","报告.pdf","资料",moduleName="第二章",courseTitle="课程 A",syllabusName="小节")
        assertEquals(listOf("课程 A","第二章 - 小节"),coursewareRelativeDirectories(item))
        assertFalse(safeCoursewareSegment("../../").contains('/'))
        assertNotEquals("..",safeCoursewareSegment(".."))
    }

    @Test fun `section equal to module is not repeated and blank chapter falls back`() {
        val same=CoursewareUiItem("1","2","3","实验","报告.pdf","资料",moduleName="第二章",courseTitle="课程 A",syllabusName="第二章")
        val blank=CoursewareUiItem("1","2","3","实验","报告.pdf","资料",courseTitle="课程 A")
        assertEquals(listOf("课程 A","第二章"),coursewareRelativeDirectories(same))
        assertEquals(listOf("课程 A","未分组"),coursewareRelativeDirectories(blank))
    }
}
