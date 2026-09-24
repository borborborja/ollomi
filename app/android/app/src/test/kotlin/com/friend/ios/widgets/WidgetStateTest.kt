package com.friend.ios.widgets

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class WidgetStateTest {
    @Test
    fun `json round trip preserves every field`() {
        val state = WidgetState(
            recording = true,
            continuous = true,
            sourceKind = "ble",
            source = "Omi CV1",
            startedAt = 1234L,
            transcriptLines = listOf("first line", "second line"),
            transcriptState = "Transcribing",
            deviceName = "Casa",
            deviceBattery = 74,
            deviceConnected = true,
            targetDeviceId = "AA:BB",
            targetAddress = "AA:BB",
            targetRequiresBond = true,
            labelOneOff = "Puntual",
            labelContinuous = "Continua",
            labelStop = "Atura",
            labelConnect = "Connecta",
            labelIdle = "Ollomi",
        )

        val restored = WidgetState.fromJson(state.toJson())

        assertEquals(state, restored)
    }

    @Test
    fun `garbage json falls back to defaults`() {
        val restored = WidgetState.fromJson("not json")

        assertFalse(restored.recording)
        assertTrue(restored.transcriptLines.isEmpty())
        assertEquals(-1, restored.deviceBattery)
        assertEquals("Ollomi", restored.labelIdle)
    }

    @Test
    fun `null json falls back to defaults`() {
        assertFalse(WidgetState.fromJson(null).recording)
    }
}
