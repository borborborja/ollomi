package com.friend.ios.widgets

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class WidgetActionsTest {
    @Test
    fun `device target with native config starts without opening the app`() {
        val decision = decideStart(
            targetAddress = "AA:BB",
            nativeStreamReady = true,
            authenticated = true,
            persistentMode = true,
            batchDirReady = false,
        )

        assertEquals(StartDecision.NATIVE_BLE, decision)
    }

    @Test
    fun `device target missing config opens the app`() {
        assertEquals(
            StartDecision.OPEN_APP,
            decideStart("AA:BB", nativeStreamReady = false, authenticated = true, persistentMode = true, batchDirReady = true),
        )
    }

    @Test
    fun `device target without persistent mode opens the app`() {
        assertEquals(
            StartDecision.OPEN_APP,
            decideStart("AA:BB", nativeStreamReady = true, authenticated = true, persistentMode = false, batchDirReady = true),
        )
    }

    @Test
    fun `phone mic without a batch directory opens the app`() {
        assertEquals(
            StartDecision.OPEN_APP,
            decideStart("", nativeStreamReady = false, authenticated = true, persistentMode = false, batchDirReady = false),
        )
    }

    @Test
    fun `phone mic with a batch directory records natively`() {
        assertEquals(
            StartDecision.NATIVE_PHONE_BATCH,
            decideStart("", nativeStreamReady = false, authenticated = true, persistentMode = false, batchDirReady = true),
        )
    }

    @Test
    fun `target address prefers the pushed state and falls back to the managed device`() {
        assertEquals("state-address", selectTargetAddress("state-address", "managed-address|true"))
        assertEquals("managed-address", selectTargetAddress("", "managed-address|true"))
        assertEquals("", selectTargetAddress("", null))
    }

    @Test
    fun `requires bond follows the state then the managed device flag`() {
        assertTrue(selectTargetRequiresBond(true, null))
        assertTrue(selectTargetRequiresBond(false, "addr|true"))
        assertFalse(selectTargetRequiresBond(false, "addr|false"))
        assertFalse(selectTargetRequiresBond(false, null))
    }

    @Test
    fun `action ids round trip and unknown ids are ignored`() {
        assertEquals(WidgetAction.START_CONTINUOUS, WidgetAction.fromId("start_continuous"))
        assertEquals(null, WidgetAction.fromId("nope"))
        assertEquals(null, WidgetAction.fromId(null))
    }
}
