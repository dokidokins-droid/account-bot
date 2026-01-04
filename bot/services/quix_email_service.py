"""
Сервис для работы с API quix.email - аренда временных почт.

API документация: https://quix.email/api

Функционал:
- Получение списка доступных доменов почт
- Заказ почты для конкретного сайта
- Проверка статуса получения письма
- Отмена заказа
- Повторный запрос на ту же почту
- Парсинг содержимого письма (код/ссылка)
"""
import re
import logging
import aiohttp
from typing import Dict, Any, List, Optional
from dataclasses import dataclass

from bot.config import settings

logger = logging.getLogger(__name__)

# Базовый URL API
QUIX_API_BASE_URL = "https://quix.email/api/v1"

# Настройки поллинга
POLL_INTERVAL = 10  # секунд
POLL_TIMEOUT = 600  # 10 минут


@dataclass
class QuixEmailResult:
    """Результат заказа почты"""
    id: str
    email: str
    site: str


@dataclass
class QuixEmailStatus:
    """Статус почты"""
    id: str
    email: str
    status: str  # waiting, completed, cancelled, no_email
    data: Optional[str] = None  # Содержимое письма
    parsed: Optional[str] = None  # Извлечённый код/ссылка


@dataclass
class ParsedEmailContent:
    """Распарсенное содержимое письма"""
    code: Optional[str] = None  # Код подтверждения (4-6 цифр)
    link: Optional[str] = None  # Ссылка подтверждения
    raw: str = ""  # Полный текст


def normalize_site(site: str) -> str:
    """
    Нормализовать домен сайта: убрать протокол, www, путь.

    Примеры:
        https://mamba.ru/registration -> mamba.ru
        www.beboo.ru -> beboo.ru
        http://ok.ru/path/to/page -> ok.ru
    """
    site = site.strip().lower()
    # Убираем протокол
    site = re.sub(r'^https?://', '', site)
    # Убираем www.
    site = re.sub(r'^www\.', '', site)
    # Убираем путь и query string
    site = site.split('/')[0]
    site = site.split('?')[0]
    site = site.split('#')[0]
    return site


def _strip_html_for_code_search(html: str) -> str:
    """
    Извлечь текстовое содержимое из HTML для поиска кодов.
    Удаляет теги, атрибуты, стили, скрипты, URL.
    """
    text = html

    # Удаляем style и script блоки
    text = re.sub(r'<style[^>]*>.*?</style>', ' ', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<script[^>]*>.*?</script>', ' ', text, flags=re.DOTALL | re.IGNORECASE)

    # Удаляем все URL (они содержат числа которые не являются кодами)
    text = re.sub(r'https?://[^\s<>"\']+', ' ', text)

    # Удаляем HTML-атрибуты с их значениями (style="...", href="...", etc)
    text = re.sub(r'\s+\w+\s*=\s*["\'][^"\']*["\']', ' ', text)
    text = re.sub(r'\s+\w+\s*=\s*[^\s>]+', ' ', text)

    # Удаляем HTML теги, оставляем содержимое
    text = re.sub(r'<[^>]+>', ' ', text)

    # Удаляем HTML entities
    text = re.sub(r'&[a-zA-Z]+;', ' ', text)
    text = re.sub(r'&#\d+;', ' ', text)

    # Нормализуем пробелы
    text = re.sub(r'\s+', ' ', text)

    return text


def parse_email_content(data: str) -> ParsedEmailContent:
    """
    Извлечь код подтверждения и/или ссылку из содержимого письма.

    Ищем:
    - Код подтверждения: 4-6 цифр подряд в тексте письма
    - Ссылку подтверждения: URL содержащий confirm/verify/activate/access/token/code
    """
    result = ParsedEmailContent(raw=data)

    if not data:
        return result

    # Ищем ссылку подтверждения в оригинальном HTML
    link_patterns = [
        # Ссылки с ключевыми словами в пути
        r'(https?://[^\s<>"\']+(?:confirm|verify|activate|access|registration|token|code|click)[^\s<>"\']*)',
        # Любые ссылки с параметрами (часто это ссылки подтверждения)
        r'(https?://[^\s<>"\']+\?[^\s<>"\']+)',
    ]

    for pattern in link_patterns:
        match = re.search(pattern, data, re.IGNORECASE)
        if match:
            link = match.group(1)
            # Очищаем от возможных артефактов
            link = link.rstrip('.,;:!?')
            result.link = link
            break

    # Ищем код в очищенном от HTML тексте
    clean_text = _strip_html_for_code_search(data)

    # Паттерны для кодов (4-6 цифр)
    # Исключаем: CSS-цвета (#333), числа в датах (05.01.2026), времени (21:45)
    code_patterns = [
        r'(?<![#\d:/.])(\d{6})(?![:\d])',  # 6 цифр
        r'(?<![#\d:/.])(\d{5})(?![:\d])',  # 5 цифр
        r'(?<![#\d:/.])(\d{4})(?![:\d])',  # 4 цифры
    ]

    for pattern in code_patterns:
        match = re.search(pattern, clean_text)
        if match:
            result.code = match.group(1)
            break

    return result


class QuixEmailAPI:
    """Клиент API quix.email"""

    def __init__(self, api_key: str = None):
        self.api_key = api_key or settings.QUIX_EMAIL_API_KEY
        self.base_url = QUIX_API_BASE_URL

    def _get_url(self, method: str) -> str:
        """Сформировать URL запроса"""
        return f"{self.base_url}/{self.api_key}/{method}"

    async def _request(self, method: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Выполнить запрос к API.

        Returns:
            dict с полями success, result/error
        """
        # Проверяем что API ключ настроен
        if not self.api_key:
            logger.error("Quix API key not configured! Set QUIX_EMAIL_API_KEY in .env")
            return {"success": False, "error": "API key not configured"}

        url = self._get_url(method)

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, timeout=30) as response:
                    # Проверяем content-type
                    content_type = response.headers.get("Content-Type", "")
                    if "application/json" not in content_type:
                        text = await response.text()
                        logger.error(f"Quix API returned non-JSON [{method}]: {content_type}, body: {text[:200]}")
                        return {"success": False, "error": f"Invalid response format: {content_type}"}

                    data = await response.json()

                    if not data.get("success"):
                        error = data.get("error", "Unknown error")
                        logger.error(f"Quix API error [{method}]: {error}")
                        return {"success": False, "error": error}

                    return data

        except aiohttp.ContentTypeError as e:
            logger.error(f"Quix API content type error [{method}]: {e}")
            return {"success": False, "error": "API returned invalid format (check API key)"}
        except aiohttp.ClientError as e:
            logger.error(f"Quix API network error [{method}]: {e}")
            return {"success": False, "error": f"Network error: {e}"}
        except Exception as e:
            logger.error(f"Quix API unexpected error [{method}]: {e}")
            return {"success": False, "error": f"Unexpected error: {e}"}

    async def get_balance(self) -> Optional[float]:
        """
        Получить баланс аккаунта.

        Returns:
            Баланс в USD или None при ошибке
        """
        data = await self._request("accountBalance")
        if data.get("success"):
            return data.get("result", {}).get("balance")
        return None

    async def get_domains(self, site: str = None, include_info: bool = True) -> List[Dict[str, Any]]:
        """
        Получить список доступных доменов почт.

        Args:
            site: Фильтр по сайту (опционально)
            include_info: Включить информацию о количестве и цене

        Returns:
            Список доменов: [{domain, quantity, price}, ...]
        """
        params = {}
        if include_info:
            params["info"] = "1"
        if site:
            params["site"] = normalize_site(site)

        data = await self._request("emailDomains", params)

        if data.get("success"):
            domains = data.get("result", [])
            # Сортируем по алфавиту
            return sorted(domains, key=lambda x: x.get("domain", ""))

        return []

    async def order_email(self, site: str, domain: str) -> Optional[QuixEmailResult]:
        """
        Заказать временную почту.

        Args:
            site: Домен сайта (например, mamba.ru)
            domain: Домен почты (например, gmail.com)

        Returns:
            QuixEmailResult с id, email, site или None при ошибке
        """
        params = {
            "site": normalize_site(site),
            "domain": domain,
        }

        data = await self._request("emailGet", params)

        if data.get("success"):
            result = data.get("result", {})
            return QuixEmailResult(
                id=result.get("id", ""),
                email=result.get("email", ""),
                site=result.get("site", ""),
            )

        return None

    async def check_status(self, activation_id: str, regex: str = None) -> Optional[QuixEmailStatus]:
        """
        Проверить статус получения письма.

        Args:
            activation_id: ID активации
            regex: Регулярное выражение для поиска кода (опционально)

        Returns:
            QuixEmailStatus или None при ошибке
        """
        params = {"id": activation_id}
        if regex:
            params["regex"] = regex

        data = await self._request("emailStatus", params)

        if data.get("success"):
            result = data.get("result", {})
            return QuixEmailStatus(
                id=result.get("id", activation_id),
                email=result.get("email", ""),
                status=result.get("status", "waiting"),
                data=result.get("data"),
                parsed=result.get("parsed"),
            )

        return None

    async def cancel_email(self, activation_id: str) -> bool:
        """
        Отменить заказ почты.

        Args:
            activation_id: ID активации

        Returns:
            True если успешно отменено
        """
        params = {"id": activation_id}
        data = await self._request("emailCancel", params)

        if data.get("success"):
            return data.get("result", {}).get("cancelled", False)

        return False

    async def repeat_email(self, activation_id: str = None, email: str = None, site: str = None) -> Optional[QuixEmailResult]:
        """
        Повторный запрос письма на ту же почту.

        Можно использовать один из вариантов:
        - activation_id: ID предыдущей активации
        - email + site: Адрес почты и домен сайта

        Returns:
            QuixEmailResult с новым id или None при ошибке
        """
        params = {}
        if activation_id:
            params["id"] = activation_id
        elif email and site:
            params["email"] = email
            params["site"] = normalize_site(site)
        else:
            logger.error("repeat_email: need activation_id or (email + site)")
            return None

        data = await self._request("emailRepeat", params)

        if data.get("success"):
            result = data.get("result", {})
            return QuixEmailResult(
                id=result.get("id", ""),
                email=result.get("email", ""),
                site=result.get("site", ""),
            )

        return None

    async def get_code(self, activation_id: str, regex: str = None) -> Optional[str]:
        """
        Получить код из письма.

        Args:
            activation_id: ID активации
            regex: Регулярное выражение для поиска (опционально)

        Returns:
            Код или None
        """
        params = {"id": activation_id}
        if regex:
            params["regex"] = regex

        data = await self._request("emailCode", params)

        if data.get("success"):
            return data.get("result", {}).get("code")

        return None


# Глобальный инстанс API клиента
quix_email_api = QuixEmailAPI()
