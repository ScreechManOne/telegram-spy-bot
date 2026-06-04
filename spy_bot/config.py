import logging
import os
import sys

from dotenv import load_dotenv

from .paths import PROJECT_ROOT

load_dotenv(PROJECT_ROOT / ".env")

BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID", "0"))
_raw_archive = os.getenv("ARCHIVE_CHAT_ID", "").strip()
ARCHIVE_CHAT_ID = int(_raw_archive) if _raw_archive else 0

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
)
logger = logging.getLogger("SpyBot")
logger.setLevel(logging.INFO)

if not BOT_TOKEN or not OWNER_ID:
    logger.error("Токен бота или User ID не найден! Проверьте файл .env")
    sys.exit(1)
