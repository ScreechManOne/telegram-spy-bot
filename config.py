import os
import logging
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID", "0"))
ARCHIVE_CHAT_ID = int(os.getenv("ARCHIVE_CHAT_ID", "-1004296785281"))

# Изменили уровень на WARNING, чтобы консоль не засорялась от каждого системного события Telegram
logging.basicConfig(level=logging.WARNING, format="%(asctime)s - %(levelname)s - %(name)s - %(message)s")
logger = logging.getLogger("SpyBot")
# Возвращаем INFO только для нашего бота, чтобы видеть важные уведомления о запуске
logger.setLevel(logging.INFO)

if not BOT_TOKEN or not OWNER_ID:
    logger.error("Токен бота или User ID не найден! Проверьте файл .env")
    exit(1)
