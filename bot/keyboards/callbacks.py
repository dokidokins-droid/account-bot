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
    """Callback для выбора ресурса в статистике"""
    resource: str


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
