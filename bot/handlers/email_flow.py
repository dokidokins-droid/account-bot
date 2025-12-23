"""Хэндлеры для работы с почтами (Gmail, Рамблер)"""
import logging

from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext

from bot.states.states import EmailFlowStates, AccountFlowStates
from bot.keyboards.callbacks import (
    EmailMenuCallback,
    EmailResourceCallback,
    EmailTypeCallback,
    EmailRegionCallback,
    EmailSearchRegionCallback,
    EmailQuantityCallback,
    EmailBackCallback,
    EmailFeedbackCallback,
    EmailReplaceCallback,
)
from bot.keyboards.email_keyboards import (
    get_email_menu_keyboard,
    get_email_type_keyboard,
    get_email_region_keyboard,
    get_email_region_keyboard_rambler,
    get_email_back_to_region_keyboard,
    get_email_quantity_keyboard,
    get_email_feedback_keyboard,
    get_email_replace_keyboard,
)
from bot.keyboards.inline import get_resource_keyboard
from bot.models.enums import EmailResource, Gender, AccountStatus
from bot.services.email_service import email_service
from bot.services.region_service import region_service
from bot.services.whitelist_service import whitelist_service
from bot.utils.formatters import format_email_message, make_compact_after_feedback


def get_status_display(status: str) -> str:
    """Получить отображаемое имя статуса с эмодзи"""
    try:
        return AccountStatus(status).display_name
    except ValueError:
        return status

logger = logging.getLogger(__name__)
router = Router()


# === Открытие меню почт ===

@router.callback_query(EmailMenuCallback.filter(F.action == "open"))
async def open_email_menu(callback: CallbackQuery, state: FSMContext):
    """Открытие меню выбора почтового ресурса"""
    await callback.answer()
    await state.clear()
    await state.set_state(EmailFlowStates.selecting_email_resource)

    await callback.message.edit_text(
        "📧 <b>Почты</b>\n\n"
        "Выберите почтовый ресурс:",
        reply_markup=get_email_menu_keyboard(),
        parse_mode="HTML",
    )


# === Выбор почтового ресурса ===

@router.callback_query(EmailResourceCallback.filter(), EmailFlowStates.selecting_email_resource)
async def select_email_resource(
    callback: CallbackQuery,
    callback_data: EmailResourceCallback,
    state: FSMContext,
):
    """Выбор почтового ресурса (Gmail/Рамблер)"""
    await callback.answer()
    email_resource = EmailResource(callback_data.resource)

    await state.update_data(email_resource=email_resource)

    if email_resource == EmailResource.GMAIL:
        # Для Gmail показываем выбор типа
        await state.set_state(EmailFlowStates.selecting_email_type)
        await callback.message.edit_text(
            f"📧 <b>Почты</b>\n\n"
            f"Ресурс: <b>{email_resource.display_name}</b>\n\n"
            f"Выберите тип:",
            reply_markup=get_email_type_keyboard(),
            parse_mode="HTML",
        )
    else:
        # Для Рамблер сразу к выбору региона
        await state.set_state(EmailFlowStates.selecting_region)
        await callback.message.edit_text(
            f"📧 <b>Почты</b>\n\n"
            f"Ресурс: <b>{email_resource.display_name}</b>\n\n"
            f"Выберите регион:",
            reply_markup=get_email_region_keyboard_rambler(),
            parse_mode="HTML",
        )


# === Выбор типа Gmail ===

@router.callback_query(EmailTypeCallback.filter(), EmailFlowStates.selecting_email_type)
async def select_email_type(
    callback: CallbackQuery,
    callback_data: EmailTypeCallback,
    state: FSMContext,
):
    """Выбор типа Gmail (Обычные/gmail.com)"""
    await callback.answer()
    email_type = Gender(callback_data.email_type)
    data = await state.get_data()
    email_resource = data.get("email_resource")

    await state.update_data(email_type=email_type)
    await state.set_state(EmailFlowStates.selecting_region)

    await callback.message.edit_text(
        f"📧 <b>Почты</b>\n\n"
        f"Ресурс: <b>{email_resource.display_name}</b>\n"
        f"Тип: <b>{email_type.display_name}</b>\n\n"
        f"Выберите регион:",
        reply_markup=get_email_region_keyboard(),
        parse_mode="HTML",
    )


# === Выбор региона ===

@router.callback_query(EmailRegionCallback.filter(), EmailFlowStates.selecting_region)
async def select_email_region(
    callback: CallbackQuery,
    callback_data: EmailRegionCallback,
    state: FSMContext,
):
    """Выбор региона для почты"""
    await callback.answer()
    region = callback_data.region
    data = await state.get_data()
    email_resource = data.get("email_resource")
    email_type = data.get("email_type")

    await state.update_data(email_region=region)
    await state.set_state(EmailFlowStates.selecting_quantity)

    # Формируем текст
    text = f"📧 <b>Почты</b>\n\n" f"Ресурс: <b>{email_resource.display_name}</b>\n"

    if email_type:
        text += f"Тип: <b>{email_type.display_name}</b>\n"

    text += f"Регион: <b>{region}</b>\n\n" f"Выберите количество:"

    await callback.message.edit_text(
        text,
        reply_markup=get_email_quantity_keyboard(),
        parse_mode="HTML",
    )


# === Поиск региона ===

@router.callback_query(EmailSearchRegionCallback.filter(), EmailFlowStates.selecting_region)
async def search_email_region_start(callback: CallbackQuery, state: FSMContext):
    """Начало поиска региона"""
    await callback.answer()
    data = await state.get_data()
    email_resource = data.get("email_resource")
    email_type = data.get("email_type")

    await state.set_state(EmailFlowStates.searching_region)

    text = f"📧 <b>Почты</b>\n\n" f"Ресурс: <b>{email_resource.display_name}</b>\n"

    if email_type:
        text += f"Тип: <b>{email_type.display_name}</b>\n"

    text += "\n🔍 Введите номер региона:"

    await callback.message.edit_text(
        text,
        reply_markup=get_email_back_to_region_keyboard(),
        parse_mode="HTML",
    )


@router.message(EmailFlowStates.searching_region)
async def search_email_region_input(message: Message, state: FSMContext):
    """Обработка ввода региона"""
    region = message.text.strip()
    data = await state.get_data()
    email_resource = data.get("email_resource")
    email_type = data.get("email_type")

    if not region:
        await message.answer(
            "❌ Введите номер региона:",
            reply_markup=get_email_back_to_region_keyboard(),
        )
        return

    # Валидация региона
    if not region_service.region_exists(region):
        available = ", ".join(region_service.get_regions()[:5])
        await message.answer(
            f"❌ Такого региона не существует: <b>{region}</b>\n\n"
            f"Доступные регионы: {available}...\n"
            f"Введите существующий регион или выберите из списка:",
            reply_markup=get_email_back_to_region_keyboard(),
            parse_mode="HTML",
        )
        return

    await state.update_data(email_region=region)
    await state.set_state(EmailFlowStates.selecting_quantity)

    text = f"📧 <b>Почты</b>\n\n" f"Ресурс: <b>{email_resource.display_name}</b>\n"

    if email_type:
        text += f"Тип: <b>{email_type.display_name}</b>\n"

    text += f"Регион: <b>{region}</b>\n\n" f"Выберите количество:"

    await message.answer(
        text,
        reply_markup=get_email_quantity_keyboard(),
        parse_mode="HTML",
    )


# === Выбор количества и выдача ===

@router.callback_query(EmailQuantityCallback.filter(), EmailFlowStates.selecting_quantity)
async def select_email_quantity_and_issue(
    callback: CallbackQuery,
    callback_data: EmailQuantityCallback,
    state: FSMContext,
):
    """Выбор количества и выдача почт"""
    await callback.answer()

    quantity = callback_data.quantity
    data = await state.get_data()
    email_resource = data.get("email_resource")
    email_type = data.get("email_type")
    region = data.get("email_region")

    # Показываем загрузку
    text = f"📧 <b>Почты</b>\n\n" f"Ресурс: <b>{email_resource.display_name}</b>\n"

    if email_type:
        text += f"Тип: <b>{email_type.display_name}</b>\n"

    text += (
        f"Регион: <b>{region}</b>\n"
        f"Количество: <b>{quantity}</b>\n\n"
        f"⏳ <i>Загрузка почт...</i>"
    )

    await callback.message.edit_text(text, parse_mode="HTML")

    # Получаем stage пользователя
    user = whitelist_service.get_user(callback.from_user.id)
    employee_stage = user.stage if user else "unknown"

    try:
        # Выдаем почты
        issued = await email_service.issue_emails(
            email_resource=email_resource,
            region=region,
            quantity=quantity,
            employee_stage=employee_stage,
            email_type=email_type,
        )

        if not issued:
            await callback.message.edit_text(
                "❌ Почты не найдены.\n\n"
                "Попробуйте другие параметры."
            )
            await state.clear()
            await state.set_state(AccountFlowStates.selecting_resource)
            await callback.message.answer(
                "📦 <b>Выдача аккаунтов</b>\n\n"
                "Выберите ресурс:",
                reply_markup=get_resource_keyboard(),
                parse_mode="HTML",
            )
            return

        # Показываем результат
        result_text = f"<b>✅ Выдано почт: {len(issued)}</b>\n\n" f"Ресурс: {email_resource.display_name}\n"

        if email_type:
            result_text += f"Тип: {email_type.display_name}\n"

        result_text += f"Регион: {region}"

        await callback.message.edit_text(result_text, parse_mode="HTML")

        # Отправляем каждую почту отдельным сообщением с кнопками статуса
        for item in issued:
            email_id = item["email_id"]
            login = item["login"]
            password = item["password"]
            extra_info = item.get("extra_info", "")

            msg = format_email_message(
                email_resource=email_resource,
                login=login,
                password=password,
                region=region,
                email_type_display=email_type.display_name if email_type else None,
                extra_info=extra_info,
            )
            await callback.message.answer(
                msg,
                reply_markup=get_email_feedback_keyboard(
                    email_id=email_id,
                    resource=email_resource.value,
                    email_type=email_type.value if email_type else "none",
                    region=region,
                ),
                parse_mode="HTML",
            )

        # Предлагаем продолжить
        await callback.message.answer(
            f"✅ Выдано почт: {len(issued)}\n\n"
            "Для получения новых — выберите ресурс:",
            reply_markup=get_resource_keyboard(),
        )

    except Exception as e:
        logger.error(f"Error issuing emails: {e}")
        await callback.message.edit_text(
            "❌ Произошла ошибка при выдаче почт.\n\n"
            "Попробуйте позже."
        )
        await callback.message.answer(
            "📦 <b>Выдача аккаунтов</b>\n\n"
            "Выберите ресурс:",
            reply_markup=get_resource_keyboard(),
            parse_mode="HTML",
        )

    await state.clear()
    await state.set_state(AccountFlowStates.selecting_resource)


# === Кнопки назад ===

@router.callback_query(EmailBackCallback.filter(F.to == "main"))
async def back_to_main_menu(callback: CallbackQuery, state: FSMContext):
    """Возврат в главное меню выбора ресурсов"""
    await callback.answer()
    await state.clear()
    await state.set_state(AccountFlowStates.selecting_resource)

    await callback.message.edit_text(
        "📦 <b>Выдача аккаунтов</b>\n\n"
        "Выберите ресурс:",
        reply_markup=get_resource_keyboard(),
        parse_mode="HTML",
    )


@router.callback_query(EmailBackCallback.filter(F.to == "email_resource"))
async def back_to_email_resource(callback: CallbackQuery, state: FSMContext):
    """Возврат к выбору почтового ресурса"""
    await callback.answer()
    await state.set_state(EmailFlowStates.selecting_email_resource)

    await callback.message.edit_text(
        "📧 <b>Почты</b>\n\n"
        "Выберите почтовый ресурс:",
        reply_markup=get_email_menu_keyboard(),
        parse_mode="HTML",
    )


@router.callback_query(EmailBackCallback.filter(F.to == "email_type"))
async def back_to_email_type(callback: CallbackQuery, state: FSMContext):
    """Возврат к выбору типа Gmail"""
    await callback.answer()
    data = await state.get_data()
    email_resource = data.get("email_resource")

    await state.set_state(EmailFlowStates.selecting_email_type)

    await callback.message.edit_text(
        f"📧 <b>Почты</b>\n\n"
        f"Ресурс: <b>{email_resource.display_name}</b>\n\n"
        f"Выберите тип:",
        reply_markup=get_email_type_keyboard(),
        parse_mode="HTML",
    )


@router.callback_query(EmailBackCallback.filter(F.to == "region"))
async def back_to_email_region(callback: CallbackQuery, state: FSMContext):
    """Возврат к выбору региона"""
    await callback.answer()
    data = await state.get_data()
    email_resource = data.get("email_resource")
    email_type = data.get("email_type")

    await state.set_state(EmailFlowStates.selecting_region)

    text = f"📧 <b>Почты</b>\n\n" f"Ресурс: <b>{email_resource.display_name}</b>\n"

    if email_type:
        text += f"Тип: <b>{email_type.display_name}</b>\n"

    text += "\nВыберите регион:"

    # Используем разные клавиатуры в зависимости от ресурса
    if email_resource == EmailResource.RAMBLER:
        keyboard = get_email_region_keyboard_rambler()
    else:
        keyboard = get_email_region_keyboard()

    await callback.message.edit_text(
        text,
        reply_markup=keyboard,
        parse_mode="HTML",
    )


# === Обработка фидбека по почте ===


@router.callback_query(EmailFeedbackCallback.filter())
async def process_email_feedback(
    callback: CallbackQuery,
    callback_data: EmailFeedbackCallback,
):
    """Обработка feedback по почте — подтверждает и переносит в таблицу выданных"""
    email_id = callback_data.email_id
    status = callback_data.action
    resource = callback_data.resource
    email_type = callback_data.email_type
    region = callback_data.region

    try:
        # Подтверждаем почту (мгновенно добавляет в буфер записи)
        success = email_service.confirm_email_feedback(email_id, status)

        # Получаем отображаемое имя статуса
        status_display = get_status_display(status)

        # Компактный формат сообщения (без строки копирования)
        new_text = make_compact_after_feedback(callback.message.html_text, status_display)

        # Для block и defect показываем кнопку замены
        if status in ("block", "defect"):
            await callback.message.edit_text(
                new_text,
                parse_mode="HTML",
                reply_markup=get_email_replace_keyboard(resource, email_type, region),
            )
        else:
            await callback.message.edit_text(
                new_text,
                parse_mode="HTML",
                reply_markup=None,
            )

        if not success:
            logger.warning(f"Email {email_id} confirmation returned False")

        await callback.answer(status_display)

    except Exception as e:
        logger.error(f"Error processing email feedback: {e}")
        await callback.answer("❌ Ошибка", show_alert=True)


@router.callback_query(EmailReplaceCallback.filter())
async def process_email_replace(
    callback: CallbackQuery,
    callback_data: EmailReplaceCallback,
):
    """Обработка замены почты"""
    await callback.answer("⏳ Ищем замену...")

    resource_str = callback_data.resource
    email_type_str = callback_data.email_type
    region = callback_data.region

    try:
        email_resource = EmailResource(resource_str)
        email_type = Gender(email_type_str) if email_type_str != "none" else None

        # Получаем stage пользователя
        user = whitelist_service.get_user(callback.from_user.id)
        employee_stage = user.stage if user else "unknown"

        # Выдаём одну почту на замену
        issued = await email_service.issue_emails(
            email_resource=email_resource,
            region=region,
            quantity=1,
            employee_stage=employee_stage,
            email_type=email_type,
        )

        if not issued:
            await callback.message.edit_reply_markup(reply_markup=None)
            await callback.message.answer("❌ Почты для замены не найдены")
            return

        # Отправляем новую почту
        item = issued[0]
        email_id = item["email_id"]
        login = item["login"]
        password = item["password"]
        extra_info = item.get("extra_info", "")

        msg = format_email_message(
            email_resource=email_resource,
            login=login,
            password=password,
            region=region,
            email_type_display=email_type.display_name if email_type else None,
            extra_info=extra_info,
        )

        await callback.message.answer(
            f"🔄 <b>Замена почты:</b>\n\n{msg}",
            reply_markup=get_email_feedback_keyboard(
                email_id=email_id,
                resource=email_resource.value,
                email_type=email_type.value if email_type else "none",
                region=region,
            ),
            parse_mode="HTML",
        )

        # Убираем кнопку замены с предыдущего сообщения
        await callback.message.edit_reply_markup(reply_markup=None)

    except Exception as e:
        logger.error(f"Error replacing email: {e}")
        await callback.message.answer("❌ Ошибка при замене почты")
