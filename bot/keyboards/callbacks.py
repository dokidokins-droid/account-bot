from aiogram.filters.callback_data import CallbackData


class AdminApprovalCallback(CallbackData, prefix="admin"):
    """Callback для одобрения/отклонения заявки админом"""
    action: str  # "approve" или "reject"
    user_id: int


class ResourceCallback(CallbackData, prefix="res"):
    """Callback для выбора ресурса"""
    resource: str  # vk, mamba, ok, gmail


class RegionCallback(CallbackData, prefix="reg"):
    """Callback для выбора региона"""
    region: str


class QuantityCallback(CallbackData, prefix="qty"):
    """Callback для выбора количества"""
    quantity: int


class GenderCallback(CallbackData, prefix="gen"):
    """Callback для выбора пола/типа"""
    gender: str  # male, female, any, gmail_domain


class AccountFeedbackCallback(CallbackData, prefix="fb"):
    """Callback для фидбека по аккаунту"""
    action: str  # block, good, defect
    account_id: str  # Уникальный ID записи (номер строки в таблице выданных)
    resource: str  # Ресурс для замены
    gender: str  # Пол/тип для замены
    region: str  # Регион для замены


class BackCallback(CallbackData, prefix="back"):
    """Callback для кнопки назад"""
    to: str  # Куда вернуться: resource, region, quantity


class SearchRegionCallback(CallbackData, prefix="search"):
    """Callback для кнопки поиска региона"""
    pass


class ReplaceAccountCallback(CallbackData, prefix="repl"):
    """Callback для замены аккаунта"""
    resource: str
    gender: str
    region: str


# === Статистика ===

class StatResourceCallback(CallbackData, prefix="stat_res"):
    """Callback для выбора ресурса в статистике (VK, Mamba, OK)"""
    resource: str


class StatEmailMenuCallback(CallbackData, prefix="stat_email"):
    """Callback для открытия раздела почт в статистике"""
    action: str  # open


class StatEmailResourceCallback(CallbackData, prefix="stat_em_res"):
    """Callback для выбора почтового ресурса в статистике (Gmail/Rambler)"""
    resource: str  # gmail, rambler


class StatNumberMenuCallback(CallbackData, prefix="stat_num"):
    """Callback для открытия раздела номеров в статистике"""
    action: str  # open


class StatGenderCallback(CallbackData, prefix="stat_gen"):
    """Callback для выбора пола/типа в статистике"""
    gender: str


class StatRegionCallback(CallbackData, prefix="stat_reg"):
    """Callback для выбора региона в статистике"""
    region: str  # "all" для всех регионов


class StatSearchRegionCallback(CallbackData, prefix="stat_search"):
    """Callback для поиска региона в статистике"""
    pass


class StatPeriodCallback(CallbackData, prefix="stat_per"):
    """Callback для выбора периода в статистике"""
    period: str  # day, week, month


class StatBackCallback(CallbackData, prefix="stat_back"):
    """Callback для кнопки назад в статистике"""
    to: str  # resource, gender, region, period


class StatDetailedByRegionsCallback(CallbackData, prefix="stat_det"):
    """Callback для детальной статистики по регионам"""
    resource: str
    gender: str
    period: str


# === Прокси ===

class ProxyMenuCallback(CallbackData, prefix="prx_menu"):
    """Callback для главного меню прокси"""
    action: str  # add, get


class ProxyResourceCallback(CallbackData, prefix="prx_res"):
    """Callback для выбора ресурса прокси"""
    resource: str
    mode: str  # add, get


class ProxyDurationCallback(CallbackData, prefix="prx_dur"):
    """Callback для выбора срока действия"""
    duration: str  # 5, 10, 15, 30


class ProxyCountryCallback(CallbackData, prefix="prx_ctr"):
    """Callback для выбора страны"""
    country: str  # Код страны (RU, US, etc.)


class ProxySelectCallback(CallbackData, prefix="prx_sel"):
    """Callback для выбора конкретного прокси"""
    row_index: int  # Индекс строки прокси в таблице


class ProxyPageCallback(CallbackData, prefix="prx_page"):
    """Callback для пагинации прокси"""
    page: int
    country: str  # Текущая выбранная страна


class ProxyBackCallback(CallbackData, prefix="prx_back"):
    """Callback для кнопки назад в прокси"""
    to: str  # menu, resource, country


class ProxyTypeCallback(CallbackData, prefix="prx_type"):
    """Callback для выбора типа прокси"""
    proxy_type: str  # http или socks5


class ProxyResourceToggleCallback(CallbackData, prefix="prx_tog"):
    """Toggle выбора ресурса для прокси (множественный выбор)"""
    resource: str


class ProxyResourceConfirmCallback(CallbackData, prefix="prx_conf"):
    """Подтверждение выбора ресурсов"""
    pass


class ProxyToggleCallback(CallbackData, prefix="prx_tgl"):
    """Toggle выбора прокси для множественного выбора"""
    row_index: int
    country: str
    page: int = 0


class ProxyConfirmMultiCallback(CallbackData, prefix="prx_cfm"):
    """Подтверждение выбора нескольких прокси"""
    country: str


# === Номера ===

class NumberMenuCallback(CallbackData, prefix="num_menu"):
    """Callback для открытия меню номеров"""
    action: str  # open


class NumberResourceToggleCallback(CallbackData, prefix="num_tog"):
    """Toggle выбора ресурса для номеров (множественный выбор)"""
    resource: str  # beboo, loloo, tabor


class NumberResourceConfirmCallback(CallbackData, prefix="num_conf"):
    """Подтверждение выбора ресурсов номеров"""
    pass


class NumberRegionCallback(CallbackData, prefix="num_reg"):
    """Callback для выбора региона для номеров"""
    region: str


class NumberSearchRegionCallback(CallbackData, prefix="num_search"):
    """Callback для поиска региона в номерах"""
    pass


class NumberQuantityCallback(CallbackData, prefix="num_qty"):
    """Callback для выбора количества номеров"""
    quantity: int


class NumberBackCallback(CallbackData, prefix="num_back"):
    """Callback для кнопки назад в номерах"""
    to: str  # resources, region


class NumberTodayModeCallback(CallbackData, prefix="num_mode"):
    """Callback для переключения режима today_only"""
    action: str  # enable, disable


class NumberFeedbackCallback(CallbackData, prefix="num_fb"):
    """Callback для фидбека по номеру"""
    action: str  # working, reset, registered, tg_kicked
    number_id: str  # Уникальный ID записи (row_index из таблицы Выдачи)
    resources: str  # Ресурсы через запятую (для отображения)
    region: str  # Регион для замены


class NumberReplaceCallback(CallbackData, prefix="num_repl"):
    """Callback для замены номера"""
    resources: str  # Ресурсы через запятую
    region: str


# === Почты ===

class EmailMenuCallback(CallbackData, prefix="email_menu"):
    """Callback для открытия меню почт"""
    action: str  # open


class EmailResourceCallback(CallbackData, prefix="email_res"):
    """Callback для выбора почтового ресурса"""
    resource: str  # gmail, rambler


class EmailTypeCallback(CallbackData, prefix="email_type"):
    """Callback для выбора типа Gmail (Обычные/gmail.com)"""
    email_type: str  # any, gmail_domain


class EmailRegionCallback(CallbackData, prefix="email_reg"):
    """Callback для выбора региона для почт"""
    region: str


class EmailSearchRegionCallback(CallbackData, prefix="email_search"):
    """Callback для поиска региона в почтах"""
    pass


class EmailQuantityCallback(CallbackData, prefix="email_qty"):
    """Callback для выбора количества почт"""
    quantity: int


class EmailBackCallback(CallbackData, prefix="email_back"):
    """Callback для кнопки назад в почтах"""
    to: str  # main, email_resource, email_type, region


class EmailFeedbackCallback(CallbackData, prefix="email_fb"):
    """Callback для фидбека по почте"""
    action: str  # block, good, defect
    email_id: str  # Уникальный ID записи
    resource: str  # gmail, rambler
    email_type: str  # any, gmail_domain, none
    region: str


class EmailReplaceCallback(CallbackData, prefix="email_repl"):
    """Callback для замены почты"""
    resource: str
    email_type: str
    region: str


# === Очистка буфера (админ) ===

class BufferClearCategoryCallback(CallbackData, prefix="buf_cat"):
    """Callback для выбора категории очистки"""
    category: str  # accounts, emails, all


class BufferClearResourceCallback(CallbackData, prefix="buf_res"):
    """Callback для выбора ресурса очистки"""
    resource: str  # vk, mamba_male, mamba_female, ok, gmail_any, gmail_domain, rambler, all_accounts, all_emails


class BufferClearTypeCallback(CallbackData, prefix="buf_type"):
    """Callback для выбора типа очистки"""
    clear_type: str  # available, pending, write_buffer, all


class BufferClearConfirmCallback(CallbackData, prefix="buf_conf"):
    """Callback для подтверждения очистки"""
    action: str  # confirm, cancel


class BufferClearBackCallback(CallbackData, prefix="buf_back"):
    """Callback для кнопки назад в очистке буфера"""
    to: str  # category, resource, type
