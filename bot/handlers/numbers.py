"""Хэндлеры для работы с номерами телефонов"""
import logging

from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext

from bot.states.states import NumberStates, AccountFlowStates
from bot.keyboards.callbacks import (
    NumberMenuCallback,
    NumberResourceToggleCallback,
    NumberResourceConfirmCallback,
    NumberRegionCallback,
    NumberSearchRegionCallback,
    NumberQuantityCallback,
    NumberBackCallback,
)
from bot.keyboards.number_keyboards import (
    get_number_resource_keyboard,
    get_number_region_keyboard,
    get_number_back_to_region_keyboard,
    get_number_quantity_keyboard,
)
from bot.keyboards.inline import get_resource_keyboard
from bot.models.enums import NumberResource
from bot.services.number_service import number_service
from bot.services.region_service import region_service
from bot.services.sheets_service import sheets_service

logger = logging.getLogger(__name__)
router = Router()


# === Открытие меню номеров ===

@router.callback_query(NumberMenuCallback.filter(F.action == "open"))
async def open_numbers_menu(callback: CallbackQuery, state: FSMContext):
    """Открытие меню выбора номеров"""
    await callback.answer()
    await state.clear()
    await state.update_data(selected_number_resources=[])
    await state.set_state(NumberStates.selecting_resources)

    mode_text = "только сегодняшние" if number_service.today_only else "все"

    await callback.message.edit_text(
        f"📱 <b>Номера телефонов</b>\n\n"
        f"Режим: {mode_text}\n\n"
        f"Выберите ресурсы (можно несколько):",
        reply_markup=get_number_resource_keyboard([]),
        parse_mode="HTML",
    )


# === Выбор ресурсов (множественный) ===

@router.callback_query(NumberResourceToggleCallback.filter(), NumberStates.selecting_resources)
async def toggle_number_resource(
    callback: CallbackQuery,
    callback_data: NumberResourceToggleCallback,
    state: FSMContext,
):
    """Переключение выбора ресурса"""
    await callback.answer()
    resource = callback_data.resource
    data = await state.get_data()
    selected = data.get("selected_number_resources", [])

    # Toggle
    if resource in selected:
        selected.remove(resource)
    else:
        selected.append(resource)

    await state.update_data(selected_number_resources=selected)

    mode_text = "только сегодняшние" if number_service.today_only else "все"

    await callback.message.edit_text(
        f"📱 <b>Номера телефонов</b>\n\n"
        f"Режим: {mode_text}\n\n"
        f"Выберите ресурсы (можно несколько):",
        reply_markup=get_number_resource_keyboard(selected),
        parse_mode="HTML",
    )


@router.callback_query(NumberResourceConfirmCallback.filter(), NumberStates.selecting_resources)
async def confirm_number_resources(callback: CallbackQuery, state: FSMContext):
    """Подтверждение выбора ресурсов"""
    data = await state.get_data()
    selected = data.get("selected_number_resources", [])

    if not selected:
        await callback.answer("Выберите хотя бы один ресурс", show_alert=True)
        return

    await callback.answer()
    await state.set_state(NumberStates.selecting_region)

    # Формируем текст выбранных ресурсов
    resources_text = ", ".join(NumberResource(r).display_name for r in selected)

    await callback.message.edit_text(
        f"📱 <b>Номера телефонов</b>\n\n"
        f"Ресурсы: <b>{resources_text}</b>\n\n"
        f"Выберите регион:",
        reply_markup=get_number_region_keyboard(),
        parse_mode="HTML",
    )


# === Выбор региона ===

@router.callback_query(NumberRegionCallback.filter(), NumberStates.selecting_region)
async def select_number_region(
    callback: CallbackQuery,
    callback_data: NumberRegionCallback,
    state: FSMContext,
):
    """Выбор региона"""
    region = callback_data.region
    data = await state.get_data()
    selected = data.get("selected_number_resources", [])

    await state.update_data(number_region=region)
    await state.set_state(NumberStates.selecting_quantity)

    resources_text = ", ".join(NumberResource(r).display_name for r in selected)

    await callback.message.edit_text(
        f"📱 <b>Номера телефонов</b>\n\n"
        f"Ресурсы: <b>{resources_text}</b>\n"
        f"Регион: <b>{region}</b>\n\n"
        f"Выберите количество:",
        reply_markup=get_number_quantity_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()


# === Поиск региона ===

@router.callback_query(NumberSearchRegionCallback.filter(), NumberStates.selecting_region)
async def search_number_region_start(callback: CallbackQuery, state: FSMContext):
    """Начало поиска региона"""
    data = await state.get_data()
    selected = data.get("selected_number_resources", [])

    await state.set_state(NumberStates.searching_region)

    resources_text = ", ".join(NumberResource(r).display_name for r in selected)

    await callback.message.edit_text(
        f"📱 <b>Номера телефонов</b>\n\n"
        f"Ресурсы: <b>{resources_text}</b>\n\n"
        f"🔍 Введите номер региона:",
        reply_markup=get_number_back_to_region_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(NumberStates.searching_region)
async def search_number_region_input(message: Message, state: FSMContext):
    """Обработка ввода региона"""
    region = message.text.strip()
    data = await state.get_data()
    selected = data.get("selected_number_resources", [])

    resources_text = ", ".join(NumberResource(r).display_name for r in selected)

    if not region:
        await message.answer(
            "❌ Введите номер региона:",
            reply_markup=get_number_back_to_region_keyboard(),
        )
        return

    # Валидация региона
    if not region_service.region_exists(region):
        available = ", ".join(region_service.get_regions()[:5])
        await message.answer(
            f"❌ Такого региона не существует: <b>{region}</b>\n\n"
            f"Доступные регионы: {available}...\n"
            f"Введите существующий регион или выберите из списка:",
            reply_markup=get_number_back_to_region_keyboard(),
            parse_mode="HTML",
        )
        return

    await state.update_data(number_region=region)
    await state.set_state(NumberStates.selecting_quantity)

    await message.answer(
        f"📱 <b>Номера телефонов</b>\n\n"
        f"Ресурсы: <b>{resources_text}</b>\n"
        f"Регион: <b>{region}</b>\n\n"
        f"Выберите количество:",
        reply_markup=get_number_quantity_keyboard(),
        parse_mode="HTML",
    )


# === Выбор количества и выдача ===

@router.callback_query(NumberQuantityCallback.filter(), NumberStates.selecting_quantity)
async def select_number_quantity_and_issue(
    callback: CallbackQuery,
    callback_data: NumberQuantityCallback,
    state: FSMContext,
):
    """Выбор количества и выдача номеров"""
    await callback.answer()

    quantity = callback_data.quantity
    data = await state.get_data()
    selected = data.get("selected_number_resources", [])
    region = data.get("number_region", "")

    resources_text = ", ".join(NumberResource(r).display_name for r in selected)

    # Показываем загрузку
    await callback.message.edit_text(
        f"📱 <b>Номера телефонов</b>\n\n"
        f"Ресурсы: <b>{resources_text}</b>\n"
        f"Регион: <b>{region}</b>\n"
        f"Количество: <b>{quantity}</b>\n\n"
        f"⏳ <i>Загрузка номеров...</i>",
        parse_mode="HTML",
    )

    # Получаем stage пользователя
    try:
        user = await sheets_service.get_user_by_telegram_id(callback.from_user.id)
        employee_stage = user.stage if user else "unknown"
    except Exception:
        employee_stage = "unknown"

    try:
        # Выдаём номера
        issued = await number_service.issue_numbers(
            resources=selected,
            region=region,
            quantity=quantity,
            employee_stage=employee_stage,
        )

        if not issued:
            mode_text = "сегодня" if number_service.today_only else ""
            await callback.message.edit_text(
                f"❌ Номера не найдены{' (добавленные ' + mode_text + ')' if mode_text else ''}.\n\n"
                "Попробуйте другие параметры."
            )
            await state.clear()
            await callback.message.answer(
                "Выберите ресурс:",
                reply_markup=get_resource_keyboard(),
            )
            return

        # Показываем результат
        await callback.message.edit_text(
            f"<b>✅ Выдано номеров: {len(issued)}</b>\n\n"
            f"Ресурсы: {resources_text}\n"
            f"Регион: {region}",
            parse_mode="HTML",
        )

        # Отправляем каждый номер отдельным сообщением
        for item in issued:
            number = item["number"]
            date_added = item.get("date_added", "")

            await callback.message.answer(
                f"📱 <code>{number}</code>\n\n"
                f"<i>Добавлен: {date_added}</i>",
                parse_mode="HTML",
            )

        # Предлагаем продолжить
        await callback.message.answer(
            f"✅ Выдано номеров: {len(issued)}\n\n"
            "Для получения новых — выберите ресурс:",
            reply_markup=get_resource_keyboard(),
        )

    except Exception as e:
        logger.error(f"Error issuing numbers: {e}")
        await callback.message.edit_text(
            "❌ Произошла ошибка при выдаче номеров.\n\n"
            "Попробуйте позже."
        )
        await callback.message.answer(
            "Выберите ресурс:",
            reply_markup=get_resource_keyboard(),
        )

    await state.clear()


# === Кнопки назад ===

@router.callback_query(NumberBackCallback.filter(F.to == "resources"))
async def back_to_number_resources(callback: CallbackQuery, state: FSMContext):
    """Возврат к выбору ресурсов"""
    data = await state.get_data()
    selected = data.get("selected_number_resources", [])

    await state.set_state(NumberStates.selecting_resources)

    mode_text = "только сегодняшние" if number_service.today_only else "все"

    await callback.message.edit_text(
        f"📱 <b>Номера телефонов</b>\n\n"
        f"Режим: {mode_text}\n\n"
        f"Выберите ресурсы (можно несколько):",
        reply_markup=get_number_resource_keyboard(selected),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(NumberBackCallback.filter(F.to == "region"))
async def back_to_number_region(callback: CallbackQuery, state: FSMContext):
    """Возврат к выбору региона"""
    data = await state.get_data()
    selected = data.get("selected_number_resources", [])

    await state.set_state(NumberStates.selecting_region)

    resources_text = ", ".join(NumberResource(r).display_name for r in selected)

    await callback.message.edit_text(
        f"📱 <b>Номера телефонов</b>\n\n"
        f"Ресурсы: <b>{resources_text}</b>\n\n"
        f"Выберите регион:",
        reply_markup=get_number_region_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(NumberBackCallback.filter(F.to == "main"))
async def back_to_main_menu(callback: CallbackQuery, state: FSMContext):
    """Возврат в главное меню выбора ресурсов"""
    await callback.answer()
    await state.clear()
    await state.set_state(AccountFlowStates.selecting_resource)

    await callback.message.edit_text(
        "Выберите ресурс:",
        reply_markup=get_resource_keyboard(),
    )
