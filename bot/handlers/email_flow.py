"""
Хэндлеры для работы с почтами (новый flow с умным распределением).

Новый flow:
1. Выбор домена (Gmail/Рамблер)
2. Выбор типа (только для Gmail: Любые/gmail.com)
3. Выбор региона
4. Выбор режима (Новая/Эконом)
5. Выбор целевых ресурсов (мультиселект)
6. Выбор количества
"""
import logging
from typing import List

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
    EmailModeCallback,
    EmailTargetResourceToggleCallback,
    EmailTargetResourceConfirmCallback,
)
from bot.keyboards.email_keyboards import (
    get_email_menu_keyboard,
    get_email_type_keyboard,
    get_email_region_keyboard,
    get_email_back_to_region_keyboard,
    get_email_mode_keyboard,
    get_email_target_resource_keyboard,
    get_email_quantity_keyboard,
    get_email_feedback_keyboard,
    get_email_replace_keyboard,
)
from bot.keyboards.inline import get_resource_keyboard
from bot.models.enums import EmailResource, EmailType, EmailMode, EmailTargetResource, AccountStatus
from bot.services.email_service import email_service
from bot.services.region_service import region_service
from bot.services.whitelist_service import whitelist_service
from bot.services.pending_messages import pending_messages
from bot.utils.formatters import format_email_message, make_compact_after_feedback


def get_status_display(status: str) -> str:
    """Получить отображаемое имя статуса с эмодзи"""
    try:
        return AccountStatus(status).display_name
    except ValueError:
        return status


def get_email_source_name(email_resource: EmailResource, email_type: EmailType) -> str:
    """Получить название источника почты для отображения (без эмодзи)"""
    if email_resource == EmailResource.RAMBLER:
        return "Рамблер почта"
    elif email_resource == EmailResource.GMAIL:
        if email_type == EmailType.GMAIL_DOMAIN:
            return "Гугл Гмейл почта"
        else:
            return "Гугл Обыч почта"
    return "Почта"


def format_target_resources(resources: List[str]) -> str:
    """Форматировать список целевых ресурсов для отображения"""
    try:
        names = []
        for r in resources:
            try:
                res = EmailTargetResource(r)
                names.append(res.display_name)
            except ValueError:
                names.append(r)
        return ", ".join(names)
    except Exception:
        return ", ".join(resources)


logger = logging.getLogger(__name__)
router = Router()


# === Открытие меню почт ===

@router.callback_query(EmailMenuCallback.filter(F.action == "open"))
async def open_email_menu(callback: CallbackQuery, state: FSMContext):
    """Открытие меню выбора почтового домена"""
    await callback.answer()
    await state.clear()
    await state.set_state(EmailFlowStates.selecting_email_resource)

    await callback.message.edit_text(
        "📧 <b>Почты</b>\n\n"
        "Выберите почтовый домен:",
        reply_markup=get_email_menu_keyboard(),
        parse_mode="HTML",
    )


# === Выбор почтового домена ===

@router.callback_query(EmailResourceCallback.filter(), EmailFlowStates.selecting_email_resource)
async def select_email_resource(
    callback: CallbackQuery,
    callback_data: EmailResourceCallback,
    state: FSMContext,
):
    """Выбор почтового домена (Gmail/Рамблер).

    Gmail -> выбор типа (Любые/gmail.com)
    Rambler -> сразу к выбору региона
    """
    await callback.answer()
    email_resource = EmailResource(callback_data.resource)

    await state.update_data(email_resource=email_resource)

    if email_resource == EmailResource.GMAIL:
        # Gmail: показываем выбор типа
        await state.set_state(EmailFlowStates.selecting_email_type)
        await callback.message.edit_text(
            f"📧 <b>Почты</b>\n\n"
            f"Домен: <b>{email_resource.display_name}</b>\n\n"
            f"Выберите тип почты:",
            reply_markup=get_email_type_keyboard(),
            parse_mode="HTML",
        )
    else:
        # Rambler: сразу к региону (типа нет)
        await state.update_data(email_type=EmailType.NONE)
        await state.set_state(EmailFlowStates.selecting_region)
        await callback.message.edit_text(
            f"📧 <b>Почты</b>\n\n"
            f"Домен: <b>{email_resource.display_name}</b>\n\n"
            f"Выберите регион:",
            reply_markup=get_email_region_keyboard(email_resource),
            parse_mode="HTML",
        )


# === Выбор типа Gmail ===

@router.callback_query(EmailTypeCallback.filter(), EmailFlowStates.selecting_email_type)
async def select_email_type(
    callback: CallbackQuery,
    callback_data: EmailTypeCallback,
    state: FSMContext,
):
    """Выбор типа Gmail (Любые/gmail.com) -> переход к выбору региона"""
    await callback.answer()
    email_type = EmailType(callback_data.email_type)
    data = await state.get_data()
    email_resource = data.get("email_resource")

    await state.update_data(email_type=email_type)
    await state.set_state(EmailFlowStates.selecting_region)

    await callback.message.edit_text(
        f"📧 <b>Почты</b>\n\n"
        f"Домен: <b>{email_resource.display_name}</b>\n"
        f"Тип: <b>{email_type.display_name}</b>\n\n"
        f"Выберите регион:",
        reply_markup=get_email_region_keyboard(email_resource),
        parse_mode="HTML",
    )


# === Выбор региона ===

@router.callback_query(EmailRegionCallback.filter(), EmailFlowStates.selecting_region)
async def select_email_region(
    callback: CallbackQuery,
    callback_data: EmailRegionCallback,
    state: FSMContext,
):
    """Выбор региона -> переход к выбору режима"""
    await callback.answer()
    region = callback_data.region
    data = await state.get_data()
    email_resource = data.get("email_resource")

    await state.update_data(email_region=region)
    await state.set_state(EmailFlowStates.selecting_mode)

    await callback.message.edit_text(
        f"📧 <b>Почты</b>\n\n"
        f"Домен: <b>{email_resource.display_name}</b>\n"
        f"Регион: <b>{region}</b>\n\n"
        f"Выберите режим:\n\n"
        f"✨ <b>Новая</b> — свежая почта из базы\n"
        f"♻️ <b>Эконом</b> — ранее использованная на других ресурсах",
        reply_markup=get_email_mode_keyboard(),
        parse_mode="HTML",
    )


# === Поиск региона ===

@router.callback_query(EmailSearchRegionCallback.filter(), EmailFlowStates.selecting_region)
async def search_email_region_start(callback: CallbackQuery, state: FSMContext):
    """Начало поиска региона"""
    await callback.answer()
    data = await state.get_data()
    email_resource = data.get("email_resource")

    await state.set_state(EmailFlowStates.searching_region)

    await callback.message.edit_text(
        f"📧 <b>Почты</b>\n\n"
        f"Домен: <b>{email_resource.display_name}</b>\n\n"
        f"🔍 Введите номер региона:",
        reply_markup=get_email_back_to_region_keyboard(),
        parse_mode="HTML",
    )


@router.message(EmailFlowStates.searching_region)
async def search_email_region_input(message: Message, state: FSMContext):
    """Обработка ввода региона"""
    region = message.text.strip()
    data = await state.get_data()
    email_resource = data.get("email_resource")

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
    await state.set_state(EmailFlowStates.selecting_mode)

    await message.answer(
        f"📧 <b>Почты</b>\n\n"
        f"Домен: <b>{email_resource.display_name}</b>\n"
        f"Регион: <b>{region}</b>\n\n"
        f"Выберите режим:\n\n"
        f"✨ <b>Новая</b> — свежая почта из базы\n"
        f"♻️ <b>Эконом</b> — ранее использованная на других ресурсах",
        reply_markup=get_email_mode_keyboard(),
        parse_mode="HTML",
    )


# === Выбор режима (Новая/Эконом) ===

@router.callback_query(EmailModeCallback.filter(), EmailFlowStates.selecting_mode)
async def select_email_mode(
    callback: CallbackQuery,
    callback_data: EmailModeCallback,
    state: FSMContext,
):
    """Выбор режима -> переход к выбору целевых ресурсов"""
    await callback.answer()
    email_mode = EmailMode(callback_data.mode)
    data = await state.get_data()
    email_resource = data.get("email_resource")
    region = data.get("email_region")

    await state.update_data(email_mode=email_mode, selected_target_resources=[])
    await state.set_state(EmailFlowStates.selecting_target_resources)

    await callback.message.edit_text(
        f"📧 <b>Почты</b>\n\n"
        f"Домен: <b>{email_resource.display_name}</b>\n"
        f"Регион: <b>{region}</b>\n"
        f"Режим: <b>{email_mode.button_text}</b>\n\n"
        f"Выберите ресурсы для регистрации:",
        reply_markup=get_email_target_resource_keyboard([]),
        parse_mode="HTML",
    )


# === Мультиселект целевых ресурсов ===

@router.callback_query(EmailTargetResourceToggleCallback.filter(), EmailFlowStates.selecting_target_resources)
async def toggle_target_resource(
    callback: CallbackQuery,
    callback_data: EmailTargetResourceToggleCallback,
    state: FSMContext,
):
    """Toggle выбора целевого ресурса"""
    await callback.answer()
    resource = callback_data.resource
    data = await state.get_data()
    email_resource = data.get("email_resource")
    region = data.get("email_region")
    email_mode = data.get("email_mode")
    selected = data.get("selected_target_resources", [])

    # Toggle
    if resource in selected:
        selected.remove(resource)
    else:
        selected.append(resource)

    await state.update_data(selected_target_resources=selected)

    # Обновляем клавиатуру
    await callback.message.edit_text(
        f"📧 <b>Почты</b>\n\n"
        f"Домен: <b>{email_resource.display_name}</b>\n"
        f"Регион: <b>{region}</b>\n"
        f"Режим: <b>{email_mode.button_text}</b>\n\n"
        f"Выберите ресурсы для регистрации:\n"
        f"<i>Выбрано: {len(selected)}</i>",
        reply_markup=get_email_target_resource_keyboard(selected),
        parse_mode="HTML",
    )


@router.callback_query(EmailTargetResourceConfirmCallback.filter(), EmailFlowStates.selecting_target_resources)
async def confirm_target_resources(
    callback: CallbackQuery,
    state: FSMContext,
):
    """Подтверждение выбора целевых ресурсов -> переход к выбору количества"""
    await callback.answer()
    data = await state.get_data()
    email_resource = data.get("email_resource")
    region = data.get("email_region")
    email_mode = data.get("email_mode")
    selected = data.get("selected_target_resources", [])

    if not selected:
        await callback.answer("Выберите хотя бы один ресурс", show_alert=True)
        return

    await state.set_state(EmailFlowStates.selecting_quantity)

    resources_text = format_target_resources(selected)

    await callback.message.edit_text(
        f"📧 <b>Почты</b>\n\n"
        f"Домен: <b>{email_resource.display_name}</b>\n"
        f"Регион: <b>{region}</b>\n"
        f"Режим: <b>{email_mode.button_text}</b>\n"
        f"Ресурсы: <b>{resources_text}</b>\n\n"
        f"Выберите количество:",
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
    email_type = data.get("email_type", EmailType.ANY)
    region = data.get("email_region")
    email_mode = data.get("email_mode")
    target_resources = data.get("selected_target_resources", [])

    resources_text = format_target_resources(target_resources)

    # Формируем текст с типом для Gmail
    type_line = ""
    if email_resource == EmailResource.GMAIL and email_type:
        type_line = f"Тип: <b>{email_type.display_name}</b>\n"

    # Показываем загрузку
    await callback.message.edit_text(
        f"📧 <b>Почты</b>\n\n"
        f"Домен: <b>{email_resource.display_name}</b>\n"
        f"{type_line}"
        f"Регион: <b>{region}</b>\n"
        f"Режим: <b>{email_mode.button_text}</b>\n"
        f"Ресурсы: <b>{resources_text}</b>\n"
        f"Количество: <b>{quantity}</b>\n\n"
        f"⏳ <i>Загрузка почт...</i>",
        parse_mode="HTML",
    )

    # Получаем stage пользователя
    user = whitelist_service.get_user(callback.from_user.id)
    employee_stage = user.stage if user else "unknown"

    try:
        # Выдаем почты
        issued = await email_service.issue_emails(
            email_resource=email_resource,
            email_type=email_type,
            region=region,
            email_mode=email_mode,
            target_resources=target_resources,
            quantity=quantity,
            employee_stage=employee_stage,
        )

        if not issued:
            mode_hint = ""
            if email_mode == EmailMode.NEW:
                mode_hint = "\n\n💡 <i>Попробуйте режим \"Эконом\" — там могут быть подходящие почты.</i>"
            else:
                mode_hint = "\n\n💡 <i>Все эконом-почты уже использованы на этих ресурсах. Попробуйте режим \"Новая\".</i>"

            await callback.message.edit_text(
                f"❌ Почты не найдены.{mode_hint}",
                parse_mode="HTML",
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
        result_text = (
            f"<b>✅ Выдано почт: {len(issued)}</b>\n\n"
            f"Домен: {email_resource.display_name}\n"
            f"Регион: {region}\n"
            f"Режим: {email_mode.button_text}\n"
            f"Ресурсы: {resources_text}"
        )

        await callback.message.edit_text(result_text, parse_mode="HTML")

        # Отправляем каждую почту отдельным сообщением с кнопками статуса
        for item in issued:
            email_id = item["email_id"]
            login = item["login"]
            password = item["password"]
            extra_info = item.get("extra_info", "")
            already_used_for = item.get("already_used_for", [])

            # Формируем сообщение (тип источника + регион сверху)
            source_name = get_email_source_name(email_resource, email_type)
            msg_parts = [
                f"<b>{source_name}</b>",
                f"<b>Регион: {region}</b>",
                f"📧 <code>{login}</code>",
                f"🔑 <code>{password}</code>",
            ]

            if extra_info:
                msg_parts.append(f"📌 <code>{extra_info}</code>")

            if already_used_for:
                used_names = format_target_resources(already_used_for)
                msg_parts.append(f"♻️ <i>Ранее: {used_names}</i>")

            msg = "\n".join(msg_parts)

            target_resources_str = ",".join(target_resources)

            sent_msg = await callback.message.answer(
                msg,
                reply_markup=get_email_feedback_keyboard(
                    email_id=email_id,
                    resource=email_resource.value,
                    region=region,
                    target_resources=target_resources_str,
                ),
                parse_mode="HTML",
            )

            # Регистрируем сообщение для автоподтверждения через 10 минут
            pending_messages.register(
                entity_type="email",
                entity_id=email_id,
                chat_id=sent_msg.chat.id,
                message_id=sent_msg.message_id,
                original_text=msg,
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
    """Возврат к выбору почтового домена"""
    await callback.answer()
    await state.set_state(EmailFlowStates.selecting_email_resource)

    await callback.message.edit_text(
        "📧 <b>Почты</b>\n\n"
        "Выберите почтовый домен:",
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
        f"Домен: <b>{email_resource.display_name}</b>\n\n"
        f"Выберите тип почты:",
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

    # Формируем текст с типом для Gmail
    type_line = ""
    if email_resource == EmailResource.GMAIL and email_type:
        type_line = f"Тип: <b>{email_type.display_name}</b>\n"

    await callback.message.edit_text(
        f"📧 <b>Почты</b>\n\n"
        f"Домен: <b>{email_resource.display_name}</b>\n"
        f"{type_line}\n"
        f"Выберите регион:",
        reply_markup=get_email_region_keyboard(email_resource),
        parse_mode="HTML",
    )


@router.callback_query(EmailBackCallback.filter(F.to == "mode"))
async def back_to_email_mode(callback: CallbackQuery, state: FSMContext):
    """Возврат к выбору режима"""
    await callback.answer()
    data = await state.get_data()
    email_resource = data.get("email_resource")
    region = data.get("email_region")

    await state.set_state(EmailFlowStates.selecting_mode)

    await callback.message.edit_text(
        f"📧 <b>Почты</b>\n\n"
        f"Домен: <b>{email_resource.display_name}</b>\n"
        f"Регион: <b>{region}</b>\n\n"
        f"Выберите режим:\n\n"
        f"✨ <b>Новая</b> — свежая почта из базы\n"
        f"♻️ <b>Эконом</b> — ранее использованная на других ресурсах",
        reply_markup=get_email_mode_keyboard(),
        parse_mode="HTML",
    )


@router.callback_query(EmailBackCallback.filter(F.to == "target_resources"))
async def back_to_target_resources(callback: CallbackQuery, state: FSMContext):
    """Возврат к выбору целевых ресурсов"""
    await callback.answer()
    data = await state.get_data()
    email_resource = data.get("email_resource")
    region = data.get("email_region")
    email_mode = data.get("email_mode")
    selected = data.get("selected_target_resources", [])

    await state.set_state(EmailFlowStates.selecting_target_resources)

    await callback.message.edit_text(
        f"📧 <b>Почты</b>\n\n"
        f"Домен: <b>{email_resource.display_name}</b>\n"
        f"Регион: <b>{region}</b>\n"
        f"Режим: <b>{email_mode.button_text}</b>\n\n"
        f"Выберите ресурсы для регистрации:\n"
        f"<i>Выбрано: {len(selected)}</i>",
        reply_markup=get_email_target_resource_keyboard(selected),
        parse_mode="HTML",
    )


# === Обработка фидбека по почте ===

@router.callback_query(EmailFeedbackCallback.filter())
async def process_email_feedback(
    callback: CallbackQuery,
    callback_data: EmailFeedbackCallback,
):
    """Обработка feedback по почте — подтверждает и переносит/обновляет в таблице"""
    email_id = callback_data.email_id
    status = callback_data.action
    resource = callback_data.resource
    region = callback_data.region

    try:
        # Снимаем с отслеживания для автоподтверждения (ручной feedback получен)
        pending_messages.unregister(email_id)

        # Подтверждаем почту (мгновенно добавляет в буфер)
        success = email_service.confirm_email_feedback(email_id, status)

        # Получаем отображаемое имя статуса
        status_display = get_status_display(status)

        # Компактный формат сообщения
        new_text = make_compact_after_feedback(callback.message.html_text, status_display)

        # Для block, auth и defect показываем кнопку замены
        if status in ("block", "auth", "defect"):
            await callback.message.edit_text(
                new_text,
                parse_mode="HTML",
                reply_markup=get_email_replace_keyboard(resource, region, ""),
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
    state: FSMContext,
):
    """Обработка замены почты"""
    await callback.answer("⏳ Ищем замену...")

    resource_str = callback_data.resource
    region = callback_data.region

    try:
        email_resource = EmailResource(resource_str)

        # Получаем данные из state (могут быть недоступны, если прошло много времени)
        data = await state.get_data()
        email_type_raw = data.get("email_type", EmailType.ANY)
        email_type = email_type_raw if isinstance(email_type_raw, EmailType) else EmailType(email_type_raw) if email_type_raw else EmailType.ANY
        email_mode = data.get("email_mode", EmailMode.NEW)
        target_resources = data.get("selected_target_resources", ["other"])

        # Получаем stage пользователя
        user = whitelist_service.get_user(callback.from_user.id)
        employee_stage = user.stage if user else "unknown"

        # Выдаём одну почту на замену
        issued = await email_service.issue_emails(
            email_resource=email_resource,
            email_type=email_type,
            region=region,
            email_mode=email_mode,
            target_resources=target_resources,
            quantity=1,
            employee_stage=employee_stage,
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
        already_used_for = item.get("already_used_for", [])

        # Формируем сообщение (тип источника + регион сверху)
        source_name = get_email_source_name(email_resource, email_type)
        msg_parts = [
            f"<b>{source_name}</b>",
            f"<b>Замена почты</b>",
            f"<b>Регион: {region}</b>",
            f"📧 <code>{login}</code>",
            f"🔑 <code>{password}</code>",
        ]

        if extra_info:
            msg_parts.append(f"📌 <code>{extra_info}</code>")

        if already_used_for:
            used_names = format_target_resources(already_used_for)
            msg_parts.append(f"♻️ <i>Ранее: {used_names}</i>")

        msg = "\n".join(msg_parts)

        target_resources_str = ",".join(target_resources)

        sent_msg = await callback.message.answer(
            msg,
            reply_markup=get_email_feedback_keyboard(
                email_id=email_id,
                resource=email_resource.value,
                region=region,
                target_resources=target_resources_str,
            ),
            parse_mode="HTML",
        )

        # Регистрируем сообщение для автоподтверждения через 10 минут
        pending_messages.register(
            entity_type="email",
            entity_id=email_id,
            chat_id=sent_msg.chat.id,
            message_id=sent_msg.message_id,
            original_text=msg,
        )

        # Убираем кнопку замены с предыдущего сообщения
        await callback.message.edit_reply_markup(reply_markup=None)

    except Exception as e:
        logger.error(f"Error replacing email: {e}")
        await callback.message.answer("❌ Ошибка при замене почты")
