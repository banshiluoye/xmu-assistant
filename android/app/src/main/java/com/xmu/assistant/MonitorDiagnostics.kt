package com.xmu.assistant

import android.content.Context
import android.os.Build
import android.os.PowerManager
import java.io.File
import java.time.OffsetDateTime

/** Bounded private monitor history. Callers supply counts and status labels only. */
internal object MonitorDiagnostics {
    private const val MAX_BYTES = 256 * 1024
    private const val LOG_NAME = "monitor-diagnostics.txt"

    @Synchronized
    fun record(context: Context, event: String) {
        runCatching {
            val log = File(context.filesDir, LOG_NAME)
            val line = "${OffsetDateTime.now()} $event\n"
            if (log.length() + line.toByteArray().size > MAX_BYTES) {
                val previous = File(context.filesDir, "$LOG_NAME.1")
                previous.delete()
                if (!log.renameTo(previous)) return@runCatching
            }
            log.appendText(line)
        }
    }

    @Synchronized
    fun export(context: Context, settings: AssistantSettings): String = buildString {
        val power = context.getSystemService(PowerManager::class.java)
        appendLine("虾大助手运行日志 ${BuildConfig.VERSION_NAME}")
        appendLine("导出时间 ${OffsetDateTime.now()}")
        appendLine("设备 ${Build.MANUFACTURER} ${Build.MODEL} · Android ${Build.VERSION.RELEASE}")
        appendLine("后台监控 requested=${settings.monitorDesired} active=${RollcallMonitorService.hasActiveWorker()} " +
            "batteryExempt=${power.isIgnoringBatteryOptimizations(context.packageName)} " +
            "lastCheckEpochMs=${settings.monitorLastCheckMillis} failures=${settings.monitorConsecutiveFailures}")
        for (name in listOf("$LOG_NAME.1", LOG_NAME)) {
            val log = File(context.filesDir, name)
            if (log.isFile) append(log.readText())
        }
    }
}

internal class EmblemTapSequence {
    private var count = 0
    private var lastTapMillis = 0L

    fun tap(nowMillis: Long): Boolean {
        if (nowMillis - lastTapMillis > 800) count = 0
        lastTapMillis = nowMillis
        count++
        if (count < 5) return false
        count = 0
        return true
    }
}
