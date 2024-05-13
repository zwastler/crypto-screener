import time

import structlog

from core.redis import redis, time_series
from core.taskiq_helper import broker
from core.telegram import create_tg_message, send_tg_message, update_tg_message
from settings import settings

logger = structlog.get_logger(__name__)
check_ranges = [
    {"period": int(signal[0]) * 60, "threshold": float(signal[1])}
    for signal in [d.split(",") for d in settings.SIGNAL_THRESHOLDS]
]


def is_uptrend_prices(prices: list[float]) -> bool:
    num_subsets = settings.PRICE_SUBSETS
    subset_size = len(prices) // num_subsets

    subset_means = []
    for i in range(num_subsets):
        subset = prices[i * subset_size : (i + 1) * subset_size]
        subset_mean = sum(subset) / len(subset)
        subset_means.append(subset_mean)

    increasing_count, decreasing_count = 0, 0

    for i in range(1, len(subset_means)):
        if subset_means[i] > subset_means[i - 1]:
            increasing_count += 1
        elif subset_means[i] < subset_means[i - 1]:
            decreasing_count += 1

    return True if increasing_count > decreasing_count else False


@broker.task
async def check_price_change(market_key: str, check_timeout: float = 2.0) -> None:
    if not await redis.exists(market_key):
        return

    check_key = f"{market_key}_check_ts"
    if check_ts := await redis.get(check_key):
        if float(check_ts) > time.time() - check_timeout:
            return

    await redis.set(check_key, time.time())

    max_period = max([check_range["period"] for check_range in check_ranges])
    start_time = (int(time.time()) - max_period) * 1000
    now_ms = int(time.time() * 1000)

    if not (price_data := await time_series.range(market_key, start_time, now_ms)):
        return

    for check_range in check_ranges:
        period = check_range["period"]
        threshold = check_range["threshold"]

        start_time = (int(time.time()) - period) * 1000
        before_24h = int((time.time() - 60 * 60 * 24) * 1000)

        prices = [price[1] for price in price_data if price[0] >= start_time]
        if len(prices) < settings.PRICE_SUBSETS:
            continue

        min_price = min(prices)
        max_price = max(prices)

        try:
            price_change_percent = round(((max_price - min_price) / min_price) * 100, 1)
            is_uptrend = is_uptrend_prices(prices)
        except Exception as err:
            await logger.aerror(f"Failed to check uptrend for {market_key}: {err}", exc_info=True)
            continue

        signal_key = f"{market_key}_{period}_last_percent"

        if signal_percent := await redis.get(signal_key):
            signal_percent = round(float(signal_percent), 1)
            if signal_ttl := await redis.ttl(signal_key):
                signal_ttl = int(signal_ttl)
        else:
            signal_ttl = int(period if period < (60 * 5) else period / 2)

        if signals := await time_series.range(f"{market_key}_signals", before_24h, now_ms):
            signals = len(signals)
        else:
            signals = 0

        if abs(price_change_percent) > threshold:
            signal_args = (market_key, price_change_percent, period, is_uptrend, min_price, max_price, signals)

            if not signal_percent:
                await signal_action.kiq(*signal_args)
                await redis.set(signal_key, price_change_percent, ex=signal_ttl)
                await time_series.add(f"{market_key}_signals", now_ms, 1)

            elif signal_percent and abs(price_change_percent) > signal_percent:
                try:
                    await redis.set(signal_key, price_change_percent, ex=signal_ttl)
                    await signal_action.kiq(*signal_args, update=True)
                except Exception as err:
                    await logger.aerror(f"Failed to update signal key: {err}", exc_info=True)


@broker.task
async def signal_action(
    market_key: str,
    percent: float,
    period: int,
    is_uptrend: bool,
    min_price: float = 0,
    max_price: float = 0,
    signals: int = 0,
    update: bool = False,
) -> None:
    try:
        period_min = int(period / 60)
        signal_ttl = int(period if period_min < 5 else period / 2)
        action = "выросла" if is_uptrend else "упала"
        txt_action = "up" if is_uptrend else "down"

        exchange, symbol = market_key.split("_", 1)

        msg_args = (exchange, symbol, is_uptrend, period_min, percent, min_price, max_price, signals)
        for chat_id in settings.TARGET_IDS:
            msg_key = f"{chat_id}_{exchange}_{symbol}_{period}_{txt_action}"

            if not update:
                await logger.ainfo(
                    f"[{chat_id}] Цена {exchange}:{symbol} {action} на {abs(percent)}% " f"за период {period_min} мин"
                )
                if tg_msg_id := await send_tg_message(chat_id, create_tg_message(*msg_args)):
                    await redis.set(msg_key, tg_msg_id, ex=signal_ttl)
                    logger.debug(f"TG message delivered: {tg_msg_id}")
            else:
                await logger.ainfo(
                    f"[{chat_id}] UPD: цена {exchange}:{symbol} {action} на {abs(percent)}% "
                    f"за период {period_min} мин"
                )
                if tg_msg_id := await redis.get(msg_key):
                    await update_tg_message(chat_id, int(tg_msg_id), create_tg_message(*msg_args))
                    logger.debug(f"TG message updated successfully: {tg_msg_id}")
    except Exception as err:
        await logger.aerror(f"Failed to send signal action: {err}", exc_info=True)
