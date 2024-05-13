from datetime import datetime, timezone
from typing import Any

from msgspec import json


def utcnow() -> datetime:
    # we can't use timezone.now() as we don't want to use the default timezone
    return datetime.utcnow().replace(tzinfo=timezone.utc)


def dumps(obj: Any, **kwargs: dict[str, Any]) -> str:
    return json.decode("utf-8")
