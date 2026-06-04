from dataclasses import dataclass

from aiogram import Bot
from aiogram.enums import ParseMode
from aiogram.types import BufferedInputFile, Message

from config import ARCHIVE_CHAT_ID, logger


@dataclass
class ArchiveMeta:
    owner_id: int
    chat_title: str
    sender_name: str
    connection_id: str
    message_id: int


def is_spoiler_media(message: Message) -> bool:
    return bool(getattr(message, "has_media_spoiler", False))


def should_archive(message: Message) -> bool:
    if message.sticker or message.animation:
        return False
    return bool(
        message.photo
        or message.video
        or message.voice
        or message.video_note
        or message.audio
        or message.document
    )


def build_archive_caption(meta: ArchiveMeta) -> str:
    return (
        f"owner:{meta.owner_id} | {meta.chat_title}\n"
        f"from: {meta.sender_name}\n"
        f"conn:{meta.connection_id} msg:{meta.message_id}"
    )


def _is_self_destruct_error(exc: Exception) -> bool:
    return "SelfDestructing" in str(exc)


def _video_filename(message: Message) -> str:
    mime = message.video.mime_type if message.video else None
    if mime and "/" in mime:
        ext = mime.split("/", 1)[-1]
        if ext in ("mp4", "quicktime", "webm", "x-m4v"):
            return f"video.{ext.replace('quicktime', 'mov').replace('x-m4v', 'm4v')}"
    return "video.mp4"


async def _download_file(bot: Bot, file_id: str, filename: str) -> BufferedInputFile:
    file_info = await bot.get_file(file_id)
    downloaded = await bot.download_file(file_info.file_path)
    return BufferedInputFile(downloaded.read(), filename=filename)


async def send_photo_with_fallback(
    bot: Bot,
    chat_id: int,
    message: Message,
    caption: str | None = None,
    parse_mode: ParseMode | None = None,
    force_spoiler: bool | None = None,
) -> Message:
    photo = message.photo[-1]
    is_hidden = force_spoiler if force_spoiler is not None else is_spoiler_media(message)
    try:
        return await bot.send_photo(
            chat_id,
            photo.file_id,
            caption=caption,
            parse_mode=parse_mode,
            has_spoiler=is_hidden,
        )
    except Exception as e:
        if not _is_self_destruct_error(e):
            raise
        input_photo = await _download_file(bot, photo.file_id, "photo.jpg")
        return await bot.send_photo(
            chat_id,
            input_photo,
            caption=caption,
            parse_mode=parse_mode,
        )


async def send_video_with_fallback(
    bot: Bot,
    chat_id: int,
    message: Message,
    caption: str | None = None,
    parse_mode: ParseMode | None = None,
    force_spoiler: bool | None = None,
) -> Message:
    video = message.video
    is_hidden = force_spoiler if force_spoiler is not None else is_spoiler_media(message)
    try:
        return await bot.send_video(
            chat_id,
            video.file_id,
            caption=caption,
            parse_mode=parse_mode,
            has_spoiler=is_hidden,
            duration=video.duration,
            width=video.width,
            height=video.height,
        )
    except Exception as e:
        if not _is_self_destruct_error(e):
            raise
        input_video = await _download_file(bot, video.file_id, _video_filename(message))
        return await bot.send_video(
            chat_id,
            input_video,
            caption=caption,
            parse_mode=parse_mode,
            duration=video.duration,
            width=video.width,
            height=video.height,
        )


async def archive_message(bot: Bot, message: Message, meta: ArchiveMeta) -> int | None:
    if not ARCHIVE_CHAT_ID or not should_archive(message):
        return None

    caption = build_archive_caption(meta)
    chat_id = ARCHIVE_CHAT_ID

    try:
        if message.photo:
            sent = await send_photo_with_fallback(bot, chat_id, message, caption)
        elif message.video:
            sent = await send_video_with_fallback(bot, chat_id, message, caption)
        elif message.voice:
            sent = await bot.send_voice(chat_id, message.voice.file_id, caption=caption)
        elif message.video_note:
            sent = await bot.send_video_note(chat_id, message.video_note.file_id)
            await bot.send_message(chat_id, caption)
        elif message.audio:
            sent = await bot.send_audio(chat_id, message.audio.file_id, caption=caption)
        elif message.document:
            sent = await bot.send_document(chat_id, message.document.file_id, caption=caption)
        else:
            return None
        return sent.message_id
    except Exception as e:
        logger.error(f"Ошибка архивации медиа (msg {meta.message_id}): {e}")
        return None


async def copy_from_archive(bot: Bot, user_id: int, archive_msg_id: int, caption: str | None = None) -> None:
    if not ARCHIVE_CHAT_ID:
        raise RuntimeError("ARCHIVE_CHAT_ID не задан")

    if caption:
        try:
            await bot.copy_message(
                chat_id=user_id,
                from_chat_id=ARCHIVE_CHAT_ID,
                message_id=archive_msg_id,
                caption=caption,
                parse_mode=ParseMode.HTML,
            )
            return
        except Exception:
            await bot.send_message(user_id, caption, parse_mode=ParseMode.HTML)

    await bot.copy_message(
        chat_id=user_id,
        from_chat_id=ARCHIVE_CHAT_ID,
        message_id=archive_msg_id,
    )


async def verify_archive_access(bot: Bot) -> bool:
    if not ARCHIVE_CHAT_ID:
        logger.warning("ARCHIVE_CHAT_ID не задан — архивация отключена")
        return True

    try:
        await bot.get_chat(ARCHIVE_CHAT_ID)
        logger.info(f"Архив-чат доступен: {ARCHIVE_CHAT_ID}")
        return True
    except Exception as e:
        logger.error(
            f"Нет доступа к архив-чату {ARCHIVE_CHAT_ID}: {e}. "
            "Проверьте ID группы и права бота на отправку сообщений."
        )
        return False
