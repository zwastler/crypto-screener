import time
from typing import Any

import structlog
from aiohttp import ClientSession

from adapters.base import BaseExchangeWSS

logger = structlog.get_logger(__name__)


class BybitWSS(BaseExchangeWSS):
    exchange = "bybit"
    wss_url = "wss://stream.bybit.com/v5/public/linear"

    @staticmethod
    def create_ws_message(method: str, args: list[str]) -> dict[str, Any]:
        timestamp = int(time.time() * 1000)
        return {"op": method, "req_id": f"{method}_{timestamp}".lower(), "args": args}

    @staticmethod
    async def get_symbols_list() -> list[str]:
        async with ClientSession() as session:
            async with session.get("https://api.bybit.com/v2/public/symbols") as response:
                data = await response.json()
                return [
                    symbol["name"]
                    for symbol in data["result"]
                    if symbol["status"] == "Trading" and symbol["name"].endswith("USDT")
                ]

    async def after_connect(self) -> None:
        if self.wss_client:
            symbols = await self.get_symbols_list()
            args = [f"publicTrade.{symbol}" for symbol in symbols]
            await self.send_json(self.create_ws_message("subscribe", args=args))


bybit_wss = BybitWSS()
