import asyncio
import time
from asyncio import Queue

import structlog

from core.redis import redis, time_series
from settings import settings
from worker import check_price_change

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

    async def process_trades(self, trades_queue: Queue) -> None:
        while True:
            market_key: str = ""
            message = await trades_queue.get()
            trades_queue.task_done()
            pass_multiplier = round((trades_queue.qsize() // 500) / 10, 1)
            exchange = message["exchange"]
            for trade in message["data"]:
                symbol = trade["s"]
                price = float(trade["p"])
                timestamp = int(trade["T"])

                market_key = f"{exchange}_{symbol}"
                self.trades_count += 1

                if not (market_data := self.symbol_prices.get(market_key, {})):
                    try:
                        await self.create_timeseries(market_key)
                        market_data = self.symbol_prices[market_key]
                    except Exception as err:
                        await logger.aerror(f"Failed to create timeseries for {market_key}: {err}", exc_info=True)

                if (
                    market_data.get("price", 0) == price
                    or market_data.get("saved_ts", 0) == timestamp
                    or market_data.get("saved_ts", 0) > int((time.time() - pass_multiplier) * 1000)
                ):
                    continue

                try:
                    await time_series.add(market_key, timestamp, price, duplicate_policy="last")
                    market_data["saved_ts"] = timestamp
                except Exception as err:
                    await logger.aerror(f"Failed to write {market_key} price to Redis: {err}", exc_info=True)

                market_data["price"] = price
                market_data["timestamp"] = timestamp

            if not market_key:
                continue

            await check_price_change.kiq(market_key)

    async def create_timeseries(self, symbol: str) -> None:
        try:
            self.symbol_prices[symbol] = {}
            if not await redis.exists(symbol):
                max_retention = max([check_range["period"] for check_range in self.check_ranges]) * 1000
                await time_series.create(symbol, retention_msecs=max_retention, duplicate_policy="last")
        except Exception as err:
            if "already exists" not in str(err):
                await logger.aerror(err)

        max_signal_retention = int((60 * 60 * 24) * 1000)
        try:
            if not await redis.exists(f"{symbol}_signals"):
                await time_series.create(
                    f"{symbol}_signals", retention_msecs=max_signal_retention, duplicate_policy="last"
                )
        except Exception as err:
            if "already exists" not in str(err):
                await logger.aerror(err)

    async def state_watcher(self, trades_queue: Queue, timeout=10):
        while True:
            tqsize = trades_queue.qsize()
            exch = ",".join(settings.EXCHANGES)
            await logger.ainfo(
                f"[{exch}] queue: {tqsize}, trades processed: {self.trades_count / timeout}/sec"
                f", markets: {len(self.symbol_prices)}"
            )
            self.trades_count = 0
            await asyncio.sleep(timeout)
