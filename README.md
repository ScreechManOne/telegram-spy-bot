# Telegram Business Spy Bot

Бот для [Telegram Business](https://telegram.org/blog/telegram-business) (нужен **Premium**): уведомления об изменении и удалении сообщений **собеседников**, архив медиа, сохранение спойлер- и одноразового («огонёк») контента.

---

## Возможности

- Уведомления в личку с ботом, если собеседник **отредактировал** или **удалил** сообщение (свои правки не отслеживаются).
- Архив медиа в закрытой группе; при удалении — копия файла из архива.
- Автосохранение медиа под спойлером и одноразовых фото/видео.
- Подключение нескольких Premium-пользователей к одному боту.
- Админ-панель `/admin` для владельца (`OWNER_ID`): статистика, рассылка.

## Требования

- Python 3.10+
- Telegram Premium + Business-бот в настройках аккаунта
- Токен бота от [@BotFather](https://t.me/BotFather)
- Закрытая супергруппа для архива (бот — админ с правом отправки сообщений)

## Быстрый старт

```bash
git clone https://github.com/ScreechManOne/telegram-business-spy-bot.git
cd telegram-business-spy-bot
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # Linux/macOS
pip install -r requirements.txt
copy .env.example .env          # Windows
# cp .env.example .env          # Linux/macOS
```

Заполните `.env`, затем из **корня проекта**:

```bash
python -m spy_bot
```

**Windows:** `scripts\run.bat` (консоль) или `scripts\start_background.vbs` (фон без окна).

### Подключение Business

1. Настройки Telegram → **Telegram для бизнеса** → **Чат-боты**
2. Добавьте бота, включите переключатель, выберите чаты
3. Дождитесь сообщения «Бот подключён» в личке с ботом
4. Проверка: `/status`

## Переменные окружения

| Переменная | Описание |
|------------|----------|
| `BOT_TOKEN` | Токен от BotFather |
| `OWNER_ID` | Ваш числовой Telegram user id (админ, алерты об архиве) |
| `ARCHIVE_CHAT_ID` | ID закрытой группы (`-100...`). Пусто = архивация отключена |

## Безопасность

- Не коммитьте `.env` и `database.db` — они в `.gitignore`.
- При утечке токена отзовите его в BotFather и создайте новый.
- Архив-группа должна быть закрытой; доступ только у вас.
- Используйте бот законно и с согласия участников переписки, где это требуется.

## Команды

| Команда | Кто | Описание |
|---------|-----|----------|
| `/start` | Все | Приветствие и инструкция по подключению |
| `/status` | Все | Статус Business-подключения |
| `/admin` | `OWNER_ID` | Статистика и рассылка |

## Структура проекта

```
├── spy_bot/
│   ├── __main__.py       # Точка входа (python -m spy_bot)
│   ├── app.py            # Business-хендлеры и polling
│   ├── config.py         # Конфиг из .env
│   ├── database.py       # SQLite
│   ├── media_archive.py  # Архив в Telegram-группу
│   ├── admin.py          # Панель администратора
│   └── paths.py          # Пути к корню проекта
├── scripts/              # Запуск на Windows
├── requirements.txt
├── .env.example
└── README.md
```

`database.db` создаётся в корне проекта при первом запуске.

## Disclaimer

Используйте бот только в рамках закона и с уважением к приватности других людей. Автор не несёт ответственности за неправомерное применение.

---

## English

**Telegram Business bot** (Premium required) that notifies you when an **interlocutor** edits or deletes messages, archives media to a private group, and saves spoiler / view-once photo and video when possible.

**Setup:** `pip install -r requirements.txt`, copy `.env.example` to `.env`, set env vars, run `python -m spy_bot` from the project root. Connect via Telegram Business → Chat bots. Commands: `/start`, `/status`, `/admin` (owner only). Never commit secrets. Use responsibly and lawfully.
