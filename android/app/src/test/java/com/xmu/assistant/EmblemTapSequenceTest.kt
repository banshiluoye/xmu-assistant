package com.xmu.assistant

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class EmblemTapSequenceTest {
    @Test
    fun onlyFiveConsecutiveTapsTriggerAnExport() {
        val taps = EmblemTapSequence()
        repeat(4) { assertFalse(taps.tap(it * 120L)) }
        assertFalse(taps.tap(2000))
        repeat(3) { assertFalse(taps.tap(2100 + it * 120L)) }
        assertTrue(taps.tap(2500))
        assertFalse(taps.tap(2600))
    }
}
