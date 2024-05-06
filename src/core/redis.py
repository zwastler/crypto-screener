from redis.asyncio import from_url

from settings import settings

redis = from_url(settings.REDIS_URI, decode_responses=True)
time_series = redis.ts()
