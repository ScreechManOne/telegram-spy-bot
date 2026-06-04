import asyncio

from aiogram import Bot, Dispatcher, F
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from config import OWNER_ID, logger
import database

CB_STATS = "admin:stats"
CB_BROADCAST = "admin:broadcast"
CB_CANCEL = "admin:cancel"
CB_CONFIRM = "admin:confirm"
CB_DECLINE = "admin:decline"


class BroadcastState(StatesGroup):
    waiting_message = State()
    confirm = State()


def admin_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📊 Статистика", callback_data=CB_STATS)],
            [InlineKeyboardButton(text="📢 Рассылка", callback_data=CB_BROADCAST)],
        ]
    )


def cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data=CB_CANCEL)]]
    )


def confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Отправить", callback_data=CB_CONFIRM),
                InlineKeyboardButton(text="❌ Отмена", callback_data=CB_DECLINE),
            ]
        ]
    )


def is_owner(user_id: int | None) -> bool:
    return user_id == OWNER_ID


async def show_admin_panel(target: Message) -> None:
    await target.answer(
        "🛠 <b>Админ-панель</b>\n\nВыберите действие:",
        parse_mode=ParseMode.HTML,
        reply_markup=admin_keyboard(),
    )


def setup_admin(dp: Dispatcher) -> None:
    @dp.message(Command("admin"))
    async def cmd_admin(message: Message, state: FSMContext):
        if not is_owner(message.from_user.id if message.from_user else None):
            return
        await state.clear()
        await show_admin_panel(message)

    @dp.callback_query(F.data == CB_STATS)
    async def admin_stats(callback: CallbackQuery):
        if not is_owner(callback.from_user.id if callback.from_user else None):
            await callback.answer("Нет доступа", show_alert=True)
            return

        await callback.answer()
        try:
            stats = await database.get_admin_stats()
            connections = await database.list_connections()
            lines = [
                f"• <code>{uid}</code>" for uid, _ in connections
            ] or ["• нет подключений"]
            text = (
                "📊 <b>Статистика</b>\n\n"
                f"👥 Запускали бота: <b>{stats['total_users']}</b>\n"
                f"🔗 Подключено сейчас: <b>{stats['connected_users']}</b>\n\n"
                "🆔 <b>User ID подключённых:</b>\n"
                + "\n".join(lines)
            )
            await callback.message.edit_text(
                text, parse_mode=ParseMode.HTML, reply_markup=admin_keyboard()
            )
        except Exception as e:
            logger.error(f"Ошибка админ-статистики: {e}")
            await callback.message.answer(f"⚠️ Ошибка: {e}")

    @dp.callback_query(F.data == CB_BROADCAST)
    async def admin_broadcast_start(callback: CallbackQuery, state: FSMContext):
        if not is_owner(callback.from_user.id if callback.from_user else None):
            await callback.answer("Нет доступа", show_alert=True)
            return

        await callback.answer()
        await state.set_state(BroadcastState.waiting_message)
        await callback.message.edit_text(
            "📢 <b>Рассылка</b>\n\n"
            "Отправьте сообщение, которое нужно разослать всем пользователям,\n"
            "которые когда-либо запускали бота.\n\n"
            "<i>Поддерживается текст, фото, видео и другие типы сообщений.</i>",
            parse_mode=ParseMode.HTML,
            reply_markup=cancel_keyboard(),
        )

    @dp.callback_query(F.data.in_({CB_CANCEL, CB_DECLINE}))
    async def admin_cancel(callback: CallbackQuery, state: FSMContext):
        if not is_owner(callback.from_user.id if callback.from_user else None):
            await callback.answer("Нет доступа", show_alert=True)
            return

        await callback.answer()
        await state.clear()
        await callback.message.edit_text(
            "🛠 <b>Админ-панель</b>\n\nВыберите действие:",
            parse_mode=ParseMode.HTML,
            reply_markup=admin_keyboard(),
        )

    @dp.message(BroadcastState.waiting_message)
    async def admin_broadcast_capture(message: Message, state: FSMContext):
        if not is_owner(message.from_user.id if message.from_user else None):
            return

        await state.update_data(
            from_chat_id=message.chat.id,
            message_id=message.message_id,
        )
        await state.set_state(BroadcastState.confirm)

        stats = await database.get_admin_stats()
        await message.answer(
            "📢 <b>Подтвердите рассылку</b>\n\n"
            f"Получателей: <b>{stats['total_users']}</b>\n\n"
            "Сообщение выше будет отправлено всем, кто когда-либо нажимал /start.",
            parse_mode=ParseMode.HTML,
            reply_markup=confirm_keyboard(),
        )

    @dp.callback_query(F.data == CB_CONFIRM, BroadcastState.confirm)
    async def admin_broadcast_send(callback: CallbackQuery, state: FSMContext, bot: Bot):
        if not is_owner(callback.from_user.id if callback.from_user else None):
            await callback.answer("Нет доступа", show_alert=True)
            return

        data = await state.get_data()
        from_chat_id = data.get("from_chat_id")
        message_id = data.get("message_id")
        if not from_chat_id or not message_id:
            await callback.answer("Сообщение не найдено", show_alert=True)
            await state.clear()
            return

        await callback.answer("Рассылка запущена...")
        await callback.message.edit_text(
            "⏳ <b>Рассылка началась...</b>",
            parse_mode=ParseMode.HTML,
        )

        user_ids = await database.get_all_bot_user_ids()
        success = 0
        failed = 0

        for user_id in user_ids:
            try:
                await bot.copy_message(
                    chat_id=user_id,
                    from_chat_id=from_chat_id,
                    message_id=message_id,
                )
                success += 1
            except Exception as e:
                failed += 1
                logger.warning(f"Рассылка: не удалось отправить user_id={user_id}: {e}")
            await asyncio.sleep(0.05)

        await state.clear()
        await callback.message.edit_text(
            "✅ <b>Рассылка завершена</b>\n\n"
            f"📬 Доставлено: <b>{success}</b>\n"
            f"❌ Ошибок: <b>{failed}</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=admin_keyboard(),
        )
