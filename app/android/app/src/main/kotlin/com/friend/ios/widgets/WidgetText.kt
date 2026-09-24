package com.friend.ios.widgets

import org.json.JSONArray

/**
 * Latest (up to [limit]) non-blank segment texts from a live transcript message.
 *
 * Pure and defensive: the background streamer passes raw server frames, some of
 * which are not transcript arrays at all.
 */
fun extractTranscriptLines(raw: String, limit: Int = 2): List<String> {
    val trimmed = raw.trimStart()
    if (!trimmed.startsWith("[")) return emptyList()
    return try {
        val array = JSONArray(trimmed)
        val texts = mutableListOf<String>()
        for (index in 0 until array.length()) {
            val text = array.optJSONObject(index)?.optString("text")?.trim().orEmpty()
            if (text.isNotEmpty()) texts.add(text)
        }
        texts.takeLast(limit)
    } catch (_: Exception) {
        emptyList()
    }
}
