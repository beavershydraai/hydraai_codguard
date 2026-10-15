"""Minimal Asterisk REST Interface (ARI) client: the requests the controller makes and the
event stream of its Stasis app. See docs/call-controller.md, section ARI."""

import base64
import json
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from urllib.parse import urlsplit

import httpx
import websockets

log = logging.getLogger(__name__)


class AriError(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(f"ARI {status}: {message}")
        self.status = status


class AriClient:
    def __init__(self, url: str, user: str, password: str, app: str) -> None:
        self.app = app
        self._url = url.rstrip("/")
        self._auth = (user, password)
        self._http = httpx.AsyncClient(base_url=f"{self._url}/ari", auth=self._auth, timeout=10)

    async def close(self) -> None:
        await self._http.aclose()

    async def _request(self, method: str, path: str, **params: Any) -> Any:
        query = {k: v for k, v in params.items() if v is not None and k != "json_body"}
        try:
            response = await self._http.request(
                method, path, params=query, json=params.get("json_body")
            )
        except httpx.HTTPError as exc:
            raise AriError(0, f"{method} {path}: {exc}") from exc
        if response.status_code >= 400:
            raise AriError(response.status_code, f"{method} {path}: {response.text[:200]}")
        return response.json() if response.content else None

    @asynccontextmanager
    async def event_stream(self) -> AsyncIterator[AsyncIterator[dict]]:
        """Connect to the events of this app; the app exists in Asterisk from here on, so
        originate only inside this block. Yields an iterator over the events."""
        parts = urlsplit(self._url)
        scheme = "wss" if parts.scheme == "https" else "ws"
        url = f"{scheme}://{parts.netloc}/ari/events?app={self.app}&subscribeAll=false"
        token = base64.b64encode(":".join(self._auth).encode()).decode()
        async with websockets.connect(
            url, additional_headers={"Authorization": f"Basic {token}"}, ping_interval=20
        ) as ws:

            async def events() -> AsyncIterator[dict]:
                async for message in ws:
                    yield json.loads(message)

            yield events()

    # Channels

    async def originate(
        self,
        endpoint: str,
        channel_id: str,
        app_args: str,
        timeout: int,
        variables: dict[str, str] | None = None,
    ) -> dict:
        return await self._request(
            "POST",
            "/channels",
            endpoint=endpoint,
            app=self.app,
            appArgs=app_args,
            channelId=channel_id,
            timeout=timeout,
            json_body={"variables": variables or {}},
        )

    async def hangup(self, channel_id: str) -> None:
        try:
            await self._request("DELETE", f"/channels/{channel_id}")
        except AriError as exc:
            if exc.status != 404:  # already gone
                raise

    async def set_variable(self, channel_id: str, variable: str, value: str) -> None:
        await self._request(
            "POST", f"/channels/{channel_id}/variable", variable=variable, value=value
        )

    async def external_media(
        self, channel_id: str, external_host: str, audio_format: str = "ulaw"
    ) -> dict:
        return await self._request(
            "POST",
            "/channels/externalMedia",
            channelId=channel_id,
            app=self.app,
            external_host=external_host,
            format=audio_format,
            encapsulation="rtp",
            transport="udp",
            direction="both",
        )

    # Bridges

    async def create_bridge(self, bridge_id: str) -> dict:
        return await self._request("POST", f"/bridges/{bridge_id}", type="mixing")

    async def add_channels(self, bridge_id: str, *channel_ids: str) -> None:
        await self._request(
            "POST", f"/bridges/{bridge_id}/addChannel", channel=",".join(channel_ids)
        )

    async def destroy_bridge(self, bridge_id: str) -> None:
        try:
            await self._request("DELETE", f"/bridges/{bridge_id}")
        except AriError as exc:
            if exc.status != 404:
                raise
