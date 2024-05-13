from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DEBUG: bool = False
    VERSION: str = "0.1.0"
    ENVIRONMENT: str = "development"

    LOGLEVEL: str = "INFO"
    JSON_LOGS: bool = False
    COLORED_LOGS: bool = not JSON_LOGS
    SAVE_LOG_FILE: bool = False
    LOG_FILE_PATH: str = "logs/test_bot.log"

    REDIS_URI: str = "redis://screener_redis:6379"

    CLEAR_INTERVAL: int = 60
    PRICE_SUBSETS: int = 5
    SIGNAL_TIMEOUT: int = 60 * 2

    BOT_API_KEY: str

    TARGET_IDS: list[int]
    SIGNAL_THRESHOLDS: list[str]

    EXCHANGES: list[str] = []


settings = Settings()
