package com.friend.ios.widgets

import android.content.Context
import io.flutter.plugin.common.BinaryMessenger
import io.flutter.plugin.common.MethodCall
import io.flutter.plugin.common.MethodChannel

/**
 * Dart <-> native bridge for the home-screen widgets.
 *
 * Dart pushes the localized state (`updateState`) and drains an action left by a
 * cold-start widget tap (`consumePendingAction`). Warm taps arrive as an
 * `onWidgetAction` call on the same channel.
 */
class WidgetBridge(private val context: Context, messenger: BinaryMessenger) {
    private val channel = MethodChannel(messenger, CHANNEL)

    init {
        channel.setMethodCallHandler { call, result -> handle(call, result) }
    }

    private fun handle(call: MethodCall, result: MethodChannel.Result) {
        when (call.method) {
            "updateState" -> {
                val raw = call.argument<String>("state")
                if (raw == null) {
                    result.error("bad_args", "state is required", null)
                    return
                }
                val state = WidgetState.fromJson(raw).copy(updatedAt = System.currentTimeMillis())
                WidgetStateStore.write(context, state)
                WidgetProviders.refreshAll(context)
                result.success(true)
            }

            "consumePendingAction" -> result.success(WidgetPendingAction.consume(context))

            else -> result.notImplemented()
        }
    }

    /** Warm widget tap: forward to Dart while the engine is alive. */
    fun notifyAction(action: String) {
        try {
            channel.invokeMethod("onWidgetAction", action)
        } catch (_: Exception) {
            // The pending action is persisted, so a later consumePendingAction wins.
        }
    }

    companion object {
        const val CHANNEL = "com.ollomi.widgets"
    }
}
