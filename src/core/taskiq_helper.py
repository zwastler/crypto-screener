from datetime import datetime, timezone
from typing import Any

import structlog
from sentry_sdk.integrations.logging import ignore_logger
from taskiq import PrometheusMiddleware, TaskiqMessage, TaskiqResult
from taskiq.abc.middleware import TaskiqMiddleware
from taskiq.events import TaskiqEvents
from taskiq.schedule_sources import LabelScheduleSource
from taskiq.scheduler.scheduler import TaskiqScheduler
from taskiq.state import TaskiqState
from taskiq_redis import ListQueueBroker

import logging
from core.logging import setup_logging
from core.utils import utcnow
from settings import settings

logger = structlog.getLogger(__name__)
logging.basicConfig(format="%(message)s", level=logging.INFO)  # type: ignore


def add_task_processed_time(
    logger: structlog.BoundLogger, log_method: str, event_dict: dict[str, Any]
) -> dict[str, Any]:
    if "task_start_time" in event_dict:
        event_dict["task_processed_time"] = (
            utcnow() - datetime.fromisoformat(event_dict["task_start_time"])
        ).total_seconds()
    return event_dict


class LoggingMiddleware(TaskiqMiddleware):
    async def post_send(self, message: "TaskiqMessage") -> None:
        structlog.contextvars.bind_contextvars(task_start_time=utcnow().isoformat())
        await logger.adebug("Task enqueued", task_id=message.task_id, task_name=message.task_name)

    async def pre_execute(self, message: "TaskiqMessage") -> "TaskiqMessage":
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            task_id=message.task_id,
            task_name=message.task_name,
            task_start_time=datetime.now(tz=timezone.utc).isoformat(),
        )
        await logger.adebug("Task started")
        return message

    async def post_execute(self, message: "TaskiqMessage", result: "TaskiqResult[Any]") -> None:
        await logger.adebug("Task finished")
        structlog.contextvars.clear_contextvars()

    async def on_error(
        self,
        message: "TaskiqMessage",
        result: "TaskiqResult[Any]",
        exception: BaseException,
    ) -> None:
        await logger.aerror("Task failed", exception=str(exception))


setup_logging()
broker = ListQueueBroker(url=settings.REDIS_URI).with_middlewares(
    LoggingMiddleware(),
    PrometheusMiddleware(server_addr="0.0.0.0", server_port=9000),
)
scheduler = TaskiqScheduler(broker=broker, sources=[LabelScheduleSource(broker)])


@broker.on_event(TaskiqEvents.WORKER_STARTUP)
def sentry_init(_: TaskiqState):
    ignore_logger("taskiq.receiver.receiver")
