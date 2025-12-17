from dataclasses import dataclass
from typing import Optional


@dataclass
class BaseAccount:
    """Базовый класс аккаунта"""
    login: str
    password: str
    row_index: int  # Индекс строки в таблице для удаления


@dataclass
class VKAccount(BaseAccount):
    """ВКонтакте: логин (номер) | пароль"""
    pass


@dataclass
class MambaAccount(BaseAccount):
    """Мамба: логин (почта) | пароль мамбы | пароль почты | ссылка подтверждения"""
    email_password: str
    confirmation_link: str


@dataclass
class OKAccount(BaseAccount):
    """Одноклассники: логин (номер/почта) | пароль"""
    pass


@dataclass
class GmailAccount(BaseAccount):
    """Gmail: логин (почта) | пароль | резервная почта (опц.)"""
    backup_email: Optional[str] = None


@dataclass
class IssuedAccount:
    """Запись о выданном аккаунте"""
    date: str
    full_data: str
    region: str
    employee_stage: str
    resource: str
    gender: str
    status: Optional[str] = None
