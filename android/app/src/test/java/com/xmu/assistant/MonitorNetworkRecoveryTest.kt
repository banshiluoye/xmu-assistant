package com.xmu.assistant

import java.net.SocketTimeoutException
import java.net.UnknownHostException
import javax.net.ssl.SSLHandshakeException
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class MonitorNetworkRecoveryTest {
    @Test fun transientNetworkFailuresDoNotSendBackgroundNotifications() {
        val recovery = MonitorNetworkRecovery()
        assertFalse(recovery.recordFailure(0))
        assertEquals(3_000L, recovery.retryDelayMillis())
        assertFalse(recovery.recordFailure(20_000))
        assertFalse(recovery.recordFailure(55_000))
        recovery.reset()
        assertFalse(recovery.recordFailure(56_000))
        assertEquals(3_000L, recovery.retryDelayMillis())
    }

    @Test fun sustainedFailureAlertsAndThrottlesRepeatedNotifications() {
        val recovery = MonitorNetworkRecovery()
        assertFalse(recovery.recordFailure(0))
        assertFalse(recovery.recordFailure(30_000))
        assertTrue(recovery.recordFailure(60_000))
        assertFalse(recovery.recordFailure(61_000))
        assertEquals(15_000L, recovery.retryDelayMillis())
        assertTrue(recovery.recordFailure(960_000))
    }

    @Test fun observedNetworkErrorsHaveSpecificMessages() {
        assertEquals(MonitorNetworkFailure.TIMEOUT, monitorNetworkFailure(SocketTimeoutException()))
        assertEquals(MonitorNetworkFailure.DNS, monitorNetworkFailure(UnknownHostException()))
        assertEquals(MonitorNetworkFailure.TLS, monitorNetworkFailure(SSLHandshakeException("test")))
    }
}
