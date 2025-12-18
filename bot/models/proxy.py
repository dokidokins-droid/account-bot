from dataclasses import dataclass, field
from datetime import datetime, date
from typing import List, Optional


@dataclass
class Proxy:
    """Модель прокси"""
    proxy: str  # Полная строка прокси (ip:port или ip:port:user:pass)
    country: str  # Код страны (RU, US, etc.)
    added_date: date  # Дата добавления
    expires_date: date  # Дата истечения
    used_for: List[str] = field(default_factory=list)  # Список ресурсов для которых использован
    row_index: Optional[int] = None  # Индекс строки в таблице

    @property
    def ip(self) -> str:
        """Получить IP из прокси строки"""
        return self.proxy.split(":")[0]

    @property
    def ip_short(self) -> str:
        """Получить сокращённый IP (первые два октета)"""
        parts = self.ip.split(".")
        if len(parts) >= 2:
            return f"{parts[0]}.{parts[1]}.."
        return self.ip

    @property
    def days_left(self) -> int:
        """Сколько дней осталось до истечения"""
        delta = self.expires_date - date.today()
        return max(0, delta.days)

    @property
    def is_expired(self) -> bool:
        """Истёк ли срок действия"""
        return self.days_left <= 0

    def is_used_for(self, resource: str) -> bool:
        """Проверить использовался ли прокси для ресурса"""
        return resource.lower() in [r.lower() for r in self.used_for]

    def add_usage(self, resource: str) -> None:
        """Добавить использование для ресурса"""
        if not self.is_used_for(resource):
            self.used_for.append(resource.lower())

    @property
    def used_for_str(self) -> str:
        """Строка использований для записи в таблицу"""
        return ",".join(self.used_for) if self.used_for else ""

    @classmethod
    def parse_used_for(cls, used_for_str: str) -> List[str]:
        """Парсинг строки использований из таблицы"""
        if not used_for_str:
            return []
        return [r.strip().lower() for r in used_for_str.split(",") if r.strip()]
