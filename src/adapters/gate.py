import asyncio
import time
from typing import Any

import structlog
from aiohttp import ClientSession

from adapters.base import BaseExchangeWSS

logger = structlog.get_logger(__name__)


class GateWSS(BaseExchangeWSS):
    exchange = "gate"
    wss_url = "wss://fx-ws.gateio.ws/v4/ws/usdt"

    @staticmethod
    def create_ws_message(method: str, args: list[str]) -> dict[str, Any]:
        timestamp = int(time.time() * 1000)
        return {"time": timestamp, "channel": method, "event": "subscribe", "payload": args}

    @staticmethod
    async def get_symbols_list() -> list[str]:
        async with ClientSession() as session:
            async with session.get("https://api.gateio.ws/api/v4/futures/usdt/contracts") as response:
                data = await response.json()
                return [
                    symbol["name"] for symbol in data if not symbol["in_delisting"] and symbol["name"].endswith("USDT")
                ]

    async def after_connect(self) -> None:
        if self.wss_client:
            symbols = await self.get_symbols_list()
            await self.send_json(self.create_ws_message("futures.trades", args=symbols))

    async def process_message(self, message: dict[str, Any], queue: asyncio.Queue) -> None:
        if message.get("event") == "subscribe":
            latency = self.calc_latency(message.get("time", 0))
            await logger.adebug("subscribed", exchange=self.exchange, latency=latency)
            return

        elif message.get("channel") == "futures.trades":
            message = {
                "exchange": self.exchange,
                "data": [
                    {"s": msg["contract"], "p": msg["price"], "T": msg["create_time_ms"]}
                    for msg in message.get("result", [{}])
                ],
            }
            queue.put_nowait(message)

        if latency := self.calc_latency(message.get("time_ms")):
            await logger.adebug(message, exchange=self.exchange, latency=latency)
        else:
            await logger.adebug(message, exchange=self.exchange)


gate_wss = GateWSS()
