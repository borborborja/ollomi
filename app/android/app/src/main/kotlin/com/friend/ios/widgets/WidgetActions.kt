package com.friend.ios.widgets

import android.content.Context

import com.friend.ios.batch.NativeBleStreamSettingsReader
import com.friend.ios.batch.SharedPreferencesValues
import com.friend.ios.ble.OmiBleForegroundService

enum class WidgetAction(val id: String) {
    START_ONE_OFF("start_one_off"),
    START_CONTINUOUS("start_continuous"),
    STOP("stop"),
    CONNECT_DEVICE("connect_device"),
    OPEN_TRANSCRIPT("open_transcript");

    companion object {
        fun fromId(id: String?): WidgetAction? = values().firstOrNull { it.id == id }
    }
}

/** Where a start request can run. */
enum class StartDecision {
    /** Device target with a saved native stream config: runs with the app closed. */
    NATIVE_BLE,

    /** No device target: native Transcribe Later on the phone microphone. */
    NATIVE_PHONE_BATCH,

    /** Missing config/auth/persistent mode: the app must be opened. */
    OPEN_APP,
}

/**
 * A start can run natively only when the native streamer/batch writer has
 * everything it reads: a target device (or none for the phone microphone), a
 * saved stream config, an authenticated session, persistent mode, and a batch
 * directory for the phone path.
 */
fun decideStart(
    targetAddress: String,
    nativeStreamReady: Boolean,
    authenticated: Boolean,
    persistentMode: Boolean,
    batchDirReady: Boolean,
): StartDecision = when {
    targetAddress.isNotEmpty() && nativeStreamReady && authenticated && persistentMode -> StartDecision.NATIVE_BLE
    targetAddress.isEmpty() && batchDirReady -> StartDecision.NATIVE_PHONE_BATCH
    else -> StartDecision.OPEN_APP
}

/** The device the widget acts on: the pushed target, else the last managed device. */
fun selectTargetAddress(stateTarget: String, managedDevice: String?): String =
    stateTarget.ifEmpty { managedDevice?.substringBefore('|') ?: "" }

fun selectTargetRequiresBond(stateRequiresBond: Boolean, managedDevice: String?): Boolean {
    if (stateRequiresBond) return true
    val parts = managedDevice?.split('|') ?: return false
    return parts.size >= 2 && parts[1].toBoolean()
}

object WidgetPrefs {
    const val FLUTTER = "FlutterSharedPreferences"
    const val BLE = "ble_config"
    const val MANAGED_DEVICE = "managed_device"

    /** Set while the widget stopped capture, so native writers stay quiet until
     *  the user (or the app) starts again. Cleared by every widget/Dart start. */
    const val CAPTURE_PAUSED = "flutter.widgetCapturePaused"

    fun flutter(context: Context) = context.getSharedPreferences(FLUTTER, Context.MODE_PRIVATE)

    fun managedDevice(context: Context): String? =
        context.getSharedPreferences(BLE, Context.MODE_PRIVATE).getString(MANAGED_DEVICE, null)

    fun capturePaused(context: Context): Boolean = flutter(context).getBoolean(CAPTURE_PAUSED, false)

    fun setCapturePaused(context: Context, paused: Boolean) {
        flutter(context).edit().putBoolean(CAPTURE_PAUSED, paused).apply()
    }
}

/** Context-dependent readiness checks, mirroring what the native writers read. */
object WidgetNativeReadiness {
    fun authenticated(context: Context): Boolean {
        val prefs = WidgetPrefs.flutter(context)
        val uid = prefs.getString("flutter.uid", "") ?: ""
        val token = (prefs.getString("flutter.nativeAuthToken", "") ?: "")
            .ifEmpty { prefs.getString("flutter.authToken", "") ?: "" }
        return uid.isNotEmpty() && token.isNotEmpty()
    }

    /** The saved stream config is valid for the configured server AND readable. */
    fun streamReady(context: Context): Boolean =
        NativeBleStreamSettingsReader(SharedPreferencesValues(WidgetPrefs.flutter(context))).settings() != null

    fun persistentMode(context: Context): Boolean = OmiBleForegroundService.isPersistentModeEnabled(context)

    fun batchDirReady(context: Context): Boolean =
        (WidgetPrefs.flutter(context).getString("flutter.batchAudioDir", "") ?: "").isNotEmpty()
}

object WidgetPendingAction {
    const val PREFS = "ollomi_widget_pending"
    const val KEY = "action"

    fun set(context: Context, action: String) {
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .edit()
            .putString(KEY, action)
            .apply()
    }

    fun consume(context: Context): String? {
        val prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        val action = prefs.getString(KEY, null)
        if (action != null) {
            prefs.edit().remove(KEY).apply()
        }
        return action
    }
}

const val EXTRA_WIDGET_ACTION = "ollomi_widget_action"
