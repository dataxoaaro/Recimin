"""Worker heartbeat loop."""

import asyncio

from recimin.config import Settings
from recimin.worker import main as worker_main


async def test_run_exits_when_stop_is_set(settings: Settings, monkeypatch) -> None:
    monkeypatch.setattr(worker_main, "HEARTBEAT_SECONDS", 0.01)
    stop = asyncio.Event()

    async def stopper() -> None:
        await asyncio.sleep(0.05)
        stop.set()

    await asyncio.gather(worker_main.run(settings, stop), stopper())
    assert stop.is_set()
