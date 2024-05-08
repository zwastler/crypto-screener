from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    VERSION: str = "0.0.2"
    ENVIRONMENT: str = "development"

    LOGLEVEL: str = "INFO"
    JSON_LOGS: bool = False
    COLORED_LOGS: bool = not JSON_LOGS
    SAVE_LOG_FILE: bool = False
    LOG_FILE_PATH: str = "logs/test_bot.log"

    REDIS_URI: str = "redis://screener_redis:6379"

    CLEAR_INTERVAL: int = 60
    PRICE_SUBSETS: int = 10
    SIGNAL_TIMEOUT: int = 60 * 2

    BOT_API_KEY: str

    TARGET_IDS: list[int]
    SIGNAL_THRESHOLDS: list[str]


settings = Settings()
