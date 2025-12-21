import logging

from aiogram import Router, Bot
from aiogram.types import Message
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext

from bot.states.states import RegistrationStates, AccountFlowStates
from bot.services.whitelist_service import whitelist_service
from bot.keyboards.inline import get_resource_keyboard, get_admin_approval_keyboard
from bot.utils.formatters import format_user_request
from bot.models.user import User
from bot.config import settings

logger = logging.getLogger(__name__)
router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, bot: Bot):
    """Обработка команды /start"""
    user_id = message.from_user.id

    try:
        # Проверяем, есть ли пользователь в whitelist
        user = whitelist_service.get_user(user_id)

        if user and user.is_approved:
            # Пользователь одобрен - показываем главное меню
            await state.clear()
            await state.set_state(AccountFlowStates.selecting_resource)
            await message.answer(
                "📦 <b>Выдача аккаунтов</b>\n\n"
                "Выберите ресурс:",
                reply_markup=get_resource_keyboard(),
                parse_mode="HTML",
            )
        elif user and not user.is_approved:
            # Пользователь ожидает одобрения
            await state.set_state(RegistrationStates.waiting_for_approval)
            await message.answer(
                "⏳ Ваша заявка на рассмотрении. Ожидайте одобрения администратора."
            )
        else:
            # Новый пользователь (или отклонённый) - сбрасываем состояние и запрашиваем stage
            await state.clear()
            await state.set_state(RegistrationStates.waiting_for_stage)
            await message.answer(
                "👋 Добро пожаловать!\n\n"
                "Для доступа к системе введите ваш рабочий никнейм (stage):"
            )
    except Exception as e:
        logger.error(f"Error in start handler: {e}")
        await message.answer(
            "⚠️ Произошла ошибка при проверке доступа. Попробуйте позже."
        )


@router.message(RegistrationStates.waiting_for_stage)
async def process_stage(message: Message, state: FSMContext, bot: Bot):
    """Обработка ввода stage"""
    stage = message.text.strip()

    if not stage or len(stage) < 2:
        await message.answer(
            "❌ Никнейм слишком короткий. Введите корректный stage (минимум 2 символа):"
        )
        return

    user_id = message.from_user.id

    # Проверяем, не существует ли уже пользователь
    existing = whitelist_service.get_user(user_id)
    if existing:
        if existing.is_approved:
            await state.clear()
            await state.set_state(AccountFlowStates.selecting_resource)
            await message.answer(
                "📦 <b>Выдача аккаунтов</b>\n\n"
                "Вы уже зарегистрированы! Выберите ресурс:",
                reply_markup=get_resource_keyboard(),
                parse_mode="HTML",
            )
        else:
            await state.set_state(RegistrationStates.waiting_for_approval)
            await message.answer(
                "⏳ Ваша заявка уже отправлена. Ожидайте одобрения."
            )
        return

    # Сохраняем пользователя в whitelist
    new_user = User(
        telegram_id=user_id,
        stage=stage,
        is_approved=False,
    )
    whitelist_service.add_user(new_user)

    # Отправляем запрос админу
    admin_notified = False
    try:
        admin_message = format_user_request(
            telegram_id=user_id,
            username=message.from_user.username,
            stage=stage,
        )

        await bot.send_message(
            chat_id=settings.ADMIN_ID,
            text=admin_message,
            reply_markup=get_admin_approval_keyboard(user_id),
            parse_mode="HTML",
        )
        admin_notified = True
        logger.info(f"Admin notification sent for user {user_id} (stage: {stage})")
    except Exception as e:
        logger.error(f"Error sending request to admin (ADMIN_ID={settings.ADMIN_ID}): {e}")

    if not admin_notified:
        # Если не удалось уведомить админа - сообщаем пользователю
        await message.answer(
            "⚠️ Не удалось отправить заявку администратору.\n"
            "Пожалуйста, обратитесь к нему напрямую."
        )
        return

    await state.set_state(RegistrationStates.waiting_for_approval)
    await message.answer(
        "✅ Ваша заявка отправлена администратору.\n\n"
        "Ожидайте одобрения. Вам придёт уведомление."
    )


@router.message(RegistrationStates.waiting_for_approval)
async def waiting_approval(message: Message):
    """Сообщение для пользователей, ожидающих одобрения"""
    await message.answer(
        "⏳ Ваша заявка ещё на рассмотрении. Пожалуйста, дождитесь одобрения администратора."
    )
