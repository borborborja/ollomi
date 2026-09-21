package com.friend.ios.batch

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class NativeBleServerEndpointPolicyTest {
    @Test
    fun `canonical endpoint accepts an Ollomi HTTP root and subpath`() {
        assertEquals(
            "https://ollomi.example.test/api/",
            NativeBleServerEndpointPolicy.canonicalHttpBaseUrl("https://OLLOMI.example.test/api///"),
        )
        assertEquals(
            "http://[fd00::10]:8080/",
            NativeBleServerEndpointPolicy.canonicalHttpBaseUrl("http://[fd00::10]:8080"),
        )
    }

    @Test
    fun `rejects credentials websocket URLs and legacy Omi hosts`() {
        for (url in listOf(
            "",
            "wss://ollomi.example.test/",
            "https://user:password@ollomi.example.test/",
            "https://ollomi.example.test/?token=secret",
            "https://api.omi.me/",
            "https://parakeet.omiapi.com/",
        )) {
            assertNull("expected rejection: $url", NativeBleServerEndpointPolicy.canonicalHttpBaseUrl(url))
        }
    }
}
