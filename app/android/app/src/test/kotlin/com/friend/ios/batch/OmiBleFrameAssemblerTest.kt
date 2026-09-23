package com.friend.ios.batch

import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class OmiBleFrameAssemblerTest {
    private fun packet(id: Int, fragment: Int, vararg payload: Int): ByteArray =
        byteArrayOf((id and 0xff).toByte(), (id shr 8).toByte(), fragment.toByte(),
            *payload.map(Int::toByte).toByteArray())

    @Test fun `assembles firmware fragments before emitting an Opus frame`() {
        val assembler = OmiBleFrameAssembler()
        assertTrue(assembler.accept(packet(10, 0, 1, 2)).isEmpty())
        assertTrue(assembler.accept(packet(11, 1, 3, 4)).isEmpty())
        assertArrayEquals(byteArrayOf(1, 2, 3, 4), assembler.accept(packet(12, 0, 5)).single())
    }

    @Test fun `missing fragment drops only the incomplete frame and rollover is valid`() {
        val assembler = OmiBleFrameAssembler()
        assembler.accept(packet(10, 0, 1))
        assertTrue(assembler.accept(packet(12, 1, 2)).isEmpty())
        assertTrue(assembler.accept(packet(65535, 0, 3)).isEmpty())
        assertArrayEquals(byteArrayOf(3), assembler.accept(packet(0, 0, 4)).single())
    }
}
