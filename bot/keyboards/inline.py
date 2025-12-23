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
    StatDetailedByRegionsCallback,
    StatEmailMenuCallback,
    StatEmailResourceCallback,
    StatNumberMenuCallback,
    # Прокси
    ProxyMenuCallback,
    # Номера
    NumberMenuCallback,
    # Почты
    EmailMenuCallback,
)
from bot.models.enums import Resource, Gender, EmailResource
from bot.services.region_service import region_service


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
    # Добавляем все ресурсы кроме Gmail
    for resource in Resource:
        if resource != Resource.GMAIL:
            builder.button(
                text=resource.button_text,
                callback_data=ResourceCallback(resource=resource.value),
            )
    # Кнопка почт (вместо прямого Gmail)
    builder.button(
        text="📧 Почты",
        callback_data=EmailMenuCallback(action="open"),
    )
    # Кнопка номеров
    builder.button(
        text="📱 Номера",
        callback_data=NumberMenuCallback(action="open"),
    )
    # Кнопка прокси
    builder.button(
        text="🌐 Прокси",
        callback_data=ProxyMenuCallback(action="open"),
    )
    # Ресурсы по 2 в ряд, почты/номера/прокси по ряду
    builder.adjust(2, 2, 1, 2)
    return builder.as_markup()


def get_region_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора региона"""
    builder = InlineKeyboardBuilder()
    # Получаем отсортированный список регионов из сервиса
    for region in region_service.get_regions():
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
    regions_count = len(region_service.get_regions())
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
    """Клавиатура выбора пола/типа. Возвращает None для VK и OK."""
    # Для VK и OK пол не выбирается
    if resource in (Resource.VK, Resource.OK):
        return None

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
        # Mamba: Мужской / Женский
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
    """Клавиатура выбора ресурса для статистики (VK, Mamba, OK + разделы Почты/Номера)"""
    builder = InlineKeyboardBuilder()
    # Основные ресурсы (без Gmail - он теперь в разделе Почты)
    for resource in Resource:
        if resource != Resource.GMAIL:
            builder.button(
                text=resource.button_text,
                callback_data=StatResourceCallback(resource=resource.value),
            )
    # Раздел Почты
    builder.button(
        text="📧 Почты",
        callback_data=StatEmailMenuCallback(action="open"),
    )
    # Раздел Номера
    builder.button(
        text="📱 Номера",
        callback_data=StatNumberMenuCallback(action="open"),
    )
    # VK, Mamba, OK по 2 в ряд, затем Почты и Номера
    builder.adjust(2, 1, 2)
    return builder.as_markup()


def get_stat_gender_keyboard(resource: Resource) -> InlineKeyboardMarkup:
    """Клавиатура выбора пола/типа для статистики. Возвращает None для VK и OK."""
    # Для VK и OK пол не выбирается
    if resource in (Resource.VK, Resource.OK):
        return None

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

    # Получаем отсортированный список регионов из сервиса
    for region in region_service.get_regions():
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
    regions_count = len(region_service.get_regions())
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


def get_stat_detailed_keyboard(resource: str, gender: str, period: str) -> InlineKeyboardMarkup:
    """Клавиатура с кнопкой 'Детальнее по регионам' для общей статистики"""
    builder = InlineKeyboardBuilder()
    builder.button(
        text="📊 Детальнее по регионам",
        callback_data=StatDetailedByRegionsCallback(resource=resource, gender=gender, period=period),
    )
    builder.adjust(1)
    return builder.as_markup()


# === Клавиатуры для статистики почт ===

def get_stat_email_resource_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора почтового ресурса для статистики (Gmail/Rambler)"""
    builder = InlineKeyboardBuilder()
    for resource in EmailResource:
        builder.button(
            text=resource.button_text,
            callback_data=StatEmailResourceCallback(resource=resource.value),
        )
    # Кнопка назад
    builder.button(
        text="« Назад",
        callback_data=StatBackCallback(to="resource"),
    )
    builder.adjust(2, 1)
    return builder.as_markup()


def get_stat_email_type_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора типа Gmail для статистики (Обычные/gmail.com)"""
    builder = InlineKeyboardBuilder()
    builder.button(
        text=Gender.ANY.button_text,
        callback_data=StatGenderCallback(gender=Gender.ANY.value),
    )
    builder.button(
        text=Gender.GMAIL_DOMAIN.button_text,
        callback_data=StatGenderCallback(gender=Gender.GMAIL_DOMAIN.value),
    )
    # Кнопка назад к выбору почтового ресурса
    builder.button(
        text="« Назад",
        callback_data=StatBackCallback(to="email_resource"),
    )
    builder.adjust(2, 1)
    return builder.as_markup()


def get_stat_email_region_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора региона для статистики почт"""
    builder = InlineKeyboardBuilder()

    for region in region_service.get_regions():
        builder.button(
            text=region,
            callback_data=StatRegionCallback(region=region),
        )

    # Кнопка поиска
    builder.button(
        text="🔍 Поиск",
        callback_data=StatSearchRegionCallback(),
    )
    # Кнопка "Все регионы"
    builder.button(
        text="🌍 Все регионы",
        callback_data=StatRegionCallback(region="all"),
    )
    # Кнопка назад к типу/ресурсу почты
    builder.button(
        text="« Назад",
        callback_data=StatBackCallback(to="email_type"),
    )

    regions_count = len(region_service.get_regions())
    builder.adjust(*([3] * (regions_count // 3 + (1 if regions_count % 3 else 0))), 1, 1, 1)
    return builder.as_markup()


def get_stat_email_back_to_region_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура с кнопкой возврата к выбору региона в статистике почт"""
    builder = InlineKeyboardBuilder()
    builder.button(
        text="« Назад к списку регионов",
        callback_data=StatBackCallback(to="email_region"),
    )
    builder.adjust(1)
    return builder.as_markup()


def get_stat_email_period_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора периода для статистики почт"""
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
        callback_data=StatBackCallback(to="email_region"),
    )
    builder.adjust(3, 1)
    return builder.as_markup()


# === Клавиатуры для статистики номеров ===

def get_stat_number_region_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора региона для статистики номеров"""
    builder = InlineKeyboardBuilder()

    for region in region_service.get_regions():
        builder.button(
            text=region,
            callback_data=StatRegionCallback(region=region),
        )

    # Кнопка поиска
    builder.button(
        text="🔍 Поиск",
        callback_data=StatSearchRegionCallback(),
    )
    # Кнопка "Все регионы"
    builder.button(
        text="🌍 Все регионы",
        callback_data=StatRegionCallback(region="all"),
    )
    # Кнопка назад к главному меню статистики
    builder.button(
        text="« Назад",
        callback_data=StatBackCallback(to="resource"),
    )

    regions_count = len(region_service.get_regions())
    builder.adjust(*([3] * (regions_count // 3 + (1 if regions_count % 3 else 0))), 1, 1, 1)
    return builder.as_markup()


def get_stat_number_back_to_region_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура с кнопкой возврата к выбору региона в статистике номеров"""
    builder = InlineKeyboardBuilder()
    builder.button(
        text="« Назад к списку регионов",
        callback_data=StatBackCallback(to="number_region"),
    )
    builder.adjust(1)
    return builder.as_markup()


def get_stat_number_period_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора периода для статистики номеров"""
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
        callback_data=StatBackCallback(to="number_region"),
    )
    builder.adjust(3, 1)
    return builder.as_markup()


# === Клавиатуры для очистки буфера (админ) ===

from bot.keyboards.callbacks import (
    BufferClearCategoryCallback,
    BufferClearResourceCallback,
    BufferClearTypeCallback,
    BufferClearConfirmCallback,
    BufferClearBackCallback,
)


def get_buffer_clear_category_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора категории для очистки буфера"""
    builder = InlineKeyboardBuilder()
    builder.button(
        text="📦 Аккаунты",
        callback_data=BufferClearCategoryCallback(category="accounts"),
    )
    builder.button(
        text="📧 Почты",
        callback_data=BufferClearCategoryCallback(category="emails"),
    )
    builder.button(
        text="🗑 Очистить ВСЁ",
        callback_data=BufferClearCategoryCallback(category="all"),
    )
    builder.adjust(2, 1)
    return builder.as_markup()


def get_buffer_clear_accounts_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора ресурса аккаунтов для очистки"""
    builder = InlineKeyboardBuilder()
    builder.button(
        text="🔵 ВКонтакте",
        callback_data=BufferClearResourceCallback(resource="vk"),
    )
    builder.button(
        text="🔴 Мамба М",
        callback_data=BufferClearResourceCallback(resource="mamba_male"),
    )
    builder.button(
        text="🔴 Мамба Ж",
        callback_data=BufferClearResourceCallback(resource="mamba_female"),
    )
    builder.button(
        text="🟠 Одноклассники",
        callback_data=BufferClearResourceCallback(resource="ok"),
    )
    builder.button(
        text="📦 Все аккаунты",
        callback_data=BufferClearResourceCallback(resource="all_accounts"),
    )
    builder.button(
        text="« Назад",
        callback_data=BufferClearBackCallback(to="category"),
    )
    builder.adjust(2, 2, 1, 1)
    return builder.as_markup()


def get_buffer_clear_emails_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора ресурса почт для очистки"""
    builder = InlineKeyboardBuilder()
    builder.button(
        text="📧 Gmail Обычные",
        callback_data=BufferClearResourceCallback(resource="gmail_any"),
    )
    builder.button(
        text="📧 Gmail gmail.com",
        callback_data=BufferClearResourceCallback(resource="gmail_domain"),
    )
    builder.button(
        text="📨 Рамблер",
        callback_data=BufferClearResourceCallback(resource="rambler"),
    )
    builder.button(
        text="📧 Все почты",
        callback_data=BufferClearResourceCallback(resource="all_emails"),
    )
    builder.button(
        text="« Назад",
        callback_data=BufferClearBackCallback(to="category"),
    )
    builder.adjust(2, 2, 1)
    return builder.as_markup()


def get_buffer_clear_type_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора типа очистки"""
    builder = InlineKeyboardBuilder()
    builder.button(
        text="📥 Готовые к выдаче (available)",
        callback_data=BufferClearTypeCallback(clear_type="available"),
    )
    builder.button(
        text="⏳ Ожидающие feedback (pending)",
        callback_data=BufferClearTypeCallback(clear_type="pending"),
    )
    builder.button(
        text="📝 Буфер записи (write_buffer)",
        callback_data=BufferClearTypeCallback(clear_type="write_buffer"),
    )
    builder.button(
        text="🗑 Очистить ВСЁ",
        callback_data=BufferClearTypeCallback(clear_type="all"),
    )
    builder.button(
        text="« Назад",
        callback_data=BufferClearBackCallback(to="resource"),
    )
    builder.adjust(1)
    return builder.as_markup()


def get_buffer_clear_confirm_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура подтверждения очистки"""
    builder = InlineKeyboardBuilder()
    builder.button(
        text="✅ Подтвердить",
        callback_data=BufferClearConfirmCallback(action="confirm"),
    )
    builder.button(
        text="❌ Отмена",
        callback_data=BufferClearConfirmCallback(action="cancel"),
    )
    builder.adjust(2)
    return builder.as_markup()


# === Клавиатуры для освобождения буфера (возврат в базу) ===

from bot.keyboards.callbacks import (
    BufferReleaseCategoryCallback,
    BufferReleaseResourceCallback,
    BufferReleaseConfirmCallback,
    BufferReleaseBackCallback,
)


def get_buffer_release_category_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора категории для освобождения буфера"""
    builder = InlineKeyboardBuilder()
    builder.button(
        text="📦 Аккаунты",
        callback_data=BufferReleaseCategoryCallback(category="accounts"),
    )
    builder.button(
        text="📧 Почты",
        callback_data=BufferReleaseCategoryCallback(category="emails"),
    )
    builder.button(
        text="📱 Номера",
        callback_data=BufferReleaseCategoryCallback(category="numbers"),
    )
    builder.adjust(2, 1)
    return builder.as_markup()


def get_buffer_release_numbers_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора ресурса номеров для освобождения"""
    builder = InlineKeyboardBuilder()
    builder.button(
        text="🔄 Освободить ВСЕ номера",
        callback_data=BufferReleaseResourceCallback(resource="all_numbers"),
    )
    builder.button(
        text="🗓 Освободить устаревшие",
        callback_data=BufferReleaseResourceCallback(resource="outdated_numbers"),
    )
    builder.button(
        text="◀️ Назад",
        callback_data=BufferReleaseBackCallback(to="category"),
    )
    builder.adjust(1, 1, 1)
    return builder.as_markup()


def get_buffer_release_accounts_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора ресурса аккаунтов для освобождения"""
    builder = InlineKeyboardBuilder()
    builder.button(
        text="🔵 VK",
        callback_data=BufferReleaseResourceCallback(resource="vk"),
    )
    builder.button(
        text="🔴 Mamba (М)",
        callback_data=BufferReleaseResourceCallback(resource="mamba_male"),
    )
    builder.button(
        text="🔴 Mamba (Ж)",
        callback_data=BufferReleaseResourceCallback(resource="mamba_female"),
    )
    builder.button(
        text="🟠 OK",
        callback_data=BufferReleaseResourceCallback(resource="ok"),
    )
    builder.button(
        text="🔄 Освободить ВСЕ аккаунты",
        callback_data=BufferReleaseResourceCallback(resource="all_accounts"),
    )
    builder.button(
        text="◀️ Назад",
        callback_data=BufferReleaseBackCallback(to="category"),
    )
    builder.adjust(2, 2, 1, 1)
    return builder.as_markup()


def get_buffer_release_emails_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора ресурса почт для освобождения"""
    builder = InlineKeyboardBuilder()
    builder.button(
        text="📧 Gmail (Обычные)",
        callback_data=BufferReleaseResourceCallback(resource="gmail_any"),
    )
    builder.button(
        text="📧 Gmail (@gmail)",
        callback_data=BufferReleaseResourceCallback(resource="gmail_domain"),
    )
    builder.button(
        text="📨 Rambler",
        callback_data=BufferReleaseResourceCallback(resource="rambler"),
    )
    builder.button(
        text="🔄 Освободить ВСЕ почты",
        callback_data=BufferReleaseResourceCallback(resource="all_emails"),
    )
    builder.button(
        text="◀️ Назад",
        callback_data=BufferReleaseBackCallback(to="category"),
    )
    builder.adjust(2, 1, 1, 1)
    return builder.as_markup()


def get_buffer_release_confirm_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура подтверждения освобождения"""
    builder = InlineKeyboardBuilder()
    builder.button(
        text="✅ Освободить",
        callback_data=BufferReleaseConfirmCallback(action="confirm"),
    )
    builder.button(
        text="❌ Отмена",
        callback_data=BufferReleaseConfirmCallback(action="cancel"),
    )
    builder.adjust(2)
    return builder.as_markup()
