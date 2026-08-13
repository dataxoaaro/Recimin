"""Worker entry point.

Drains the import queue, one job at a time, until told to stop.
"""

import asyncio
import logging
import signal

from recimin import __version__
from recimin.config import get_settings
from recimin.db import schema
from recimin.db.connection import connect
from recimin.logging import configure_logging
from recimin.worker.handlers import handle_import
from recimin.worker.loop import run_forever

logger = logging.getLogger(__name__)


async def _main() -> None:
    settings = get_settings()
    conn = connect(settings.db_path)
    schema.migrate(conn)

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)

    logger.info("worker started", extra={"version": __version__})
    try:
        await run_forever(conn, settings, handle_import, stop)
    finally:
        conn.close()
        logger.info("worker stopped")


def main() -> None:
    """Console entry point."""
    configure_logging()
    asyncio.run(_main())


if __name__ == "__main__":
    main()
