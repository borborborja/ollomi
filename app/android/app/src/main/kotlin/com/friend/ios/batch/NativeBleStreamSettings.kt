package com.friend.ios.batch

import org.json.JSONObject
import java.util.Locale

internal interface NativeBlePreferences {
    fun string(key: String, defaultValue: String = ""): String
    fun boolean(key: String, defaultValue: Boolean = false): Boolean
    fun integer(key: String, defaultValue: Int): Int
}

internal data class NativeBleStreamConfig(
    val deviceId: String,
    val codec: String,
    val sampleRate: Int,
    val source: String,
    val apiBaseUrl: String,
    val serviceUuid: String,
    val characteristicUuid: String,
    val deviceType: String,
    val geolocation: String?,
)

internal data class NativeBleStreamSettings(
    val config: NativeBleStreamConfig,
    val uid: String,
    val token: String,
    val deviceIdHash: String,
    val language: String,
    val timeout: Int,
    val vadGate: Boolean,
)

/** Read security gates synchronously: SharedPreferences listeners can lag BLE callbacks.
 * Only JSON decoding is cached; every use observes the current preference values. */
internal class NativeBleStreamSettingsReader(private val prefs: NativeBlePreferences) {
    private var configRaw: String? = null
    private var serverRaw: String? = null
    private var config: NativeBleStreamConfig? = null

    @Synchronized
    fun config(): NativeBleStreamConfig? {
        if (!prefs.boolean("nativeBleStreamingEnabled")) return null
        val raw = prefs.string("nativeBleStreamConfig")
        val server = prefs.string("ollomi.server")
        if (raw != configRaw || server != serverRaw) {
            config = parseConfig(raw, server)
            configRaw = raw
            serverRaw = server
        }
        return config
    }

    fun settings(): NativeBleStreamSettings? {
        val config = config() ?: return null
        val uid = prefs.string("uid")
        val token = prefs.string("nativeAuthToken").ifEmpty { prefs.string("authToken") }
        if (uid.isEmpty() || token.isEmpty()) return null
        return NativeBleStreamSettings(
            config, uid, token, prefs.string("deviceIdHash"),
            if (prefs.boolean("hasSetPrimaryLanguage")) {
                prefs.string("userPrimaryLanguage", "multi").ifEmpty { "multi" }
            } else "multi",
            prefs.integer("conversationSilenceDuration", 120).takeIf { it > 0 } ?: 120,
            prefs.boolean("vadGateEnabled"),
        )
    }

    private fun parseConfig(raw: String, configuredServer: String): NativeBleStreamConfig? = try {
        val json = JSONObject(raw)
        val deviceId = json.optString("deviceId")
        val serviceUuid = json.optString("serviceUuid").lowercase(Locale.US)
        val characteristicUuid = json.optString("characteristicUuid").lowercase(Locale.US)
        val server = NativeBleServerEndpointPolicy.canonicalHttpBaseUrl(configuredServer)
        val target = NativeBleServerEndpointPolicy.canonicalHttpBaseUrl(json.optString("apiBaseUrl"))
        if (deviceId.isEmpty() || serviceUuid.isEmpty() || characteristicUuid.isEmpty() ||
            server == null || target == null || target != server
        ) {
            null
        } else {
            NativeBleStreamConfig(
                deviceId, json.optString("codec", "pcm8"), json.optInt("sampleRate", 16000),
                json.optString("source"), target, serviceUuid, characteristicUuid,
                json.optString("deviceType"), json.optJSONObject("geolocation")?.toString(),
            )
        }
    } catch (_: Exception) {
        null
    }
}
