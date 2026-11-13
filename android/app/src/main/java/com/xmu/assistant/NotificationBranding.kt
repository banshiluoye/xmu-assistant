package com.xmu.assistant

import android.app.Notification
import android.content.Context
import android.graphics.drawable.Icon

internal fun xmuNotification(context: Context, channelId: String): Notification.Builder =
    Notification.Builder(context, channelId)
        .setSmallIcon(R.drawable.ic_xmu_notification)
        .setLargeIcon(Icon.createWithResource(context, R.drawable.xmu_assistant_mark))
