import asyncio
import signal

import structlog
import uvloop

from adapters.binance import binance_wss
from adapters.bybit import bybit_wss
from adapters.gate import gate_wss
from adapters.okx import okx_wss
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
        asyncio.create_task(bybit_wss.wss_connect(queue)),
        asyncio.create_task(binance_wss.wss_connect(queue)),
        asyncio.create_task(gate_wss.wss_connect(queue)),
        asyncio.create_task(okx_wss.wss_connect(queue)),
        asyncio.create_task(screener.process_trades(queue)),
        asyncio.create_task(screener.process_trades(queue)),
        asyncio.create_task(screener.state_watcher(queue)),
    ]

    for sig in (signal.SIGTERM, signal.SIGINT):
        asyncio.get_running_loop().add_signal_handler(sig, lambda: close_tasks(tasks))

    await asyncio.gather(*tasks, return_exceptions=True)


if __name__ == "__main__":
    with asyncio.Runner(loop_factory=uvloop.new_event_loop) as runner:
        runner.run(main())
