package com.friend.ios.widgets

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject

/**
 * Snapshot the home-screen widgets render.
 *
 * Persisted in [WidgetStateStore] so a widget paints immediately after a
 * process restart, before Dart pushes a fresh state. Everything here is plain
 * data; [parse] has no Android dependency so the round-trip is unit-testable.
 */
data class WidgetState(
    val recording: Boolean = false,
    val continuous: Boolean = false,
    val sourceKind: String = "",
    val source: String = "",
    val startedAt: Long = 0L,
    val transcriptLines: List<String> = emptyList(),
    val transcriptState: String = "",
    val deviceName: String = "",
    val deviceBattery: Int = -1,
    val deviceConnected: Boolean = false,
    val targetDeviceId: String = "",
    val targetAddress: String = "",
    val targetRequiresBond: Boolean = false,
    val labelOneOff: String = "Quick recording",
    val labelContinuous: String = "Continuous",
    val labelStop: String = "Stop",
    val labelConnect: String = "Connect",
    val labelIdle: String = "Ollomi",
    val labelOpenApp: String = "Open the app",
    val updatedAt: Long = 0L,
) {
    fun toJsonObject(): JSONObject = JSONObject().apply {
        put("recording", recording)
        put("continuous", continuous)
        put("source_kind", sourceKind)
        put("source", source)
        put("started_at", startedAt)
        put("transcript_lines", JSONArray(transcriptLines))
        put("transcript_state", transcriptState)
        put("device_name", deviceName)
        put("device_battery", deviceBattery)
        put("device_connected", deviceConnected)
        put("target_device_id", targetDeviceId)
        put("target_address", targetAddress)
        put("target_requires_bond", targetRequiresBond)
        put("label_one_off", labelOneOff)
        put("label_continuous", labelContinuous)
        put("label_stop", labelStop)
        put("label_connect", labelConnect)
        put("label_idle", labelIdle)
        put("label_open_app", labelOpenApp)
        put("updated_at", updatedAt)
    }

    fun toJson(): String = toJsonObject().toString()

    companion object {
        fun fromJson(raw: String?): WidgetState = try {
            parse(JSONObject(raw ?: ""))
        } catch (_: Exception) {
            WidgetState()
        }

        fun parse(json: JSONObject): WidgetState {
            val lines = mutableListOf<String>()
            json.optJSONArray("transcript_lines")?.let { array ->
                for (index in 0 until array.length()) {
                    lines.add(array.optString(index))
                }
            }
            return WidgetState(
                recording = json.optBoolean("recording"),
                continuous = json.optBoolean("continuous"),
                sourceKind = json.optString("source_kind"),
                source = json.optString("source"),
                startedAt = json.optLong("started_at"),
                transcriptLines = lines,
                transcriptState = json.optString("transcript_state"),
                deviceName = json.optString("device_name"),
                deviceBattery = json.optInt("device_battery", -1),
                deviceConnected = json.optBoolean("device_connected"),
                targetDeviceId = json.optString("target_device_id"),
                targetAddress = json.optString("target_address"),
                targetRequiresBond = json.optBoolean("target_requires_bond"),
                labelOneOff = json.optString("label_one_off", "Quick recording"),
                labelContinuous = json.optString("label_continuous", "Continuous"),
                labelStop = json.optString("label_stop", "Stop"),
                labelConnect = json.optString("label_connect", "Connect"),
                labelIdle = json.optString("label_idle", "Idle"),
                labelOpenApp = json.optString("label_open_app", "Open the app"),
                updatedAt = json.optLong("updated_at"),
            )
        }
    }
}

object WidgetStateStore {
    const val PREFS = "ollomi_widget_state"
    const val KEY = "state"

    fun read(context: Context): WidgetState {
        val prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        return WidgetState.fromJson(prefs.getString(KEY, null))
    }

    fun write(context: Context, state: WidgetState) {
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .edit()
            .putString(KEY, state.toJson())
            .apply()
    }
}
