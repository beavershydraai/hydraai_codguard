"""PCM helpers for the call audio path.

Asterisk's External Media channel sends and expects 16 kHz signed linear audio in RTP payloads,
in network byte order. The Live API takes 16 kHz little-endian PCM and answers with 24 kHz
little-endian PCM.
"""

import numpy as np

SAMPLE_RATE = 16_000
FRAME_MS = 20
FRAME_BYTES = SAMPLE_RATE * FRAME_MS // 1000 * 2  # 640: 20 ms of 16-bit mono at 16 kHz


def swap16(pcm: bytes) -> bytes:
    """Swap the byte order of 16-bit samples (big-endian <-> little-endian)."""
    return np.frombuffer(pcm, dtype="<i2").byteswap().tobytes()


class Resampler:
    """Stateful linear resampler for 16-bit little-endian mono PCM.

    Chunks can have any length; the output is the same as resampling the whole stream at once,
    so there are no clicks at chunk boundaries. Linear interpolation is enough here: the phone
    leg is 8 kHz, and Asterisk low-pass filters when it converts 16 kHz down to it.
    """

    def __init__(self, rate_in: int, rate_out: int) -> None:
        self._step = rate_in / rate_out
        self._carry = np.zeros(0, dtype=np.float64)  # last input sample of the previous chunk
        self._pos = 0.0  # position of the next output sample, relative to the carry

    def process(self, pcm: bytes) -> bytes:
        samples = np.frombuffer(pcm, dtype="<i2").astype(np.float64)
        buf = np.concatenate([self._carry, samples])
        if len(buf) < 2:
            self._carry = buf
            return b""
        last = len(buf) - 1
        count = int(np.floor((last - self._pos) / self._step)) + 1 if self._pos <= last else 0
        positions = self._pos + self._step * np.arange(count)
        index = np.floor(positions).astype(np.int64)
        frac = positions - index
        upper = np.minimum(index + 1, last)
        out = buf[index] * (1.0 - frac) + buf[upper] * frac
        self._pos = self._pos + self._step * count - last
        self._carry = buf[-1:]
        return np.clip(np.rint(out), -32768, 32767).astype("<i2").tobytes()


class Framer:
    """Cuts a byte stream into fixed-size frames, keeping the remainder for the next call."""

    def __init__(self, frame_bytes: int = FRAME_BYTES) -> None:
        self._frame_bytes = frame_bytes
        self._buffer = bytearray()

    def push(self, data: bytes) -> list[bytes]:
        self._buffer.extend(data)
        size = self._frame_bytes
        count = len(self._buffer) // size
        frames = [bytes(self._buffer[i * size : (i + 1) * size]) for i in range(count)]
        del self._buffer[: count * size]
        return frames

    def clear(self) -> None:
        self._buffer.clear()
