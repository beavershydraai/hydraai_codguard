"""RTP for the External Media channel: Asterisk sends the caller's audio here, and we send the
agent's audio back, both as 8 kHz G.711 μ-law in 20 ms packets."""

import asyncio
import logging
import os
import struct
import time
from collections import deque
from collections.abc import Callable

from app.telephony.audio import (
    FRAME_MS,
    PHONE_FRAME_SAMPLES,
    Framer,
    pcm16_to_ulaw,
    ulaw_to_pcm16,
)

log = logging.getLogger(__name__)

PCMU = 0  # static RTP payload type of G.711 μ-law


def parse_rtp(packet: bytes) -> tuple[int, bytes] | None:
    """Payload type and payload of an RTP packet, or None if it is not RTP version 2."""
    if len(packet) < 12 or packet[0] >> 6 != 2:
        return None
    csrc_count = packet[0] & 0x0F
    offset = 12 + 4 * csrc_count
    if packet[0] & 0x10:  # header extension
        if len(packet) < offset + 4:
            return None
        (length,) = struct.unpack_from("!H", packet, offset + 2)
        offset += 4 + 4 * length
    end = len(packet)
    if packet[0] & 0x20:  # padding: the last byte is its length
        end -= packet[-1]
    if offset > end:
        return None
    return packet[1] & 0x7F, packet[offset:end]


def build_rtp(
    payload_type: int, seq: int, timestamp: int, ssrc: int, payload: bytes, marker: bool = False
) -> bytes:
    first = 0x80
    second = (0x80 if marker else 0) | (payload_type & 0x7F)
    header = struct.pack("!BBHII", first, second, seq & 0xFFFF, timestamp & 0xFFFFFFFF, ssrc)
    return header + payload


class RtpEndpoint(asyncio.DatagramProtocol):
    """One UDP socket per call. Incoming μ-law goes to `on_audio` as 8 kHz 16-bit little-endian
    PCM; `play()` queues PCM in the same format, which a paced sender encodes and writes out
    every 20 ms."""

    def __init__(self, on_audio: Callable[[bytes], None]) -> None:
        self._on_audio = on_audio
        self._transport: asyncio.DatagramTransport | None = None
        self._remote: tuple[str, int] | None = None
        self._payload_type = PCMU
        self._framer = Framer()
        self._queue: deque[bytes] = deque()
        self._seq = int.from_bytes(os.urandom(2))
        self._timestamp = int.from_bytes(os.urandom(4))
        self._ssrc = int.from_bytes(os.urandom(4))
        self._sender: asyncio.Task | None = None
        self._talking = False
        self.packets_in = 0
        self.packets_out = 0

    @classmethod
    async def open(
        cls, on_audio: Callable[[bytes], None], host: str = "127.0.0.1"
    ) -> "RtpEndpoint":
        loop = asyncio.get_running_loop()
        _, endpoint = await loop.create_datagram_endpoint(
            lambda: cls(on_audio), local_addr=(host, 0)
        )
        endpoint._sender = asyncio.create_task(endpoint._send_loop())
        return endpoint

    @property
    def local_address(self) -> str:
        assert self._transport is not None
        host, port = self._transport.get_extra_info("sockname")[:2]
        return f"{host}:{port}"

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        self._transport = transport  # type: ignore[assignment]

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        parsed = parse_rtp(data)
        if parsed is None:
            return
        payload_type, payload = parsed
        # Answer to wherever Asterisk sends from, with the payload type it uses.
        self._remote = addr
        self._payload_type = payload_type
        self.packets_in += 1
        if payload:
            self._on_audio(ulaw_to_pcm16(payload))

    def set_remote(self, host: str, port: int) -> None:
        """Where Asterisk listens (UNICASTRTP_LOCAL_* of the External Media channel), so the
        agent can speak first, before any audio has come in."""
        self._remote = (host, port)

    def play(self, pcm: bytes) -> None:
        self._queue.extend(self._framer.push(pcm))

    def clear(self) -> None:
        """Drop audio not sent yet, for example when the buyer interrupts the agent."""
        self._queue.clear()
        self._framer.clear()

    @property
    def pending_ms(self) -> int:
        return len(self._queue) * FRAME_MS

    async def drain(self, timeout: float) -> None:
        """Wait until the queued audio has been sent, at most `timeout` seconds."""
        deadline = time.monotonic() + timeout
        while self._queue and time.monotonic() < deadline:
            await asyncio.sleep(FRAME_MS / 1000)

    async def _send_loop(self) -> None:
        interval = FRAME_MS / 1000
        next_at = time.monotonic()
        while True:
            next_at += interval
            if self._queue and self._remote and self._transport:
                frame = self._queue.popleft()
                packet = build_rtp(
                    self._payload_type,
                    self._seq,
                    self._timestamp,
                    self._ssrc,
                    pcm16_to_ulaw(frame),
                    marker=not self._talking,
                )
                self._transport.sendto(packet, self._remote)
                self._seq += 1
                self._talking = True
                self.packets_out += 1
            else:
                self._talking = False
            # The timestamp advances in silence too, so the receiver sees real time.
            self._timestamp += PHONE_FRAME_SAMPLES
            delay = next_at - time.monotonic()
            if delay < -0.2:  # fell far behind (paused loop): resync instead of bursting
                next_at = time.monotonic()
                delay = 0
            await asyncio.sleep(max(delay, 0))

    def close(self) -> None:
        if self._sender:
            self._sender.cancel()
        if self._transport:
            self._transport.close()
