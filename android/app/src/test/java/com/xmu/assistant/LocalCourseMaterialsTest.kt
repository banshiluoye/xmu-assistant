package com.xmu.assistant

import androidx.test.core.app.ApplicationProvider
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(sdk=[28])
class LocalCourseMaterialsTest {
    @Test fun `large and unknown files reference without copying`() {
        val boundary=50L*1024*1024
        assertFalse(shouldReferenceLocal(boundary,50,false))
        assertTrue(shouldReferenceLocal(boundary+1,50,false))
        assertTrue(shouldReferenceLocal(-1,50,false))
        assertTrue(shouldReferenceLocal(1,50,true))
    }
    @Test fun `empty library reads only own account and default threshold`() {
        val context=ApplicationProvider.getApplicationContext<android.content.Context>()
        val first=LocalCourseLibrary(context,"local-test-a")
        val second=LocalCourseLibrary(context,"local-test-b")
        assertEquals(50L,first.threshold())
        assertTrue(first.items("course").isEmpty())
        assertTrue(second.items("course").isEmpty())
        first.remove("course","nonexistent")
        assertTrue(second.items("course").isEmpty())
    }
}
