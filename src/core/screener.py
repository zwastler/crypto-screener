import asyncio
import time
from asyncio import Queue

import structlog

from core.helpers import timeit
from core.redis import redis, time_series
from core.telegram import create_tg_message, send_tg_message, update_tg_message
from settings import settings

logger = structlog.getLogger(__name__)


class Screener:
    symbol_prices: dict
    trades_count: int = 0

    def __init__(self, time_frame: str = "ms"):
        self.time_frame = time_frame
        self.symbol_prices = {}
        self.exchange = "Bybit"
        self.check_ranges = [
            {"period": int(signal[0]) * 60, "threshold": float(signal[1])}
            for signal in [d.split(",") for d in settings.SIGNAL_THRESHOLDS]
        ]

    async def process_trades(self, queue: Queue) -> None:
        symbol: str = ""
        market_key: str = ""
        while True:
            message = await queue.get()
            queue.task_done()
            pass_multiplier = (queue.qsize() // 500) / 10
            exchange = message["exchange"]
            for trade in message["data"]:
                symbol = trade["s"]
                price = float(trade["p"])
                timestamp = int(trade["T"])

                market_key = f"{exchange}_{symbol}"
                self.trades_count += 1

                if not self.symbol_prices.get(market_key, {}):
                    try:
                        await self.create_timeseries(market_key)
                    except Exception as err:
                        logger.error(f"Failed to create timeseries for {market_key}: {err}", exc_info=True)

                if (
                    self.symbol_prices.get(market_key, {}).get("price", 0) == price
                    or self.symbol_prices.get(market_key, {}).get("saved_ts", 0) == timestamp
                    or self.symbol_prices.get(market_key, {}).get("saved_ts", 0)
                    > int((time.time() - pass_multiplier) * 1000)
                ):
                    continue

                try:
                    await time_series.add(market_key, timestamp, price, duplicate_policy="last")
                    self.symbol_prices[market_key]["saved_ts"] = timestamp
                except Exception as err:
                    logger.error(f"Failed to write {market_key} price to Redis: {err}", exc_info=True)

                self.symbol_prices[market_key].update({"price": price, "timestamp": timestamp})

            if not market_key:
                continue

            try:
                await self.check_price_change(market_key, pass_multiplier)
                await self.delete_old_timeseries(market_key)
            except Exception as err:
                logger.error(f"Failed to check {symbol}: {err}", exc_info=True)

    async def create_timeseries(self, symbol: str) -> None:
        try:
            self.symbol_prices[symbol] = {}
            if not await redis.exists(symbol):
                max_retention = max([check_range["period"] for check_range in self.check_ranges]) * 1000
                await time_series.create(symbol, retention_msecs=max_retention, duplicate_policy="last")
        except Exception as err:
            if "already exists" not in str(err):
                logger.error(err)

        max_signal_retention = int((time.time() - 60 * 60 * 24) * 1000)
        try:
            if not await redis.exists(f"{symbol}_signals"):
                await time_series.create(
                    f"{symbol}_signals", retention_msecs=max_signal_retention, duplicate_policy="last"
                )
        except Exception as err:
            if "already exists" not in str(err):
                logger.error(err)

    @timeit
    async def delete_old_timeseries(self, market_key: str) -> None:
        if (
            self.symbol_prices[market_key].get("clear_ts")
            and self.symbol_prices[market_key].get("clear_ts", 0) > time.time() - settings.CLEAR_INTERVAL
        ):
            return

        self.symbol_prices[market_key]["clear_ts"] = int(time.time())

        max_period = max([check_range["period"] for check_range in self.check_ranges])
        start_period = (int(time.time()) - 60 * 60 * 24) * 1000
        await time_series.delete(market_key, start_period, (int(time.time()) - max_period) * 1000)
        start_signals_ts = int((time.time() - (60 * 60 * 24 * 7)) * 1000)
        await time_series.delete(f"{market_key}_signals", start_signals_ts, start_period)

    @staticmethod
    async def is_uptrend(prices: list[float]) -> bool:
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

    @timeit
    async def check_price_change(self, market_key: str, qsize_multiplier: int = 2) -> None:
        if not market_key or not self.symbol_prices.get(market_key):
            return

        if (
            self.symbol_prices[market_key].get("check_ts")
            and self.symbol_prices[market_key].get("check_ts", 0) > time.time() - qsize_multiplier
        ):
            return
        symbol_data = self.symbol_prices[market_key]
        symbol_data["check_ts"] = time.time()

        for check_range in self.check_ranges:
            period = check_range["period"]
            threshold = check_range["threshold"]

            start_time = (int(time.time()) - period) * 1000
            end_time = int(time.time() * 1000)
            before_24h = int((time.time() - 60 * 60 * 24) * 1000)
            price_data = await time_series.range(market_key, start_time, end_time)

            if not price_data or len(price_data) < settings.PRICE_SUBSETS:
                continue

            prices = [price[1] for price in price_data]

            min_price = min(prices)
            max_price = max(prices)

            price_change_percent = round(((max_price - min_price) / min_price) * 100, 1)
            is_uptrend = await self.is_uptrend(prices)

            signal_key = f"{market_key}_{period}_last_percent"

            if signal_percent := await redis.get(signal_key):
                signal_percent = float(signal_percent)
                if signal_ttl := await redis.ttl(signal_key):
                    signal_ttl = int(signal_ttl)
            else:
                signal_ttl = period if period < 60 * 5 else period / 2

            if signals := await time_series.range(f"{market_key}_signals", before_24h, end_time):
                signals = len(signals)
            else:
                signals = 0

            if abs(price_change_percent) > threshold:
                signal_args = (market_key, price_change_percent, period, is_uptrend, min_price, max_price, signals)

                if not signal_percent:
                    await self.signal_action(*signal_args)
                    await redis.set(signal_key, price_change_percent, ex=settings.SIGNAL_TIMEOUT)
                    await time_series.add(f"{market_key}_signals", end_time, 1)

                elif signal_percent and abs(price_change_percent) > signal_percent:
                    try:
                        await redis.set(signal_key, price_change_percent, ex=signal_ttl)
                        await self.signal_action(*signal_args, update=True)
                    except Exception as err:
                        logger.error(f"Failed to update signal key: {err}", exc_info=True)

    @staticmethod
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
        period_min = int(period / 60)
        action = "выросла" if is_uptrend else "упала"
        txt_action = "up" if is_uptrend else "down"

        exchange, symbol = market_key.split("_", 1)

        msg_args = (exchange, symbol, is_uptrend, period_min, percent, min_price, max_price, signals)
        for chat_id in settings.TARGET_IDS:
            msg_key = f"{chat_id}_{exchange}_{symbol}_{period}_{txt_action}"

            if not update:
                logger.info(f"Цена {exchange}:{symbol} {action} на {abs(percent)}% за период {period_min} мин")
                if tg_msg_id := await send_tg_message(chat_id, create_tg_message(*msg_args)):
                    await redis.set(msg_key, tg_msg_id, ex=60 * 2)
                    logger.debug(f"TG message delivered: {tg_msg_id}")
            else:
                logger.info(f"UPD: цена {exchange}:{symbol} {action} на {abs(percent)}% за период {period_min} мин")
                if tg_msg_id := await redis.get(msg_key):
                    await update_tg_message(chat_id, int(tg_msg_id), create_tg_message(*msg_args))
                    logger.debug(f"TG message updated successfully: {tg_msg_id}")

    async def state_watcher(self, queue: Queue, timeout=10):
        while True:
            qsize = queue.qsize()
            logger.info(f"Queue size: {qsize}, trades processed: {self.trades_count/timeout}/sec"
                        f", markets: {len(self.symbol_prices)}")
            self.trades_count = 0
            await asyncio.sleep(timeout)
