from dataclasses import dataclass
from typing import Optional


@dataclass
class User:
    """Пользователь системы (сотрудник)"""
    telegram_id: int
    stage: str  # Рабочий никнейм
    is_approved: bool = False
    row_index: Optional[int] = None  # Индекс строки в whitelist таблице
