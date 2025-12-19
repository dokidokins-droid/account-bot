import logging

from aiogram import Router, Bot
from aiogram.types import CallbackQuery, Message
from aiogram.filters import Command

from bot.keyboards.callbacks import AdminApprovalCallback, NumberTodayModeCallback
from bot.services.sheets_service import sheets_service
from bot.services.region_service import region_service
from bot.services.number_service import number_service
from bot.keyboards.number_keyboards import get_number_today_mode_keyboard
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
        try:
            # Одобряем пользователя
            success = await sheets_service.approve_user(user_id)

            if success:
                # Уведомляем пользователя
                await bot.send_message(
                    chat_id=user_id,
                    text="✅ Ваша заявка одобрена!\n\n"
                    "Используйте /start для начала работы.",
                )

                # Обновляем сообщение админа
                await callback.message.edit_text(
                    callback.message.text + "\n\n✅ <b>ОДОБРЕНО</b>",
                    parse_mode="HTML",
                )
                await callback.answer("✅ Пользователь одобрен")
            else:
                await callback.answer("❌ Пользователь не найден", show_alert=True)

        except Exception as e:
            logger.error(f"Error approving user: {e}")
            await callback.answer("❌ Ошибка при одобрении", show_alert=True)

    elif action == "reject":
        try:
            # Удаляем пользователя из whitelist (чтобы мог подать заявку заново)
            await sheets_service.reject_user(user_id)

            # Уведомляем пользователя об отклонении
            await bot.send_message(
                chat_id=user_id,
                text="❌ Ваша заявка отклонена.\n\n"
                "Вы можете подать заявку повторно через /start",
            )

            # Обновляем сообщение админа
            await callback.message.edit_text(
                callback.message.text + "\n\n❌ <b>ОТКЛОНЕНО</b>",
                parse_mode="HTML",
            )
            await callback.answer("❌ Пользователь отклонен")

        except Exception as e:
            logger.error(f"Error rejecting user: {e}")
            await callback.answer("❌ Ошибка при отклонении", show_alert=True)


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
