import emoji
import structlog
from aiohttp import ClientSession

from settings import settings

logger = structlog.getLogger(__name__)


def create_tg_message(
    exchange: str,
    symbol: str,
    is_uptrend: bool,
    period: int,
    percent: float,
    price_min: float,
    price_max: float,
    signals: int = 0,
) -> str:
    grc = emoji.emojize(":black_circle:")  # ":green_circle:"
    delim = emoji.emojize(":minus:")
    signal_icon = emoji.emojize(":counterclockwise_arrows_button:")

    price_min = f"{price_min:.9f}".rstrip("0")
    price_min = price_min if not price_min.endswith(".") else price_min + "0"

    price_max = f"{price_max:.9f}".rstrip("0")
    price_max = price_max if not price_max.endswith(".") else price_max + "0"

    if is_uptrend:
        icon = emoji.emojize(":red_triangle_pointed_up:")
        action = "Pump: +"
        txt_prices = f"{price_min} - {price_max}"
    else:
        icon = emoji.emojize(":red_triangle_pointed_down:")
        action = "Dump: -"
        txt_prices = f"{price_max} - {price_min}"
    DEBUG = "" if not settings.DEBUG else f" {emoji.emojize(":robot:")}"

    return (
        f"{grc} {exchange} {delim} {period}м {delim}"
        f"[{symbol}](https://www.coinglass.com/tv/{exchange.capitalize()}_{symbol}){DEBUG}\n"
        f"{icon} {action}{str(abs(percent))}% ({txt_prices})\n{signal_icon} Signals 24h: {signals}"
    )


async def send_tg_message(chat_id: int, message: str) -> None:
    async with ClientSession() as sess:
        url = f"https://api.telegram.org/bot{settings.BOT_API_KEY}/sendMessage"
        logger.debug(f"SEND TELEGRAM: {chat_id=}: {url=}, {message=}")

        res = await sess.post(
            url,
            json={
                "chat_id": chat_id,
                "text": message,
                "parse_mode": "Markdown",
                "disable_web_page_preview": True,
            },
        )
        if not res.status == 200:
            text_error = await res.text()
            logger.error(f"Failed to send message to Telegram: {res.status} error={text_error}")
        resp = await res.json()
        return resp.get("result", {}).get("message_id", None)


async def update_tg_message(chat_id: int, message_id: int, message: str) -> None:
    async with ClientSession() as sess:
        url = f"https://api.telegram.org/bot{settings.BOT_API_KEY}/editMessageText"
        logger.debug(f"SEND TELEGRAM: {chat_id=}: {url=}, {message=}")

        res = await sess.post(
            url,
            json={
                "chat_id": chat_id,
                "message_id": message_id,
                "text": message,
                "parse_mode": "Markdown",
                "disable_web_page_preview": True,
            },
        )
        if not res.status == 200:
            text_error = await res.text()
            logger.error(f"Failed to send message to Telegram: {res.status} error={text_error}")
        resp = await res.json()
        return resp.get("result", {}).get("message_id", None)
