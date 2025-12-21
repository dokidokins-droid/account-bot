import logging

from aiogram import Router
from aiogram.types import CallbackQuery

from bot.keyboards.callbacks import AccountFeedbackCallback, ReplaceAccountCallback
from bot.keyboards.inline import get_replace_keyboard, get_feedback_keyboard
from bot.services.account_service import account_service
from bot.services.whitelist_service import whitelist_service
from bot.models.enums import Resource, Gender, AccountStatus
from bot.utils.formatters import format_account_message, make_compact_after_feedback

logger = logging.getLogger(__name__)
router = Router()


def get_status_display(status: str) -> str:
    """Получить отображаемое имя статуса с эмодзи"""
    try:
        return AccountStatus(status).display_name
    except ValueError:
        return status


@router.callback_query(AccountFeedbackCallback.filter())
async def process_feedback(
    callback: CallbackQuery,
    callback_data: AccountFeedbackCallback,
):
    """Обработка feedback по аккаунту — подтверждает и переносит в таблицу выданных"""
    account_id = callback_data.account_id
    status = callback_data.action
    resource = callback_data.resource
    gender = callback_data.gender
    region = callback_data.region

    try:
        # Подтверждаем аккаунт мгновенно (добавляет в буфер записи)
        success = account_service.confirm_feedback(account_id, status)

        # Получаем отображаемое имя статуса
        status_display = get_status_display(status)

        # Компактный формат сообщения (без строки копирования)
        new_text = make_compact_after_feedback(callback.message.html_text, status_display)

        # Для block и defect показываем кнопку замены
        if status in ("block", "defect"):
            await callback.message.edit_text(
                new_text,
                parse_mode="HTML",
                reply_markup=get_replace_keyboard(resource, gender, region),
            )
        else:
            await callback.message.edit_text(
                new_text,
                parse_mode="HTML",
                reply_markup=None,
            )

        if not success:
            logger.warning(f"Account {account_id} confirmation returned False")

        await callback.answer(status_display)

    except Exception as e:
        logger.error(f"Error processing feedback: {e}")
        await callback.answer("❌ Ошибка", show_alert=True)


@router.callback_query(ReplaceAccountCallback.filter())
async def process_replace(
    callback: CallbackQuery,
    callback_data: ReplaceAccountCallback,
):
    """Обработка замены аккаунта"""
    await callback.answer("⏳ Ищем замену...")

    resource_str = callback_data.resource
    gender_str = callback_data.gender
    region = callback_data.region

    try:
        resource = Resource(resource_str)
        gender = Gender(gender_str)

        # Получаем stage пользователя
        user = whitelist_service.get_user(callback.from_user.id)
        employee_stage = user.stage if user else "unknown"

        # Выдаём один аккаунт на замену (мгновенно из кэша)
        issued = await account_service.issue_accounts(
            resource=resource,
            region=region,
            quantity=1,
            gender=gender,
            employee_stage=employee_stage,
        )

        if not issued:
            await callback.message.edit_reply_markup(reply_markup=None)
            await callback.message.answer("❌ Аккаунты для замены не найдены")
            return

        # Отправляем новый аккаунт
        item = issued[0]
        account = item["account"]
        account_id = item["account_id"]

        message_text = format_account_message(resource, account, region)

        await callback.message.answer(
            f"🔄 <b>Замена аккаунта:</b>\n\n{message_text}",
            reply_markup=get_feedback_keyboard(
                account_id=account_id,
                resource=resource.value,
                gender=gender.value,
                region=region,
            ),
            parse_mode="HTML",
        )

        # Убираем кнопку замены с предыдущего сообщения
        await callback.message.edit_reply_markup(reply_markup=None)

    except Exception as e:
        logger.error(f"Error replacing account: {e}")
        await callback.message.answer("❌ Ошибка при замене аккаунта")
