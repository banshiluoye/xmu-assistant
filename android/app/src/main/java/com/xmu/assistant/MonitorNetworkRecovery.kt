package com.xmu.assistant

import java.net.ConnectException
import java.net.NoRouteToHostException
import java.net.SocketTimeoutException
import java.net.UnknownHostException
import javax.net.ssl.SSLException

internal enum class MonitorNetworkFailure(val message: String) {
    TIMEOUT("连接畅课超时，正在重试"),
    DNS("暂时无法解析畅课域名，正在重试"),
    TLS("暂时无法建立到畅课的安全连接，正在重试"),
    ROUTE("暂时无法连接畅课，正在重试"),
}

internal fun monitorNetworkFailure(error: Exception): MonitorNetworkFailure? =
    when (error) {
        is SocketTimeoutException -> MonitorNetworkFailure.TIMEOUT
        is UnknownHostException -> MonitorNetworkFailure.DNS
        is SSLException -> MonitorNetworkFailure.TLS
        is ConnectException, is NoRouteToHostException -> MonitorNetworkFailure.ROUTE
        else -> null
    }

internal class MonitorNetworkRecovery {
    private var firstFailureAt: Long? = null
    private var lastAlertAt: Long? = null
    private var failures = 0

    fun recordFailure(now: Long): Boolean {
        val first = firstFailureAt ?: now.also { firstFailureAt = it }
        failures++
        if (failures < 3 || now - first < 60_000L ||
            lastAlertAt?.let { now - it < 15 * 60_000L } == true
        ) return false
        lastAlertAt = now
        return true
    }

    fun retryDelayMillis(): Long = when (failures) {
        1 -> 3_000L
        2 -> 5_000L
        3 -> 10_000L
        else -> 15_000L
    }

    fun reset() {
        firstFailureAt = null
        lastAlertAt = null
        failures = 0
    }
}
