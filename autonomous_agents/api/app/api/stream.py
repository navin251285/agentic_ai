"""SSE endpoint: the full Snapshot JSON every tick, plus a heartbeat comment every 15s.

The simulation calls `SnapshotHub.publish` after every tick (while holding its lock). The snapshot is
serialised once per tick, only when someone is listening, and each client keeps just the latest one,
so a slow client skips frames instead of building a backlog.
"""

import asyncio
import contextlib
import signal
import threading
import time
from collections.abc import AsyncIterable, Callable

from fastapi import APIRouter, Request
from fastapi.sse import EventSourceResponse, ServerSentEvent

from app.domain.models import Snapshot

HEARTBEAT_S = 15.0
RETRY_MS = 2000  # EventSource reconnect delay

router = APIRouter(prefix="/api")


class _Client:
    def __init__(self) -> None:
        self.latest: str | None = None
        self.ready = asyncio.Event()

    def offer(self, data: str) -> None:
        self.latest = data
        self.ready.set()

    def take(self) -> str | None:
        data, self.latest = self.latest, None
        self.ready.clear()
        return data


class SnapshotHub:
    def __init__(self, snapshot_json: Callable[[], str]):
        self.snapshot_json = snapshot_json
        self.clients: set[_Client] = set()
        self.closed = asyncio.Event()

    def publish(self) -> None:
        if not self.clients:
            return
        data = self.snapshot_json()
        for client in self.clients:
            client.offer(data)

    def close(self) -> None:
        """End every open stream (server shutting down)."""
        self.closed.set()
        for client in self.clients:
            client.ready.set()  # wake waiting streams so they see `closed`

    async def events(self) -> AsyncIterable[ServerSentEvent]:
        client = _Client()
        client.offer(self.snapshot_json())  # the first frame goes out immediately
        self.clients.add(client)
        try:
            yield ServerSentEvent(retry=RETRY_MS, comment="connected")
            next_heartbeat = time.monotonic() + HEARTBEAT_S
            while not self.closed.is_set():  # a client disconnect cancels this generator
                timeout = max(0.0, next_heartbeat - time.monotonic())
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(client.ready.wait(), timeout)
                if (data := client.take()) is not None:
                    yield ServerSentEvent(raw_data=data)
                if time.monotonic() >= next_heartbeat:
                    yield ServerSentEvent(comment="heartbeat")
                    next_heartbeat = time.monotonic() + HEARTBEAT_S
        finally:
            self.clients.discard(client)


def end_streams_on_exit_signal(hub: SnapshotHub) -> None:
    """Uvicorn waits for open responses to finish before running lifespan shutdown, and an SSE stream
    never finishes by itself, so Ctrl+C / docker stop would hang and skip the final save. Chain onto
    the server's SIGINT/SIGTERM handlers to end the streams first. No-op outside the main thread
    (e.g. TestClient) or when no server handler is installed."""
    if threading.current_thread() is not threading.main_thread():
        return
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        previous = signal.getsignal(sig)
        if not callable(previous):
            continue

        def handler(signum, frame, previous=previous):
            loop.call_soon_threadsafe(hub.close)
            previous(signum, frame)

        signal.signal(sig, handler)


@router.get(
    "/stream",
    response_class=EventSourceResponse,
    summary="Live snapshot stream (SSE)",
    description=(
        "Server-Sent Events. Each message's data is the same `Snapshot` JSON as "
        "`GET /api/snapshot`, sent every tick (0.5s). A `: heartbeat` comment is sent every 15s."
    ),
)
async def stream(request: Request) -> AsyncIterable[Snapshot]:
    async for event in request.app.state.hub.events():
        yield event
