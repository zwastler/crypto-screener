import asyncio
import signal

import structlog
import uvloop

from adapters.bybit import wss_client
from core.logging import setup_logging
from core.screener import Screener
from settings import settings

setup_logging()


def close_tasks(tasks: list) -> None:
    for task in tasks:
        task.cancel()


async def main() -> None:
    structlog.contextvars.bind_contextvars(version=settings.VERSION, environment=settings.ENVIRONMENT)

    queue: asyncio.Queue = asyncio.Queue()
    screener = Screener()
    tasks = [
        asyncio.create_task(wss_client.wss_connect(queue)),
        asyncio.create_task(screener.process_trades(queue)),
    ]

    for sig in (signal.SIGTERM, signal.SIGINT):
        asyncio.get_running_loop().add_signal_handler(sig, lambda: close_tasks(tasks))

    await asyncio.gather(*tasks, return_exceptions=True)


if __name__ == "__main__":
    with asyncio.Runner(loop_factory=uvloop.new_event_loop) as runner:
        runner.run(main())
