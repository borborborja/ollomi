package com.friend.ios.batch

import java.net.URI
import java.util.Locale

/**
 * Native BLE audio can only be sent to the signed-in Ollomi server.  The JSON
 * handoff is stored in preferences, so validate its endpoint again on the
 * native side instead of trusting a legacy client-side STT preference.
 */
internal object NativeBleServerEndpointPolicy {
    fun canonicalHttpBaseUrl(raw: String): String? {
        val value = raw.trim()
        if (value.isEmpty()) return null

        return try {
            val uri = URI(value)
            val scheme = uri.scheme?.lowercase(Locale.US) ?: return null
            val host = uri.host?.removeSurrounding("[", "]")?.lowercase(Locale.US)?.trimEnd('.') ?: return null
            if (scheme !in setOf("http", "https") ||
                uri.userInfo != null ||
                uri.rawQuery != null ||
                uri.rawFragment != null ||
                uri.port !in -1..65535 ||
                isLegacyOmiHost(host)
            ) {
                return null
            }

            val path = uri.rawPath.orEmpty().trimEnd('/')
            if (path.split('/').any { it == "." || it == ".." }) return null
            val authorityHost = if (host.contains(':')) "[$host]" else host
            val port = if (uri.port == -1) "" else ":${uri.port}"
            "$scheme://$authorityHost$port$path/"
        } catch (_: Exception) {
            null
        }
    }

    private fun isLegacyOmiHost(host: String): Boolean =
        host == "omi.me" || host.endsWith(".omi.me") ||
            host == "omiapi.com" || host.endsWith(".omiapi.com")
}
