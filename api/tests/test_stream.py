"""SSE hub: first frame at once, one frame per publish (latest only), heartbeat, close ends the stream."""

import asyncio
import json

from app.api import stream
from app.api.stream import SnapshotHub


class Counter:
    def __init__(self):
        self.n = 0

    def __call__(self) -> str:
        self.n += 1
        return json.dumps({"frame": self.n})


async def collect(hub, n):
    gen = hub.events()
    return gen, [await anext(gen) for _ in range(n)]


def test_first_frame_then_one_per_publish():
    async def run():
        hub = SnapshotHub(Counter())
        gen, (hello, first) = await collect(hub, 2)
        assert hello.retry == stream.RETRY_MS and hello.comment == "connected"
        assert json.loads(first.raw_data) == {"frame": 1}
        hub.publish()
        hub.publish()  # a slow client only gets the latest
        assert json.loads((await anext(gen)).raw_data) == {"frame": 3}
        await gen.aclose()
        assert hub.clients == set()

    asyncio.run(run())


def test_publish_without_listeners_builds_nothing():
    snapshot = Counter()
    SnapshotHub(snapshot).publish()
    assert snapshot.n == 0


def test_heartbeat_comment_when_quiet(monkeypatch):
    monkeypatch.setattr(stream, "HEARTBEAT_S", 0.05)

    async def run():
        gen, _ = await collect(SnapshotHub(Counter()), 2)
        beat = await asyncio.wait_for(anext(gen), 1)
        assert beat.comment == "heartbeat" and beat.raw_data is None
        await gen.aclose()

    asyncio.run(run())


def test_close_ends_open_streams():
    async def run():
        hub = SnapshotHub(Counter())
        gen, _ = await collect(hub, 2)
        waiting = asyncio.ensure_future(anext(gen))
        await asyncio.sleep(0.01)
        hub.close()
        try:
            await asyncio.wait_for(waiting, 1)
            raise AssertionError("stream should have ended")
        except StopAsyncIteration:
            pass
        assert hub.clients == set()

    asyncio.run(run())
