import asyncio
import time
from typing import Any

import structlog
from aiohttp import ClientSession, ClientWebSocketResponse, WSMsgType, client_exceptions
from msgspec import json

logger = structlog.get_logger(__name__)
decoder = json.Decoder()
encoder = json.Encoder()


class SingletonMeta(type):
    _instances: dict = {}

    def __call__(cls, *args: list[Any], **kwargs: dict[str, Any]) -> Any:
        if cls not in cls._instances:
            instance = super(SingletonMeta, cls).__call__(*args, **kwargs)
            cls._instances[cls] = instance
        return cls._instances[cls]


class ExchangeWSS(metaclass=SingletonMeta):
    wss_client: ClientWebSocketResponse = None
    queue: asyncio.Queue = None  # type: ignore

    def __init__(self, channel: str, url: str) -> None:
        self.wss_url = url
        self.channel = channel

    def create_ws_message(self, method: str, args: list[str]) -> dict[str, Any]:
        timestamp = int(time.time() * 1000)
        payload = {"op": method, "req_id": f"{method}_{timestamp}".lower(), "args": args}

        match method:
            case _:
                pass
        return payload

    async def get_symbols_list(self) -> list[str]:
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
            messages = [f"publicTrade.{symbol}" for symbol in symbols]
            await self.send_json(self.create_ws_message("subscribe", args=messages))

    async def after_cancel(self) -> None: ...

    async def send_json(self, message: dict[str, Any]) -> None:
        await logger.adebug(message, channel=self.channel)
        if self.wss_client:
            try:
                await self.wss_client.send_str(encoder.encode(message).decode(), compress=False)
            except client_exceptions.ClientError:
                await logger.awarning("Failed to send message", message=message, channel=self.channel, exc_info=True)
        else:
            await logger.awarning("WebSocket connection not established", channel=self.channel)

    async def wss_connect(self, queue: asyncio.Queue) -> None:
        self.queue = queue
        while True:
            try:
                async with ClientSession() as session:
                    await logger.ainfo(f"Connecting to {self.channel} wss channel", channel=self.channel)
                    async with session.ws_connect(self.wss_url, autoclose=False) as wss:
                        self.wss_client = wss
                        await self.after_connect()
                        await self.receive_messages(queue)
            except asyncio.CancelledError:
                logger.info(f"Task was cancelled: {self.__class__.__name__}")
                if self.wss_client:
                    await self.wss_client.close()
                await self.after_cancel()
                break
            except Exception as err:
                await logger.awarning(
                    "WebSocket connection failed, attempting to reconnect...",
                    channel=self.channel,
                    exception=err,
                    exc_info=True,
                )
                await asyncio.sleep(0.25)  # wait before attempting to reconnect

    async def receive_messages(self, queue: asyncio.Queue) -> None:
        while True:
            if not self.wss_client:
                await logger.awarning("WebSocket connection not established", channel=self.channel)
                await asyncio.sleep(0.25)
                continue
            async for msg in self.wss_client:  # type: ignore
                if msg.type == WSMsgType.TEXT:
                    message = decoder.decode(msg.data)
                    try:
                        await self.process_message(message, queue)
                    except Exception:
                        await logger.awarning(
                            "Failed process message", message=message, channel=self.channel, exc_info=True
                        )

                elif msg.type in (WSMsgType.ERROR, WSMsgType.CLOSED):
                    await logger.awarning("WebSocket closed", channel=self.channel)
                    break
                else:
                    await logger.awarning(f"Unknown MsgType: {msg.type}", channel=self.channel)

    async def process_message(self, message: dict[str, Any], queue: asyncio.Queue) -> None:
        message_id, message_ts = self.parse_message_metadata(message)
        message["channel"] = self.channel

        if message.get("topic", "") and message["topic"].startswith("publicTrade"):
            queue.put_nowait(message)

        if latency := self.calc_latency(message_ts):
            await logger.adebug(message, channel=self.channel, latency=latency)
        else:
            await logger.adebug(message, channel=self.channel)

    def parse_message_metadata(self, message: dict[str, Any]) -> tuple[str, int]:
        if "_" in message.get("id", ""):
            message_id, message_ts = message.get("id", "").rsplit("_", 1)
        else:
            message_id, message_ts = "public", message.get("id", 0)
        if message.get("e") and message.get("E"):
            message_ts = int(message["E"])
        return message_id, int(message_ts)

    def calc_latency(self, message_ts: int | str) -> int:
        if isinstance(message_ts, str):
            message_ts = int(message_ts) if message_ts.isdigit() else 0
        elif not isinstance(message_ts, int):
            return 0
        return int(time.time() * 1000) - message_ts


wss_client = ExchangeWSS(
    channel="public",
    url="wss://stream.bybit.com/v5/public/linear",
)
