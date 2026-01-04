"""Клавиатуры для аренды временных почт через quix.email"""
from typing import List, Dict, Any
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardMarkup

from bot.keyboards.callbacks import (
    EmailRentalDomainCallback,
    EmailRentalDomainPageCallback,
    EmailRentalCancelCallback,
    EmailRentalRepeatCallback,
    EmailRentalBackCallback,
)

# Количество доменов на одной странице
DOMAINS_PER_PAGE = 12


def get_email_rental_enter_site_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для ввода домена сайта (только кнопка назад)"""
    builder = InlineKeyboardBuilder()
    builder.button(
        text="« Назад",
        callback_data=EmailRentalBackCallback(to="email_menu"),
    )
    builder.adjust(1)
    return builder.as_markup()


def get_email_rental_domains_keyboard(
    domains: List[Dict[str, Any]],
    page: int = 0,
) -> InlineKeyboardMarkup:
    """
    Клавиатура выбора домена почты с пагинацией.

    Args:
        domains: Список доменов [{domain, quantity, price}, ...]
        page: Номер страницы (0-based)
    """
    builder = InlineKeyboardBuilder()

    # Вычисляем пагинацию
    total_pages = (len(domains) + DOMAINS_PER_PAGE - 1) // DOMAINS_PER_PAGE
    start_idx = page * DOMAINS_PER_PAGE
    end_idx = min(start_idx + DOMAINS_PER_PAGE, len(domains))
    page_domains = domains[start_idx:end_idx]

    # Кнопки доменов
    for domain_info in page_domains:
        domain = domain_info.get("domain", "")
        quantity = domain_info.get("quantity", 0)
        price = domain_info.get("price", 0)

        # Формат: "gmail.com (5)" где 5 - количество
        if quantity > 0:
            text = f"{domain} ({quantity})"
        else:
            text = domain

        builder.button(
            text=text,
            callback_data=EmailRentalDomainCallback(domain=domain),
        )

    # Кнопки пагинации (если нужны)
    if total_pages > 1:
        nav_buttons = []

        if page > 0:
            builder.button(
                text="◀️",
                callback_data=EmailRentalDomainPageCallback(page=page - 1),
            )

        builder.button(
            text=f"{page + 1}/{total_pages}",
            callback_data=EmailRentalDomainPageCallback(page=page),  # Текущая страница
        )

        if page < total_pages - 1:
            builder.button(
                text="▶️",
                callback_data=EmailRentalDomainPageCallback(page=page + 1),
            )

    # Кнопка назад
    builder.button(
        text="« Назад",
        callback_data=EmailRentalBackCallback(to="enter_site"),
    )

    # Layout: домены по 2, затем навигация, затем назад
    domains_count = len(page_domains)
    rows = [2] * (domains_count // 2)
    if domains_count % 2:
        rows.append(1)

    if total_pages > 1:
        # Кнопки навигации: prev, current, next (или меньше)
        nav_count = 1  # минимум текущая страница
        if page > 0:
            nav_count += 1
        if page < total_pages - 1:
            nav_count += 1
        rows.append(nav_count)

    rows.append(1)  # Назад

    builder.adjust(*rows)
    return builder.as_markup()


def get_email_rental_waiting_keyboard(activation_id: str) -> InlineKeyboardMarkup:
    """Клавиатура ожидания письма с кнопкой отмены"""
    builder = InlineKeyboardBuilder()
    builder.button(
        text="❌ Отменить",
        callback_data=EmailRentalCancelCallback(activation_id=activation_id),
    )
    builder.adjust(1)
    return builder.as_markup()


def get_email_rental_received_keyboard(
    activation_id: str,
    email: str,
    site: str,
) -> InlineKeyboardMarkup:
    """Клавиатура после получения письма с кнопкой повторного запроса"""
    builder = InlineKeyboardBuilder()
    builder.button(
        text="🔄 Запросить ещё раз",
        callback_data=EmailRentalRepeatCallback(
            activation_id=activation_id,
            email=email,
            site=site,
        ),
    )
    builder.adjust(1)
    return builder.as_markup()


def get_email_rental_timeout_keyboard(
    activation_id: str,
    email: str,
    site: str,
) -> InlineKeyboardMarkup:
    """Клавиатура при таймауте (письмо не пришло)"""
    builder = InlineKeyboardBuilder()
    builder.button(
        text="🔄 Попробовать снова",
        callback_data=EmailRentalRepeatCallback(
            activation_id=activation_id,
            email=email,
            site=site,
        ),
    )
    builder.button(
        text="❌ Отменить",
        callback_data=EmailRentalCancelCallback(activation_id=activation_id),
    )
    builder.adjust(1, 1)
    return builder.as_markup()


def get_email_rental_error_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура при ошибке (только назад)"""
    builder = InlineKeyboardBuilder()
    builder.button(
        text="« Назад в меню почт",
        callback_data=EmailRentalBackCallback(to="email_menu"),
    )
    builder.adjust(1)
    return builder.as_markup()
