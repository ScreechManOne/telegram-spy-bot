import asyncio

from aiogram import Bot, Dispatcher, Router
from aiogram.types import BufferedInputFile, Message, BusinessMessagesDeleted, BusinessConnection
from aiogram.filters import CommandStart
from aiogram.enums import ParseMode

from config import BOT_TOKEN, OWNER_ID, logger
import database
from media_archive import (
    ArchiveMeta,
    archive_message,
    copy_from_archive,
    should_archive,
    verify_archive_access,
)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
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


def build_hidden_media_saved_notice(replied: Message) -> str:
    sender = get_sender_name(replied) if replied.from_user else "Неизвестный"
    return f"Сохранено одноразовое медиа из чата\n-{sender}"


async def send_replied_media_to_user(user_id: int, replied: Message) -> bool:
    is_hidden = getattr(replied, "has_media_spoiler", False)
    notice = build_hidden_media_saved_notice(replied)

    if replied.photo:
        try:
            msg = await bot.send_photo(
                user_id,
                replied.photo[-1].file_id,
                caption=notice if is_hidden else None,
                has_spoiler=is_hidden,
            )
            if not is_hidden:
                await bot.delete_message(user_id, msg.message_id)
                return False
            return True
        except Exception as e:
            if "SelfDestructingPhoto" in str(e):
                file_info = await bot.get_file(replied.photo[-1].file_id)
                downloaded = await bot.download_file(file_info.file_path)
                input_photo = BufferedInputFile(downloaded.read(), filename="photo.jpg")
                await bot.send_photo(user_id, input_photo, caption=notice)
                return True
            raise
    elif replied.video and is_hidden:
        await bot.send_video(user_id, replied.video.file_id, caption=notice, has_spoiler=True)
        return True
    elif replied.voice and is_hidden:
        await bot.send_voice(user_id, replied.voice.file_id, caption=notice)
        return True
    elif replied.video_note and is_hidden:
        await bot.send_video_note(user_id, replied.video_note.file_id)
        await bot.send_message(user_id, notice)
        return True

    return False


@dp.message(CommandStart())
async def cmd_start(message: Message):
    me = await bot.get_me()
    bot_username = f"@{me.username}" if me.username else "username бота из описания"

    text = (
        "👋 <b>Добро пожаловать!</b>\n\n"
        "Этот бот помогает не терять важное из переписок:\n"
        "• уведомляет, если сообщение изменили или удалили;\n"
        "• присылает, что было в сообщении раньше — текст и медиа.\n\n"
        "<b>Как подключить бота к аккаунту</b>\n"
        "<i>(нужен Telegram Premium)</i>\n\n"
        "1. Откройте <b>Настройки</b> Telegram\n"
        "2. Перейдите в <b>Telegram для бизнеса</b>\n"
        "3. Выберите <b>Чат-боты</b> → <b>Добавить бота</b>\n"
        f"4. Введите {bot_username} и подтвердите добавление\n"
        "5. Включите бота переключателем и при необходимости укажите, "
        "в каких чатах он может работать\n"
        "6. После подключения вы получите сообщение от бота в этот чат — "
        "значит всё готово\n\n"
        "🔒 Данные обрабатываются через защищённую инфраструктуру Telegram.\n"
        "Переписки шифруются на вашем устройстве и в мессенджере — "
        "посторонние не имеют к ним доступа.\n"
        "Бот работает только с вашим аккаунтом после подключения."
    )
    await message.answer(text, parse_mode=ParseMode.HTML)


@dp.business_connection()
async def process_business_connection(connection: BusinessConnection):
    if connection.is_enabled:
        await database.add_connection(connection.id, connection.user.id)
        await bot.send_message(
            connection.user.id,
            "✅ <b>Бот подключён и готов работать.</b>\n\n"
            "Вы будете получать уведомления об изменённых и удалённых сообщениях прямо сюда.\n"
            "🔒 Данные остаются в защищённой среде Telegram — только вы видите свои отчёты.",
            parse_mode=ParseMode.HTML,
        )
        logger.info(f"Новое подключение Business API от пользователя ID: {connection.user.id}")
    else:
        await database.remove_connection(connection.id)
        await bot.send_message(
            connection.user.id,
            "Бот отключён от вашего аккаунта. Уведомления больше не приходят.",
            parse_mode=ParseMode.HTML,
        )


@business_router.business_message()
async def process_new_business_message(message: Message):
    user_id = await database.get_user_by_connection(message.business_connection_id)
    if not user_id:
        return

    chat_title = message.chat.title or message.chat.full_name or "Личный чат"
    sender_name = get_sender_name(message)

    if message.reply_to_message and message.from_user and message.from_user.id == user_id:
        replied = message.reply_to_message
        try:
            await send_replied_media_to_user(user_id, replied)

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

    await database.save_message(
        connection_id=message.business_connection_id,
        message_id=message.message_id,
        text=content,
        sender_name=sender_name,
        media_file_id=media_file_id,
        media_type=media_type,
        archive_message_id=archive_msg_id,
    )


@business_router.edited_business_message()
async def process_edited_business_message(message: Message):
    user_id = await database.get_user_by_connection(message.business_connection_id)
    if not user_id:
        return

    new_content = get_message_content(message)
    old_msg = await database.get_message(message.business_connection_id, message.message_id)
    sender_name = get_sender_name(message)
    chat_title = message.chat.title or message.chat.full_name or "Личный чат"

    if old_msg:
        old_text = old_msg["text"]
        if old_text != new_content:
            report = (
                f"✏️ <b>Изменено сообщение</b> в чате: <i>{chat_title}</i>\n"
                f"👤 От: <b>{sender_name}</b>\n\n"
                f"📝 <b>Было:</b>\n<blockquote>{old_text}</blockquote>\n\n"
                f"🆕 <b>Стало:</b>\n<blockquote>{new_content}</blockquote>"
            )
            await bot.send_message(user_id, report, parse_mode=ParseMode.HTML)
            await database.update_message(message.business_connection_id, message.message_id, new_content)
    else:
        await database.save_message(
            connection_id=message.business_connection_id,
            message_id=message.message_id,
            text=new_content,
            sender_name=sender_name,
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
        media_file_id = old_msg["media_file_id"]
        media_type = old_msg["media_type"]
        archive_message_id = old_msg["archive_message_id"]

        report = (
            f"🗑 <b>Удалено сообщение</b> в чате: <i>{chat_title}</i>\n"
            f"👤 От: <b>{sender_name}</b>\n\n"
            f"📝 <b>Удаленный текст/медиа:</b>\n<blockquote>{old_text}</blockquote>"
        )

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
    dp.include_router(business_router)

    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
