import logging

from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext

from bot.states.states import AccountFlowStates
from bot.keyboards.callbacks import (
    ResourceCallback,
    RegionCallback,
    QuantityCallback,
    GenderCallback,
    BackCallback,
    SearchRegionCallback,
)
from bot.keyboards.inline import (
    get_resource_keyboard,
    get_region_keyboard,
    get_quantity_keyboard,
    get_gender_keyboard,
    get_feedback_keyboard,
)
from bot.models.enums import Resource, Gender
from bot.services.account_service import account_service
from bot.services.sheets_service import sheets_service
from bot.utils.formatters import format_account_message, format_selection_summary

logger = logging.getLogger(__name__)
router = Router()


@router.callback_query(ResourceCallback.filter(), AccountFlowStates.selecting_resource)
async def process_resource(
    callback: CallbackQuery,
    callback_data: ResourceCallback,
    state: FSMContext,
):
    """Обработка выбора ресурса"""
    await callback.answer()
    resource = Resource(callback_data.resource)

    await state.update_data(resource=resource)
    await state.set_state(AccountFlowStates.selecting_region)

    await callback.message.edit_text(
        f"Ресурс: <b>{resource.display_name}</b>\n\n"
        f"Выберите регион:",
        reply_markup=get_region_keyboard(),
        parse_mode="HTML",
    )


@router.callback_query(RegionCallback.filter(), AccountFlowStates.selecting_region)
async def process_region(
    callback: CallbackQuery,
    callback_data: RegionCallback,
    state: FSMContext,
):
    """Обработка выбора региона"""
    await callback.answer()
    region = callback_data.region
    data = await state.get_data()
    resource = data["resource"]

    await state.update_data(region=region)
    await state.set_state(AccountFlowStates.selecting_quantity)

    await callback.message.edit_text(
        f"Ресурс: <b>{resource.display_name}</b>\n"
        f"Регион: <b>{region}</b>\n\n"
        f"Выберите количество:",
        reply_markup=get_quantity_keyboard(),
        parse_mode="HTML",
    )


@router.callback_query(SearchRegionCallback.filter(), AccountFlowStates.selecting_region)
async def search_region_start(callback: CallbackQuery, state: FSMContext):
    """Начало поиска региона"""
    await callback.answer()
    from bot.keyboards.inline import get_back_to_region_keyboard

    data = await state.get_data()
    resource = data["resource"]

    await state.set_state(AccountFlowStates.searching_region)
    await callback.message.edit_text(
        f"Ресурс: <b>{resource.display_name}</b>\n\n"
        f"🔍 Введите номер региона (например: 77, 50, 197):",
        reply_markup=get_back_to_region_keyboard(),
        parse_mode="HTML",
    )


from bot.services.region_service import region_service


def is_valid_region(region: str) -> bool:
    """Проверка существования региона в системе"""
    return region_service.region_exists(region)


@router.message(AccountFlowStates.searching_region)
async def search_region_input(message: Message, state: FSMContext):
    """Обработка ввода региона"""
    from bot.keyboards.inline import get_back_to_region_keyboard

    region = message.text.strip()
    data = await state.get_data()
    resource = data["resource"]

    if not region:
        await message.answer(
            "❌ Введите номер региона:",
            reply_markup=get_back_to_region_keyboard(),
        )
        return

    # Валидация региона
    if not is_valid_region(region):
        available = ", ".join(region_service.get_regions()[:5])
        await message.answer(
            f"❌ Такого региона не существует: <b>{region}</b>\n\n"
            f"Доступные регионы: {available}...\n"
            f"Введите существующий регион или выберите из списка:",
            reply_markup=get_back_to_region_keyboard(),
            parse_mode="HTML",
        )
        return

    # Сохраняем регион и переходим к выбору количества
    await state.update_data(region=region)
    await state.set_state(AccountFlowStates.selecting_quantity)

    await message.answer(
        f"Ресурс: <b>{resource.display_name}</b>\n"
        f"Регион: <b>{region}</b>\n\n"
        f"Выберите количество:",
        reply_markup=get_quantity_keyboard(),
        parse_mode="HTML",
    )


@router.callback_query(QuantityCallback.filter(), AccountFlowStates.selecting_quantity)
async def process_quantity(
    callback: CallbackQuery,
    callback_data: QuantityCallback,
    state: FSMContext,
):
    """Обработка выбора количества"""
    await callback.answer()
    quantity = callback_data.quantity
    data = await state.get_data()
    resource = data["resource"]
    region = data["region"]

    await state.update_data(quantity=quantity)
    await state.set_state(AccountFlowStates.selecting_gender)

    await callback.message.edit_text(
        f"Ресурс: <b>{resource.display_name}</b>\n"
        f"Регион: <b>{region}</b>\n"
        f"Количество: <b>{quantity}</b>\n\n"
        f"Выберите тип:",
        reply_markup=get_gender_keyboard(resource),
        parse_mode="HTML",
    )


@router.callback_query(GenderCallback.filter(), AccountFlowStates.selecting_gender)
async def process_gender_and_issue(
    callback: CallbackQuery,
    callback_data: GenderCallback,
    state: FSMContext,
):
    """Обработка выбора пола и выдача аккаунтов"""
    # Сразу отвечаем на callback чтобы избежать timeout
    await callback.answer()

    gender = Gender(callback_data.gender)
    data = await state.get_data()
    resource = data["resource"]
    region = data["region"]
    quantity = data["quantity"]

    # Показываем статус загрузки
    await callback.message.edit_text(
        f"{format_selection_summary(resource, region, quantity, gender.display_name)}\n\n"
        f"⏳ <i>Загрузка аккаунтов...</i>",
        parse_mode="HTML",
    )

    # Получаем stage пользователя
    try:
        user = await sheets_service.get_user_by_telegram_id(callback.from_user.id)
        employee_stage = user.stage if user else "unknown"
    except Exception:
        employee_stage = "unknown"

    try:
        # Выдаём аккаунты
        issued = await account_service.issue_accounts(
            resource=resource,
            region=region,
            quantity=quantity,
            gender=gender,
            employee_stage=employee_stage,
        )

        if not issued:
            await callback.message.edit_text(
                "❌ К сожалению, аккаунты не найдены.\n\n"
                "Попробуйте другие параметры."
            )
            await state.set_state(AccountFlowStates.selecting_resource)
            await callback.message.answer(
                "Выберите ресурс:",
                reply_markup=get_resource_keyboard(),
            )
            return

        # Обновляем сводку
        await callback.message.edit_text(
            f"<b>Выдано:</b>\n"
            f"Ресурс: {resource.display_name}\n"
            f"Регион: {region}\n"
            f"Количество: {len(issued)}\n"
            f"Тип: {gender.display_name}",
            parse_mode="HTML",
        )

        # Отправляем каждый аккаунт отдельным сообщением
        for item in issued:
            account = item["account"]
            account_id = item["account_id"]

            message_text = format_account_message(resource, account, region)

            await callback.message.answer(
                message_text,
                reply_markup=get_feedback_keyboard(
                    account_id=account_id,
                    resource=resource.value,
                    gender=gender.value,
                    region=region,
                ),
                parse_mode="HTML",
            )

        # Предлагаем продолжить
        await callback.message.answer(
            f"✅ Выдано аккаунтов: {len(issued)}\n\n"
            "Для получения новых аккаунтов выберите ресурс:",
            reply_markup=get_resource_keyboard(),
        )

    except Exception as e:
        logger.error(f"Error issuing accounts: {e}")
        await callback.message.edit_text(
            f"❌ Произошла ошибка при выдаче аккаунтов.\n\n"
            f"Попробуйте позже."
        )
        await callback.message.answer(
            "Выберите ресурс:",
            reply_markup=get_resource_keyboard(),
        )

    await state.set_state(AccountFlowStates.selecting_resource)


# === Обработка кнопки "Назад" ===


@router.callback_query(BackCallback.filter(F.to == "resource"))
async def back_to_resource(callback: CallbackQuery, state: FSMContext):
    """Возврат к выбору ресурса"""
    await callback.answer()
    await state.set_state(AccountFlowStates.selecting_resource)
    await callback.message.edit_text(
        "Выберите ресурс:",
        reply_markup=get_resource_keyboard(),
    )


@router.callback_query(BackCallback.filter(F.to == "region"))
async def back_to_region(callback: CallbackQuery, state: FSMContext):
    """Возврат к выбору региона"""
    await callback.answer()
    data = await state.get_data()
    resource = data.get("resource")

    if not resource:
        await state.set_state(AccountFlowStates.selecting_resource)
        await callback.message.edit_text(
            "Выберите ресурс:",
            reply_markup=get_resource_keyboard(),
        )
    else:
        await state.set_state(AccountFlowStates.selecting_region)
        await callback.message.edit_text(
            f"Ресурс: <b>{resource.display_name}</b>\n\n"
            f"Выберите регион:",
            reply_markup=get_region_keyboard(),
            parse_mode="HTML",
        )


@router.callback_query(BackCallback.filter(F.to == "region"), AccountFlowStates.searching_region)
async def back_to_region_from_search(callback: CallbackQuery, state: FSMContext):
    """Возврат к выбору региона из режима поиска"""
    await callback.answer()
    data = await state.get_data()
    resource = data.get("resource")

    await state.set_state(AccountFlowStates.selecting_region)
    await callback.message.edit_text(
        f"Ресурс: <b>{resource.display_name}</b>\n\n"
        f"Выберите регион:",
        reply_markup=get_region_keyboard(),
        parse_mode="HTML",
    )


@router.callback_query(BackCallback.filter(F.to == "quantity"))
async def back_to_quantity(callback: CallbackQuery, state: FSMContext):
    """Возврат к выбору количества"""
    await callback.answer()
    data = await state.get_data()
    resource = data.get("resource")
    region = data.get("region")

    if not resource or not region:
        await state.set_state(AccountFlowStates.selecting_resource)
        await callback.message.edit_text(
            "Выберите ресурс:",
            reply_markup=get_resource_keyboard(),
        )
    else:
        await state.set_state(AccountFlowStates.selecting_quantity)
        await callback.message.edit_text(
            f"Ресурс: <b>{resource.display_name}</b>\n"
            f"Регион: <b>{region}</b>\n\n"
            f"Выберите количество:",
            reply_markup=get_quantity_keyboard(),
            parse_mode="HTML",
        )
