import logging

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramBadRequest

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
    ProxyGetResourceToggleCallback,
    ProxyGetResourceConfirmCallback,
    ProxyToggleCallback,
    ProxyConfirmMultiCallback,
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
    get_proxy_resource_multi_keyboard_get,
    get_proxy_list_multi_keyboard,
)
from bot.keyboards.inline import get_resource_keyboard
from bot.models.enums import ProxyResource, ProxyDuration, ProxyType, get_country_flag, get_country_name
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
        await state.update_data(get_selected_resources=[])
        await state.set_state(ProxyStates.get_selecting_resources)
        await callback.message.edit_text(
            "📥 <b>Получение прокси</b>\n\n"
            "Выберите ресурс\\сы, для которых будет использован прокси:\n"
            "<i>(можно выбрать несколько, если эти прокси для них используются)</i>",
            reply_markup=get_proxy_resource_multi_keyboard_get([]),
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
        "Отправьте прокси (каждый с новой строки).\n\n"
        "<b>Поддерживаемые форматы:</b>\n"
        "• <code>socks5://ip:port@user:pass</code>\n"
        "• <code>http://user:pass@ip:port</code>\n"
        "• <code>socks5://user:pass@ip:port</code>\n"
        "• <code>user:pass@ip:port</code>\n"
        "• <code>ip:port@user:pass</code>\n"
        "• <code>ip:port:user:pass</code>\n"
        "• <code>ip:port</code>",
        reply_markup=get_proxy_back_keyboard("type"),
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(ProxyStates.add_waiting_proxy)
async def add_proxy_receive(message: Message, state: FSMContext):
    """Получение текста с прокси"""
    from bot.utils.proxy_parser import parse_proxies

    text = message.text.strip()

    if not text:
        await message.answer(
            "❌ Отправьте список прокси",
            reply_markup=get_proxy_back_keyboard("type"),
        )
        return

    # Парсим прокси (каждая строка = отдельный прокси)
    lines = [line.strip() for line in text.split("\n") if line.strip()]

    if not lines:
        await message.answer(
            "❌ Не удалось распознать прокси",
            reply_markup=get_proxy_back_keyboard("type"),
        )
        return

    # Парсим и нормализуем прокси
    parsed, failed = parse_proxies(lines)

    if not parsed:
        await message.answer(
            "❌ Не удалось распознать ни одного прокси\n\n"
            "<b>Поддерживаемые форматы:</b>\n"
            "• <code>socks5://ip:port@user:pass</code>\n"
            "• <code>http://user:pass@ip:port</code>\n"
            "• <code>socks5://user:pass@ip:port</code>\n"
            "• <code>user:pass@ip:port</code>\n"
            "• <code>ip:port@user:pass</code>\n"
            "• <code>ip:port:user:pass</code>\n"
            "• <code>ip:port</code>",
            reply_markup=get_proxy_back_keyboard("type"),
            parse_mode="HTML",
        )
        return

    # Нормализуем в стандартный формат (ip:port:user:pass)
    proxies = [p.to_standard_format() for p in parsed]

    # Сохраняем в state
    await state.update_data(proxies=proxies, selected_resources=[])
    await state.set_state(ProxyStates.add_selecting_resources)

    # Формируем сообщение
    result_text = f"✅ Распознано прокси: <b>{len(parsed)}</b>\n"
    if failed:
        result_text += f"⚠️ Не распознано: <b>{len(failed)}</b>\n"

    result_text += "\nВыберите ресурсы, для которых использовались:\n<i>(можно выбрать несколько)</i>"

    await message.answer(
        result_text,
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

    except TelegramBadRequest as e:
        if "message is not modified" not in str(e):
            logger.error(f"Error adding proxies: {e}")
    except Exception as e:
        logger.error(f"Error adding proxies: {e}")
        try:
            await callback.message.edit_text("❌ Произошла ошибка при добавлении прокси")
        except TelegramBadRequest:
            pass

    # Возвращаемся в главное меню
    await state.clear()
    await state.set_state(AccountFlowStates.selecting_resource)
    await callback.message.answer(
        "📦 <b>Выдача аккаунтов</b>\n\n"
        "Выберите ресурс:",
        reply_markup=get_resource_keyboard(),
        parse_mode="HTML",
    )


# === Получение прокси: выбор ресурсов ===

@router.callback_query(ProxyGetResourceToggleCallback.filter(), ProxyStates.get_selecting_resources)
async def get_proxy_toggle_resource(
    callback: CallbackQuery,
    callback_data: ProxyGetResourceToggleCallback,
    state: FSMContext,
):
    """Toggle выбора ресурса при получении прокси"""
    resource = callback_data.resource
    data = await state.get_data()
    selected = data.get("get_selected_resources", [])

    # Toggle ресурса
    if resource in selected:
        selected.remove(resource)
    else:
        selected.append(resource)

    await state.update_data(get_selected_resources=selected)

    # Обновляем клавиатуру
    await callback.message.edit_text(
        "📥 <b>Получение прокси</b>\n\n"
        "Выберите ресурс\\сы, для которых будет использован прокси:\n"
        "<i>(можно выбрать несколько, если эти прокси для них используются)</i>",
        reply_markup=get_proxy_resource_multi_keyboard_get(selected),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(ProxyGetResourceConfirmCallback.filter(), ProxyStates.get_selecting_resources)
async def get_proxy_confirm_resources(
    callback: CallbackQuery,
    state: FSMContext,
):
    """Подтверждение выбора ресурсов при получении прокси"""
    data = await state.get_data()
    selected = data.get("get_selected_resources", [])

    if not selected:
        await callback.answer("❌ Выберите хотя бы один ресурс!", show_alert=True)
        return

    # Формируем текст выбранных ресурсов
    resource_names = []
    for r in selected:
        try:
            resource_names.append(ProxyResource(r).button_text)
        except ValueError:
            resource_names.append(r)

    await state.update_data(get_resources=selected)

    # Показываем загрузку
    await callback.message.edit_text(
        f"📥 Ресурсы: {', '.join(resource_names)}\n\n"
        "⏳ Загрузка...",
        parse_mode="HTML",
    )

    try:
        # Получаем страны с количеством
        countries = await get_proxy_service().get_countries_with_counts(selected)

        resources_text = ", ".join(resource_names)

        if not countries:
            await callback.message.edit_text(
                f"📥 Ресурсы: {resources_text}\n\n"
                "❌ Нет доступных прокси для этих ресурсов",
                reply_markup=get_proxy_back_keyboard("menu"),
                parse_mode="HTML",
            )
            return

        await state.set_state(ProxyStates.get_selecting_country)
        await callback.message.edit_text(
            f"📥 Ресурсы: {resources_text}\n\n"
            "Выберите страну:",
            reply_markup=get_proxy_countries_keyboard(countries),
            parse_mode="HTML",
        )

    except TelegramBadRequest as e:
        if "message is not modified" not in str(e):
            logger.error(f"Error getting countries: {e}")
    except Exception as e:
        logger.error(f"Error getting countries: {e}")
        try:
            await callback.message.edit_text(
                "❌ Ошибка при загрузке прокси",
                reply_markup=get_proxy_back_keyboard("menu"),
            )
        except TelegramBadRequest:
            pass

    await callback.answer()


# === Получение прокси: выбор страны и прокси ===

@router.callback_query(ProxyCountryCallback.filter(), ProxyStates.get_selecting_country)
async def get_proxy_country(
    callback: CallbackQuery,
    callback_data: ProxyCountryCallback,
    state: FSMContext,
):
    """Выбор страны - переход к множественному выбору прокси"""
    await callback.answer()

    country = callback_data.country
    data = await state.get_data()
    resources = data.get("get_resources", [])
    user_id = callback.from_user.id

    await state.update_data(get_country=country)

    try:
        # Получаем прокси с учётом резерваций текущего пользователя
        proxies, user_reserved = await get_proxy_service().get_proxies_for_user(
            resources, country, user_id
        )
        flag = get_country_flag(country)
        country_name = get_country_name(country)

        if not proxies:
            await callback.message.edit_text(
                f"❌ Нет доступных прокси для страны {flag} {country_name}",
                reply_markup=get_proxy_back_keyboard("country"),
            )
            return

        # Получаем общее количество выбранных (всех стран)
        all_reservations = await get_proxy_service().get_user_reservations(user_id)
        total_selected = len(all_reservations)

        # Переходим в режим множественного выбора
        await state.set_state(ProxyStates.get_multiselecting)

        await callback.message.edit_text(
            f"📥 Страна: {flag} <b>{country_name}</b>\n"
            f"Доступно: {len(proxies)} | Выбрано всего: {total_selected}\n\n"
            "Выберите прокси (можно несколько):",
            reply_markup=get_proxy_list_multi_keyboard(
                proxies, country, user_reserved, total_selected, page=0
            ),
            parse_mode="HTML",
        )

    except TelegramBadRequest as e:
        if "message is not modified" in str(e):
            return
        logger.error(f"Error getting proxies by country: {e}")
        await callback.message.edit_text(
            "❌ Ошибка при загрузке прокси",
            reply_markup=get_proxy_back_keyboard("country"),
        )
    except Exception as e:
        logger.error(f"Error getting proxies by country: {e}")
        await callback.message.edit_text(
            "❌ Ошибка при загрузке прокси",
            reply_markup=get_proxy_back_keyboard("country"),
        )


@router.callback_query(ProxyCountryCallback.filter(), ProxyStates.get_multiselecting)
async def switch_country_multiselect(
    callback: CallbackQuery,
    callback_data: ProxyCountryCallback,
    state: FSMContext,
):
    """Переключение между странами БЕЗ сброса выбора"""
    await callback.answer()

    country = callback_data.country
    data = await state.get_data()
    resources = data.get("get_resources", [])
    user_id = callback.from_user.id

    await state.update_data(get_country=country)

    try:
        proxies, user_reserved = await get_proxy_service().get_proxies_for_user(
            resources, country, user_id
        )
        flag = get_country_flag(country)
        country_name = get_country_name(country)

        # Общее количество выбранных всех стран
        all_reservations = await get_proxy_service().get_user_reservations(user_id)
        total_selected = len(all_reservations)

        if not proxies:
            await callback.message.edit_text(
                f"❌ Нет доступных прокси для страны {flag} {country_name}\n"
                f"Выбрано всего: {total_selected}",
                reply_markup=get_proxy_back_keyboard("country"),
            )
            return

        await callback.message.edit_text(
            f"📥 Страна: {flag} <b>{country_name}</b>\n"
            f"Доступно: {len(proxies)} | Выбрано всего: {total_selected}\n\n"
            "Выберите прокси (можно несколько):",
            reply_markup=get_proxy_list_multi_keyboard(
                proxies, country, user_reserved, total_selected, page=0
            ),
            parse_mode="HTML",
        )

    except TelegramBadRequest as e:
        if "message is not modified" not in str(e):
            logger.error(f"Error switching country: {e}")
    except Exception as e:
        logger.error(f"Error switching country: {e}")


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
    resources = data.get("get_resources", [])

    try:
        proxies = await get_proxy_service().get_proxies_by_country(resources, country)
        flag = get_country_flag(country)
        country_name = get_country_name(country)

        await callback.message.edit_text(
            f"📥 Страна: {flag} <b>{country_name}</b>\n"
            f"Доступно: {len(proxies)}\n\n"
            "Выберите прокси:",
            reply_markup=get_proxy_list_keyboard(proxies, country, page=page),
            parse_mode="HTML",
        )

    except TelegramBadRequest as e:
        if "message is not modified" not in str(e):
            logger.error(f"Error in pagination: {e}")
    except Exception as e:
        logger.error(f"Error in pagination: {e}")
        try:
            await callback.message.edit_text(
                "❌ Ошибка при загрузке",
                reply_markup=get_proxy_back_keyboard("country"),
            )
        except TelegramBadRequest:
            pass


@router.callback_query(ProxySelectCallback.filter(), ProxyStates.get_selecting_proxy)
async def proxy_select(
    callback: CallbackQuery,
    callback_data: ProxySelectCallback,
    state: FSMContext,
):
    """Выбор конкретного прокси"""
    row_index = callback_data.row_index
    data = await state.get_data()
    resources = data.get("get_resources", [])
    country = data.get("get_country", "")
    user_id = callback.from_user.id

    # Сначала получаем информацию о прокси ДО записи текущих ресурсов
    proxy_before = await get_proxy_service().get_proxy_by_row(row_index)
    previous_used_for = proxy_before.used_for if proxy_before else []

    # Пытаемся взять прокси (это добавит текущие ресурсы в used_for)
    proxy = await get_proxy_service().try_take_proxy(row_index, resources, user_id)

    if proxy is None:
        # Прокси уже занят - обновляем список
        await callback.answer("❌ Этот прокси уже занят!", show_alert=True)

        # Обновляем список
        try:
            proxies = await get_proxy_service().get_proxies_by_country(resources, country)
            flag = get_country_flag(country)
            country_name = get_country_name(country)

            if proxies:
                await callback.message.edit_text(
                    f"📥 Страна: {flag} <b>{country_name}</b>\n"
                    f"Доступно: {len(proxies)}\n\n"
                    "Выберите прокси:",
                    reply_markup=get_proxy_list_keyboard(proxies, country, page=0),
                    parse_mode="HTML",
                )
            else:
                await callback.message.edit_text(
                    f"❌ Больше нет доступных прокси для {flag} {country_name}",
                    reply_markup=get_proxy_back_keyboard("country"),
                )
        except TelegramBadRequest as e:
            if "message is not modified" not in str(e):
                logger.error(f"Error refreshing proxy list: {e}")
        except Exception as e:
            logger.error(f"Error refreshing proxy list: {e}")

        return

    # Успешно взяли прокси
    await callback.answer("✅ Прокси получен!")

    flag = get_country_flag(proxy.country)
    country_name = get_country_name(proxy.country)

    # Формируем названия ресурсов для отображения
    resource_names = []
    for r in resources:
        try:
            resource_names.append(ProxyResource(r).button_text)
        except ValueError:
            resource_names.append(r)
    resources_text = ", ".join(resource_names)

    # Формируем список ПРЕДЫДУЩИХ использований
    used_for_names = []
    for r in previous_used_for:
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
        f"<b>🌐 Прокси получен</b> | {resources_text}\n"
        f"Страна: {flag} {country_name}\n"
        f"Тип: {proxy_type_display}\n"
        f"Осталось дней: {proxy.days_left}\n"
        f"Ранее использован для: {used_for_text}\n\n"
        f"<b>HTTP:</b> <code>{http_proxy}</code>\n"
        f"<b>SOCKS5:</b> <code>{socks5_proxy}</code>",
        parse_mode="HTML",
    )

    # Возвращаемся к выбору ресурсов для получения прокси
    await state.clear()
    await state.set_state(ProxyStates.get_selecting_resources)
    await state.update_data(get_selected_resources=[])
    await callback.message.answer(
        "📥 <b>Получение прокси</b>\n\n"
        "Выберите ресурс\\сы, для которых будет использован прокси:\n"
        "<i>(можно выбрать несколько, если эти прокси для них используются)</i>",
        reply_markup=get_proxy_resource_multi_keyboard_get([]),
        parse_mode="HTML",
    )


# === Множественный выбор прокси ===

@router.callback_query(ProxyToggleCallback.filter(), ProxyStates.get_multiselecting)
async def proxy_toggle_selection(
    callback: CallbackQuery,
    callback_data: ProxyToggleCallback,
    state: FSMContext,
):
    """Toggle выбора прокси (добавить/убрать из выбранных)"""
    row_index = callback_data.row_index
    country = callback_data.country
    page = callback_data.page
    user_id = callback.from_user.id

    data = await state.get_data()
    resources = data.get("get_resources", [])

    service = get_proxy_service()

    # Проверяем текущие резервации пользователя
    user_reservations = await service.get_user_reservations(user_id)

    if row_index in user_reservations:
        # Уже выбран - отменяем резервацию
        await service.cancel_reservation(row_index, user_id)
        await callback.answer("Убрано из выбора")
    else:
        # Не выбран - резервируем
        reserved = await service.reserve_proxies([row_index], resources, user_id)
        if reserved:
            await callback.answer("Добавлено в выбор")
        else:
            await callback.answer("❌ Прокси уже занят!", show_alert=True)

    # Обновляем клавиатуру
    try:
        proxies, user_reserved = await service.get_proxies_for_user(resources, country, user_id)
        flag = get_country_flag(country)
        country_name = get_country_name(country)

        # Общее количество выбранных (все страны)
        all_reservations = await service.get_user_reservations(user_id)
        total_selected = len(all_reservations)

        await callback.message.edit_text(
            f"📥 Страна: {flag} <b>{country_name}</b>\n"
            f"Доступно: {len(proxies)} | Выбрано всего: {total_selected}\n\n"
            "Выберите прокси (можно несколько):",
            reply_markup=get_proxy_list_multi_keyboard(
                proxies, country, user_reserved, total_selected, page=page
            ),
            parse_mode="HTML",
        )
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e):
            logger.error(f"Error updating proxy list: {e}")


@router.callback_query(ProxyPageCallback.filter(), ProxyStates.get_multiselecting)
async def proxy_pagination_multi(
    callback: CallbackQuery,
    callback_data: ProxyPageCallback,
    state: FSMContext,
):
    """Пагинация в режиме множественного выбора"""
    await callback.answer()

    page = callback_data.page
    country = callback_data.country
    user_id = callback.from_user.id
    data = await state.get_data()
    resources = data.get("get_resources", [])

    try:
        service = get_proxy_service()
        proxies, user_reserved = await service.get_proxies_for_user(
            resources, country, user_id
        )
        flag = get_country_flag(country)
        country_name = get_country_name(country)

        # Общее количество выбранных (все страны)
        all_reservations = await service.get_user_reservations(user_id)
        total_selected = len(all_reservations)

        await callback.message.edit_text(
            f"📥 Страна: {flag} <b>{country_name}</b>\n"
            f"Доступно: {len(proxies)} | Выбрано всего: {total_selected}\n\n"
            "Выберите прокси (можно несколько):",
            reply_markup=get_proxy_list_multi_keyboard(
                proxies, country, user_reserved, total_selected, page=page
            ),
            parse_mode="HTML",
        )
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e):
            logger.error(f"Error in multi pagination: {e}")
    except Exception as e:
        logger.error(f"Error in multi pagination: {e}")


@router.callback_query(ProxyConfirmMultiCallback.filter(), ProxyStates.get_multiselecting)
async def proxy_confirm_multi(
    callback: CallbackQuery,
    callback_data: ProxyConfirmMultiCallback,
    state: FSMContext,
):
    """Подтверждение множественного выбора прокси"""
    user_id = callback.from_user.id
    data = await state.get_data()
    resources = data.get("get_resources", [])

    service = get_proxy_service()

    # Получаем резервации пользователя
    user_reservations = await service.get_user_reservations(user_id)

    if not user_reservations:
        await callback.answer("❌ Выберите хотя бы один прокси!", show_alert=True)
        return

    # Показываем статус
    await callback.message.edit_text(
        f"⏳ Получение {len(user_reservations)} прокси...",
        parse_mode="HTML",
    )

    try:
        # Batch update - один API запрос для всех прокси
        taken, failed = await service.take_proxies_batch(
            user_reservations, resources, user_id
        )

        if not taken:
            await callback.message.edit_text(
                "❌ Не удалось получить прокси. Попробуйте ещё раз.",
                reply_markup=get_proxy_back_keyboard("country"),
            )
            await callback.answer()
            return

        # Формируем названия выбранных ресурсов
        resource_names = []
        for r in resources:
            try:
                resource_names.append(ProxyResource(r).button_text)
            except ValueError:
                resource_names.append(r)
        resources_text = ", ".join(resource_names)

        # Заголовок с иконками ресурсов
        lines = [f"<b>✅ Получено прокси: {len(taken)}</b> | {resources_text}\n"]

        for proxy in taken:
            flag = get_country_flag(proxy.country)
            country_name = get_country_name(proxy.country)
            http_proxy = proxy.get_http_proxy()
            socks5_proxy = proxy.get_socks5_proxy()

            # Компактный формат: флаг ip (дней) страна + 2 строки для копирования
            lines.append(
                f"\n{flag} <b>{proxy.ip_short}</b> ({proxy.days_left}д) {country_name}\n"
                f"<code>{http_proxy}</code>\n"
                f"<code>{socks5_proxy}</code>"
            )

        if failed:
            lines.append(f"\n\n⚠️ Не удалось получить: {len(failed)} (уже заняты)")

        await callback.message.edit_text(
            "\n".join(lines),
            parse_mode="HTML",
        )

        await callback.answer("✅ Прокси получены!")

    except Exception as e:
        logger.error(f"Error confirming proxies: {e}")
        await callback.message.edit_text(
            "❌ Произошла ошибка при получении прокси",
            reply_markup=get_proxy_back_keyboard("country"),
        )
        await callback.answer()
        return

    # Возвращаемся к выбору ресурсов
    await state.clear()
    await state.set_state(ProxyStates.get_selecting_resources)
    await state.update_data(get_selected_resources=[])
    await callback.message.answer(
        "📥 <b>Получение прокси</b>\n\n"
        "Выберите ресурс\\сы, для которых будет использован прокси:\n"
        "<i>(можно выбрать несколько, если эти прокси для них используются)</i>",
        reply_markup=get_proxy_resource_multi_keyboard_get([]),
        parse_mode="HTML",
    )


# === Кнопки "Назад" ===

@router.callback_query(ProxyBackCallback.filter(F.to == "main"))
async def proxy_back_to_main(callback: CallbackQuery, state: FSMContext):
    """Возврат в главное меню выбора ресурсов"""
    user_id = callback.from_user.id
    # Очищаем резервации при выходе
    await get_proxy_service().cancel_all_reservations(user_id)

    await state.clear()
    await state.set_state(AccountFlowStates.selecting_resource)
    await callback.message.edit_text(
        "📦 <b>Выдача аккаунтов</b>\n\n"
        "Выберите ресурс:",
        reply_markup=get_resource_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(ProxyBackCallback.filter(F.to == "menu"))
async def proxy_back_to_menu(callback: CallbackQuery, state: FSMContext):
    """Возврат в главное меню прокси"""
    user_id = callback.from_user.id
    # Очищаем резервации при выходе
    await get_proxy_service().cancel_all_reservations(user_id)

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
    user_id = callback.from_user.id

    # Очищаем резервации при выходе из режима выбора прокси
    await get_proxy_service().cancel_all_reservations(user_id)

    if current_state and "add_" in current_state:
        await state.set_state(ProxyStates.add_selecting_resources)
        await state.update_data(selected_resources=[])
        await callback.message.edit_text(
            "➕ <b>Добавление прокси</b>\n\n"
            "Выберите ресурсы, для которых использовались:\n"
            "<i>(можно выбрать несколько)</i>",
            reply_markup=get_proxy_resource_multi_keyboard([]),
            parse_mode="HTML",
        )
    else:
        await state.set_state(ProxyStates.get_selecting_resources)
        await state.update_data(get_selected_resources=[])
        await callback.message.edit_text(
            "📥 <b>Получение прокси</b>\n\n"
            "Выберите ресурс\\сы, для которых будет использован прокси:\n"
            "<i>(можно выбрать несколько, если эти прокси для них используются)</i>",
            reply_markup=get_proxy_resource_multi_keyboard_get([]),
            parse_mode="HTML",
        )
    await callback.answer()


@router.callback_query(ProxyBackCallback.filter(F.to == "country"), ProxyStates.get_multiselecting)
async def proxy_back_to_country_multiselect(callback: CallbackQuery, state: FSMContext):
    """Возврат к выбору страны БЕЗ сброса выбранных прокси"""
    data = await state.get_data()
    resources = data.get("get_resources", [])
    user_id = callback.from_user.id

    # НЕ очищаем резервации - сохраняем выбор между странами
    all_reservations = await get_proxy_service().get_user_reservations(user_id)
    total_selected = len(all_reservations)

    # Формируем названия выбранных ресурсов
    resource_names = []
    for r in resources:
        try:
            resource_names.append(ProxyResource(r).button_text)
        except ValueError:
            resource_names.append(r)
    resources_text = ", ".join(resource_names) if resource_names else "не выбраны"

    # Остаёмся в режиме multiselecting для переключения между странами
    # Но показываем список стран

    try:
        countries = await get_proxy_service().get_countries_with_counts(resources)

        selected_text = f" | Выбрано: {total_selected}" if total_selected > 0 else ""

        await callback.message.edit_text(
            f"📥 Ресурсы: {resources_text}{selected_text}\n\n"
            "Выберите страну:",
            reply_markup=get_proxy_countries_keyboard(countries),
            parse_mode="HTML",
        )
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e):
            logger.error(f"Error going back to countries: {e}")
    except Exception as e:
        logger.error(f"Error going back to countries: {e}")
        try:
            await callback.message.edit_text(
                "❌ Ошибка при загрузке",
                reply_markup=get_proxy_back_keyboard("menu"),
            )
        except TelegramBadRequest:
            pass

    await callback.answer()


@router.callback_query(ProxyBackCallback.filter(F.to == "country"))
async def proxy_back_to_country(callback: CallbackQuery, state: FSMContext):
    """Возврат к выбору страны (из обычного режима)"""
    data = await state.get_data()
    resources = data.get("get_resources", [])

    await state.set_state(ProxyStates.get_selecting_country)

    # Формируем названия выбранных ресурсов
    resource_names = []
    for r in resources:
        try:
            resource_names.append(ProxyResource(r).button_text)
        except ValueError:
            resource_names.append(r)
    resources_text = ", ".join(resource_names) if resource_names else "не выбраны"

    try:
        countries = await get_proxy_service().get_countries_with_counts(resources)

        await callback.message.edit_text(
            f"📥 Ресурсы: {resources_text}\n\n"
            "Выберите страну:",
            reply_markup=get_proxy_countries_keyboard(countries),
            parse_mode="HTML",
        )
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e):
            logger.error(f"Error going back to countries: {e}")
    except Exception as e:
        logger.error(f"Error going back to countries: {e}")
        try:
            await callback.message.edit_text(
                "❌ Ошибка при загрузке",
                reply_markup=get_proxy_back_keyboard("menu"),
            )
        except TelegramBadRequest:
            pass

    await callback.answer()
