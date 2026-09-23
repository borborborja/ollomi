package com.friend.ios.batch

/** Reassembles a CV1 Opus frame split across BLE notifications by the firmware MTU. */
internal class OmiBleFrameAssembler {
    private var pending: ByteArray? = null
    private var lastPacketId: Int? = null
    private var lastFragmentIndex: Int? = null

    fun accept(value: ByteArray): List<ByteArray> {
        if (value.size <= 3) return emptyList()
        val packetId = (value[0].toInt() and 0xff) or ((value[1].toInt() and 0xff) shl 8)
        val fragmentIndex = value[2].toInt() and 0xff
        val continuous = lastPacketId?.let { packetId == ((it + 1) and 0xffff) } ?: false
        val payload = value.copyOfRange(3, value.size)
        if (fragmentIndex == 0) {
            val complete = if (continuous) pending?.let { listOf(it) } ?: emptyList() else emptyList()
            pending = payload
            lastPacketId = packetId
            lastFragmentIndex = 0
            return complete
        }
        val previous = pending
        if (!continuous || previous == null || fragmentIndex != lastFragmentIndex!! + 1 ||
            previous.size + payload.size > MAX_OPUS_FRAME_BYTES) {
            reset()
            return emptyList()
        }
        pending = previous + payload
        lastPacketId = packetId
        lastFragmentIndex = fragmentIndex
        return emptyList()
    }

    fun reset() {
        pending = null
        lastPacketId = null
        lastFragmentIndex = null
    }

    companion object { private const val MAX_OPUS_FRAME_BYTES = 1275 }
}
