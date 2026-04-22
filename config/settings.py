import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    BASE_URL: str = ""
    CURRENT_ENV: str = ""
    ADMIN_EMAIL: str = os.getenv("ADMIN_EMAIL", "")
    ADMIN_PASSWORD: str = os.getenv("ADMIN_PASSWORD", "")
    DEFAULT_TIMEOUT: int = int(os.getenv("DEFAULT_TIMEOUT", "30000"))
    HEADLESS: bool = os.getenv("HEADLESS", "true").lower() == "true"
    SLOW_MO: int = int(os.getenv("SLOW_MO", "0"))
    BROWSER: str = os.getenv("BROWSER", "chromium")


settings = Settings()


def has_real_credentials() -> bool:
    return bool(settings.ADMIN_EMAIL and settings.ADMIN_PASSWORD)
