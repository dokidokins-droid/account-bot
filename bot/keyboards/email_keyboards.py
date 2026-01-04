"""Клавиатуры для работы с почтами (новый flow с умным распределением)"""
from typing import List
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
    EmailModeCallback,
    EmailTargetResourceToggleCallback,
    EmailTargetResourceConfirmCallback,
    EmailRentalMenuCallback,
)
from bot.models.enums import EmailResource, EmailType, EmailMode, EmailTargetResource
from bot.services.region_service import region_service


def get_email_menu_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора почтового домена (Gmail/Рамблер)"""
    builder = InlineKeyboardBuilder()

    for resource in EmailResource:
        builder.button(
            text=resource.button_text,
            callback_data=EmailResourceCallback(resource=resource.value),
        )

    # Кнопка аренды временных почт
    builder.button(
        text="🔄 Аренда",
        callback_data=EmailRentalMenuCallback(action="open"),
    )

    # Кнопка назад в главное меню
    builder.button(
        text="« Назад",
        callback_data=EmailBackCallback(to="main"),
    )

    builder.adjust(2, 1, 1)
    return builder.as_markup()


def get_email_type_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора типа Gmail (Любые / только gmail.com)"""
    builder = InlineKeyboardBuilder()

    # Только ANY и GMAIL_DOMAIN (NONE для Rambler)
    for email_type in [EmailType.ANY, EmailType.GMAIL_DOMAIN]:
        builder.button(
            text=email_type.display_name,
            callback_data=EmailTypeCallback(email_type=email_type.value),
        )

    # Кнопка назад к выбору домена
    builder.button(
        text="« Назад",
        callback_data=EmailBackCallback(to="email_resource"),
    )

    builder.adjust(2, 1)
    return builder.as_markup()


def get_email_region_keyboard(email_resource: EmailResource) -> InlineKeyboardMarkup:
    """Клавиатура выбора региона для почт.

    Для Gmail кнопка "Назад" ведёт к выбору типа.
    Для Rambler — к выбору домена.
    """
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

    # Кнопка назад: для Gmail — к типу, для Rambler — к ресурсу
    if email_resource == EmailResource.GMAIL:
        back_to = "email_type"
    else:
        back_to = "email_resource"

    builder.button(
        text="« Назад",
        callback_data=EmailBackCallback(to=back_to),
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


def get_email_mode_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора режима (Новая/Эконом)"""
    builder = InlineKeyboardBuilder()

    for mode in EmailMode:
        # Показываем кнопку с эмодзи и описанием
        builder.button(
            text=mode.button_text,
            callback_data=EmailModeCallback(mode=mode.value),
        )

    # Кнопка назад к выбору региона
    builder.button(
        text="« Назад",
        callback_data=EmailBackCallback(to="region"),
    )

    builder.adjust(2, 1)
    return builder.as_markup()


def get_email_target_resource_keyboard(selected: List[str]) -> InlineKeyboardMarkup:
    """
    Клавиатура множественного выбора целевых ресурсов для почты.
    Аналогична клавиатуре прокси.
    """
    builder = InlineKeyboardBuilder()

    # Все ресурсы кроме OTHER
    main_resources = [r for r in EmailTargetResource if r != EmailTargetResource.OTHER]
    for resource in main_resources:
        check = "✅ " if resource.value in selected else ""
        builder.button(
            text=f"{check}{resource.button_text}",
            callback_data=EmailTargetResourceToggleCallback(resource=resource.value),
        )

    # OTHER (Другие) на отдельной строке
    check = "✅ " if EmailTargetResource.OTHER.value in selected else ""
    builder.button(
        text=f"{check}{EmailTargetResource.OTHER.button_text}",
        callback_data=EmailTargetResourceToggleCallback(resource=EmailTargetResource.OTHER.value),
    )

    # Кнопка подтвердить ИЛИ назад (заменяют друг друга)
    if selected:
        builder.button(
            text="✅ Подтвердить",
            callback_data=EmailTargetResourceConfirmCallback(),
        )
    else:
        builder.button(
            text="« Назад",
            callback_data=EmailBackCallback(to="mode"),
        )

    # Динамический layout: основные ресурсы по 2, затем Другие, Подтвердить или Назад
    rows = [2] * (len(main_resources) // 2)
    if len(main_resources) % 2:
        rows.append(1)
    rows.append(1)  # Другие
    rows.append(1)  # Подтвердить или Назад

    builder.adjust(*rows)
    return builder.as_markup()


def get_email_quantity_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора количества почт"""
    builder = InlineKeyboardBuilder()

    for qty in range(1, 6):
        builder.button(
            text=str(qty),
            callback_data=EmailQuantityCallback(quantity=qty),
        )

    # Кнопка назад к выбору ресурсов
    builder.button(
        text="« Назад",
        callback_data=EmailBackCallback(to="target_resources"),
    )

    builder.adjust(5, 1)
    return builder.as_markup()


def get_email_feedback_keyboard(
    email_id: str,
    resource: str,
    region: str,
    target_resources: str,  # Через запятую
) -> InlineKeyboardMarkup:
    """Клавиатура фидбека по почте.

    Статусы:
    - Блок: почта заблокирована, недоступна для выдачи
    - Авторизация: просит авторизацию, недоступна для выдачи
    - Хороший: работает нормально
    - Дефектный: есть проблемы, но можно использовать
    """
    builder = InlineKeyboardBuilder()
    builder.button(
        text="🚫 Блок",
        callback_data=EmailFeedbackCallback(
            action="block",
            email_id=email_id,
            resource=resource,
            email_type="none",  # Больше не используется, но нужен для совместимости
            region=region,
        ),
    )
    builder.button(
        text="🔐 Авторизация",
        callback_data=EmailFeedbackCallback(
            action="auth",
            email_id=email_id,
            resource=resource,
            email_type="none",
            region=region,
        ),
    )
    builder.button(
        text="✅ Хороший",
        callback_data=EmailFeedbackCallback(
            action="good",
            email_id=email_id,
            resource=resource,
            email_type="none",
            region=region,
        ),
    )
    builder.button(
        text="⚠️ Дефектный",
        callback_data=EmailFeedbackCallback(
            action="defect",
            email_id=email_id,
            resource=resource,
            email_type="none",
            region=region,
        ),
    )
    builder.adjust(2, 2)  # 2 кнопки в первом ряду, 2 во втором
    return builder.as_markup()


def get_email_replace_keyboard(
    resource: str,
    region: str,
    target_resources: str,
) -> InlineKeyboardMarkup:
    """Клавиатура с кнопкой замены почты"""
    builder = InlineKeyboardBuilder()
    builder.button(
        text="🔄 Заменить",
        callback_data=EmailReplaceCallback(
            resource=resource,
            email_type="none",  # Для совместимости
            region=region,
        ),
    )
    builder.adjust(1)
    return builder.as_markup()
