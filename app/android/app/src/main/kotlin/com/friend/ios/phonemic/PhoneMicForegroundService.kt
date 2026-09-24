package com.friend.ios.phonemic

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.IBinder
import android.util.Log
import androidx.core.app.NotificationCompat
import androidx.core.content.ContextCompat
import com.friend.ios.background.CaptureWakeLock

/**
 * Thin lifecycle shell that keeps native mic capture alive in the background. It
 * owns the foreground-service promotion, the notification and the partial wake
 * lock that keeps AudioRecord fed while the screen is off; the capture engine and
 * all capture policy live in the controller.
 *
 * No restart/resurrect policy of its own: [onStartCommand] returns
 * START_NOT_STICKY (Granola-identical) — the controller owns when to
 * [start]/[stop] this service (e.g. it stops it on engine death), so the service
 * never second-guesses it.
 */
class PhoneMicForegroundService : Service() {

    companion object {
        private const val TAG = "PhoneMic.FgService"
        private const val CHANNEL_ID = "omi_phone_mic_channel"
        private const val NOTIFICATION_ID = 2002 // BLE uses 2001

        /**
         * Promote the service to the foreground. Returns whether the OS accepted the
         * start; the controller surfaces a non-fatal error when it did not (rethrows
         * nothing — an uncaught throw from here would kill the process).
         */
        fun start(context: Context): Boolean {
            return try {
                ContextCompat.startForegroundService(
                    context,
                    Intent(context, PhoneMicForegroundService::class.java)
                )
                true
            } catch (e: Exception) {
                Log.e(TAG, "Failed to start phone-mic foreground service", e)
                false
            }
        }

        fun stop(context: Context) {
            try {
                context.stopService(Intent(context, PhoneMicForegroundService::class.java))
            } catch (e: Exception) {
                Log.w(TAG, "Failed to stop phone-mic foreground service: ${e.message}")
            }
        }
    }

    private lateinit var captureWakeLock: CaptureWakeLock

    override fun onCreate() {
        super.onCreate()
        captureWakeLock = CaptureWakeLock(this)
        createNotificationChannel()
        Log.d(TAG, "Service created")
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        // FIRST thing: promote to foreground with the microphone type. On Android 14+
        // startForeground(mic) without RECORD_AUDIO granted throws SecurityException, and
        // any uncaught throw here silently kills the whole process. Stop cleanly instead.
        //
        // Ordering is safe by construction: controller start (main turn T) -> onStartCommand
        // (T+1) -> any stop (later turn) are serialized by the main-thread FIFO, so the classic
        // "startForegroundService did not call startForeground in time" crash is unreachable.
        try {
            startForeground(
                NOTIFICATION_ID,
                buildNotification(),
                ServiceInfo.FOREGROUND_SERVICE_TYPE_MICROPHONE
            )
        } catch (e: Exception) {
            Log.e(TAG, "startForeground failed; stopping service instead of crashing", e)
            stopSelf()
            return START_NOT_STICKY
        }
        // CPU can enter Doze with the screen off even with a foreground service;
        // without this lock AudioRecord stops delivering frames and the recording
        // silently truncates. Held for the session (service lifetime).
        captureWakeLock.acquire()
        // No resurrect path by design — the controller owns restart policy.
        return START_NOT_STICKY
    }

    /**
     * Task removal (swipe from recents) is deliberately a no-op here: capture
     * survival is the controller's call, and it stops this service when the
     * Flutter engine is destroyed for good. Pressing Home never reaches this.
     */
    override fun onTaskRemoved(rootIntent: Intent?) {
        Log.d(TAG, "Task removed; leaving capture lifecycle to the controller")
        super.onTaskRemoved(rootIntent)
    }

    override fun onDestroy() {
        captureWakeLock.release()
        Log.d(TAG, "Service destroyed")
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null

    private fun createNotificationChannel() {
        val channel = NotificationChannel(
            CHANNEL_ID,
            "Ollomi Phone Recording",
            NotificationManager.IMPORTANCE_LOW
        ).apply {
            setShowBadge(false)
        }
        getSystemService(NotificationManager::class.java).createNotificationChannel(channel)
    }

    private fun buildNotification(): Notification {
        val launchIntent = packageManager.getLaunchIntentForPackage(packageName)
        val pendingIntent = if (launchIntent != null) {
            PendingIntent.getActivity(this, 0, launchIntent, PendingIntent.FLAG_IMMUTABLE)
        } else null

        return NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle("Ollomi")
            .setContentText("Recording in progress")
            .setSmallIcon(applicationInfo.icon)
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .setOngoing(true)
            .apply { if (pendingIntent != null) setContentIntent(pendingIntent) }
            .build()
    }
}
