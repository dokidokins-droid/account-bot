import logging

from aiogram import Router, Bot
from aiogram.types import CallbackQuery, Message
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext

from bot.keyboards.callbacks import (
    AdminApprovalCallback,
    NumberTodayModeCallback,
    BufferClearCategoryCallback,
    BufferClearResourceCallback,
    BufferClearTypeCallback,
    BufferClearConfirmCallback,
    BufferClearBackCallback,
)
from bot.services.whitelist_service import whitelist_service
from bot.services.region_service import region_service
from bot.services.number_service import number_service
from bot.services.account_service import account_cache
from bot.services.email_service import email_cache
from bot.keyboards.number_keyboards import get_number_today_mode_keyboard
from bot.keyboards.inline import (
    get_buffer_clear_category_keyboard,
    get_buffer_clear_accounts_keyboard,
    get_buffer_clear_emails_keyboard,
    get_buffer_clear_type_keyboard,
    get_buffer_clear_confirm_keyboard,
)
from bot.states.states import BufferClearStates
from bot.config import settings

logger = logging.getLogger(__name__)
router = Router()


@router.callback_query(AdminApprovalCallback.filter())
async def process_admin_decision(
    callback: CallbackQuery,
    callback_data: AdminApprovalCallback,
    bot: Bot,
):
    """Обработка решения админа по заявке"""
    # Проверяем, что это действительно админ
    if callback.from_user.id != settings.ADMIN_ID:
        await callback.answer("❌ У вас нет прав для этого действия", show_alert=True)
        return

    user_id = callback_data.user_id
    action = callback_data.action

    if action == "approve":
        # Одобряем пользователя
        success = whitelist_service.approve_user(user_id)

        if success:
            # Уведомляем пользователя
            try:
                await bot.send_message(
                    chat_id=user_id,
                    text="✅ Ваша заявка одобрена!\n\n"
                    "Используйте /start для начала работы.",
                )
            except Exception as e:
                logger.warning(f"Failed to notify user {user_id}: {e}")

            # Обновляем сообщение админа
            await callback.message.edit_text(
                callback.message.text + "\n\n✅ <b>ОДОБРЕНО</b>",
                parse_mode="HTML",
            )
            await callback.answer("✅ Пользователь одобрен")
        else:
            await callback.answer("❌ Пользователь не найден", show_alert=True)

    elif action == "reject":
        # Удаляем пользователя из whitelist (чтобы мог подать заявку заново)
        whitelist_service.reject_user(user_id)

        # Уведомляем пользователя об отклонении
        try:
            await bot.send_message(
                chat_id=user_id,
                text="❌ Ваша заявка отклонена.\n\n"
                "Вы можете подать заявку повторно через /start",
            )
        except Exception as e:
            logger.warning(f"Failed to notify user {user_id}: {e}")

        # Обновляем сообщение админа
        await callback.message.edit_text(
            callback.message.text + "\n\n❌ <b>ОТКЛОНЕНО</b>",
            parse_mode="HTML",
        )
        await callback.answer("❌ Пользователь отклонен")


# === Команды управления регионами (только для админа) ===


@router.message(Command("add_region"))
async def cmd_add_region(message: Message):
    """Добавить новый регион (только для админа)"""
    if message.from_user.id != settings.ADMIN_ID:
        return  # Молча игнорируем, если не админ

    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        regions = ", ".join(region_service.get_regions())
        await message.answer(
            f"<b>Использование:</b> /add_region &lt;номер&gt;\n"
            f"<b>Пример:</b> /add_region 777\n\n"
            f"<b>Текущие регионы:</b>\n{regions}",
            parse_mode="HTML",
        )
        return

    region = args[1].strip()

    if region_service.add_region(region):
        regions = ", ".join(region_service.get_regions())
        await message.answer(
            f"✅ Регион <b>{region}</b> добавлен!\n\n"
            f"<b>Текущие регионы:</b>\n{regions}",
            parse_mode="HTML",
        )
    else:
        await message.answer(
            f"⚠️ Регион <b>{region}</b> уже существует.",
            parse_mode="HTML",
        )


@router.message(Command("remove_region"))
async def cmd_remove_region(message: Message):
    """Удалить регион (только для админа)"""
    if message.from_user.id != settings.ADMIN_ID:
        return  # Молча игнорируем, если не админ

    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        regions = ", ".join(region_service.get_regions())
        await message.answer(
            f"<b>Использование:</b> /remove_region &lt;номер&gt;\n"
            f"<b>Пример:</b> /remove_region 777\n\n"
            f"<b>Текущие регионы:</b>\n{regions}",
            parse_mode="HTML",
        )
        return

    region = args[1].strip()

    if region_service.remove_region(region):
        regions = ", ".join(region_service.get_regions())
        await message.answer(
            f"✅ Регион <b>{region}</b> удалён!\n\n"
            f"<b>Текущие регионы:</b>\n{regions}",
            parse_mode="HTML",
        )
    else:
        await message.answer(
            f"⚠️ Регион <b>{region}</b> не найден.",
            parse_mode="HTML",
        )


@router.message(Command("regions"))
async def cmd_list_regions(message: Message):
    """Показать список регионов (только для админа)"""
    if message.from_user.id != settings.ADMIN_ID:
        return  # Молча игнорируем, если не админ

    regions = region_service.get_regions()
    if regions:
        regions_text = ", ".join(regions)
        await message.answer(
            f"<b>Регионы ({len(regions)}):</b>\n{regions_text}",
            parse_mode="HTML",
        )
    else:
        await message.answer("Список регионов пуст.")


# === Команда управления режимом номеров ===


@router.message(Command("whitelist"))
async def cmd_whitelist(message: Message):
    """Показать всех пользователей в белом списке (только для админа)"""
    if message.from_user.id != settings.ADMIN_ID:
        return  # Молча игнорируем, если не админ

    users = whitelist_service.get_all_users()

    if not users:
        await message.answer("📋 Белый список пуст.")
        return

    # Сортируем: сначала одобренные, потом ожидающие
    approved = [u for u in users if u.is_approved]
    pending = [u for u in users if not u.is_approved]

    lines = [f"<b>📋 Белый список ({len(users)} чел.)</b>\n"]

    if approved:
        lines.append(f"<b>✅ Одобренные ({len(approved)}):</b>")
        for user in approved:
            lines.append(f"  • <code>{user.telegram_id}</code> — {user.stage}")
        lines.append("")

    if pending:
        lines.append(f"<b>⏳ Ожидающие ({len(pending)}):</b>")
        for user in pending:
            lines.append(f"  • <code>{user.telegram_id}</code> — {user.stage}")

    await message.answer("\n".join(lines), parse_mode="HTML")


@router.message(Command("whitelist_remove"))
async def cmd_whitelist_remove(message: Message):
    """Удалить пользователя из белого списка (только для админа)"""
    if message.from_user.id != settings.ADMIN_ID:
        return  # Молча игнорируем, если не админ

    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer(
            "<b>Использование:</b> /whitelist_remove &lt;telegram_id&gt;\n"
            "<b>Пример:</b> /whitelist_remove 123456789",
            parse_mode="HTML",
        )
        return

    try:
        telegram_id = int(args[1].strip())
    except ValueError:
        await message.answer("❌ Некорректный Telegram ID. Должно быть число.")
        return

    user = whitelist_service.get_user(telegram_id)
    if not user:
        await message.answer(
            f"❌ Пользователь <code>{telegram_id}</code> не найден в белом списке.",
            parse_mode="HTML",
        )
        return

    # Удаляем пользователя
    whitelist_service.reject_user(telegram_id)

    await message.answer(
        f"✅ Пользователь удалён из белого списка:\n\n"
        f"ID: <code>{telegram_id}</code>\n"
        f"Stage: {user.stage}\n"
        f"Был одобрен: {'да' if user.is_approved else 'нет'}",
        parse_mode="HTML",
    )


@router.message(Command("numbers_today_mod"))
async def cmd_numbers_today_mod(message: Message):
    """Управление режимом выдачи номеров (только для админа)"""
    if message.from_user.id != settings.ADMIN_ID:
        return  # Молча игнорируем, если не админ

    today_only = number_service.today_only

    if today_only:
        mode_text = "🟢 <b>Включён</b> — выдаются только номера, добавленные сегодня"
    else:
        mode_text = "🔴 <b>Выключён</b> — выдаются все номера"

    await message.answer(
        f"<b>Режим выдачи номеров</b>\n\n"
        f"Текущий статус: {mode_text}",
        reply_markup=get_number_today_mode_keyboard(today_only),
        parse_mode="HTML",
    )


@router.callback_query(NumberTodayModeCallback.filter())
async def toggle_numbers_today_mode(
    callback: CallbackQuery,
    callback_data: NumberTodayModeCallback,
):
    """Переключение режима today_only для номеров"""
    if callback.from_user.id != settings.ADMIN_ID:
        await callback.answer("❌ У вас нет прав для этого действия", show_alert=True)
        return

    action = callback_data.action

    if action == "enable":
        number_service.set_today_only(True)
        mode_text = "🟢 <b>Включён</b> — выдаются только номера, добавленные сегодня"
    else:
        number_service.set_today_only(False)
        mode_text = "🔴 <b>Выключён</b> — выдаются все номера"

    await callback.message.edit_text(
        f"<b>Режим выдачи номеров</b>\n\n"
        f"Текущий статус: {mode_text}",
        reply_markup=get_number_today_mode_keyboard(number_service.today_only),
        parse_mode="HTML",
    )
    await callback.answer("✅ Режим изменён")


# === Очистка буфера ===

RESOURCE_NAMES = {
    "vk": "🔵 ВКонтакте",
    "mamba_male": "🟠 Мамба Мужские",
    "mamba_female": "🟠 Мамба Женские",
    "ok": "🟡 Одноклассники",
    "gmail_any": "🟢 Gmail Обычные",
    "gmail_domain": "🟢 Gmail gmail.com",
    "rambler": "🔵 Рамблер",
    "all_accounts": "📦 Все аккаунты",
    "all_emails": "📧 Все почты",
    "all": "🗑 Всё",
}

CLEAR_TYPE_NAMES = {
    "available": "📥 Готовые к выдаче",
    "pending": "⏳ Ожидающие feedback",
    "write_buffer": "📝 Буфер записи",
    "all": "🗑 Всё",
}

# Ключи для аккаунтов
ACCOUNT_KEYS = {
    "vk": "vk_none",
    "mamba_male": "mamba_male",
    "mamba_female": "mamba_female",
    "ok": "ok_none",
}

# Ключи для почт
EMAIL_KEYS = {
    "gmail_any": "gmail_any",
    "gmail_domain": "gmail_gmail_domain",
    "rambler": "rambler_none",
}


def get_cache_stats_text() -> str:
    """Получить текст со статистикой кэша"""
    account_stats = account_cache.get_stats()
    email_stats = email_cache.get_stats()

    lines = ["<b>📊 Текущее состояние буферов:</b>\n"]

    if account_stats:
        lines.append("<b>Аккаунты:</b>")
        for key, stats in account_stats.items():
            total = stats["available"] + stats["pending"] + stats["write_buffer"]
            if total > 0:
                lines.append(f"  {key}: {stats['available']}📥 {stats['pending']}⏳ {stats['write_buffer']}📝")

    if email_stats:
        lines.append("\n<b>Почты:</b>")
        for key, stats in email_stats.items():
            total = stats["available"] + stats["pending"] + stats["write_buffer"]
            if total > 0:
                lines.append(f"  {key}: {stats['available']}📥 {stats['pending']}⏳ {stats['write_buffer']}📝")

    if len(lines) == 1:
        lines.append("Буферы пусты")

    return "\n".join(lines)


@router.message(Command("buffer_clear"))
async def cmd_buffer_clear(message: Message, state: FSMContext):
    """Очистка буфера (только для админа)"""
    if message.from_user.id != settings.ADMIN_ID:
        return

    await state.clear()
    await state.set_state(BufferClearStates.selecting_category)

    stats_text = get_cache_stats_text()

    await message.answer(
        f"🗑 <b>Очистка буфера</b>\n\n"
        f"{stats_text}\n\n"
        f"Выберите категорию:",
        reply_markup=get_buffer_clear_category_keyboard(),
        parse_mode="HTML",
    )


@router.callback_query(BufferClearCategoryCallback.filter(), BufferClearStates.selecting_category)
async def buffer_clear_category(
    callback: CallbackQuery,
    callback_data: BufferClearCategoryCallback,
    state: FSMContext,
):
    """Выбор категории для очистки"""
    if callback.from_user.id != settings.ADMIN_ID:
        await callback.answer("❌ Нет доступа", show_alert=True)
        return

    await callback.answer()
    category = callback_data.category

    await state.update_data(category=category)

    if category == "accounts":
        await state.set_state(BufferClearStates.selecting_resource)
        await callback.message.edit_text(
            "🗑 <b>Очистка буфера аккаунтов</b>\n\n"
            "Выберите ресурс:",
            reply_markup=get_buffer_clear_accounts_keyboard(),
            parse_mode="HTML",
        )
    elif category == "emails":
        await state.set_state(BufferClearStates.selecting_resource)
        await callback.message.edit_text(
            "🗑 <b>Очистка буфера почт</b>\n\n"
            "Выберите ресурс:",
            reply_markup=get_buffer_clear_emails_keyboard(),
            parse_mode="HTML",
        )
    else:  # all
        await state.update_data(resource="all")
        await state.set_state(BufferClearStates.selecting_type)
        await callback.message.edit_text(
            "🗑 <b>Очистка ВСЕХ буферов</b>\n\n"
            "Что очистить?",
            reply_markup=get_buffer_clear_type_keyboard(),
            parse_mode="HTML",
        )


@router.callback_query(BufferClearResourceCallback.filter(), BufferClearStates.selecting_resource)
async def buffer_clear_resource(
    callback: CallbackQuery,
    callback_data: BufferClearResourceCallback,
    state: FSMContext,
):
    """Выбор ресурса для очистки"""
    if callback.from_user.id != settings.ADMIN_ID:
        await callback.answer("❌ Нет доступа", show_alert=True)
        return

    await callback.answer()
    resource = callback_data.resource

    await state.update_data(resource=resource)
    await state.set_state(BufferClearStates.selecting_type)

    resource_name = RESOURCE_NAMES.get(resource, resource)

    await callback.message.edit_text(
        f"🗑 <b>Очистка буфера</b>\n\n"
        f"Ресурс: {resource_name}\n\n"
        f"Что очистить?",
        reply_markup=get_buffer_clear_type_keyboard(),
        parse_mode="HTML",
    )


@router.callback_query(BufferClearTypeCallback.filter(), BufferClearStates.selecting_type)
async def buffer_clear_type(
    callback: CallbackQuery,
    callback_data: BufferClearTypeCallback,
    state: FSMContext,
):
    """Выбор типа очистки"""
    if callback.from_user.id != settings.ADMIN_ID:
        await callback.answer("❌ Нет доступа", show_alert=True)
        return

    await callback.answer()
    clear_type = callback_data.clear_type

    data = await state.get_data()
    resource = data.get("resource")

    await state.update_data(clear_type=clear_type)
    await state.set_state(BufferClearStates.confirming)

    resource_name = RESOURCE_NAMES.get(resource, resource)
    type_name = CLEAR_TYPE_NAMES.get(clear_type, clear_type)

    await callback.message.edit_text(
        f"🗑 <b>Подтверждение очистки</b>\n\n"
        f"Ресурс: {resource_name}\n"
        f"Очистить: {type_name}\n\n"
        f"⚠️ <b>Это действие необратимо!</b>\n"
        f"Данные будут потеряны.",
        reply_markup=get_buffer_clear_confirm_keyboard(),
        parse_mode="HTML",
    )


@router.callback_query(BufferClearConfirmCallback.filter(), BufferClearStates.confirming)
async def buffer_clear_confirm(
    callback: CallbackQuery,
    callback_data: BufferClearConfirmCallback,
    state: FSMContext,
):
    """Подтверждение или отмена очистки"""
    if callback.from_user.id != settings.ADMIN_ID:
        await callback.answer("❌ Нет доступа", show_alert=True)
        return

    await callback.answer()

    if callback_data.action == "cancel":
        await state.clear()
        await callback.message.edit_text("❌ Очистка отменена.")
        return

    # Выполняем очистку
    data = await state.get_data()
    resource = data.get("resource")
    clear_type = data.get("clear_type")

    total_cleared = {"available": 0, "pending": 0, "write_buffer": 0}

    # Определяем что и как очищать
    if resource == "all":
        # Очистить все аккаунты и почты
        acc_cleared = account_cache.clear_cache(key=None, clear_type=clear_type)
        email_cleared = email_cache.clear_cache(key=None, clear_type=clear_type)
        for k in total_cleared:
            total_cleared[k] = acc_cleared[k] + email_cleared[k]

    elif resource == "all_accounts":
        total_cleared = account_cache.clear_cache(key=None, clear_type=clear_type)

    elif resource == "all_emails":
        total_cleared = email_cache.clear_cache(key=None, clear_type=clear_type)

    elif resource in ACCOUNT_KEYS:
        key = ACCOUNT_KEYS[resource]
        total_cleared = account_cache.clear_cache(key=key, clear_type=clear_type)

    elif resource in EMAIL_KEYS:
        key = EMAIL_KEYS[resource]
        total_cleared = email_cache.clear_cache(key=key, clear_type=clear_type)

    await state.clear()

    resource_name = RESOURCE_NAMES.get(resource, resource)
    type_name = CLEAR_TYPE_NAMES.get(clear_type, clear_type)

    total = sum(total_cleared.values())

    await callback.message.edit_text(
        f"✅ <b>Очистка завершена</b>\n\n"
        f"Ресурс: {resource_name}\n"
        f"Тип: {type_name}\n\n"
        f"<b>Удалено:</b>\n"
        f"  📥 Готовые к выдаче: {total_cleared['available']}\n"
        f"  ⏳ Ожидающие feedback: {total_cleared['pending']}\n"
        f"  📝 Буфер записи: {total_cleared['write_buffer']}\n\n"
        f"<b>Всего: {total}</b>",
        parse_mode="HTML",
    )


@router.callback_query(BufferClearBackCallback.filter())
async def buffer_clear_back(
    callback: CallbackQuery,
    callback_data: BufferClearBackCallback,
    state: FSMContext,
):
    """Кнопка назад в очистке буфера"""
    if callback.from_user.id != settings.ADMIN_ID:
        await callback.answer("❌ Нет доступа", show_alert=True)
        return

    await callback.answer()
    to = callback_data.to

    if to == "category":
        await state.set_state(BufferClearStates.selecting_category)
        stats_text = get_cache_stats_text()
        await callback.message.edit_text(
            f"🗑 <b>Очистка буфера</b>\n\n"
            f"{stats_text}\n\n"
            f"Выберите категорию:",
            reply_markup=get_buffer_clear_category_keyboard(),
            parse_mode="HTML",
        )
    elif to == "resource":
        data = await state.get_data()
        category = data.get("category")
        await state.set_state(BufferClearStates.selecting_resource)

        if category == "accounts":
            await callback.message.edit_text(
                "🗑 <b>Очистка буфера аккаунтов</b>\n\n"
                "Выберите ресурс:",
                reply_markup=get_buffer_clear_accounts_keyboard(),
                parse_mode="HTML",
            )
        else:
            await callback.message.edit_text(
                "🗑 <b>Очистка буфера почт</b>\n\n"
                "Выберите ресурс:",
                reply_markup=get_buffer_clear_emails_keyboard(),
                parse_mode="HTML",
            )
