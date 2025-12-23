import logging

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext

from bot.states.states import StatisticStates
from bot.keyboards.callbacks import (
    StatResourceCallback,
    StatGenderCallback,
    StatRegionCallback,
    StatSearchRegionCallback,
    StatPeriodCallback,
    StatBackCallback,
    StatDetailedByRegionsCallback,
    StatEmailMenuCallback,
    StatEmailResourceCallback,
    StatNumberMenuCallback,
)
from bot.keyboards.inline import (
    get_stat_resource_keyboard,
    get_stat_gender_keyboard,
    get_stat_region_keyboard,
    get_stat_back_to_region_keyboard,
    get_stat_period_keyboard,
    get_stat_detailed_keyboard,
    # Email keyboards
    get_stat_email_resource_keyboard,
    get_stat_email_type_keyboard,
    get_stat_email_region_keyboard,
    get_stat_email_back_to_region_keyboard,
    get_stat_email_period_keyboard,
    # Number keyboards
    get_stat_number_region_keyboard,
    get_stat_number_back_to_region_keyboard,
    get_stat_number_period_keyboard,
)
from bot.models.enums import Resource, Gender, EmailResource
from bot.services.sheets_service import sheets_service, NumberStatistics
from bot.services.region_service import region_service

logger = logging.getLogger(__name__)
router = Router()


def is_valid_region(region: str) -> bool:
    """Проверка существования региона в системе"""
    return region_service.region_exists(region)


def format_statistics(
    resource: Resource,
    gender: Gender,
    region: str,
    period: str,
    stats,
) -> str:
    """Форматирование статистики для вывода"""
    period_names = {
        "day": "за день",
        "week": "за неделю",
        "month": "за месяц",
    }
    region_display = "🌍 все регионы" if region == "all" else region

    lines = [
        f"<b>📈 Статистика</b>",
        f"",
        f"Ресурс: {resource.display_name}",
    ]

    # Для ресурсов с типом добавляем строку типа
    if gender != Gender.NONE:
        lines.append(f"Тип: {gender.display_name}")

    lines.extend([
        f"Регион: {region_display}",
        f"Период: {period_names.get(period, period)}",
        f"",
        f"<b>Результаты:</b>",
        f"📦 Всего: {stats.total}",
        f"✅ Хороших: {stats.good}",
        f"🚫 Блоков: {stats.block}",
        f"⚠️ Дефектных: {stats.defect}",
    ])

    if stats.no_status > 0:
        lines.append(f"❓ Без статуса: {stats.no_status}")

    # Добавляем процент успешных если есть данные
    if stats.total > 0:
        success_rate = (stats.good / stats.total) * 100
        lines.append(f"")
        lines.append(f"📊 Процент хороших: <b>{success_rate:.1f}%</b>")

    return "\n".join(lines)


def format_region_stats_line(region: str, stats) -> str:
    """Форматирование строки статистики по региону (компактный вид)"""
    if stats.total == 0:
        return f"<b>{region}</b>: 0"

    success_rate = (stats.good / stats.total) * 100

    # Формат: регион: всего (✅N 🚫N ⚠️N) — X%
    return (
        f"<b>{region}</b>: {stats.total} "
        f"(✅{stats.good} 🚫{stats.block} ⚠️{stats.defect}) "
        f"— {success_rate:.0f}%"
    )


def format_email_statistics(
    email_resource: EmailResource,
    email_type: Gender,
    region: str,
    period: str,
    stats,
) -> str:
    """Форматирование статистики почт для вывода"""
    period_names = {
        "day": "за день",
        "week": "за неделю",
        "month": "за месяц",
    }
    region_display = "🌍 все регионы" if region == "all" else region

    lines = [
        f"<b>📈 Статистика почт</b>",
        f"",
        f"Ресурс: {email_resource.emoji} {email_resource.display_name}",
    ]

    # Для Gmail добавляем тип
    if email_type and email_type != Gender.NONE:
        lines.append(f"Тип: {email_type.display_name}")

    lines.extend([
        f"Регион: {region_display}",
        f"Период: {period_names.get(period, period)}",
        f"",
        f"<b>Результаты:</b>",
        f"📦 Всего: {stats.total}",
        f"✅ Хороших: {stats.good}",
        f"🚫 Блоков: {stats.block}",
        f"⚠️ Дефектных: {stats.defect}",
    ])

    if stats.no_status > 0:
        lines.append(f"❓ Без статуса: {stats.no_status}")

    if stats.total > 0:
        success_rate = (stats.good / stats.total) * 100
        lines.append(f"")
        lines.append(f"📊 Процент хороших: <b>{success_rate:.1f}%</b>")

    return "\n".join(lines)


def format_number_statistics(
    region: str,
    period: str,
    stats: NumberStatistics,
) -> str:
    """Форматирование статистики номеров для вывода"""
    period_names = {
        "day": "за день",
        "week": "за неделю",
        "month": "за месяц",
    }
    region_display = "🌍 все регионы" if region == "all" else region

    lines = [
        f"<b>📈 Статистика номеров</b>",
        f"",
        f"Регион: {region_display}",
        f"Период: {period_names.get(period, period)}",
        f"",
        f"<b>Номеров выдано:</b> {stats.total}",
        f"",
        f"<b>Регистрации по ресурсам:</b>",
        f"🟧 Beboo: {stats.beboo}",
        f"🟦 Loloo: {stats.loloo}",
        f"🟥 Табор: {stats.tabor}",
        f"",
        f"<b>Статусы:</b>",
        f"✅ Рабочих: {stats.working}",
        f"🔄 Сброс: {stats.reset}",
        f"📝 Зарегистрирован: {stats.registered}",
        f"❌ Выбило ТГ: {stats.tg_kicked}",
    ]

    if stats.no_status > 0:
        lines.append(f"❓ Без статуса: {stats.no_status}")

    if stats.total > 0:
        working_rate = (stats.working / stats.total) * 100
        lines.append(f"")
        lines.append(f"📊 Процент рабочих: <b>{working_rate:.1f}%</b>")

    return "\n".join(lines)


def format_number_region_stats_line(region: str, stats: NumberStatistics) -> str:
    """Форматирование строки статистики номеров по региону (компактный вид)"""
    if stats.total == 0:
        return f"<b>{region}</b>: 0"

    # Формат: регион: всего (Beboo:N Loloo:N Tabor:N) — N% рабочих
    working_rate = (stats.working / stats.total) * 100 if stats.total > 0 else 0
    return (
        f"<b>{region}</b>: {stats.total} "
        f"(B:{stats.beboo} L:{stats.loloo} T:{stats.tabor}) "
        f"— {working_rate:.0f}% рабочих"
    )


# ================== КОМАНДА /statistic ==================

@router.message(Command("statistic"))
async def cmd_statistic(message: Message, state: FSMContext):
    """Обработка команды /statistic"""
    await state.clear()
    await state.set_state(StatisticStates.selecting_resource)

    await message.answer(
        "📈 <b>Статистика</b>\n\n"
        "Выберите ресурс:",
        reply_markup=get_stat_resource_keyboard(),
        parse_mode="HTML",
    )


# ================== АККАУНТЫ (VK, Mamba, OK) ==================

@router.callback_query(StatResourceCallback.filter(), StatisticStates.selecting_resource)
async def stat_process_resource(
    callback: CallbackQuery,
    callback_data: StatResourceCallback,
    state: FSMContext,
):
    """Обработка выбора ресурса"""
    await callback.answer()
    resource = Resource(callback_data.resource)

    await state.update_data(stat_resource=resource)

    # Для VK и OK пропускаем выбор пола
    if resource in (Resource.VK, Resource.OK):
        await state.update_data(stat_gender=Gender.NONE)
        await state.set_state(StatisticStates.selecting_region)

        await callback.message.edit_text(
            f"Ресурс: <b>{resource.display_name}</b>\n\n"
            f"Выберите регион:",
            reply_markup=get_stat_region_keyboard(),
            parse_mode="HTML",
        )
    else:
        await state.set_state(StatisticStates.selecting_gender)

        await callback.message.edit_text(
            f"Ресурс: <b>{resource.display_name}</b>\n\n"
            f"Выберите тип:",
            reply_markup=get_stat_gender_keyboard(resource),
            parse_mode="HTML",
        )


@router.callback_query(StatGenderCallback.filter(), StatisticStates.selecting_gender)
async def stat_process_gender(
    callback: CallbackQuery,
    callback_data: StatGenderCallback,
    state: FSMContext,
):
    """Обработка выбора пола/типа (для аккаунтов)"""
    await callback.answer()
    gender = Gender(callback_data.gender)
    data = await state.get_data()
    resource = data["stat_resource"]

    await state.update_data(stat_gender=gender)
    await state.set_state(StatisticStates.selecting_region)

    await callback.message.edit_text(
        f"Ресурс: <b>{resource.display_name}</b>\n"
        f"Тип: <b>{gender.display_name}</b>\n\n"
        f"Выберите регион:",
        reply_markup=get_stat_region_keyboard(),
        parse_mode="HTML",
    )


@router.callback_query(StatRegionCallback.filter(), StatisticStates.selecting_region)
async def stat_process_region(
    callback: CallbackQuery,
    callback_data: StatRegionCallback,
    state: FSMContext,
):
    """Обработка выбора региона (для аккаунтов)"""
    await callback.answer()
    region = callback_data.region
    data = await state.get_data()
    resource = data["stat_resource"]
    gender = data["stat_gender"]

    region_display = "все регионы" if region == "all" else region

    await state.update_data(stat_region=region)
    await state.set_state(StatisticStates.selecting_period)

    # Для VK/OK не показываем тип
    text = f"Ресурс: <b>{resource.display_name}</b>\n"
    if gender != Gender.NONE:
        text += f"Тип: <b>{gender.display_name}</b>\n"
    text += f"Регион: <b>{region_display}</b>\n\nВыберите период:"

    await callback.message.edit_text(
        text,
        reply_markup=get_stat_period_keyboard(),
        parse_mode="HTML",
    )


@router.callback_query(StatSearchRegionCallback.filter(), StatisticStates.selecting_region)
async def stat_search_region_start(callback: CallbackQuery, state: FSMContext):
    """Начало поиска региона в статистике (для аккаунтов)"""
    await callback.answer()
    data = await state.get_data()
    resource = data["stat_resource"]
    gender = data["stat_gender"]

    await state.set_state(StatisticStates.searching_region)

    text = f"Ресурс: <b>{resource.display_name}</b>\n"
    if gender != Gender.NONE:
        text += f"Тип: <b>{gender.display_name}</b>\n"
    text += "\nВведите номер региона (например: 77, 50, 197):"

    await callback.message.edit_text(
        text,
        reply_markup=get_stat_back_to_region_keyboard(),
        parse_mode="HTML",
    )


@router.message(StatisticStates.searching_region)
async def stat_search_region_input(message: Message, state: FSMContext):
    """Обработка ввода региона в статистике (для аккаунтов)"""
    region = message.text.strip()
    data = await state.get_data()
    resource = data["stat_resource"]
    gender = data["stat_gender"]

    if not region:
        await message.answer(
            "Введите номер региона:",
            reply_markup=get_stat_back_to_region_keyboard(),
        )
        return

    if not is_valid_region(region):
        available = ", ".join(region_service.get_regions()[:5])
        await message.answer(
            f"❌ Такого региона не существует: <b>{region}</b>\n\n"
            f"Доступные регионы: {available}...\n"
            f"Введите существующий регион или выберите из списка:",
            reply_markup=get_stat_back_to_region_keyboard(),
            parse_mode="HTML",
        )
        return

    await state.update_data(stat_region=region)
    await state.set_state(StatisticStates.selecting_period)

    text = f"Ресурс: <b>{resource.display_name}</b>\n"
    if gender != Gender.NONE:
        text += f"Тип: <b>{gender.display_name}</b>\n"
    text += f"Регион: <b>{region}</b>\n\nВыберите период:"

    await message.answer(
        text,
        reply_markup=get_stat_period_keyboard(),
        parse_mode="HTML",
    )


@router.callback_query(StatPeriodCallback.filter(), StatisticStates.selecting_period)
async def stat_process_period(
    callback: CallbackQuery,
    callback_data: StatPeriodCallback,
    state: FSMContext,
):
    """Обработка выбора периода и показ статистики (для аккаунтов)"""
    await callback.answer()

    period = callback_data.period
    data = await state.get_data()
    resource = data["stat_resource"]
    gender = data["stat_gender"]
    region = data["stat_region"]

    # Показываем загрузку
    region_display = "все регионы" if region == "all" else region
    text = f"Ресурс: <b>{resource.display_name}</b>\n"
    if gender != Gender.NONE:
        text += f"Тип: <b>{gender.display_name}</b>\n"
    text += f"Регион: <b>{region_display}</b>\n\n<i>Загрузка статистики...</i>"

    await callback.message.edit_text(text, parse_mode="HTML")

    try:
        # Получаем статистику
        stats = await sheets_service.get_statistics(
            resource=resource,
            gender=gender,
            region=region if region != "all" else None,
            period=period,
        )

        # Форматируем и показываем
        stats_text = format_statistics(resource, gender, region, period, stats)

        # Если выбраны все регионы — показываем кнопку "Детальнее"
        if region == "all":
            await callback.message.edit_text(
                stats_text,
                reply_markup=get_stat_detailed_keyboard(
                    resource=resource.value,
                    gender=gender.value,
                    period=period,
                ),
                parse_mode="HTML",
            )
        else:
            await callback.message.edit_text(
                stats_text,
                parse_mode="HTML",
            )

    except Exception as e:
        logger.error(f"Error getting statistics: {e}")
        await callback.message.edit_text(
            "Произошла ошибка при получении статистики.\n"
            "Попробуйте позже."
        )

    # Возвращаемся к выбору ресурса статистики
    await state.clear()
    await state.set_state(StatisticStates.selecting_resource)
    await callback.message.answer(
        "📈 <b>Статистика</b>\n\n"
        "Выберите ресурс:",
        reply_markup=get_stat_resource_keyboard(),
        parse_mode="HTML",
    )


@router.callback_query(StatDetailedByRegionsCallback.filter())
async def stat_detailed_by_regions(
    callback: CallbackQuery,
    callback_data: StatDetailedByRegionsCallback,
):
    """Показ детальной статистики по каждому региону (для аккаунтов)"""
    await callback.answer()

    resource = Resource(callback_data.resource)
    gender = Gender(callback_data.gender)
    period = callback_data.period

    period_names = {
        "day": "за день",
        "week": "за неделю",
        "month": "за месяц",
    }

    # Показываем загрузку
    await callback.message.edit_text(
        f"<b>📊 Детальная статистика по регионам</b>\n\n"
        f"Ресурс: {resource.display_name}\n"
        f"Тип: {gender.display_name}\n"
        f"Период: {period_names.get(period, period)}\n\n"
        f"<i>Загрузка...</i>",
        parse_mode="HTML",
    )

    try:
        # Получаем список всех регионов
        regions = region_service.get_regions()

        # Получаем статистику по всем регионам
        stats_by_region = await sheets_service.get_statistics_by_regions(
            resource=resource,
            gender=gender,
            regions=regions,
            period=period,
        )

        # Формируем текст
        lines = [
            f"<b>📊 Детальная статистика по регионам</b>",
            f"",
            f"Ресурс: {resource.display_name}",
        ]

        # Для ресурсов с типом добавляем строку типа
        if gender != Gender.NONE:
            lines.append(f"Тип: {gender.display_name}")

        lines.extend([
            f"Период: {period_names.get(period, period)}",
            f"",
        ])

        # Добавляем статистику по каждому региону (отсортированы)
        for region in regions:
            stats = stats_by_region.get(region)
            if stats:
                lines.append(format_region_stats_line(region, stats))

        # Если все регионы пустые
        total_all = sum(s.total for s in stats_by_region.values())
        if total_all == 0:
            lines.append("Нет данных за выбранный период")

        await callback.message.edit_text(
            "\n".join(lines),
            parse_mode="HTML",
        )

    except Exception as e:
        logger.error(f"Error getting detailed statistics: {e}")
        await callback.message.edit_text(
            "Произошла ошибка при получении статистики.\n"
            "Попробуйте позже."
        )


# ================== ПОЧТЫ ==================

@router.callback_query(StatEmailMenuCallback.filter(), StatisticStates.selecting_resource)
async def stat_open_email_menu(callback: CallbackQuery, state: FSMContext):
    """Открытие раздела статистики почт"""
    await callback.answer()
    await state.set_state(StatisticStates.email_selecting_resource)

    await callback.message.edit_text(
        "📈 <b>Статистика почт</b>\n\n"
        "Выберите ресурс:",
        reply_markup=get_stat_email_resource_keyboard(),
        parse_mode="HTML",
    )


@router.callback_query(StatEmailResourceCallback.filter(), StatisticStates.email_selecting_resource)
async def stat_email_process_resource(
    callback: CallbackQuery,
    callback_data: StatEmailResourceCallback,
    state: FSMContext,
):
    """Обработка выбора почтового ресурса"""
    await callback.answer()
    email_resource = EmailResource(callback_data.resource)

    await state.update_data(stat_email_resource=email_resource)

    # Для Gmail показываем выбор типа
    if email_resource == EmailResource.GMAIL:
        await state.set_state(StatisticStates.email_selecting_type)
        await callback.message.edit_text(
            f"Ресурс: <b>{email_resource.emoji} {email_resource.display_name}</b>\n\n"
            f"Выберите тип:",
            reply_markup=get_stat_email_type_keyboard(),
            parse_mode="HTML",
        )
    else:
        # Для Rambler сразу к выбору региона
        await state.update_data(stat_email_type=None)
        await state.set_state(StatisticStates.email_selecting_region)
        await callback.message.edit_text(
            f"Ресурс: <b>{email_resource.emoji} {email_resource.display_name}</b>\n\n"
            f"Выберите регион:",
            reply_markup=get_stat_email_region_keyboard(),
            parse_mode="HTML",
        )


@router.callback_query(StatGenderCallback.filter(), StatisticStates.email_selecting_type)
async def stat_email_process_type(
    callback: CallbackQuery,
    callback_data: StatGenderCallback,
    state: FSMContext,
):
    """Обработка выбора типа Gmail"""
    await callback.answer()
    email_type = Gender(callback_data.gender)
    data = await state.get_data()
    email_resource = data["stat_email_resource"]

    await state.update_data(stat_email_type=email_type)
    await state.set_state(StatisticStates.email_selecting_region)

    await callback.message.edit_text(
        f"Ресурс: <b>{email_resource.emoji} {email_resource.display_name}</b>\n"
        f"Тип: <b>{email_type.display_name}</b>\n\n"
        f"Выберите регион:",
        reply_markup=get_stat_email_region_keyboard(),
        parse_mode="HTML",
    )


@router.callback_query(StatRegionCallback.filter(), StatisticStates.email_selecting_region)
async def stat_email_process_region(
    callback: CallbackQuery,
    callback_data: StatRegionCallback,
    state: FSMContext,
):
    """Обработка выбора региона для почт"""
    await callback.answer()
    region = callback_data.region
    data = await state.get_data()
    email_resource = data["stat_email_resource"]
    email_type = data.get("stat_email_type")

    region_display = "все регионы" if region == "all" else region

    await state.update_data(stat_email_region=region)
    await state.set_state(StatisticStates.email_selecting_period)

    text = f"Ресурс: <b>{email_resource.emoji} {email_resource.display_name}</b>\n"
    if email_type:
        text += f"Тип: <b>{email_type.display_name}</b>\n"
    text += f"Регион: <b>{region_display}</b>\n\nВыберите период:"

    await callback.message.edit_text(
        text,
        reply_markup=get_stat_email_period_keyboard(),
        parse_mode="HTML",
    )


@router.callback_query(StatSearchRegionCallback.filter(), StatisticStates.email_selecting_region)
async def stat_email_search_region_start(callback: CallbackQuery, state: FSMContext):
    """Начало поиска региона в статистике почт"""
    await callback.answer()
    data = await state.get_data()
    email_resource = data["stat_email_resource"]
    email_type = data.get("stat_email_type")

    await state.set_state(StatisticStates.email_searching_region)

    text = f"Ресурс: <b>{email_resource.emoji} {email_resource.display_name}</b>\n"
    if email_type:
        text += f"Тип: <b>{email_type.display_name}</b>\n"
    text += f"\nВведите номер региона (например: 77, 50, 197):"

    await callback.message.edit_text(
        text,
        reply_markup=get_stat_email_back_to_region_keyboard(),
        parse_mode="HTML",
    )


@router.message(StatisticStates.email_searching_region)
async def stat_email_search_region_input(message: Message, state: FSMContext):
    """Обработка ввода региона в статистике почт"""
    region = message.text.strip()
    data = await state.get_data()
    email_resource = data["stat_email_resource"]
    email_type = data.get("stat_email_type")

    if not region:
        await message.answer(
            "Введите номер региона:",
            reply_markup=get_stat_email_back_to_region_keyboard(),
        )
        return

    if not is_valid_region(region):
        available = ", ".join(region_service.get_regions()[:5])
        await message.answer(
            f"❌ Такого региона не существует: <b>{region}</b>\n\n"
            f"Доступные регионы: {available}...\n"
            f"Введите существующий регион или выберите из списка:",
            reply_markup=get_stat_email_back_to_region_keyboard(),
            parse_mode="HTML",
        )
        return

    await state.update_data(stat_email_region=region)
    await state.set_state(StatisticStates.email_selecting_period)

    text = f"Ресурс: <b>{email_resource.emoji} {email_resource.display_name}</b>\n"
    if email_type:
        text += f"Тип: <b>{email_type.display_name}</b>\n"
    text += f"Регион: <b>{region}</b>\n\nВыберите период:"

    await message.answer(
        text,
        reply_markup=get_stat_email_period_keyboard(),
        parse_mode="HTML",
    )


@router.callback_query(StatPeriodCallback.filter(), StatisticStates.email_selecting_period)
async def stat_email_process_period(
    callback: CallbackQuery,
    callback_data: StatPeriodCallback,
    state: FSMContext,
):
    """Обработка выбора периода и показ статистики почт"""
    await callback.answer()

    period = callback_data.period
    data = await state.get_data()
    email_resource = data["stat_email_resource"]
    email_type = data.get("stat_email_type")
    region = data["stat_email_region"]

    region_display = "все регионы" if region == "all" else region

    # Показываем загрузку
    text = f"Ресурс: <b>{email_resource.emoji} {email_resource.display_name}</b>\n"
    if email_type:
        text += f"Тип: <b>{email_type.display_name}</b>\n"
    text += f"Регион: <b>{region_display}</b>\n\n<i>Загрузка статистики...</i>"

    await callback.message.edit_text(text, parse_mode="HTML")

    try:
        stats = await sheets_service.get_email_statistics(
            email_resource=email_resource,
            email_type=email_type,
            region=region if region != "all" else None,
            period=period,
        )

        stats_text = format_email_statistics(email_resource, email_type, region, period, stats)
        await callback.message.edit_text(stats_text, parse_mode="HTML")

    except Exception as e:
        logger.error(f"Error getting email statistics: {e}")
        await callback.message.edit_text(
            "Произошла ошибка при получении статистики.\n"
            "Попробуйте позже."
        )

    # Возвращаемся к главному меню статистики
    await state.clear()
    await state.set_state(StatisticStates.selecting_resource)
    await callback.message.answer(
        "📈 <b>Статистика</b>\n\n"
        "Выберите ресурс:",
        reply_markup=get_stat_resource_keyboard(),
        parse_mode="HTML",
    )


# ================== НОМЕРА ==================

@router.callback_query(StatNumberMenuCallback.filter(), StatisticStates.selecting_resource)
async def stat_open_number_menu(callback: CallbackQuery, state: FSMContext):
    """Открытие раздела статистики номеров"""
    await callback.answer()
    await state.set_state(StatisticStates.number_selecting_region)

    await callback.message.edit_text(
        "📈 <b>Статистика номеров</b>\n\n"
        "Выберите регион:",
        reply_markup=get_stat_number_region_keyboard(),
        parse_mode="HTML",
    )


@router.callback_query(StatRegionCallback.filter(), StatisticStates.number_selecting_region)
async def stat_number_process_region(
    callback: CallbackQuery,
    callback_data: StatRegionCallback,
    state: FSMContext,
):
    """Обработка выбора региона для номеров"""
    await callback.answer()
    region = callback_data.region

    region_display = "все регионы" if region == "all" else region

    await state.update_data(stat_number_region=region)
    await state.set_state(StatisticStates.number_selecting_period)

    await callback.message.edit_text(
        f"📈 <b>Статистика номеров</b>\n\n"
        f"Регион: <b>{region_display}</b>\n\n"
        f"Выберите период:",
        reply_markup=get_stat_number_period_keyboard(),
        parse_mode="HTML",
    )


@router.callback_query(StatSearchRegionCallback.filter(), StatisticStates.number_selecting_region)
async def stat_number_search_region_start(callback: CallbackQuery, state: FSMContext):
    """Начало поиска региона в статистике номеров"""
    await callback.answer()
    await state.set_state(StatisticStates.number_searching_region)

    await callback.message.edit_text(
        "📈 <b>Статистика номеров</b>\n\n"
        "Введите номер региона (например: 77, 50, 197):",
        reply_markup=get_stat_number_back_to_region_keyboard(),
        parse_mode="HTML",
    )


@router.message(StatisticStates.number_searching_region)
async def stat_number_search_region_input(message: Message, state: FSMContext):
    """Обработка ввода региона в статистике номеров"""
    region = message.text.strip()

    if not region:
        await message.answer(
            "Введите номер региона:",
            reply_markup=get_stat_number_back_to_region_keyboard(),
        )
        return

    if not is_valid_region(region):
        available = ", ".join(region_service.get_regions()[:5])
        await message.answer(
            f"❌ Такого региона не существует: <b>{region}</b>\n\n"
            f"Доступные регионы: {available}...\n"
            f"Введите существующий регион или выберите из списка:",
            reply_markup=get_stat_number_back_to_region_keyboard(),
            parse_mode="HTML",
        )
        return

    await state.update_data(stat_number_region=region)
    await state.set_state(StatisticStates.number_selecting_period)

    await message.answer(
        f"📈 <b>Статистика номеров</b>\n\n"
        f"Регион: <b>{region}</b>\n\n"
        f"Выберите период:",
        reply_markup=get_stat_number_period_keyboard(),
        parse_mode="HTML",
    )


@router.callback_query(StatPeriodCallback.filter(), StatisticStates.number_selecting_period)
async def stat_number_process_period(
    callback: CallbackQuery,
    callback_data: StatPeriodCallback,
    state: FSMContext,
):
    """Обработка выбора периода и показ статистики номеров"""
    await callback.answer()

    period = callback_data.period
    data = await state.get_data()
    region = data["stat_number_region"]

    region_display = "все регионы" if region == "all" else region

    # Показываем загрузку
    await callback.message.edit_text(
        f"📈 <b>Статистика номеров</b>\n\n"
        f"Регион: <b>{region_display}</b>\n\n"
        f"<i>Загрузка статистики...</i>",
        parse_mode="HTML",
    )

    try:
        stats = await sheets_service.get_number_statistics(
            region=region if region != "all" else None,
            period=period,
        )

        stats_text = format_number_statistics(region, period, stats)
        await callback.message.edit_text(stats_text, parse_mode="HTML")

    except Exception as e:
        logger.error(f"Error getting number statistics: {e}")
        await callback.message.edit_text(
            "Произошла ошибка при получении статистики.\n"
            "Попробуйте позже."
        )

    # Возвращаемся к главному меню статистики
    await state.clear()
    await state.set_state(StatisticStates.selecting_resource)
    await callback.message.answer(
        "📈 <b>Статистика</b>\n\n"
        "Выберите ресурс:",
        reply_markup=get_stat_resource_keyboard(),
        parse_mode="HTML",
    )


# ================== КНОПКИ "НАЗАД" ==================

@router.callback_query(StatBackCallback.filter(F.to == "resource"))
async def stat_back_to_resource(callback: CallbackQuery, state: FSMContext):
    """Возврат к выбору ресурса (главное меню статистики)"""
    await callback.answer()
    await state.clear()
    await state.set_state(StatisticStates.selecting_resource)
    await callback.message.edit_text(
        "📈 <b>Статистика</b>\n\n"
        "Выберите ресурс:",
        reply_markup=get_stat_resource_keyboard(),
        parse_mode="HTML",
    )


@router.callback_query(StatBackCallback.filter(F.to == "gender"), StatisticStates.selecting_region)
async def stat_back_to_gender(callback: CallbackQuery, state: FSMContext):
    """Возврат к выбору пола/типа (для аккаунтов) или к ресурсу (для VK/OK)"""
    await callback.answer()
    data = await state.get_data()
    resource = data.get("stat_resource")

    # Для VK и OK нет выбора типа — возвращаемся сразу к ресурсу
    if not resource or resource in (Resource.VK, Resource.OK):
        await state.clear()
        await state.set_state(StatisticStates.selecting_resource)
        await callback.message.edit_text(
            "📈 <b>Статистика</b>\n\n"
            "Выберите ресурс:",
            reply_markup=get_stat_resource_keyboard(),
            parse_mode="HTML",
        )
    else:
        await state.set_state(StatisticStates.selecting_gender)
        await callback.message.edit_text(
            f"Ресурс: <b>{resource.display_name}</b>\n\n"
            f"Выберите тип:",
            reply_markup=get_stat_gender_keyboard(resource),
            parse_mode="HTML",
        )


@router.callback_query(StatBackCallback.filter(F.to == "region"))
async def stat_back_to_region(callback: CallbackQuery, state: FSMContext):
    """Возврат к выбору региона (для аккаунтов)"""
    await callback.answer()
    data = await state.get_data()
    resource = data.get("stat_resource")
    gender = data.get("stat_gender")

    if not resource or gender is None:
        await state.set_state(StatisticStates.selecting_resource)
        await callback.message.edit_text(
            "📈 <b>Статистика</b>\n\n"
            "Выберите ресурс:",
            reply_markup=get_stat_resource_keyboard(),
            parse_mode="HTML",
        )
    else:
        await state.set_state(StatisticStates.selecting_region)
        text = f"Ресурс: <b>{resource.display_name}</b>\n"
        if gender != Gender.NONE:
            text += f"Тип: <b>{gender.display_name}</b>\n"
        text += "\nВыберите регион:"

        await callback.message.edit_text(
            text,
            reply_markup=get_stat_region_keyboard(),
            parse_mode="HTML",
        )


# === Кнопки назад для почт ===

@router.callback_query(StatBackCallback.filter(F.to == "email_resource"))
async def stat_back_to_email_resource(callback: CallbackQuery, state: FSMContext):
    """Возврат к выбору почтового ресурса"""
    await callback.answer()
    await state.set_state(StatisticStates.email_selecting_resource)
    await callback.message.edit_text(
        "📈 <b>Статистика почт</b>\n\n"
        "Выберите ресурс:",
        reply_markup=get_stat_email_resource_keyboard(),
        parse_mode="HTML",
    )


@router.callback_query(StatBackCallback.filter(F.to == "email_type"))
async def stat_back_to_email_type(callback: CallbackQuery, state: FSMContext):
    """Возврат к выбору типа Gmail или к ресурсу (для Rambler)"""
    await callback.answer()
    data = await state.get_data()
    email_resource = data.get("stat_email_resource")

    if not email_resource:
        await state.set_state(StatisticStates.email_selecting_resource)
        await callback.message.edit_text(
            "📈 <b>Статистика почт</b>\n\n"
            "Выберите ресурс:",
            reply_markup=get_stat_email_resource_keyboard(),
            parse_mode="HTML",
        )
    elif email_resource == EmailResource.GMAIL:
        await state.set_state(StatisticStates.email_selecting_type)
        await callback.message.edit_text(
            f"Ресурс: <b>{email_resource.emoji} {email_resource.display_name}</b>\n\n"
            f"Выберите тип:",
            reply_markup=get_stat_email_type_keyboard(),
            parse_mode="HTML",
        )
    else:
        # Rambler - возвращаемся к выбору ресурса
        await state.set_state(StatisticStates.email_selecting_resource)
        await callback.message.edit_text(
            "📈 <b>Статистика почт</b>\n\n"
            "Выберите ресурс:",
            reply_markup=get_stat_email_resource_keyboard(),
            parse_mode="HTML",
        )


@router.callback_query(StatBackCallback.filter(F.to == "email_region"))
async def stat_back_to_email_region(callback: CallbackQuery, state: FSMContext):
    """Возврат к выбору региона для почт"""
    await callback.answer()
    data = await state.get_data()
    email_resource = data.get("stat_email_resource")
    email_type = data.get("stat_email_type")

    if not email_resource:
        await state.set_state(StatisticStates.email_selecting_resource)
        await callback.message.edit_text(
            "📈 <b>Статистика почт</b>\n\n"
            "Выберите ресурс:",
            reply_markup=get_stat_email_resource_keyboard(),
            parse_mode="HTML",
        )
    else:
        await state.set_state(StatisticStates.email_selecting_region)
        text = f"Ресурс: <b>{email_resource.emoji} {email_resource.display_name}</b>\n"
        if email_type:
            text += f"Тип: <b>{email_type.display_name}</b>\n"
        text += "\nВыберите регион:"

        await callback.message.edit_text(
            text,
            reply_markup=get_stat_email_region_keyboard(),
            parse_mode="HTML",
        )


# === Кнопки назад для номеров ===

@router.callback_query(StatBackCallback.filter(F.to == "number_region"))
async def stat_back_to_number_region(callback: CallbackQuery, state: FSMContext):
    """Возврат к выбору региона для номеров"""
    await callback.answer()
    await state.set_state(StatisticStates.number_selecting_region)
    await callback.message.edit_text(
        "📈 <b>Статистика номеров</b>\n\n"
        "Выберите регион:",
        reply_markup=get_stat_number_region_keyboard(),
        parse_mode="HTML",
    )
