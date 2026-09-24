package com.friend.ios.background

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class CaptureWakeLockTest {

    @Test
    fun lockStateAcquireIsIdempotent() {
        val state = CaptureLockState()
        assertTrue(state.acquire())
        assertTrue(state.held)
        assertFalse(state.acquire())
        assertTrue(state.held)
    }

    @Test
    fun lockStateReleaseIsIdempotent() {
        val state = CaptureLockState()
        assertTrue(state.acquire())
        assertTrue(state.release())
        assertFalse(state.held)
        assertFalse(state.release())
    }

    @Test
    fun lockStateAcquireAfterReleaseHolds() {
        val state = CaptureLockState()
        state.acquire()
        state.release()
        assertTrue(state.acquire())
        assertTrue(state.held)
    }

    @Test
    fun audioTargetRejectsUnconfiguredDevice() {
        assertFalse(CaptureAudioTargets.matches(null, "service", "audio"))
    }

    @Test
    fun audioTargetMatchesConfiguredCharacteristic() {
        val target = "service" to "audio"
        assertTrue(CaptureAudioTargets.matches(target, "service", "audio"))
    }

    @Test
    fun audioTargetMatchesCaseInsensitiveUuids() {
        val target = "0000fe59-0000-1000-8000-00805f9b34fb" to "2ea1 feature"
        assertTrue(
            CaptureAudioTargets.matches(
                target,
                "0000FE59-0000-1000-8000-00805F9B34FB",
                "2EA1 FEATURE",
            ),
        )
    }

    @Test
    fun audioTargetRejectsOtherServiceOrCharacteristic() {
        val target = "service" to "audio"
        assertFalse(CaptureAudioTargets.matches(target, "battery", "audio"))
        assertFalse(CaptureAudioTargets.matches(target, "service", "battery"))
    }
}
