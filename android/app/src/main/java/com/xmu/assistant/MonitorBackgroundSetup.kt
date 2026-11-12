package com.xmu.assistant

import android.content.ActivityNotFoundException
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.os.PowerManager
import android.provider.Settings
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp

internal enum class BackgroundSetup(val instruction: String, val shortcutLabel: String) {
    HONOR("在系统设置搜索「应用启动管理」，找到虾大助手，关闭自动管理，打开「允许后台活动」。", "打开应用启动管理"),
    XIAOMI("在设置搜索「后台自启动」，允许虾大助手；再在应用的省电策略中选择「无限制」。", "打开后台自启动"),
    COLOR_OS("在设置搜索「应用耗电管理」或「后台活动」，允许虾大助手在后台运行。", "打开应用设置"),
    VIVO("在设置搜索「后台耗电管理」，允许虾大助手后台运行；如有「自启动」选项也可开启。", "打开应用设置"),
    SAMSUNG("在设置搜索「后台使用限制」，把虾大助手加入「从不休眠的应用」。", "打开电池设置"),
    OTHER("如果系统另有后台使用限制，在虾大助手的应用信息中检查「电池」，允许后台使用。", "打开应用设置");
}

internal fun backgroundSetupFor(manufacturer: String, brand: String): BackgroundSetup {
    val names = setOf(manufacturer.lowercase(), brand.lowercase())
    return when {
        names.any { it in setOf("honor", "huawei") } -> BackgroundSetup.HONOR
        names.any { it in setOf("xiaomi", "redmi", "poco") } -> BackgroundSetup.XIAOMI
        names.any { it in setOf("oppo", "oneplus", "realme") } -> BackgroundSetup.COLOR_OS
        names.any { it in setOf("vivo", "iqoo") } -> BackgroundSetup.VIVO
        "samsung" in names -> BackgroundSetup.SAMSUNG
        else -> BackgroundSetup.OTHER
    }
}

private fun Context.openSettingsIntent(intent: Intent): Boolean = try {
    startActivity(intent)
    true
} catch (_: ActivityNotFoundException) {
    false
} catch (_: SecurityException) {
    false
}

private fun Context.appSettingsIntent() =
    Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS, Uri.fromParts("package", packageName, null))

private fun Context.openVendorBackgroundSetup(setup: BackgroundSetup) {
    // Vendor activities are optional and may be private on some firmware. Always offer a standard fallback.
    val components = when (setup) {
        BackgroundSetup.HONOR -> listOf(
            "com.hihonor.systemmanager" to "com.hihonor.systemmanager.startupmgr.ui.StartupNormalAppListActivity",
            "com.huawei.systemmanager" to "com.huawei.systemmanager.startupmgr.ui.StartupNormalAppListActivity",
        )
        BackgroundSetup.XIAOMI -> listOf(
            "com.miui.securitycenter" to "com.miui.permcenter.autostart.AutoStartManagementActivity",
        )
        else -> emptyList()
    }
    if (components.any { (pkg, cls) -> openSettingsIntent(Intent().setClassName(pkg, cls)) }) return
    if (setup == BackgroundSetup.SAMSUNG && openSettingsIntent(Intent(Settings.ACTION_BATTERY_SAVER_SETTINGS))) return
    if (!openSettingsIntent(appSettingsIntent())) openSettingsIntent(Intent(Settings.ACTION_SETTINGS))
}

@Composable
internal fun MonitorBackgroundSetupDialog(onDismiss: () -> Unit) {
    val context = LocalContext.current
    val setup = backgroundSetupFor(Build.MANUFACTURER, Build.BRAND)
    val power = context.getSystemService(PowerManager::class.java)
    val exempt = power.isIgnoringBatteryOptimizations(context.packageName)
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("锁屏监控设置") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text(if (exempt) "已允许忽略 Android 电池优化。" else "先允许虾大助手忽略 Android 电池优化。")
                if (!exempt) OutlinedButton(
                    onClick = {
                        val request = Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS,
                            Uri.fromParts("package", context.packageName, null))
                        if (!context.openSettingsIntent(request) &&
                            !context.openSettingsIntent(Intent(Settings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS))
                        ) context.openSettingsIntent(context.appSettingsIntent())
                        onDismiss()
                    },
                    modifier = Modifier.fillMaxWidth(),
                ) { Text("忽略电池优化") }
                Text(setup.instruction)
                OutlinedButton(
                    onClick = { context.openVendorBackgroundSetup(setup); onDismiss() },
                    modifier = Modifier.fillMaxWidth(),
                ) { Text(setup.shortcutLabel) }
            }
        },
        confirmButton = { TextButton(onClick = onDismiss) { Text("关闭") } },
    )
}
