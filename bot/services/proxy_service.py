import logging
import asyncio
import aiohttp
from typing import List, Optional, Dict
from datetime import datetime, date, timedelta
from collections import defaultdict

import gspread_asyncio

from bot.config import settings
from bot.models.proxy import Proxy
from bot.models.enums import get_country_flag

logger = logging.getLogger(__name__)

# Лист для прокси
PROXY_SHEET_NAME = "Прокси"


def parse_date(date_str: str) -> date:
    """Парсинг даты в форматах dd.mm.yy или YYYY-MM-DD (для совместимости)"""
    if not date_str:
        return date.today()

    # Сначала пробуем новый формат dd.mm.yy
    try:
        return datetime.strptime(date_str, "%d.%m.%y").date()
    except ValueError:
        pass

    # Затем старый формат YYYY-MM-DD
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return date.today()


class ProxyService:
    """Сервис для работы с прокси"""

    def __init__(self, agcm):
        self.agcm = agcm
        # Блокировка для конкурентного доступа: {row_index: locked}
        self._locks: Dict[int, bool] = {}
        self._lock = asyncio.Lock()

    async def _get_client(self):
        """Получение авторизованного клиента"""
        return await self.agcm.authorize()

    async def _get_worksheet(self):
        """Получить worksheet для прокси"""
        agc = await self._get_client()
        ss = await agc.open_by_key(settings.SPREADSHEET_ACCOUNTS)
        try:
            ws = await ss.worksheet(PROXY_SHEET_NAME)
        except gspread_asyncio.gspread.exceptions.WorksheetNotFound:
            # Создаём лист если не существует
            ws = await ss.add_worksheet(PROXY_SHEET_NAME, rows=1000, cols=10)
            # Добавляем заголовки
            await ws.append_row(
                ["proxy", "country", "added_date", "expires_date", "used_for", "proxy_type"],
                value_input_option="USER_ENTERED",
            )
        return ws

    # === Определение страны по IP ===

    async def get_country_by_ip(self, ip: str) -> str:
        """Определить страну по IP через ip-api.com"""
        try:
            async with aiohttp.ClientSession() as session:
                # Используем бесплатный API ip-api.com
                url = f"http://ip-api.com/json/{ip}?fields=countryCode"
                async with session.get(url, timeout=10) as response:
                    if response.status == 200:
                        data = await response.json()
                        country_code = data.get("countryCode", "UNKNOWN")
                        return country_code if country_code else "UNKNOWN"
        except Exception as e:
            logger.error(f"Error getting country for IP {ip}: {e}")
        return "UNKNOWN"

    def extract_ip(self, proxy: str) -> str:
        """Извлечь IP из строки прокси"""
        # Формат: ip:port или ip:port:user:pass
        parts = proxy.split(":")
        return parts[0] if parts else proxy

    # === Добавление прокси ===

    async def add_proxies(
        self,
        proxies: List[str],
        resources: List[str],
        duration_days: int,
        proxy_type: str = "http",
    ) -> List[Dict]:
        """Добавить список прокси в таблицу

        Args:
            proxies: Список прокси строк
            resources: Список ресурсов для которых использованы прокси
            duration_days: Срок действия в днях
            proxy_type: Тип прокси (http или socks5)
        """
        ws = await self._get_worksheet()
        results = []
        today = date.today()
        expires = today + timedelta(days=duration_days)

        # Формируем строку ресурсов через запятую
        used_for_str = ",".join([r.lower() for r in resources])

        for proxy_str in proxies:
            proxy_str = proxy_str.strip()
            if not proxy_str:
                continue

            # Определяем страну по IP
            ip = self.extract_ip(proxy_str)
            country = await self.get_country_by_ip(ip)

            # Добавляем в таблицу
            row_data = [
                proxy_str,
                country,
                today.strftime("%d.%m.%y"),
                expires.strftime("%d.%m.%y"),
                used_for_str,  # used_for - список ресурсов
                proxy_type,  # proxy_type
            ]

            await ws.append_row(row_data, value_input_option="USER_ENTERED")

            results.append({
                "proxy": proxy_str,
                "country": country,
                "country_flag": get_country_flag(country),
                "expires": expires.strftime("%d.%m.%y"),
            })

            # Небольшая задержка чтобы не превысить лимиты API
            await asyncio.sleep(0.5)

        return results

    # === Получение прокси ===

    async def get_all_proxies(self) -> List[Proxy]:
        """Получить все прокси из таблицы"""
        ws = await self._get_worksheet()
        all_values = await ws.get_all_values()

        proxies = []
        # Пропускаем заголовок
        for idx, row in enumerate(all_values[1:], start=2):
            if not row or not row[0]:
                continue

            try:
                proxy = Proxy(
                    proxy=row[0],
                    country=row[1] if len(row) > 1 else "UNKNOWN",
                    added_date=parse_date(row[2] if len(row) > 2 else ""),
                    expires_date=parse_date(row[3] if len(row) > 3 else ""),
                    used_for=Proxy.parse_used_for(row[4] if len(row) > 4 else ""),
                    row_index=idx,
                    proxy_type=row[5] if len(row) > 5 and row[5] else "http",  # Дефолт http для старых записей
                )
                proxies.append(proxy)
            except Exception as e:
                logger.error(f"Error parsing proxy row {idx}: {e}")
                continue

        return proxies

    async def get_available_proxies(self, resource: str) -> List[Proxy]:
        """Получить доступные прокси для ресурса (не использованные и не просроченные)"""
        all_proxies = await self.get_all_proxies()

        available = []
        for proxy in all_proxies:
            # Пропускаем просроченные
            if proxy.is_expired:
                continue
            # Пропускаем уже использованные для этого ресурса
            if proxy.is_used_for(resource):
                continue
            available.append(proxy)

        return available

    async def get_countries_with_counts(self, resource: str) -> Dict[str, int]:
        """Получить словарь стран с количеством доступных прокси"""
        proxies = await self.get_available_proxies(resource)

        counts = defaultdict(int)
        for proxy in proxies:
            counts[proxy.country] += 1

        return dict(counts)

    async def get_proxies_by_country(self, resource: str, country: str) -> List[Proxy]:
        """Получить прокси для ресурса по стране"""
        proxies = await self.get_available_proxies(resource)
        return [p for p in proxies if p.country.upper() == country.upper()]

    # === Взятие прокси (с блокировкой) ===

    async def try_take_proxy(self, row_index: int, resource: str, user_id: int) -> Optional[Proxy]:
        """
        Попытаться взять прокси.
        Возвращает Proxy если успешно, None если уже занят.
        """
        async with self._lock:
            # Проверяем блокировку
            if self._locks.get(row_index):
                return None

            # Блокируем
            self._locks[row_index] = True

        try:
            # Получаем текущие данные прокси
            ws = await self._get_worksheet()
            row = await ws.row_values(row_index)

            if not row or not row[0]:
                return None

            # Проверяем что прокси ещё доступен для этого ресурса
            used_for = Proxy.parse_used_for(row[4] if len(row) > 4 else "")
            if resource.lower() in [r.lower() for r in used_for]:
                # Уже использован для этого ресурса (кто-то успел раньше)
                return None

            # Добавляем ресурс в used_for
            used_for.append(resource.lower())
            new_used_for = ",".join(used_for)

            # Обновляем в таблице (колонка E = 5)
            await ws.update_cell(row_index, 5, new_used_for)

            # Создаём объект Proxy
            proxy = Proxy(
                proxy=row[0],
                country=row[1] if len(row) > 1 else "UNKNOWN",
                added_date=parse_date(row[2] if len(row) > 2 else ""),
                expires_date=parse_date(row[3] if len(row) > 3 else ""),
                used_for=used_for,
                row_index=row_index,
                proxy_type=row[5] if len(row) > 5 and row[5] else "http",
            )

            logger.info(f"User {user_id} took proxy {proxy.ip_short} for {resource}")
            return proxy

        except Exception as e:
            logger.error(f"Error taking proxy {row_index}: {e}")
            return None
        finally:
            # Снимаем блокировку
            async with self._lock:
                self._locks.pop(row_index, None)

    async def get_proxy_by_row(self, row_index: int) -> Optional[Proxy]:
        """Получить прокси по индексу строки"""
        try:
            ws = await self._get_worksheet()
            row = await ws.row_values(row_index)

            if not row or not row[0]:
                return None

            return Proxy(
                proxy=row[0],
                country=row[1] if len(row) > 1 else "UNKNOWN",
                added_date=parse_date(row[2] if len(row) > 2 else ""),
                expires_date=parse_date(row[3] if len(row) > 3 else ""),
                used_for=Proxy.parse_used_for(row[4] if len(row) > 4 else ""),
                row_index=row_index,
                proxy_type=row[5] if len(row) > 5 and row[5] else "http",
            )
        except Exception as e:
            logger.error(f"Error getting proxy by row {row_index}: {e}")
            return None


# Глобальный экземпляр сервиса
_proxy_service: Optional[ProxyService] = None


def init_proxy_service(agcm):
    """Инициализация сервиса прокси"""
    global _proxy_service
    _proxy_service = ProxyService(agcm)
    return _proxy_service


def get_proxy_service() -> ProxyService:
    """Получить экземпляр сервиса прокси"""
    if _proxy_service is None:
        raise RuntimeError("Proxy service not initialized. Call init_proxy_service first.")
    return _proxy_service
