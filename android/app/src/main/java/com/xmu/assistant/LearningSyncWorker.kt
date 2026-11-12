package com.xmu.assistant

import android.content.Context
import androidx.work.*
import java.util.concurrent.TimeUnit

/** System-managed fallback when the existing foreground monitor is stopped. */
class LearningSyncWorker(context:Context, parameters:WorkerParameters):Worker(context,parameters) {
    override fun doWork():Result {
        val settings=AssistantSettings(applicationContext)
        val cookie=settings.cookieHeader
        val owner=settings.username
        if(cookie.isBlank()) return Result.success()
        runCatching {LearningPoller.poll(applicationContext,owner,cookie,settings.rollcall().pollIntervalSeconds,ensureCurrent={
            check(settings.cookieHeader==cookie && settings.username==owner){"登录态已变化"}
        })}
        return Result.success()
    }
    companion object {
        fun schedule(context:Context) {
            val request=PeriodicWorkRequestBuilder<LearningSyncWorker>(15,TimeUnit.MINUTES)
                .setConstraints(Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build()).build()
            WorkManager.getInstance(context).enqueueUniquePeriodicWork("learning-inbox-sync",ExistingPeriodicWorkPolicy.KEEP,request)
        }
    }
}
