"""Worker entry point.

Phase 0 is a heartbeat only. The job loop arrives in Phase 5, and it processes
exactly one job at a time — concurrency of one is a requirement, not a default.
"""

import asyncio
import contextlib
import logging
import signal

from recimin import __version__
from recimin.config import Settings, get_settings
from recimin.logging import configure_logging

logger = logging.getLogger(__name__)

HEARTBEAT_SECONDS = 30


async def run(settings: Settings, stop: asyncio.Event) -> None:
    """Poll until asked to stop."""
    logger.info("worker started", extra={"version": __version__})
    while not stop.is_set():
        logger.info("heartbeat", extra={"queue_depth": 0})
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=HEARTBEAT_SECONDS)
    logger.info("worker stopped")


async def _main() -> None:
    settings = get_settings()
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)
    await run(settings, stop)


def main() -> None:
    """Console entry point."""
    configure_logging()
    asyncio.run(_main())


if __name__ == "__main__":
    main()
