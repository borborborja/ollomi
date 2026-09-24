package com.friend.ios.background

import android.content.Context
import android.net.wifi.WifiManager
import android.os.PowerManager

/**
 * Tracks wake-lock ownership so acquire/release stay idempotent even when the
 * triggers overlap (e.g. a service start racing the first captured frame).
 */
class CaptureLockState {
    var held: Boolean = false
        private set

    fun acquire(): Boolean {
        if (held) return false
        held = true
        return true
    }

    fun release(): Boolean {
        if (!held) return false
        held = false
        return true
    }
}

/**
 * Partial wake lock (plus Wi-Fi lock) for an active capture session. Without it
 * the CPU can enter Doze while the screen is off: AudioRecord stops delivering
 * frames and BLE GATT callbacks are deferred until the device wakes, silently
 * truncating recordings. The Wi-Fi lock keeps the radio up so the live
 * transcription socket survives too (buffered audio covers the rest).
 *
 * Hold it while capture is actually running — never for the whole lifetime of a
 * service that may sit connected-but-idle for hours.
 */
class CaptureWakeLock(context: Context) {
    private val powerManager =
        context.applicationContext.getSystemService(Context.POWER_SERVICE) as PowerManager
    private val wifiManager = context.applicationContext.getSystemService(Context.WIFI_SERVICE) as? WifiManager
    private val state = CaptureLockState()
    private var lock: PowerManager.WakeLock? = null
    private var wifiLock: WifiManager.WifiLock? = null

    fun acquire() {
        if (!state.acquire()) return
        val wakeLock = powerManager.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, TAG).apply {
            setReferenceCounted(false)
        }
        wakeLock.acquire()
        lock = wakeLock
        @Suppress("DEPRECATION")
        wifiLock = wifiManager?.createWifiLock(WifiManager.WIFI_MODE_FULL_HIGH_PERF, "$TAG:wifi")?.apply {
            setReferenceCounted(false)
            acquire()
        }
    }

    fun release() {
        if (!state.release()) return
        lock?.let { if (it.isHeld) it.release() }
        lock = null
        wifiLock?.let { if (it.isHeld) it.release() }
        wifiLock = null
    }

    companion object {
        const val TAG = "ollomi:capture"
    }
}

/** Pure decision for "is this GATT notification a frame one of the capture sinks consumes?". */
object CaptureAudioTargets {
    fun matches(target: Pair<String, String>?, serviceUuid: String, characteristicUuid: String): Boolean =
        target != null &&
            target.first.equals(serviceUuid, ignoreCase = true) &&
            target.second.equals(characteristicUuid, ignoreCase = true)
}
