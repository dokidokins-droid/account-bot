"""Клавиатуры для работы с почтами"""
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardMarkup

from bot.keyboards.callbacks import (
    EmailResourceCallback,
    EmailTypeCallback,
    EmailRegionCallback,
    EmailSearchRegionCallback,
    EmailQuantityCallback,
    EmailBackCallback,
    EmailFeedbackCallback,
    EmailReplaceCallback,
)
from bot.models.enums import EmailResource, Gender
from bot.services.region_service import region_service


def get_email_menu_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора почтового ресурса (Gmail/Рамблер)"""
    builder = InlineKeyboardBuilder()

    for resource in EmailResource:
        builder.button(
            text=resource.button_text,
            callback_data=EmailResourceCallback(resource=resource.value),
        )

    # Кнопка назад в главное меню
    builder.button(
        text="« Назад",
        callback_data=EmailBackCallback(to="main"),
    )

    builder.adjust(2, 1)
    return builder.as_markup()


def get_email_type_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора типа Gmail (Обычные/gmail.com)"""
    builder = InlineKeyboardBuilder()

    # Обычные
    builder.button(
        text=Gender.ANY.button_text,
        callback_data=EmailTypeCallback(email_type=Gender.ANY.value),
    )
    # gmail.com
    builder.button(
        text=Gender.GMAIL_DOMAIN.button_text,
        callback_data=EmailTypeCallback(email_type=Gender.GMAIL_DOMAIN.value),
    )

    # Кнопка назад к выбору ресурса
    builder.button(
        text="« Назад",
        callback_data=EmailBackCallback(to="email_resource"),
    )

    builder.adjust(2, 1)
    return builder.as_markup()


def get_email_region_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора региона для почт"""
    builder = InlineKeyboardBuilder()

    # Получаем отсортированный список регионов из сервиса
    for region in region_service.get_regions():
        builder.button(
            text=region,
            callback_data=EmailRegionCallback(region=region),
        )

    # Кнопка поиска
    builder.button(
        text="🔍 Поиск",
        callback_data=EmailSearchRegionCallback(),
    )

    # Кнопка назад
    builder.button(
        text="« Назад",
        callback_data=EmailBackCallback(to="email_type"),
    )

    # Регионы по 3 в ряд, затем поиск и назад по одной кнопке
    regions_count = len(region_service.get_regions())
    builder.adjust(*([3] * (regions_count // 3 + (1 if regions_count % 3 else 0))), 1, 1)
    return builder.as_markup()


def get_email_region_keyboard_rambler() -> InlineKeyboardMarkup:
    """Клавиатура выбора региона для Рамблер (без типа)"""
    builder = InlineKeyboardBuilder()

    # Получаем отсортированный список регионов из сервиса
    for region in region_service.get_regions():
        builder.button(
            text=region,
            callback_data=EmailRegionCallback(region=region),
        )

    # Кнопка поиска
    builder.button(
        text="🔍 Поиск",
        callback_data=EmailSearchRegionCallback(),
    )

    # Кнопка назад к выбору ресурса
    builder.button(
        text="« Назад",
        callback_data=EmailBackCallback(to="email_resource"),
    )

    # Регионы по 3 в ряд, затем поиск и назад по одной кнопке
    regions_count = len(region_service.get_regions())
    builder.adjust(*([3] * (regions_count // 3 + (1 if regions_count % 3 else 0))), 1, 1)
    return builder.as_markup()


def get_email_back_to_region_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура с кнопкой возврата к выбору региона (для режима поиска)"""
    builder = InlineKeyboardBuilder()
    builder.button(
        text="« Назад к списку регионов",
        callback_data=EmailBackCallback(to="region"),
    )
    builder.adjust(1)
    return builder.as_markup()


def get_email_quantity_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора количества почт"""
    builder = InlineKeyboardBuilder()

    for qty in range(1, 6):
        builder.button(
            text=str(qty),
            callback_data=EmailQuantityCallback(quantity=qty),
        )

    # Кнопка назад
    builder.button(
        text="« Назад",
        callback_data=EmailBackCallback(to="region"),
    )

    builder.adjust(5, 1)
    return builder.as_markup()


def get_email_feedback_keyboard(
    email_id: str,
    resource: str,
    email_type: str,
    region: str,
) -> InlineKeyboardMarkup:
    """Клавиатура фидбека по почте"""
    builder = InlineKeyboardBuilder()
    builder.button(
        text="🚫 Блок",
        callback_data=EmailFeedbackCallback(
            action="block", email_id=email_id, resource=resource, email_type=email_type, region=region
        ),
    )
    builder.button(
        text="✅ Хороший",
        callback_data=EmailFeedbackCallback(
            action="good", email_id=email_id, resource=resource, email_type=email_type, region=region
        ),
    )
    builder.button(
        text="⚠️ Дефектный",
        callback_data=EmailFeedbackCallback(
            action="defect", email_id=email_id, resource=resource, email_type=email_type, region=region
        ),
    )
    builder.adjust(3)
    return builder.as_markup()


def get_email_replace_keyboard(resource: str, email_type: str, region: str) -> InlineKeyboardMarkup:
    """Клавиатура с кнопкой замены почты"""
    builder = InlineKeyboardBuilder()
    builder.button(
        text="🔄 Заменить",
        callback_data=EmailReplaceCallback(resource=resource, email_type=email_type, region=region),
    )
    builder.adjust(1)
    return builder.as_markup()
