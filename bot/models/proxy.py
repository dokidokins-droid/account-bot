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
    proxy_type: str = "http"  # Тип прокси: http или socks5

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

    @property
    def port(self) -> Optional[int]:
        """Получить порт из прокси строки"""
        parts = self.proxy.split(":")
        if len(parts) >= 2:
            try:
                return int(parts[1])
            except ValueError:
                return None
        return None

    @property
    def auth(self) -> str:
        """Получить аутентификацию (user:pass) если есть"""
        parts = self.proxy.split(":")
        if len(parts) >= 4:
            return f"{parts[2]}:{parts[3]}"
        return ""

    def get_http_proxy(self) -> str:
        """Получить HTTP вариант прокси с полным URL"""
        port = self.port
        if port is None:
            return f"http://{self.proxy}"

        if self.proxy_type == "socks5":
            # Для SOCKS5 прокси: HTTP порт = текущий порт - 1
            http_port = port - 1
        else:
            # Уже HTTP
            http_port = port

        auth = self.auth
        if auth:
            return f"http://{self.ip}:{http_port}:{auth}"
        return f"http://{self.ip}:{http_port}"

    def get_socks5_proxy(self) -> str:
        """Получить SOCKS5 вариант прокси с полным URL"""
        port = self.port
        if port is None:
            return f"socks5://{self.proxy}"

        if self.proxy_type == "http":
            # Для HTTP прокси: SOCKS5 порт = текущий порт + 1
            socks5_port = port + 1
        else:
            # Уже SOCKS5
            socks5_port = port

        auth = self.auth
        if auth:
            return f"socks5://{self.ip}:{socks5_port}:{auth}"
        return f"socks5://{self.ip}:{socks5_port}"
