import logging

from aiogram import Router, Bot
from aiogram.types import CallbackQuery

from bot.keyboards.callbacks import AdminApprovalCallback
from bot.services.sheets_service import sheets_service
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
