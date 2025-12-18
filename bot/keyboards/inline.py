from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardMarkup

from bot.keyboards.callbacks import (
    AdminApprovalCallback,
    ResourceCallback,
    RegionCallback,
    QuantityCallback,
    GenderCallback,
    AccountFeedbackCallback,
    BackCallback,
    SearchRegionCallback,
    ReplaceAccountCallback,
    # Статистика
    StatResourceCallback,
    StatGenderCallback,
    StatRegionCallback,
    StatSearchRegionCallback,
    StatPeriodCallback,
    StatBackCallback,
    # Прокси
    ProxyMenuCallback,
)
from bot.models.enums import Resource, Gender
from bot.config import settings


def get_admin_approval_keyboard(user_id: int) -> InlineKeyboardMarkup:
    """Клавиатура для одобрения/отклонения заявки"""
    builder = InlineKeyboardBuilder()
    builder.button(
        text="✅ Одобрить",
        callback_data=AdminApprovalCallback(action="approve", user_id=user_id),
    )
    builder.button(
        text="❌ Отклонить",
        callback_data=AdminApprovalCallback(action="reject", user_id=user_id),
    )
    builder.adjust(2)
    return builder.as_markup()


def get_resource_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора ресурса"""
    builder = InlineKeyboardBuilder()
    for resource in Resource:
        builder.button(
            text=resource.button_text,
            callback_data=ResourceCallback(resource=resource.value),
        )
    # Кнопка прокси на всю ширину
    builder.button(
        text="🌐 Прокси",
        callback_data=ProxyMenuCallback(action="open"),
    )
    # Ресурсы по 2 в ряд, прокси на всю ширину
    builder.adjust(2, 2, 2, 2, 1)
    return builder.as_markup()


def get_region_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора региона"""
    builder = InlineKeyboardBuilder()
    for region in settings.regions_list:
        builder.button(
            text=region,
            callback_data=RegionCallback(region=region),
        )
    # Кнопка поиска (на всю ширину)
    builder.button(
        text="🔍 Поиск",
        callback_data=SearchRegionCallback(),
    )
    # Кнопка назад (на всю ширину)
    builder.button(
        text="« Назад",
        callback_data=BackCallback(to="resource"),
    )
    # Регионы по 3 в ряд, затем поиск и назад по одной кнопке на строку
    regions_count = len(settings.regions_list)
    builder.adjust(*([3] * (regions_count // 3 + (1 if regions_count % 3 else 0))), 1, 1)
    return builder.as_markup()


def get_quantity_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора количества"""
    builder = InlineKeyboardBuilder()
    for qty in range(1, 6):
        builder.button(
            text=str(qty),
            callback_data=QuantityCallback(quantity=qty),
        )
    # Кнопка назад
    builder.button(
        text="« Назад",
        callback_data=BackCallback(to="region"),
    )
    builder.adjust(5, 1)
    return builder.as_markup()


def get_gender_keyboard(resource: Resource) -> InlineKeyboardMarkup:
    """Клавиатура выбора пола/типа"""
    builder = InlineKeyboardBuilder()

    if resource == Resource.GMAIL:
        # Gmail: Обычные / gmail.com
        builder.button(
            text=Gender.ANY.button_text,
            callback_data=GenderCallback(gender=Gender.ANY.value),
        )
        builder.button(
            text=Gender.GMAIL_DOMAIN.button_text,
            callback_data=GenderCallback(gender=Gender.GMAIL_DOMAIN.value),
        )
    else:
        # VK/Mamba/OK: Мужской / Женский
        builder.button(
            text=Gender.MALE.button_text,
            callback_data=GenderCallback(gender=Gender.MALE.value),
        )
        builder.button(
            text=Gender.FEMALE.button_text,
            callback_data=GenderCallback(gender=Gender.FEMALE.value),
        )

    # Кнопка назад
    builder.button(
        text="« Назад",
        callback_data=BackCallback(to="quantity"),
    )
    builder.adjust(2, 1)
    return builder.as_markup()


def get_feedback_keyboard(account_id: str, resource: str, gender: str, region: str) -> InlineKeyboardMarkup:
    """Клавиатура фидбека по аккаунту"""
    builder = InlineKeyboardBuilder()
    builder.button(
        text="🚫 Блок",
        callback_data=AccountFeedbackCallback(
            action="block", account_id=account_id, resource=resource, gender=gender, region=region
        ),
    )
    builder.button(
        text="✅ Хороший",
        callback_data=AccountFeedbackCallback(
            action="good", account_id=account_id, resource=resource, gender=gender, region=region
        ),
    )
    builder.button(
        text="⚠️ Дефектный",
        callback_data=AccountFeedbackCallback(
            action="defect", account_id=account_id, resource=resource, gender=gender, region=region
        ),
    )
    builder.adjust(3)
    return builder.as_markup()


def get_replace_keyboard(resource: str, gender: str, region: str) -> InlineKeyboardMarkup:
    """Клавиатура с кнопкой замены аккаунта"""
    builder = InlineKeyboardBuilder()
    builder.button(
        text="🔄 Заменить",
        callback_data=ReplaceAccountCallback(resource=resource, gender=gender, region=region),
    )
    builder.adjust(1)
    return builder.as_markup()


def get_back_to_region_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура с кнопкой возврата к выбору региона (для режима поиска)"""
    builder = InlineKeyboardBuilder()
    builder.button(
        text="« Назад к списку регионов",
        callback_data=BackCallback(to="region"),
    )
    builder.adjust(1)
    return builder.as_markup()


# === Клавиатуры для статистики ===

def get_stat_resource_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора ресурса для статистики"""
    builder = InlineKeyboardBuilder()
    for resource in Resource:
        builder.button(
            text=resource.button_text,
            callback_data=StatResourceCallback(resource=resource.value),
        )
    builder.adjust(2)
    return builder.as_markup()


def get_stat_gender_keyboard(resource: Resource) -> InlineKeyboardMarkup:
    """Клавиатура выбора пола/типа для статистики"""
    builder = InlineKeyboardBuilder()

    if resource == Resource.GMAIL:
        builder.button(
            text=Gender.ANY.button_text,
            callback_data=StatGenderCallback(gender=Gender.ANY.value),
        )
        builder.button(
            text=Gender.GMAIL_DOMAIN.button_text,
            callback_data=StatGenderCallback(gender=Gender.GMAIL_DOMAIN.value),
        )
    else:
        builder.button(
            text=Gender.MALE.button_text,
            callback_data=StatGenderCallback(gender=Gender.MALE.value),
        )
        builder.button(
            text=Gender.FEMALE.button_text,
            callback_data=StatGenderCallback(gender=Gender.FEMALE.value),
        )

    # Кнопка назад
    builder.button(
        text="« Назад",
        callback_data=StatBackCallback(to="resource"),
    )
    builder.adjust(2, 1)
    return builder.as_markup()


def get_stat_region_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора региона для статистики (с кнопкой 'Все регионы')"""
    builder = InlineKeyboardBuilder()

    for region in settings.regions_list:
        builder.button(
            text=region,
            callback_data=StatRegionCallback(region=region),
        )

    # Кнопка поиска
    builder.button(
        text="🔍 Поиск",
        callback_data=StatSearchRegionCallback(),
    )
    # Кнопка "Все регионы" на всю ширину
    builder.button(
        text="🌍 Все регионы",
        callback_data=StatRegionCallback(region="all"),
    )
    # Кнопка назад
    builder.button(
        text="« Назад",
        callback_data=StatBackCallback(to="gender"),
    )

    # Layout: регионы по 3, затем поиск (1), все регионы (1), назад (1)
    regions_count = len(settings.regions_list)
    builder.adjust(*([3] * (regions_count // 3 + (1 if regions_count % 3 else 0))), 1, 1, 1)
    return builder.as_markup()


def get_stat_back_to_region_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура с кнопкой возврата к выбору региона в статистике"""
    builder = InlineKeyboardBuilder()
    builder.button(
        text="« Назад к списку регионов",
        callback_data=StatBackCallback(to="region"),
    )
    builder.adjust(1)
    return builder.as_markup()


def get_stat_period_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора периода для статистики"""
    builder = InlineKeyboardBuilder()
    builder.button(
        text="📅 За день",
        callback_data=StatPeriodCallback(period="day"),
    )
    builder.button(
        text="📆 За неделю",
        callback_data=StatPeriodCallback(period="week"),
    )
    builder.button(
        text="🗓 За месяц",
        callback_data=StatPeriodCallback(period="month"),
    )
    # Кнопка назад
    builder.button(
        text="« Назад",
        callback_data=StatBackCallback(to="region"),
    )
    builder.adjust(3, 1)
    return builder.as_markup()
