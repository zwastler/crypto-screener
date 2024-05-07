import asyncio
import time
from typing import Any

import structlog
from aiohttp import ClientSession

from adapters.base import BaseExchangeWSS

logger = structlog.get_logger(__name__)


class BinanceWSS(BaseExchangeWSS):
    exchange = "binance"
    wss_url = "wss://stream.binance.com:9443/ws"

    @staticmethod
    def create_ws_message(method: str, args: list[str]) -> dict[str, Any]:
        timestamp = int(time.time() * 1000)
        message = {
            "id": f"{method.lower()}_{timestamp}".replace(".", "_").lower(),
            "method": method,
            "params": args,
        }
        return message

    @staticmethod
    async def get_symbols_list() -> list[str]:
        async with ClientSession() as session:
            async with session.get("https://api.binance.com/api/v3/exchangeInfo") as response:
                data = await response.json()
                return [
                    symbol["symbol"]
                    for symbol in data["symbols"]
                    if symbol["status"] == "TRADING" and symbol["symbol"].endswith("USDT")
                ]

    async def after_connect(self) -> None:
        if self.wss_client:
            symbols = await self.get_symbols_list()
            args = [f"{symbol.lower()}@trade" for symbol in symbols]
            await self.send_json(self.create_ws_message("SUBSCRIBE", args=args))

    async def process_message(self, message: dict[str, Any], queue: asyncio.Queue) -> None:
        if "subscribe" in message.get("id", ""):
            latency = self.calc_latency(int(message.get("id").split("_")[-1]))
            await logger.adebug("subscribed", exchange=self.exchange, latency=latency)
            return

        elif message.get("e") == "trade":
            message = {
                "exchange": self.exchange,
                "data": [{"s": message["s"], "p": message["p"], "T": message["T"]}],
            }
            queue.put_nowait(message)

        if latency := self.calc_latency(message.get("T")):
            await logger.adebug(message, exchange=self.exchange, latency=latency)
        else:
            await logger.adebug(message, exchange=self.exchange)


binance_wss = BinanceWSS()
