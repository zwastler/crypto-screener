import asyncio
import time
from typing import Any

import structlog
from aiohttp import ClientSession

from adapters.base import BaseExchangeWSS

logger = structlog.get_logger(__name__)


class HtxWSS(BaseExchangeWSS):
    exchange = "htx"
    wss_url = "wss://api.hbdm.com/linear-swap-ws"

    @staticmethod
    def create_ws_message(method: str, args: list[str]) -> dict[str, Any]:
        return {"sub": args[0], "id": str(int(time.time()))}

    @staticmethod
    async def get_symbols_list() -> list[str]:
        async with ClientSession() as session:
            async with session.get(
                "https://api.hbdm.com/v2/linear-swap-ex/market/detail/batch_merged?business_type=swap"
            ) as response:
                data = await response.json()
                return [s["contract_code"] for s in data["ticks"] if s["contract_code"].endswith("USDT")]

    async def after_connect(self) -> None:
        if self.wss_client:
            symbols = await self.get_symbols_list()
            for symbol in symbols:
                await self.send_json(self.create_ws_message("sub", args=[f"market.{symbol}.trade.detail"]))

    async def process_message(self, message: dict[str, Any], queue: asyncio.Queue) -> None:
        await logger.adebug(message, exchange=self.exchange)
        if topic := message.get("subbed"):
            symbol = topic.split(".")[1]
            await logger.adebug(f"subscribed {symbol}", exchange=self.exchange)
            return
        elif message.get("ping"):
            await self.send_json({"pong": message["ping"]})
            return

        elif message.get("ch", "").endswith(".trade.detail"):
            symbol = message["ch"].split(".")[1]
            try:
                payload = {
                    "exchange": self.exchange,
                    "data": [
                        {"s": symbol, "p": msg["price"], "T": msg["ts"]} for msg in message["tick"].get("data", [])
                    ],
                }
            except Exception as err:
                logger.error(f"Failed to process message: {err}", exc_info=True)
            else:
                queue.put_nowait(payload)


htx_wss = HtxWSS()
