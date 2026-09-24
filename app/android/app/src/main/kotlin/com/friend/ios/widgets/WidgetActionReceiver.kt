package com.friend.ios.widgets

import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.util.Log

import com.friend.ios.MainActivity
import com.friend.ios.ble.OmiBleForegroundService
import com.friend.ios.phonemic.PhoneMicCaptureMode
import com.friend.ios.phonemic.PhoneMicController
import com.friend.ios.phonemic.PhoneMicForegroundService

/**
 * Executes the home-screen widget buttons.
 *
 * Capture starts here without opening the app whenever the native writers have
 * everything they need (a device target with a saved stream config, or the
 * phone-mic batch directory). Otherwise the app is opened with the action so
 * Dart can run the same request through the normal capture controller.
 */
class WidgetActionReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        val action = WidgetAction.fromId(intent.getStringExtra(EXTRA_WIDGET_ACTION)) ?: return
        Log.i(TAG, "Widget action: ${action.id}")
        when (action) {
            WidgetAction.START_ONE_OFF -> startRecording(context, continuous = false)
            WidgetAction.START_CONTINUOUS -> startRecording(context, continuous = true)
            WidgetAction.STOP -> stopRecording(context)
            WidgetAction.CONNECT_DEVICE -> connectDevice(context)
            WidgetAction.OPEN_TRANSCRIPT -> openApp(context, action.id)
        }
    }

    private fun startRecording(context: Context, continuous: Boolean) {
        val state = WidgetStateStore.read(context)
        val target = selectTargetAddress(state.targetAddress, WidgetPrefs.managedDevice(context))
        WidgetPrefs.setCapturePaused(context, false)

        val decision = decideStart(
            targetAddress = target,
            nativeStreamReady = WidgetNativeReadiness.streamReady(context),
            authenticated = WidgetNativeReadiness.authenticated(context),
            persistentMode = WidgetNativeReadiness.persistentMode(context),
            batchDirReady = WidgetNativeReadiness.batchDirReady(context),
        )
        Log.i(TAG, "startRecording continuous=$continuous target=$target decision=$decision")

        when (decision) {
            StartDecision.NATIVE_BLE -> {
                val requiresBond = selectTargetRequiresBond(state.targetRequiresBond, WidgetPrefs.managedDevice(context))
                WidgetPrefs.flutter(context).edit()
                    .putBoolean("flutter.nativeBleStreamingEnabled", true)
                    .putBoolean("flutter.nativeBleForegroundReady", false)
                    .apply()
                OmiBleForegroundService.startService(context, target, requiresBond, caller = "Widget")
                updateState(context, state) {
                    it.copy(
                        recording = true,
                        continuous = continuous,
                        sourceKind = "ble",
                        source = state.deviceName,
                        startedAt = System.currentTimeMillis(),
                        transcriptState = "",
                        updatedAt = System.currentTimeMillis(),
                    )
                }
            }

            StartDecision.NATIVE_PHONE_BATCH -> {
                val started = startPhoneBatch(context)
                updateState(context, state) {
                    it.copy(
                        recording = started,
                        continuous = false,
                        sourceKind = "phone",
                        source = "",
                        startedAt = if (started) System.currentTimeMillis() else 0L,
                        transcriptState = if (started) BATCH_WARNING else "",
                        updatedAt = System.currentTimeMillis(),
                    )
                }
                if (!started) openApp(context, WidgetAction.START_ONE_OFF.id)
            }

            StartDecision.OPEN_APP -> openApp(context, if (continuous) {
                WidgetAction.START_CONTINUOUS.id
            } else {
                WidgetAction.START_ONE_OFF.id
            })
        }
    }

    private fun stopRecording(context: Context) {
        val state = WidgetStateStore.read(context)
        when (state.sourceKind) {
            "ble" -> OmiBleForegroundService.stopCapture(context)
            "phone" -> stopPhoneCapture(context)
            else -> {
                // Unknown source (state lost): stop both, cheap and idempotent.
                OmiBleForegroundService.stopCapture(context)
                stopPhoneCapture(context)
            }
        }
        updateState(context, state) {
            it.copy(
                recording = false,
                continuous = false,
                sourceKind = "",
                source = "",
                startedAt = 0L,
                transcriptLines = emptyList(),
                transcriptState = "",
                updatedAt = System.currentTimeMillis(),
            )
        }
    }

    private fun connectDevice(context: Context) {
        val state = WidgetStateStore.read(context)
        val target = selectTargetAddress(state.targetAddress, WidgetPrefs.managedDevice(context))
        if (target.isEmpty()) {
            openApp(context, WidgetAction.CONNECT_DEVICE.id)
            return
        }
        val requiresBond = selectTargetRequiresBond(state.targetRequiresBond, WidgetPrefs.managedDevice(context))
        OmiBleForegroundService.startService(context, target, requiresBond, caller = "Widget")
        updateState(context, state) {
            it.copy(deviceConnected = true, updatedAt = System.currentTimeMillis())
        }
    }

    private fun startPhoneBatch(context: Context): Boolean = try {
        val application = context.applicationContext as android.app.Application
        if (!PhoneMicController.isInitialized) {
            PhoneMicController.initialize(application)
        }
        PhoneMicController.instance.start(PhoneMicCaptureMode.BATCH, System.currentTimeMillis()) { result ->
            if (result.isFailure) {
                Log.w(TAG, "Phone batch start failed: ${result.exceptionOrNull()?.message}")
            }
        }
        true
    } catch (e: Exception) {
        Log.e(TAG, "Phone batch start error", e)
        false
    }

    private fun stopPhoneCapture(context: Context) {
        try {
            if (PhoneMicController.isInitialized) {
                PhoneMicController.instance.stop { }
            }
            PhoneMicForegroundService.stop(context.applicationContext)
        } catch (e: Exception) {
            Log.e(TAG, "Phone capture stop error", e)
        }
    }

    private fun updateState(context: Context, current: WidgetState, transform: (WidgetState) -> WidgetState) {
        WidgetStateStore.write(context, transform(current))
        WidgetProviders.refreshAll(context)
    }

    private fun openApp(context: Context, action: String) {
        WidgetPendingAction.set(context, action)
        val intent = Intent(context, MainActivity::class.java).apply {
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP)
            putExtra(EXTRA_WIDGET_ACTION, action)
        }
        try {
            context.startActivity(intent)
        } catch (e: Exception) {
            Log.e(TAG, "Failed to open app for widget action $action", e)
        }
    }

    companion object {
        private const val TAG = "WidgetAction"
        private const val BATCH_WARNING = "Will transcribe later"

        fun pendingIntent(context: Context, action: WidgetAction, requestCode: Int): PendingIntent {
            val intent = Intent(context, WidgetActionReceiver::class.java).apply {
                this.action = action.id
                putExtra(EXTRA_WIDGET_ACTION, action.id)
            }
            return PendingIntent.getBroadcast(
                context,
                requestCode,
                intent,
                PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
            )
        }
    }
}
