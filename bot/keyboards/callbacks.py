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
