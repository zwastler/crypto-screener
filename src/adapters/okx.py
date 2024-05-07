import asyncio
from typing import Any

import structlog
from aiohttp import ClientSession

from adapters.base import BaseExchangeWSS

logger = structlog.get_logger(__name__)


class OkxWSS(BaseExchangeWSS):
    exchange = "okx"
    wss_url = "wss://ws.okx.com:8443/ws/v5/public"

    @staticmethod
    def create_ws_message(method: str, args: list[str]) -> dict[str, Any]:
        return {"op": method, "args": args}

    @staticmethod
    async def get_symbols_list() -> list[str]:
        async with ClientSession() as session:
            async with session.get("https://www.okx.com/api/v5/public/instruments?instType=SWAP") as response:
                data = await response.json()
                return [s["instId"] for s in data["data"] if s["uly"].endswith("USDT")]

    async def after_connect(self) -> None:
        if self.wss_client:
            symbols = await self.get_symbols_list()
            args = [{"channel": "trades", "instId": f"{symbol}"} for symbol in symbols]
            await self.send_json(self.create_ws_message("subscribe", args=args))

    async def process_message(self, message: dict[str, Any], queue: asyncio.Queue) -> None:
        if message.get("event", "") == "subscribe":
            await logger.adebug("subscribed", exchange=self.exchange)
            return

        elif message.get("arg", {}).get("channel") == "trades":
            try:
                message = {
                    "exchange": self.exchange,
                    "data": [{"s": msg["instId"], "p": msg["px"], "T": msg["ts"]} for msg in message["data"]],
                }
            except Exception as err:
                logger.error(f"Failed to process message: {err}", exc_info=True)
            else:
                queue.put_nowait(message)
            finally:
                await logger.adebug(message, exchange=self.exchange)


okx_wss = OkxWSS()
