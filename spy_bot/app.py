from html import escape

from aiogram import Bot, Dispatcher, Router
from aiogram.types import Message, BusinessMessagesDeleted, BusinessConnection
from aiogram.filters import Command, CommandStart
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from . import database
from .admin import setup_admin
from .config import BOT_TOKEN, OWNER_ID, logger
from .media_archive import (
    ArchiveMeta,
    archive_message,
    copy_from_archive,
    is_spoiler_media,
    should_archive,
    verify_archive_access,
    send_photo_with_fallback,
    send_video_with_fallback,
)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
business_router = Router()


def get_message_content(message: Message) -> str:
    text = message.text or message.caption or ""
    media_info = []

    if message.photo:
        media_info.append("[Фото]")
    if message.video:
        media_info.append("[Видео]")
    if message.voice:
        media_info.append("[Голосовое сообщение]")
    if message.audio:
        media_info.append("[Аудио]")
    if message.document:
        media_info.append("[Файл]")
    if message.sticker:
        media_info.append("[Стикер]")

    media_prefix = " ".join(media_info)
    if media_prefix:
        return f"{media_prefix} {text}".strip()
    return text


def get_sender_id(message: Message) -> int | None:
    return message.from_user.id if message.from_user else None


def is_interlocutor_message(message: Message, owner_id: int) -> bool:
    sender_id = get_sender_id(message)
    return sender_id is not None and sender_id != owner_id


def get_sender_name(message: Message) -> str:
    if message.from_user and message.from_user.username:
        return f"@{message.from_user.username}"
    if message.from_user:
        return message.from_user.full_name
    return "Неизвестный"


def get_media_fallback(message: Message) -> tuple[str | None, str | None]:
    if message.voice:
        return message.voice.file_id, "voice"
    if message.video_note:
        return message.video_note.file_id, "video_note"
    return None, None


def blockquote(content: str) -> str:
    return f"<blockquote>{escape(content)}</blockquote>"


def fmt_chat_header(emoji: str, action: str, chat_title: str) -> str:
    return f"{emoji} {action} <i>{escape(chat_title)}</i>"


def fmt_sender_line(sender_name: str) -> str:
    return f"👤 От: {sender_name}"


def build_edit_report(chat_title: str, sender_name: str, old_text: str, new_text: str) -> str:
    return (
        f"{fmt_chat_header('✏️', 'Изменено сообщение в чате:', chat_title)}\n"
        f"{fmt_sender_line(sender_name)}\n\n"
        f"📝 <b>Было:</b>\n{blockquote(old_text)}\n\n"
        f"🆕 <b>Стало:</b>\n{blockquote(new_text)}"
    )


def build_delete_report(chat_title: str, sender_name: str, content: str) -> str:
    return (
        f"{fmt_chat_header('🗑', 'Удалено сообщение в чате:', chat_title)}\n"
        f"{fmt_sender_line(sender_name)}\n\n"
        f"📝 <b>Содержимое:</b>\n{blockquote(content)}"
    )


def build_hidden_media_saved_notice(chat_title: str, sender_name: str) -> str:
    return (
        f"{fmt_chat_header('💾', 'Сохранено одноразовое медиа в чате:', chat_title)}\n"
        f"{fmt_sender_line(sender_name)}"
    )


def build_archive_meta(
    message: Message, user_id: int, chat_title: str, sender_name: str
) -> ArchiveMeta:
    return ArchiveMeta(
        owner_id=user_id,
        chat_title=chat_title,
        sender_name=sender_name,
        connection_id=message.business_connection_id,
        message_id=message.message_id,
    )


async def deliver_secret_media(user_id: int, message: Message, chat_title: str) -> bool:
    """Сохраняет спойлер- или одноразовое (огонёк) медиа в личку пользователя."""
    sender = get_sender_name(message) if message.from_user else "Неизвестный"
    notice = build_hidden_media_saved_notice(chat_title, sender)
    is_hidden = is_spoiler_media(message)

    try:
        if message.photo:
            if is_hidden:
                await send_photo_with_fallback(
                    bot, user_id, message, caption=notice, parse_mode=ParseMode.HTML
                )
                return True
            try:
                msg = await bot.send_photo(user_id, message.photo[-1].file_id)
                await bot.delete_message(user_id, msg.message_id)
                return False
            except Exception as e:
                if "SelfDestructing" not in str(e):
                    raise
                await send_photo_with_fallback(
                    bot, user_id, message, caption=notice, parse_mode=ParseMode.HTML
                )
                return True

        if message.video:
            if is_hidden or getattr(message, "has_protected_content", False):
                await send_video_with_fallback(
                    bot, user_id, message, caption=notice, parse_mode=ParseMode.HTML
                )
                return True
            try:
                msg = await bot.send_video(user_id, message.video.file_id)
            except Exception as e:
                if "SelfDestructing" not in str(e):
                    raise
                await send_video_with_fallback(
                    bot, user_id, message, caption=notice, parse_mode=ParseMode.HTML
                )
                return True
            if getattr(msg, "has_protected_content", False):
                await bot.send_message(user_id, notice, parse_mode=ParseMode.HTML)
                return True
            try:
                duplicate = await bot.copy_message(
                    chat_id=user_id,
                    from_chat_id=user_id,
                    message_id=msg.message_id,
                )
                await bot.delete_message(user_id, msg.message_id)
                await bot.delete_message(user_id, duplicate.message_id)
                return False
            except Exception:
                await bot.send_message(user_id, notice, parse_mode=ParseMode.HTML)
                return True
        if message.voice and is_hidden:
            await bot.send_voice(
                user_id, message.voice.file_id, caption=notice, parse_mode=ParseMode.HTML
            )
            return True
        if message.video_note and is_hidden:
            await bot.send_video_note(user_id, message.video_note.file_id)
            await bot.send_message(user_id, notice, parse_mode=ParseMode.HTML)
            return True
    except Exception as e:
        logger.error(f"Ошибка сохранения секретного медиа: {e}")

    return False


@dp.message(CommandStart())
async def cmd_start(message: Message):
    if message.from_user:
        await database.register_bot_user(
            message.from_user.id,
            message.from_user.username,
            message.from_user.full_name,
        )

    me = await bot.get_me()
    bot_username = f"@{me.username}" if me.username else "username бота из описания"

    text = (
        "👋 <b>Добро пожаловать!</b>\n\n"
        "📋 <b>Возможности:</b>\n"
        f"{blockquote('• уведомляет, если сообщение изменили или удалили\n• присылает, что было в сообщении раньше — текст и медиа')}\n\n"
        "🔧 <b>Как подключить бота</b> <i>(нужен Telegram Premium)</i>\n"
        f"{blockquote(
            '1. Настройки → Telegram для бизнеса\n'
            '2. Чат-боты → Добавить бота\n'
            f'3. Введите {bot_username} и подтвердите\n'
            '4. Включите бота и выберите нужные чаты\n'
            '5. Дождитесь сообщения от бота — значит, всё готово'
        )}\n\n"
        "🔒 <b>Безопасность:</b>\n"
        f"{blockquote(
            'Данные обрабатываются через защищённую инфраструктуру Telegram. '
            'Переписки шифруются на вашем устройстве и в мессенджере. '
            'Бот работает только с вашим аккаунтом после подключения.'
        )}"
    )
    await message.answer(text, parse_mode=ParseMode.HTML)


@dp.message(Command("status"))
async def cmd_status(message: Message):
    if not message.from_user:
        return

    user_id = message.from_user.id
    connection_id = await database.get_connection_for_user(user_id)

    if connection_id:
        text = (
            "✅ <b>Business-подключение активно</b>\n\n"
            f"🔗 ID сессии: <code>{connection_id[:16]}…</code>\n\n"
            "Уведомления об изменениях и удалениях сообщений <b>собеседников</b> "
            "приходят в этот чат с ботом.\n\n"
            "<i>Свои правки и удаления не отслеживаются.</i>"
        )
    else:
        text = (
            "❌ <b>Business не подключён</b>\n\n"
            "Сейчас бот не видит ваши переписки.\n\n"
            "🔧 <b>Что сделать:</b>\n"
            f"{blockquote(
                '1. Настройки → Telegram для бизнеса → Чат-боты\n'
                '2. Добавьте бота и включите переключатель\n'
                '3. Выберите чаты для работы бота\n'
                '4. Должно прийти сообщение «Бот подключён»'
            )}"
        )
    await message.answer(text, parse_mode=ParseMode.HTML)


@dp.business_connection()
async def process_business_connection(connection: BusinessConnection):
    if connection.is_enabled:
        user = connection.user
        await database.register_bot_user(user.id, user.username, user.full_name)
        await database.add_connection(connection.id, user.id)
        await bot.send_message(
            connection.user.id,
            "✅ <b>Бот подключён</b>\n\n"
            "📬 <b>Уведомления:</b>\n"
            f"{blockquote('Изменённые и удалённые сообщения будут приходить прямо сюда.')}\n\n"
            "🔒 <b>Конфиденциальность:</b>\n"
            f"{blockquote('Данные остаются в защищённой среде Telegram — только вы видите свои отчёты.')}",
            parse_mode=ParseMode.HTML,
        )
        logger.info(
            f"Business подключён: user_id={user.id}, connection_id={connection.id}"
        )
    else:
        await database.remove_connection(connection.id)
        await bot.send_message(
            connection.user.id,
            "❌ <b>Бот отключён</b>\n\n"
            "📭 <b>Статус:</b>\n"
            f"{blockquote('Уведомления больше не приходят.')}",
            parse_mode=ParseMode.HTML,
        )


@business_router.business_message()
async def process_new_business_message(message: Message):
    user_id = await database.get_user_by_connection(message.business_connection_id)
    if not user_id:
        logger.warning(
            f"Пропуск business_message: неизвестный connection_id="
            f"{message.business_connection_id}"
        )
        return

    chat_title = message.chat.title or message.chat.full_name or "Личный чат"
    sender_name = get_sender_name(message)

    if is_interlocutor_message(message, user_id):
        try:
            await deliver_secret_media(user_id, message, chat_title)
        except Exception as e:
            logger.error(f"Ошибка автосохранения секретного медиа: {e}")

    if message.reply_to_message and message.from_user and message.from_user.id == user_id:
        replied = message.reply_to_message
        try:
            saved = await deliver_secret_media(user_id, replied, chat_title)
            if saved:
                replied_sender = get_sender_name(replied) if replied.from_user else sender_name
                archive_meta = ArchiveMeta(
                    owner_id=user_id,
                    chat_title=chat_title,
                    sender_name=replied_sender,
                    connection_id=message.business_connection_id,
                    message_id=replied.message_id,
                )
                archive_msg_id = await archive_message(bot, replied, archive_meta)
                if archive_msg_id:
                    existing = await database.get_message(
                        message.business_connection_id, replied.message_id
                    )
                    if existing:
                        await database.update_message_archive(
                            message.business_connection_id,
                            replied.message_id,
                            archive_msg_id,
                        )
        except Exception as e:
            logger.error(f"Ошибка обработки reply-медиа: {e}")

    archive_msg_id = None
    if should_archive(message):
        archive_msg_id = await archive_message(
            bot, message, build_archive_meta(message, user_id, chat_title, sender_name)
        )

    media_file_id, media_type = get_media_fallback(message)
    content = get_message_content(message)
    sender_id = get_sender_id(message)

    await database.save_message(
        connection_id=message.business_connection_id,
        message_id=message.message_id,
        text=content,
        sender_name=sender_name,
        media_file_id=media_file_id,
        media_type=media_type,
        archive_message_id=archive_msg_id,
        sender_id=sender_id,
    )


@business_router.edited_business_message()
async def process_edited_business_message(message: Message):
    user_id = await database.get_user_by_connection(message.business_connection_id)
    if not user_id:
        return

    new_content = get_message_content(message)
    old_msg = await database.get_message(message.business_connection_id, message.message_id)
    sender_name = get_sender_name(message)
    sender_id = get_sender_id(message)
    chat_title = message.chat.title or message.chat.full_name or "Личный чат"

    if old_msg:
        old_text = old_msg["text"]
        if old_text != new_content:
            if is_interlocutor_message(message, user_id):
                report = build_edit_report(chat_title, sender_name, old_text, new_content)
                await bot.send_message(user_id, report, parse_mode=ParseMode.HTML)
            await database.update_message(message.business_connection_id, message.message_id, new_content)
    else:
        await database.save_message(
            connection_id=message.business_connection_id,
            message_id=message.message_id,
            text=new_content,
            sender_name=sender_name,
            sender_id=sender_id,
        )


@business_router.deleted_business_messages()
async def process_deleted_business_messages(deleted: BusinessMessagesDeleted):
    user_id = await database.get_user_by_connection(deleted.business_connection_id)
    if not user_id:
        return

    chat_title = deleted.chat.title or deleted.chat.full_name or "Личный чат"

    for msg_id in deleted.message_ids:
        old_msg = await database.get_message(deleted.business_connection_id, msg_id)
        if not old_msg:
            continue

        old_text = old_msg["text"]
        sender_name = old_msg["sender_name"]
        sender_id = old_msg.get("sender_id")
        media_file_id = old_msg["media_file_id"]
        media_type = old_msg["media_type"]
        archive_message_id = old_msg["archive_message_id"]

        if sender_id == user_id:
            continue

        report = build_delete_report(chat_title, sender_name, old_text)

        if archive_message_id:
            try:
                await copy_from_archive(bot, user_id, archive_message_id, report)
                continue
            except Exception as e:
                logger.error(f"Ошибка копирования из архива (msg {msg_id}): {e}")

        if media_type == "voice" and media_file_id:
            try:
                await bot.send_voice(user_id, media_file_id, caption=report, parse_mode=ParseMode.HTML)
                continue
            except Exception:
                pass
        elif media_type == "video_note" and media_file_id:
            try:
                await bot.send_message(user_id, report, parse_mode=ParseMode.HTML)
                await bot.send_video_note(user_id, media_file_id)
                continue
            except Exception:
                pass

        await bot.send_message(user_id, report, parse_mode=ParseMode.HTML)


async def main():
    logger.info("Инициализация базы данных SQLite...")
    await database.init_db()

    if not await verify_archive_access(bot) and OWNER_ID:
        try:
            await bot.send_message(
                OWNER_ID,
                "⚠️ Бот запущен, но архив-чат недоступен. Проверьте ARCHIVE_CHAT_ID и права бота в группе.",
            )
        except Exception:
            pass

    logger.info("Бот запущен. Ожидание событий для всех подключенных пользователей...")
    setup_admin(dp)
    dp.include_router(business_router)

    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(
        bot,
        allowed_updates=[
            "message",
            "callback_query",
            "business_connection",
            "business_message",
            "edited_business_message",
            "deleted_business_messages",
        ],
    )
