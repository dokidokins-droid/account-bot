import logging

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from bot.states.states import ProxyStates, AccountFlowStates
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
)
from bot.keyboards.proxy_keyboards import (
    get_proxy_menu_keyboard,
    get_proxy_resource_keyboard,
    get_proxy_duration_keyboard,
    get_proxy_countries_keyboard,
    get_proxy_list_keyboard,
    get_proxy_back_keyboard,
    get_proxy_type_keyboard,
    get_proxy_resource_multi_keyboard,
)
from bot.keyboards.inline import get_resource_keyboard
from bot.models.enums import ProxyResource, ProxyDuration, ProxyType, get_country_flag
from bot.services.proxy_service import get_proxy_service

logger = logging.getLogger(__name__)
router = Router()


# === Вход в прокси из главного меню ресурсов ===

@router.callback_query(ProxyMenuCallback.filter(F.action == "open"), AccountFlowStates.selecting_resource)
async def proxy_from_main_menu(
    callback: CallbackQuery,
    state: FSMContext,
):
    """Переход в меню прокси из главного меню выбора ресурсов"""
    await callback.answer()
    await state.set_state(ProxyStates.main_menu)
    await callback.message.edit_text(
        "🌐 <b>Прокси</b>\n\n"
        "Выберите действие:",
        reply_markup=get_proxy_menu_keyboard(),
        parse_mode="HTML",
    )


# === Главное меню прокси ===

@router.callback_query(ProxyMenuCallback.filter(), ProxyStates.main_menu)
async def proxy_menu_action(
    callback: CallbackQuery,
    callback_data: ProxyMenuCallback,
    state: FSMContext,
):
    """Обработка выбора в главном меню прокси"""
    await callback.answer()
    action = callback_data.action

    if action == "add":
        await state.set_state(ProxyStates.add_selecting_type)
        await callback.message.edit_text(
            "➕ <b>Добавление прокси</b>\n\n"
            "Выберите тип прокси:",
            reply_markup=get_proxy_type_keyboard(),
            parse_mode="HTML",
        )

    elif action == "get":
        await state.set_state(ProxyStates.get_selecting_resource)
        await callback.message.edit_text(
            "📥 <b>Получение прокси</b>\n\n"
            "Выберите ресурс:",
            reply_markup=get_proxy_resource_keyboard("get"),
            parse_mode="HTML",
        )


# === Добавление прокси ===

@router.callback_query(ProxyTypeCallback.filter(), ProxyStates.add_selecting_type)
async def add_proxy_type(
    callback: CallbackQuery,
    callback_data: ProxyTypeCallback,
    state: FSMContext,
):
    """Выбор типа прокси (HTTP/SOCKS5)"""
    proxy_type = ProxyType(callback_data.proxy_type)

    await state.update_data(proxy_type=proxy_type.value)
    await state.set_state(ProxyStates.add_waiting_proxy)

    await callback.message.edit_text(
        f"➕ <b>Добавление прокси</b>\n"
        f"Тип: <b>{proxy_type.display_name}</b>\n\n"
        "Отправьте прокси (каждый с новой строки):\n"
        "<code>ip:port</code> или <code>ip:port:user:pass</code>",
        reply_markup=get_proxy_back_keyboard("type"),
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(ProxyStates.add_waiting_proxy)
async def add_proxy_receive(message: Message, state: FSMContext):
    """Получение текста с прокси"""
    text = message.text.strip()

    if not text:
        await message.answer(
            "❌ Отправьте список прокси",
            reply_markup=get_proxy_back_keyboard("type"),
        )
        return

    # Парсим прокси (каждая строка = отдельный прокси)
    proxies = [line.strip() for line in text.split("\n") if line.strip()]

    if not proxies:
        await message.answer(
            "❌ Не удалось распознать прокси",
            reply_markup=get_proxy_back_keyboard("type"),
        )
        return

    # Сохраняем в state
    await state.update_data(proxies=proxies, selected_resources=[])
    await state.set_state(ProxyStates.add_selecting_resources)

    await message.answer(
        f"📝 Получено прокси: <b>{len(proxies)}</b>\n\n"
        "Выберите ресурсы, для которых использовались:\n"
        "<i>(можно выбрать несколько)</i>",
        reply_markup=get_proxy_resource_multi_keyboard([]),
        parse_mode="HTML",
    )


@router.callback_query(ProxyResourceToggleCallback.filter(), ProxyStates.add_selecting_resources)
async def add_proxy_toggle_resource(
    callback: CallbackQuery,
    callback_data: ProxyResourceToggleCallback,
    state: FSMContext,
):
    """Toggle выбора ресурса (добавить/убрать)"""
    resource = callback_data.resource
    data = await state.get_data()
    selected = data.get("selected_resources", [])

    # Toggle ресурса
    if resource in selected:
        selected.remove(resource)
    else:
        selected.append(resource)

    await state.update_data(selected_resources=selected)

    # Обновляем клавиатуру
    proxies = data.get("proxies", [])
    await callback.message.edit_text(
        f"📝 Получено прокси: <b>{len(proxies)}</b>\n\n"
        "Выберите ресурсы, для которых использовались:\n"
        "<i>(можно выбрать несколько)</i>",
        reply_markup=get_proxy_resource_multi_keyboard(selected),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(ProxyResourceConfirmCallback.filter(), ProxyStates.add_selecting_resources)
async def add_proxy_confirm_resources(
    callback: CallbackQuery,
    state: FSMContext,
):
    """Подтверждение выбора ресурсов"""
    data = await state.get_data()
    selected = data.get("selected_resources", [])

    if not selected:
        await callback.answer("❌ Выберите хотя бы один ресурс!", show_alert=True)
        return

    # Формируем текст выбранных ресурсов
    resource_names = []
    for r in selected:
        try:
            resource_names.append(ProxyResource(r).display_name)
        except ValueError:
            resource_names.append(r)

    await state.set_state(ProxyStates.add_selecting_duration)

    await callback.message.edit_text(
        f"📝 Ресурсы: <b>{', '.join(resource_names)}</b>\n\n"
        "Выберите срок действия:",
        reply_markup=get_proxy_duration_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(ProxyDurationCallback.filter(), ProxyStates.add_selecting_duration)
async def add_proxy_duration(
    callback: CallbackQuery,
    callback_data: ProxyDurationCallback,
    state: FSMContext,
):
    """Выбор срока и сохранение прокси"""
    await callback.answer()

    duration = ProxyDuration(callback_data.duration)
    data = await state.get_data()
    proxies = data.get("proxies", [])
    selected_resources = data.get("selected_resources", [])
    proxy_type = data.get("proxy_type", "http")

    # Показываем статус
    await callback.message.edit_text(
        f"⏳ Добавление {len(proxies)} прокси...\n"
        f"Определение стран по IP...",
        parse_mode="HTML",
    )

    try:
        # Добавляем прокси с новыми параметрами
        results = await get_proxy_service().add_proxies(
            proxies=proxies,
            resources=selected_resources,
            duration_days=duration.days,
            proxy_type=proxy_type,
        )

        # Формируем отчёт
        lines = [f"✅ <b>Добавлено прокси: {len(results)}</b>\n"]
        for r in results[:10]:  # Показываем первые 10
            lines.append(f"• {r['proxy'][:20]}... {r['country_flag']} ({r['country']})")
        if len(results) > 10:
            lines.append(f"\n... и ещё {len(results) - 10}")

        await callback.message.edit_text(
            "\n".join(lines),
            parse_mode="HTML",
        )

    except Exception as e:
        logger.error(f"Error adding proxies: {e}")
        await callback.message.edit_text(
            "❌ Произошла ошибка при добавлении прокси",
        )

    # Возвращаемся в главное меню
    await state.clear()
    await state.set_state(AccountFlowStates.selecting_resource)
    await callback.message.answer(
        "Выберите ресурс:",
        reply_markup=get_resource_keyboard(),
    )


# === Получение прокси ===

@router.callback_query(ProxyResourceCallback.filter(F.mode == "get"), ProxyStates.get_selecting_resource)
async def get_proxy_resource(
    callback: CallbackQuery,
    callback_data: ProxyResourceCallback,
    state: FSMContext,
):
    """Выбор ресурса при получении прокси"""
    await callback.answer()

    resource = ProxyResource(callback_data.resource)
    await state.update_data(get_resource=resource.value)

    # Показываем загрузку
    await callback.message.edit_text(
        f"📥 Ресурс: <b>{resource.display_name}</b>\n\n"
        "⏳ Загрузка...",
        parse_mode="HTML",
    )

    try:
        # Получаем страны с количеством
        countries = await get_proxy_service().get_countries_with_counts(resource.value)

        if not countries:
            await callback.message.edit_text(
                f"📥 Ресурс: <b>{resource.display_name}</b>\n\n"
                "❌ Нет доступных прокси для этого ресурса",
                reply_markup=get_proxy_back_keyboard("resource"),
                parse_mode="HTML",
            )
            return

        await state.set_state(ProxyStates.get_selecting_country)
        await callback.message.edit_text(
            f"📥 Ресурс: <b>{resource.display_name}</b>\n\n"
            "Выберите страну:",
            reply_markup=get_proxy_countries_keyboard(countries),
            parse_mode="HTML",
        )

    except Exception as e:
        logger.error(f"Error getting countries: {e}")
        await callback.message.edit_text(
            "❌ Ошибка при загрузке прокси",
            reply_markup=get_proxy_back_keyboard("menu"),
        )


@router.callback_query(ProxyCountryCallback.filter(), ProxyStates.get_selecting_country)
async def get_proxy_country(
    callback: CallbackQuery,
    callback_data: ProxyCountryCallback,
    state: FSMContext,
):
    """Выбор страны"""
    await callback.answer()

    country = callback_data.country
    data = await state.get_data()
    resource = data.get("get_resource", "")

    await state.update_data(get_country=country)

    try:
        # Получаем прокси для страны
        proxies = await get_proxy_service().get_proxies_by_country(resource, country)

        if not proxies:
            await callback.message.edit_text(
                f"❌ Нет доступных прокси для страны {get_country_flag(country)}",
                reply_markup=get_proxy_back_keyboard("country"),
            )
            return

        await state.set_state(ProxyStates.get_selecting_proxy)
        flag = get_country_flag(country)

        await callback.message.edit_text(
            f"📥 Страна: {flag} <b>{country}</b>\n"
            f"Доступно: {len(proxies)}\n\n"
            "Выберите прокси:",
            reply_markup=get_proxy_list_keyboard(proxies, country, page=0),
            parse_mode="HTML",
        )

    except Exception as e:
        logger.error(f"Error getting proxies by country: {e}")
        await callback.message.edit_text(
            "❌ Ошибка при загрузке прокси",
            reply_markup=get_proxy_back_keyboard("country"),
        )


@router.callback_query(ProxyPageCallback.filter(), ProxyStates.get_selecting_proxy)
async def proxy_pagination(
    callback: CallbackQuery,
    callback_data: ProxyPageCallback,
    state: FSMContext,
):
    """Пагинация прокси"""
    await callback.answer()

    page = callback_data.page
    country = callback_data.country
    data = await state.get_data()
    resource = data.get("get_resource", "")

    try:
        proxies = await get_proxy_service().get_proxies_by_country(resource, country)
        flag = get_country_flag(country)

        await callback.message.edit_text(
            f"📥 Страна: {flag} <b>{country}</b>\n"
            f"Доступно: {len(proxies)}\n\n"
            "Выберите прокси:",
            reply_markup=get_proxy_list_keyboard(proxies, country, page=page),
            parse_mode="HTML",
        )

    except Exception as e:
        logger.error(f"Error in pagination: {e}")
        await callback.message.edit_text(
            "❌ Ошибка при загрузке",
            reply_markup=get_proxy_back_keyboard("country"),
        )


@router.callback_query(ProxySelectCallback.filter(), ProxyStates.get_selecting_proxy)
async def proxy_select(
    callback: CallbackQuery,
    callback_data: ProxySelectCallback,
    state: FSMContext,
):
    """Выбор конкретного прокси"""
    row_index = callback_data.row_index
    data = await state.get_data()
    resource = data.get("get_resource", "")
    country = data.get("get_country", "")
    user_id = callback.from_user.id

    # Пытаемся взять прокси
    proxy = await get_proxy_service().try_take_proxy(row_index, resource, user_id)

    if proxy is None:
        # Прокси уже занят - обновляем список
        await callback.answer("❌ Этот прокси уже занят!", show_alert=True)

        # Обновляем список
        try:
            proxies = await get_proxy_service().get_proxies_by_country(resource, country)
            flag = get_country_flag(country)

            if proxies:
                await callback.message.edit_text(
                    f"📥 Страна: {flag} <b>{country}</b>\n"
                    f"Доступно: {len(proxies)}\n\n"
                    "Выберите прокси:",
                    reply_markup=get_proxy_list_keyboard(proxies, country, page=0),
                    parse_mode="HTML",
                )
            else:
                await callback.message.edit_text(
                    f"❌ Больше нет доступных прокси для {flag}",
                    reply_markup=get_proxy_back_keyboard("country"),
                )
        except Exception as e:
            logger.error(f"Error refreshing proxy list: {e}")

        return

    # Успешно взяли прокси
    await callback.answer("✅ Прокси получен!")

    flag = get_country_flag(proxy.country)
    resource_obj = ProxyResource(resource)

    # Формируем список использований
    used_for_names = []
    for r in proxy.used_for:
        try:
            used_for_names.append(ProxyResource(r).display_name)
        except ValueError:
            used_for_names.append(r)
    used_for_text = ", ".join(used_for_names) if used_for_names else "—"

    # Получаем оба формата прокси (HTTP и SOCKS5)
    http_proxy = proxy.get_http_proxy()
    socks5_proxy = proxy.get_socks5_proxy()

    # Определяем тип для отображения
    proxy_type_display = "HTTP" if proxy.proxy_type == "http" else "SOCKS5"

    await callback.message.edit_text(
        f"✅ <b>Прокси получен</b>\n\n"
        f"Ресурс: {resource_obj.display_name}\n"
        f"Страна: {flag} {proxy.country}\n"
        f"Тип: {proxy_type_display}\n"
        f"Осталось дней: {proxy.days_left}\n"
        f"Использован для: {used_for_text}\n\n"
        f"<b>HTTP:</b>\n<code>{http_proxy}</code>\n\n"
        f"<b>SOCKS5:</b>\n<code>{socks5_proxy}</code>",
        parse_mode="HTML",
    )

    # Возвращаемся к выбору ресурса для получения прокси
    await state.clear()
    await state.set_state(ProxyStates.get_selecting_resource)
    await callback.message.answer(
        "📥 <b>Получение прокси</b>\n\n"
        "Выберите ресурс:",
        reply_markup=get_proxy_resource_keyboard("get"),
        parse_mode="HTML",
    )


# === Кнопки "Назад" ===

@router.callback_query(ProxyBackCallback.filter(F.to == "main"))
async def proxy_back_to_main(callback: CallbackQuery, state: FSMContext):
    """Возврат в главное меню выбора ресурсов"""
    await state.clear()
    await state.set_state(AccountFlowStates.selecting_resource)
    await callback.message.edit_text(
        "Выберите ресурс:",
        reply_markup=get_resource_keyboard(),
    )
    await callback.answer()


@router.callback_query(ProxyBackCallback.filter(F.to == "menu"))
async def proxy_back_to_menu(callback: CallbackQuery, state: FSMContext):
    """Возврат в главное меню прокси"""
    await state.set_state(ProxyStates.main_menu)
    await callback.message.edit_text(
        "🌐 <b>Прокси</b>\n\n"
        "Выберите действие:",
        reply_markup=get_proxy_menu_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(ProxyBackCallback.filter(F.to == "type"))
async def proxy_back_to_type(callback: CallbackQuery, state: FSMContext):
    """Возврат к выбору типа прокси"""
    await state.set_state(ProxyStates.add_selecting_type)
    await callback.message.edit_text(
        "➕ <b>Добавление прокси</b>\n\n"
        "Выберите тип прокси:",
        reply_markup=get_proxy_type_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(ProxyBackCallback.filter(F.to == "resource"))
async def proxy_back_to_resource(callback: CallbackQuery, state: FSMContext):
    """Возврат к выбору ресурса"""
    current_state = await state.get_state()

    if current_state and "add_" in current_state:
        mode = "add"
        text = "➕ <b>Добавление прокси</b>\n\nВыберите ресурс:"
    else:
        mode = "get"
        text = "📥 <b>Получение прокси</b>\n\nВыберите ресурс:"

    await state.set_state(
        ProxyStates.add_selecting_resource if mode == "add"
        else ProxyStates.get_selecting_resource
    )

    await callback.message.edit_text(
        text,
        reply_markup=get_proxy_resource_keyboard(mode),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(ProxyBackCallback.filter(F.to == "country"))
async def proxy_back_to_country(callback: CallbackQuery, state: FSMContext):
    """Возврат к выбору страны"""
    data = await state.get_data()
    resource = data.get("get_resource", "")

    await state.set_state(ProxyStates.get_selecting_country)

    try:
        countries = await get_proxy_service().get_countries_with_counts(resource)
        resource_obj = ProxyResource(resource)

        await callback.message.edit_text(
            f"📥 Ресурс: <b>{resource_obj.display_name}</b>\n\n"
            "Выберите страну:",
            reply_markup=get_proxy_countries_keyboard(countries),
            parse_mode="HTML",
        )
    except Exception as e:
        logger.error(f"Error going back to countries: {e}")
        await callback.message.edit_text(
            "❌ Ошибка при загрузке",
            reply_markup=get_proxy_back_keyboard("menu"),
        )

    await callback.answer()
