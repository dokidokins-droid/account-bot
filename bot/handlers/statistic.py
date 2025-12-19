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
)
from bot.keyboards.inline import (
    get_stat_resource_keyboard,
    get_stat_gender_keyboard,
    get_stat_region_keyboard,
    get_stat_back_to_region_keyboard,
    get_stat_period_keyboard,
    get_stat_detailed_keyboard,
)
from bot.models.enums import Resource, Gender
from bot.services.sheets_service import sheets_service
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
        f"Тип: {gender.display_name}",
        f"Регион: {region_display}",
        f"Период: {period_names.get(period, period)}",
        f"",
        f"<b>Результаты:</b>",
        f"📦 Всего: {stats.total}",
        f"✅ Хороших: {stats.good}",
        f"🚫 Блоков: {stats.block}",
        f"⚠️ Дефектных: {stats.defect}",
    ]

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


# === Команда /statistic ===

@router.message(Command("statistic"))
async def cmd_statistic(message: Message, state: FSMContext):
    """Обработка команды /statistic"""
    await state.clear()
    await state.set_state(StatisticStates.selecting_resource)

    await message.answer(
        "Выберите ресурс для просмотра статистики:",
        reply_markup=get_stat_resource_keyboard(),
    )


# === Выбор ресурса ===

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
    await state.set_state(StatisticStates.selecting_gender)

    await callback.message.edit_text(
        f"Ресурс: <b>{resource.display_name}</b>\n\n"
        f"Выберите тип:",
        reply_markup=get_stat_gender_keyboard(resource),
        parse_mode="HTML",
    )


# === Выбор пола/типа ===

@router.callback_query(StatGenderCallback.filter(), StatisticStates.selecting_gender)
async def stat_process_gender(
    callback: CallbackQuery,
    callback_data: StatGenderCallback,
    state: FSMContext,
):
    """Обработка выбора пола/типа"""
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


# === Выбор региона ===

@router.callback_query(StatRegionCallback.filter(), StatisticStates.selecting_region)
async def stat_process_region(
    callback: CallbackQuery,
    callback_data: StatRegionCallback,
    state: FSMContext,
):
    """Обработка выбора региона"""
    await callback.answer()
    region = callback_data.region
    data = await state.get_data()
    resource = data["stat_resource"]
    gender = data["stat_gender"]

    region_display = "все регионы" if region == "all" else region

    await state.update_data(stat_region=region)
    await state.set_state(StatisticStates.selecting_period)

    await callback.message.edit_text(
        f"Ресурс: <b>{resource.display_name}</b>\n"
        f"Тип: <b>{gender.display_name}</b>\n"
        f"Регион: <b>{region_display}</b>\n\n"
        f"Выберите период:",
        reply_markup=get_stat_period_keyboard(),
        parse_mode="HTML",
    )


# === Поиск региона ===

@router.callback_query(StatSearchRegionCallback.filter(), StatisticStates.selecting_region)
async def stat_search_region_start(callback: CallbackQuery, state: FSMContext):
    """Начало поиска региона в статистике"""
    await callback.answer()
    data = await state.get_data()
    resource = data["stat_resource"]
    gender = data["stat_gender"]

    await state.set_state(StatisticStates.searching_region)
    await callback.message.edit_text(
        f"Ресурс: <b>{resource.display_name}</b>\n"
        f"Тип: <b>{gender.display_name}</b>\n\n"
        f"Введите номер региона (например: 77, 50, 197):",
        reply_markup=get_stat_back_to_region_keyboard(),
        parse_mode="HTML",
    )


@router.message(StatisticStates.searching_region)
async def stat_search_region_input(message: Message, state: FSMContext):
    """Обработка ввода региона в статистике"""
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

    await message.answer(
        f"Ресурс: <b>{resource.display_name}</b>\n"
        f"Тип: <b>{gender.display_name}</b>\n"
        f"Регион: <b>{region}</b>\n\n"
        f"Выберите период:",
        reply_markup=get_stat_period_keyboard(),
        parse_mode="HTML",
    )


# === Выбор периода и показ статистики ===

@router.callback_query(StatPeriodCallback.filter(), StatisticStates.selecting_period)
async def stat_process_period(
    callback: CallbackQuery,
    callback_data: StatPeriodCallback,
    state: FSMContext,
):
    """Обработка выбора периода и показ статистики"""
    await callback.answer()

    period = callback_data.period
    data = await state.get_data()
    resource = data["stat_resource"]
    gender = data["stat_gender"]
    region = data["stat_region"]

    # Показываем загрузку
    region_display = "все регионы" if region == "all" else region
    await callback.message.edit_text(
        f"Ресурс: <b>{resource.display_name}</b>\n"
        f"Тип: <b>{gender.display_name}</b>\n"
        f"Регион: <b>{region_display}</b>\n\n"
        f"<i>Загрузка статистики...</i>",
        parse_mode="HTML",
    )

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
        "Выберите ресурс для просмотра статистики:",
        reply_markup=get_stat_resource_keyboard(),
    )


# === Детальная статистика по регионам ===

@router.callback_query(StatDetailedByRegionsCallback.filter())
async def stat_detailed_by_regions(
    callback: CallbackQuery,
    callback_data: StatDetailedByRegionsCallback,
):
    """Показ детальной статистики по каждому региону"""
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
            f"Тип: {gender.display_name}",
            f"Период: {period_names.get(period, period)}",
            f"",
        ]

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


# === Кнопки "Назад" ===

@router.callback_query(StatBackCallback.filter(F.to == "resource"), StatisticStates.selecting_gender)
async def stat_back_to_resource(callback: CallbackQuery, state: FSMContext):
    """Возврат к выбору ресурса"""
    await callback.answer()
    await state.set_state(StatisticStates.selecting_resource)
    await callback.message.edit_text(
        "Выберите ресурс для просмотра статистики:",
        reply_markup=get_stat_resource_keyboard(),
    )


@router.callback_query(StatBackCallback.filter(F.to == "gender"), StatisticStates.selecting_region)
async def stat_back_to_gender(callback: CallbackQuery, state: FSMContext):
    """Возврат к выбору пола/типа"""
    await callback.answer()
    data = await state.get_data()
    resource = data.get("stat_resource")

    if not resource:
        await state.set_state(StatisticStates.selecting_resource)
        await callback.message.edit_text(
            "Выберите ресурс для просмотра статистики:",
            reply_markup=get_stat_resource_keyboard(),
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
    """Возврат к выбору региона"""
    await callback.answer()
    data = await state.get_data()
    resource = data.get("stat_resource")
    gender = data.get("stat_gender")

    if not resource or not gender:
        await state.set_state(StatisticStates.selecting_resource)
        await callback.message.edit_text(
            "Выберите ресурс для просмотра статистики:",
            reply_markup=get_stat_resource_keyboard(),
        )
    else:
        await state.set_state(StatisticStates.selecting_region)
        await callback.message.edit_text(
            f"Ресурс: <b>{resource.display_name}</b>\n"
            f"Тип: <b>{gender.display_name}</b>\n\n"
            f"Выберите регион:",
            reply_markup=get_stat_region_keyboard(),
            parse_mode="HTML",
        )
