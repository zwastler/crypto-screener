import time
from functools import wraps
from typing import Any, Callable

import structlog

logger = structlog.get_logger(__name__)


def timeit(func: Callable[..., Any]) -> Callable[..., Any]:
    @wraps(func)
    async def wrapper(*func_args: Any, **func_kwargs: Any) -> Any:
        start_time = time.perf_counter_ns()
        result = await func(*func_args, **func_kwargs)
        logger.debug(f"{func.__name__} delay {time.perf_counter_ns() - start_time} ns")
        return result

    return wrapper
