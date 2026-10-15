"""PCM helpers for the call audio path.

Asterisk's External Media channel carries G.711 μ-law at 8 kHz, the phone network's own format
(Asterisk 20.6 drops slin16 sent back by an External Media application). The Live API takes
16 kHz and answers with 24 kHz 16-bit little-endian PCM. So caller audio goes 8 kHz -> 16 kHz and
model audio 24 kHz -> 8 kHz, both with stateful resamplers that give the same output however the
stream is cut into chunks.
"""

import numpy as np

PHONE_RATE = 8_000
FRAME_MS = 20
PHONE_FRAME_SAMPLES = PHONE_RATE * FRAME_MS // 1000  # 160 μ-law bytes per RTP packet
PHONE_FRAME_BYTES = PHONE_FRAME_SAMPLES * 2  # the same 20 ms as 16-bit PCM

_BIAS = 0x84
_SEGMENT_ENDS = np.array([0x3F, 0x7F, 0xFF, 0x1FF, 0x3FF, 0x7FF, 0xFFF, 0x1FFF])


def pcm16_to_ulaw(pcm: bytes) -> bytes:
    """G.711 μ-law encoding of 16-bit little-endian PCM (the reference g711.c algorithm, on the
    top 14 bits)."""
    x = np.frombuffer(pcm, dtype="<i2").astype(np.int32) >> 2
    negative = x < 0
    magnitude = np.minimum(np.where(negative, -x, x), 8159) + 0x21
    segment = np.searchsorted(_SEGMENT_ENDS, magnitude)
    value = np.where(
        segment >= 8, 0x7F, (segment << 4) | ((magnitude >> (np.minimum(segment, 7) + 1)) & 0x0F)
    )
    return (value ^ np.where(negative, 0x7F, 0xFF)).astype(np.uint8).tobytes()


def ulaw_to_pcm16(ulaw: bytes) -> bytes:
    """G.711 μ-law decoding to 16-bit little-endian PCM."""
    u = ~np.frombuffer(ulaw, dtype=np.uint8).astype(np.int32) & 0xFF
    exponent = (u >> 4) & 0x07
    mantissa = u & 0x0F
    magnitude = (((mantissa << 3) + _BIAS) << exponent) - _BIAS
    return np.where(u & 0x80, -magnitude, magnitude).astype("<i2").tobytes()


def _to_pcm(samples: np.ndarray) -> bytes:
    return np.clip(np.rint(samples), -32768, 32767).astype("<i2").tobytes()


class Resampler:
    """Stateful linear interpolation, for upsampling (caller audio 8 kHz -> 16 kHz)."""

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
        return _to_pcm(out)


class Downsampler:
    """Stateful low-pass filter and decimation by a whole factor (model audio 24 kHz -> 8 kHz).
    The filter removes what lies above the new Nyquist frequency, which would otherwise fold
    back into the speech band as hiss."""

    def __init__(self, factor: int, taps: int = 63) -> None:
        self._factor = factor
        n = np.arange(taps) - (taps - 1) / 2
        cutoff = 0.45 / factor  # cycles per input sample, a little under the new Nyquist
        kernel = 2 * cutoff * np.sinc(2 * cutoff * n) * np.hamming(taps)
        self._kernel = kernel / kernel.sum()
        self._history = np.zeros(taps - 1)
        self._consumed = 0

    def process(self, pcm: bytes) -> bytes:
        samples = np.frombuffer(pcm, dtype="<i2").astype(np.float64)
        if not len(samples):
            return b""
        filtered = np.convolve(np.concatenate([self._history, samples]), self._kernel, "valid")
        start = (-self._consumed) % self._factor  # keep every factor-th sample of the stream
        self._consumed += len(samples)
        self._history = np.concatenate([self._history, samples])[-(len(self._kernel) - 1) :]
        return _to_pcm(filtered[start :: self._factor])


class Framer:
    """Cuts a byte stream into fixed-size frames, keeping the remainder for the next call."""

    def __init__(self, frame_bytes: int = PHONE_FRAME_BYTES) -> None:
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
