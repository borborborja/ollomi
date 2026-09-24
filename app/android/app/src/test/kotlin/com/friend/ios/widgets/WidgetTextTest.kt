package com.friend.ios.widgets

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class WidgetTextTest {
    @Test
    fun `keeps the latest two non blank lines from a transcript array`() {
        val raw = """[{"text":"one"},{"text":"  "},{"text":"two"},{"text":"three"}]"""

        assertEquals(listOf("two", "three"), extractTranscriptLines(raw))
    }

    @Test
    fun `ignores service status frames and malformed json`() {
        assertTrue(extractTranscriptLines("""{"type":"service_status","status":"ready"}""").isEmpty())
        assertTrue(extractTranscriptLines("[not json").isEmpty())
        assertTrue(extractTranscriptLines("").isEmpty())
    }
}
