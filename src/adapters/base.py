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

    def __call__(cls, *args: Any, **kwargs: Any) -> Any:
        if cls not in cls._instances:
            instance = super().__call__(*args, **kwargs)
            cls._instances[cls] = instance
        return cls._instances[cls]


class BaseExchangeWSS(metaclass=SingletonMeta):
    exchange: str = "base"
    wss_url: str
    wss_client: ClientWebSocketResponse = None
    queue: asyncio.Queue = None  # type: ignore

    def __init__(self) -> None:
        self.loop = asyncio.get_event_loop()

    async def after_connect(self) -> None: ...

    async def after_cancel(self) -> None: ...

    async def send_json(self, message: dict[str, Any]) -> None:
        await logger.adebug(message, exchange=self.exchange)
        if self.wss_client:
            try:
                await self.wss_client.send_str(encoder.encode(message).decode(), compress=False)
            except client_exceptions.ClientError:
                await logger.awarning("Failed to send message", message=message, exchange=self.exchange, exc_info=True)
        else:
            await logger.awarning("WebSocket connection not established", exchange=self.exchange)

    async def wss_connect(self, queue: asyncio.Queue) -> None:
        if not self.wss_url:
            await logger.awarning("WSS URL not set", exchange=self.exchange)
            raise NotImplementedError("WSS URL not set")
        self.queue = queue
        while True:
            try:
                async with ClientSession() as session:
                    await logger.ainfo(f"Connecting to {self.exchange} wss channel", exchange=self.exchange)
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
                    exchange=self.exchange,
                    exception=err,
                    exc_info=True,
                )
                await asyncio.sleep(0.25)  # wait before attempting to reconnect

    async def receive_messages(self, queue: asyncio.Queue) -> None:
        while True:
            if not self.wss_client:
                await logger.awarning("WebSocket connection not established", exchange=self.exchange)
                await asyncio.sleep(0.25)
                continue
            async for msg in self.wss_client:  # type: ignore
                if msg.type == WSMsgType.TEXT:
                    message = decoder.decode(msg.data)
                    try:
                        await self.process_message(message, queue)
                    except Exception:
                        await logger.awarning(
                            "Failed process message", message=message, exchange=self.exchange, exc_info=True
                        )

                elif msg.type in (WSMsgType.ERROR, WSMsgType.CLOSED):
                    await logger.awarning("WebSocket closed", exchange=self.exchange)
                    break
                else:
                    await logger.awarning(f"Unknown MsgType: {msg.type}", exchange=self.exchange)

    async def process_message(self, message: dict[str, Any], queue: asyncio.Queue) -> None:
        message_id, message_ts = self.parse_message_metadata(message)
        message["exchange"] = self.exchange

        if message.get("topic", "") and message["topic"].startswith("publicTrade"):
            queue.put_nowait(message)

        if latency := self.calc_latency(message_ts):
            await logger.adebug(message, exchange=self.exchange, latency=latency)
        else:
            await logger.adebug(message, exchange=self.exchange)

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
