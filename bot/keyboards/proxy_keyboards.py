from typing import List, Dict, Set
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardMarkup

from bot.keyboards.callbacks import (
    ProxyMenuCallback,
    ProxyResourceCallback,
    ProxyDurationCallback,
    ProxyCountryCallback,
    ProxySelectCallback,
    ProxyPageCallback,
    ProxyBackCallback,
    ProxyTypeCallback,
    ProxyResourceToggleCallback,
    ProxyResourceConfirmCallback,
    ProxyGetResourceToggleCallback,
    ProxyGetResourceConfirmCallback,
    ProxyToggleCallback,
    ProxyConfirmMultiCallback,
)
from bot.models.enums import ProxyResource, ProxyDuration, ProxyType, get_country_flag, get_country_name
from bot.models.proxy import Proxy

# Количество прокси на странице (2x5 сетка)
PROXIES_PER_PAGE = 10


def get_proxy_menu_keyboard() -> InlineKeyboardMarkup:
    """Главное меню прокси: добавить или получить"""
    builder = InlineKeyboardBuilder()
    builder.button(
        text="➕ Добавить прокси",
        callback_data=ProxyMenuCallback(action="add"),
    )
    builder.button(
        text="📥 Получить прокси",
        callback_data=ProxyMenuCallback(action="get"),
    )
    builder.button(
        text="« Назад",
        callback_data=ProxyBackCallback(to="main"),
    )
    builder.adjust(1)
    return builder.as_markup()


def get_proxy_resource_keyboard(mode: str) -> InlineKeyboardMarkup:
    """Клавиатура выбора ресурса для прокси"""
    builder = InlineKeyboardBuilder()

    # Все ресурсы кроме OTHER
    main_resources = [r for r in ProxyResource if r != ProxyResource.OTHER]
    for resource in main_resources:
        builder.button(
            text=resource.button_text,
            callback_data=ProxyResourceCallback(resource=resource.value, mode=mode),
        )

    # OTHER (Другие) на отдельной строке
    builder.button(
        text=ProxyResource.OTHER.button_text,
        callback_data=ProxyResourceCallback(resource=ProxyResource.OTHER.value, mode=mode),
    )

    # Кнопка назад: для get - в главное меню ресурсов, для add - в меню прокси
    back_to = "main" if mode == "get" else "menu"
    builder.button(
        text="« Назад",
        callback_data=ProxyBackCallback(to=back_to),
    )

    # Динамический layout: основные ресурсы по 2, затем Другие и Назад по 1
    rows = [2] * (len(main_resources) // 2)
    if len(main_resources) % 2:
        rows.append(1)
    rows.extend([1, 1])  # Другие + Назад

    builder.adjust(*rows)
    return builder.as_markup()


def get_proxy_duration_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора срока действия прокси"""
    builder = InlineKeyboardBuilder()
    for duration in ProxyDuration:
        builder.button(
            text=duration.button_text,
            callback_data=ProxyDurationCallback(duration=duration.value),
        )
    # Кнопка назад
    builder.button(
        text="« Назад",
        callback_data=ProxyBackCallback(to="resource"),
    )
    builder.adjust(4, 1)
    return builder.as_markup()


def get_proxy_countries_keyboard(countries: Dict[str, int]) -> InlineKeyboardMarkup:
    """Клавиатура выбора страны с количеством прокси"""
    builder = InlineKeyboardBuilder()

    # Сортируем по количеству (больше = выше)
    sorted_countries = sorted(countries.items(), key=lambda x: x[1], reverse=True)

    for country_code, count in sorted_countries:
        flag = get_country_flag(country_code)
        name = get_country_name(country_code)
        builder.button(
            text=f"{flag} {name} ({count})",
            callback_data=ProxyCountryCallback(country=country_code),
        )

    # Кнопка назад к выбору ресурса
    builder.button(
        text="« Назад",
        callback_data=ProxyBackCallback(to="resource"),
    )

    # Раскладка: по 2 в ряд для стран (т.к. с названиями длиннее), затем кнопка назад
    rows = [2] * (len(sorted_countries) // 2)
    if len(sorted_countries) % 2:
        rows.append(1)
    rows.append(1)  # Кнопка назад

    builder.adjust(*rows)
    return builder.as_markup()


def get_proxy_list_keyboard(
    proxies: List[Proxy],
    country: str,
    page: int = 0,
) -> InlineKeyboardMarkup:
    """Клавиатура списка прокси с пагинацией"""
    builder = InlineKeyboardBuilder()

    total_pages = (len(proxies) + PROXIES_PER_PAGE - 1) // PROXIES_PER_PAGE
    start_idx = page * PROXIES_PER_PAGE
    end_idx = min(start_idx + PROXIES_PER_PAGE, len(proxies))

    page_proxies = proxies[start_idx:end_idx]

    # Кнопки прокси
    for proxy in page_proxies:
        flag = get_country_flag(proxy.country)
        text = f"{proxy.ip_short} {flag} ({proxy.days_left}д)"
        builder.button(
            text=text,
            callback_data=ProxySelectCallback(row_index=proxy.row_index),
        )

    # По 2 прокси в ряд
    proxy_rows = [2] * (len(page_proxies) // 2)
    if len(page_proxies) % 2:
        proxy_rows.append(1)

    # Пагинация
    pagination_buttons = []
    if page > 0:
        pagination_buttons.append(("« Пред", page - 1))
    if page < total_pages - 1:
        pagination_buttons.append(("След »", page + 1))

    for text, pg in pagination_buttons:
        builder.button(
            text=text,
            callback_data=ProxyPageCallback(page=pg, country=country),
        )

    if pagination_buttons:
        proxy_rows.append(len(pagination_buttons))

    # Кнопка назад
    builder.button(
        text="« К странам",
        callback_data=ProxyBackCallback(to="country"),
    )
    proxy_rows.append(1)

    builder.adjust(*proxy_rows)
    return builder.as_markup()


def get_proxy_back_keyboard(to: str = "menu") -> InlineKeyboardMarkup:
    """Клавиатура с кнопкой назад"""
    builder = InlineKeyboardBuilder()
    builder.button(
        text="« Назад",
        callback_data=ProxyBackCallback(to=to),
    )
    builder.adjust(1)
    return builder.as_markup()


def get_proxy_type_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора типа прокси (HTTP/SOCKS5)"""
    builder = InlineKeyboardBuilder()
    for proxy_type in ProxyType:
        builder.button(
            text=proxy_type.button_text,
            callback_data=ProxyTypeCallback(proxy_type=proxy_type.value),
        )
    builder.button(
        text="« Назад",
        callback_data=ProxyBackCallback(to="menu"),
    )
    builder.adjust(2, 1)
    return builder.as_markup()


def get_proxy_resource_multi_keyboard(selected: List[str]) -> InlineKeyboardMarkup:
    """Клавиатура множественного выбора ресурсов для прокси"""
    builder = InlineKeyboardBuilder()

    # Все ресурсы кроме OTHER
    main_resources = [r for r in ProxyResource if r != ProxyResource.OTHER]
    for resource in main_resources:
        check = "✅ " if resource.value in selected else ""
        builder.button(
            text=f"{check}{resource.button_text}",
            callback_data=ProxyResourceToggleCallback(resource=resource.value),
        )

    # OTHER (Другие) на отдельной строке
    check = "✅ " if ProxyResource.OTHER.value in selected else ""
    builder.button(
        text=f"{check}{ProxyResource.OTHER.button_text}",
        callback_data=ProxyResourceToggleCallback(resource=ProxyResource.OTHER.value),
    )

    # Кнопка подтвердить ИЛИ назад (заменяют друг друга)
    if selected:
        builder.button(
            text="✅ Подтвердить",
            callback_data=ProxyResourceConfirmCallback(),
        )
    else:
        builder.button(
            text="« Назад",
            callback_data=ProxyBackCallback(to="type"),
        )

    # Динамический layout: основные ресурсы по 2, затем Другие, Подтвердить или Назад
    rows = [2] * (len(main_resources) // 2)
    if len(main_resources) % 2:
        rows.append(1)
    rows.append(1)  # Другие
    rows.append(1)  # Подтвердить или Назад

    builder.adjust(*rows)
    return builder.as_markup()


def get_proxy_resource_multi_keyboard_get(selected: List[str]) -> InlineKeyboardMarkup:
    """
    Клавиатура множественного выбора ресурсов при ПОЛУЧЕНИИ прокси.

    Аналогична get_proxy_resource_multi_keyboard, но с другой кнопкой "Назад"
    и другими callback-ами.
    """
    builder = InlineKeyboardBuilder()

    # Все ресурсы кроме OTHER
    main_resources = [r for r in ProxyResource if r != ProxyResource.OTHER]
    for resource in main_resources:
        check = "✅ " if resource.value in selected else ""
        builder.button(
            text=f"{check}{resource.button_text}",
            callback_data=ProxyGetResourceToggleCallback(resource=resource.value),
        )

    # OTHER (Другие) на отдельной строке
    check = "✅ " if ProxyResource.OTHER.value in selected else ""
    builder.button(
        text=f"{check}{ProxyResource.OTHER.button_text}",
        callback_data=ProxyGetResourceToggleCallback(resource=ProxyResource.OTHER.value),
    )

    # Кнопка подтвердить ИЛИ назад (заменяют друг друга)
    if selected:
        builder.button(
            text="✅ Подтвердить",
            callback_data=ProxyGetResourceConfirmCallback(),
        )
    else:
        builder.button(
            text="« Назад",
            callback_data=ProxyBackCallback(to="menu"),
        )

    # Динамический layout
    rows = [2] * (len(main_resources) // 2)
    if len(main_resources) % 2:
        rows.append(1)
    rows.append(1)  # Другие
    rows.append(1)  # Подтвердить или Назад

    builder.adjust(*rows)
    return builder.as_markup()


def get_proxy_list_multi_keyboard(
    proxies: List[Proxy],
    country: str,
    selected_rows: Set[int],
    total_selected: int = 0,
    page: int = 0,
) -> InlineKeyboardMarkup:
    """
    Клавиатура списка прокси с множественным выбором.

    Args:
        proxies: Список доступных прокси (уже отсортированный по days_left DESC)
        country: Код страны
        selected_rows: Set индексов выбранных строк (для этой страны)
        total_selected: Общее количество выбранных прокси (всех стран)
        page: Текущая страница

    Returns:
        Клавиатура с флагами/галочками, пагинацией и кнопкой подтверждения
    """
    builder = InlineKeyboardBuilder()

    total_pages = (len(proxies) + PROXIES_PER_PAGE - 1) // PROXIES_PER_PAGE
    start_idx = page * PROXIES_PER_PAGE
    end_idx = min(start_idx + PROXIES_PER_PAGE, len(proxies))

    page_proxies = proxies[start_idx:end_idx]
    flag = get_country_flag(country)

    # Кнопки прокси: флаг → галочка при выборе
    for proxy in page_proxies:
        is_selected = proxy.row_index in selected_rows
        icon = "✅" if is_selected else flag
        text = f"{icon} {proxy.ip_short} ({proxy.days_left}д)"
        builder.button(
            text=text,
            callback_data=ProxyToggleCallback(
                row_index=proxy.row_index,
                country=country,
                page=page
            ),
        )

    # По 2 прокси в ряд (сетка 2x5)
    proxy_rows = [2] * (len(page_proxies) // 2)
    if len(page_proxies) % 2:
        proxy_rows.append(1)

    # Кнопка подтверждения (если есть выбранные - показываем общее количество)
    if total_selected > 0:
        builder.button(
            text=f"✅ Подтвердить ({total_selected})",
            callback_data=ProxyConfirmMultiCallback(country=country),
        )
        proxy_rows.append(1)

    # Пагинация
    pagination_buttons = []
    if page > 0:
        pagination_buttons.append(("« Пред", page - 1))
    if page < total_pages - 1:
        pagination_buttons.append(("След »", page + 1))

    for text, pg in pagination_buttons:
        builder.button(
            text=text,
            callback_data=ProxyPageCallback(page=pg, country=country),
        )

    if pagination_buttons:
        proxy_rows.append(len(pagination_buttons))

    # Кнопка назад к странам
    builder.button(
        text="« К странам",
        callback_data=ProxyBackCallback(to="country"),
    )
    proxy_rows.append(1)

    builder.adjust(*proxy_rows)
    return builder.as_markup()
