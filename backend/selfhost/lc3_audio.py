"""Decode the Friend Pendant's 30-byte, 10 ms, 16 kHz mono LC3 frames."""

import ctypes
import ctypes.util


FRAME_BYTES = 30
SAMPLE_RATE = 16000
FRAME_SAMPLES = 160
FRAME_DURATION_US = 10000


class Lc3Decoder:
    def __init__(self):
        library_name = ctypes.util.find_library("lc3")
        if not library_name:
            raise RuntimeError("liblc3 is required for Friend Pendant audio")
        self._library = ctypes.CDLL(library_name)
        self._library.lc3_decoder_size.argtypes = (ctypes.c_int, ctypes.c_int)
        self._library.lc3_decoder_size.restype = ctypes.c_uint
        self._library.lc3_setup_decoder.argtypes = (
            ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_void_p
        )
        self._library.lc3_setup_decoder.restype = ctypes.c_void_p
        self._library.lc3_decode.argtypes = (
            ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int, ctypes.c_int,
            ctypes.c_void_p, ctypes.c_int
        )
        self._library.lc3_decode.restype = ctypes.c_int
        size = self._library.lc3_decoder_size(FRAME_DURATION_US, SAMPLE_RATE)
        if not size:
            raise RuntimeError("Cannot allocate LC3 decoder")
        # Keep the state buffer alive as long as the opaque decoder handle exists.
        self._memory = ctypes.create_string_buffer(size)
        self._decoder = self._library.lc3_setup_decoder(
            FRAME_DURATION_US, SAMPLE_RATE, 0, self._memory
        )
        if not self._decoder:
            raise RuntimeError("Cannot initialize LC3 decoder")

    def decode(self, frame: bytes) -> bytes:
        if len(frame) != FRAME_BYTES:
            raise ValueError("Friend Pendant LC3 frame must be 30 bytes")
        samples = (ctypes.c_int16 * FRAME_SAMPLES)()
        input_frame = ctypes.create_string_buffer(frame)
        result = self._library.lc3_decode(
            self._decoder, input_frame, FRAME_BYTES, 0, samples, 1
        )
        if result < 0:
            raise ValueError("Invalid Friend Pendant LC3 frame")
        return ctypes.string_at(samples, FRAME_SAMPLES * 2)
