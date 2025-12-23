"""Клавиатуры для работы с номерами телефонов"""
from typing import List

from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardMarkup

from bot.keyboards.callbacks import (
    NumberResourceToggleCallback,
    NumberResourceConfirmCallback,
    NumberRegionCallback,
    NumberSearchRegionCallback,
    NumberQuantityCallback,
    NumberBackCallback,
    NumberTodayModeCallback,
    NumberFeedbackCallback,
    NumberReplaceCallback,
)
from bot.models.enums import NumberResource, NumberStatus
from bot.services.region_service import region_service


def get_number_resource_keyboard(selected: List[str]) -> InlineKeyboardMarkup:
    """Клавиатура множественного выбора ресурсов для номеров"""
    builder = InlineKeyboardBuilder()

    for resource in NumberResource:
        # Добавляем галочку если ресурс выбран
        if resource.value in selected:
            text = f"✅ {resource.button_text}"
        else:
            text = resource.button_text

        builder.button(
            text=text,
            callback_data=NumberResourceToggleCallback(resource=resource.value),
        )

    # Если выбран хотя бы один ресурс — "Подтвердить", иначе — "Назад"
    if selected:
        builder.button(
            text="✅ Подтвердить",
            callback_data=NumberResourceConfirmCallback(),
        )
    else:
        builder.button(
            text="« Назад",
            callback_data=NumberBackCallback(to="main"),
        )

    # Layout: ресурсы в ряд (3 шт), кнопка подтверждения/назад на отдельной строке
    builder.adjust(3, 1)
    return builder.as_markup()


def get_number_region_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора региона для номеров"""
    builder = InlineKeyboardBuilder()

    # Получаем отсортированный список регионов
    for region in region_service.get_regions():
        builder.button(
            text=region,
            callback_data=NumberRegionCallback(region=region),
        )

    # Кнопка поиска
    builder.button(
        text="🔍 Поиск",
        callback_data=NumberSearchRegionCallback(),
    )

    # Кнопка назад
    builder.button(
        text="« Назад",
        callback_data=NumberBackCallback(to="resources"),
    )

    # Layout: регионы по 3, затем поиск и назад по одной
    regions_count = len(region_service.get_regions())
    builder.adjust(*([3] * (regions_count // 3 + (1 if regions_count % 3 else 0))), 1, 1)
    return builder.as_markup()


def get_number_back_to_region_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура с кнопкой возврата к выбору региона"""
    builder = InlineKeyboardBuilder()
    builder.button(
        text="« Назад к списку регионов",
        callback_data=NumberBackCallback(to="region"),
    )
    builder.adjust(1)
    return builder.as_markup()


def get_number_quantity_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора количества номеров"""
    builder = InlineKeyboardBuilder()

    for qty in range(1, 6):
        builder.button(
            text=str(qty),
            callback_data=NumberQuantityCallback(quantity=qty),
        )

    # Кнопка назад
    builder.button(
        text="« Назад",
        callback_data=NumberBackCallback(to="region"),
    )

    builder.adjust(5, 1)
    return builder.as_markup()


def get_number_today_mode_keyboard(today_only: bool) -> InlineKeyboardMarkup:
    """Клавиатура для переключения режима today_only"""
    builder = InlineKeyboardBuilder()

    if today_only:
        builder.button(
            text="🔴 Выключить (разрешить все номера)",
            callback_data=NumberTodayModeCallback(action="disable"),
        )
    else:
        builder.button(
            text="🟢 Включить (только сегодняшние)",
            callback_data=NumberTodayModeCallback(action="enable"),
        )

    builder.adjust(1)
    return builder.as_markup()


def get_number_feedback_keyboard(number_id: str, resources: str, region: str) -> InlineKeyboardMarkup:
    """Клавиатура фидбека по номеру"""
    builder = InlineKeyboardBuilder()

    for status in NumberStatus:
        builder.button(
            text=status.display_name,
            callback_data=NumberFeedbackCallback(
                action=status.value,
                number_id=number_id,
                resources=resources,
                region=region,
            ),
        )

    # Layout: 4 кнопки в 2 ряда по 2
    builder.adjust(2, 2)
    return builder.as_markup()


def get_number_replace_keyboard(resources: str, region: str) -> InlineKeyboardMarkup:
    """Клавиатура с кнопкой замены номера"""
    builder = InlineKeyboardBuilder()
    builder.button(
        text="🔄 Заменить",
        callback_data=NumberReplaceCallback(resources=resources, region=region),
    )
    builder.adjust(1)
    return builder.as_markup()
