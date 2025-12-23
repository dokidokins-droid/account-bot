# Анализ парсинга прокси и рекомендации по расширению

## Текущая реализация

### Анализ кодовой базы

#### 1. bot/models/proxy.py
**Текущее состояние:**
- Модель `Proxy` хранит прокси в виде строки без детального парсинга
- Формат хранения: `ip:port` или `ip:port:user:pass`
- Парсинг происходит через простое разделение по `:`
- Методы `extract_ip()`, `port`, `auth` используют базовый split

**Проблемы:**
- Не поддерживает префиксы протоколов (`http://`, `socks5://`)
- Не поддерживает формат `login:password@ip:port`
- Не поддерживает формат `ip:port@login:password`
- Жестко привязан к порядку `ip:port:user:pass`

#### 2. bot/services/proxy_service.py
**Текущее состояние:**
- `extract_ip()` (строка 214-217): простой split по `:`
- Нет валидации формата прокси
- Нет нормализации входных данных
- Прокси сохраняется в таблице "как есть"

**Проблемы:**
- Отсутствие унифицированного парсера
- Нет обработки различных форматов

#### 3. bot/handlers/proxy.py
**Текущее состояние:**
- Прием прокси происходит через текст (строка 116-149)
- Простое разделение по `\n`
- Нет валидации формата
- Нет нормализации

**Проблемы:**
- Любая строка принимается как прокси
- Нет обратной связи пользователю о некорректных форматах

---

## Требуемые форматы

### 1. Стандартные форматы с префиксом
```
http://login:password@ip:port
socks5://login:password@ip:port
http://ip:port
socks5://ip:port
```

### 2. Форматы без префикса
```
ip:port:login:password        # текущий формат
ip:port@login:password        # новый формат
login:password@ip:port        # популярный формат
ip:port                       # без авторизации
```

### 3. Примеры реальных прокси
```
http://user123:pass456@192.168.1.1:8080
socks5://admin:secret@10.0.0.1:1080
192.168.1.1:8080:user:pass
192.168.1.1:8080@user:pass
user:pass@192.168.1.1:8080
192.168.1.1:8080
```

---

## Рекомендуемая архитектура

### 1. Создание модуля парсера прокси

**Файл:** `bot/utils/proxy_parser.py`

```python
"""
Universal proxy parser supporting multiple formats.

Supported formats:
1. http://login:password@ip:port
2. socks5://login:password@ip:port
3. ip:port:login:password
4. ip:port@login:password
5. login:password@ip:port
6. ip:port (no auth)
"""

import re
from typing import Optional, Tuple
from dataclasses import dataclass
from enum import Enum


class ProxyProtocol(str, Enum):
    """Proxy protocol types"""
    HTTP = "http"
    SOCKS5 = "socks5"
    UNKNOWN = "unknown"


@dataclass
class ParsedProxy:
    """
    Structured representation of parsed proxy.

    Attributes:
        ip: IP address
        port: Port number
        username: Optional username for authentication
        password: Optional password for authentication
        protocol: Proxy protocol (http/socks5)
        original: Original proxy string
    """
    ip: str
    port: int
    username: Optional[str] = None
    password: Optional[str] = None
    protocol: ProxyProtocol = ProxyProtocol.HTTP
    original: str = ""

    @property
    def has_auth(self) -> bool:
        """Check if proxy has authentication"""
        return bool(self.username and self.password)

    @property
    def host_port(self) -> str:
        """Get IP:PORT string"""
        return f"{self.ip}:{self.port}"

    @property
    def auth_string(self) -> str:
        """Get username:password string or empty"""
        if self.has_auth:
            return f"{self.username}:{self.password}"
        return ""

    def to_standard_format(self) -> str:
        """
        Convert to standard format: ip:port:user:pass
        This is the format stored in Google Sheets.
        """
        if self.has_auth:
            return f"{self.ip}:{self.port}:{self.username}:{self.password}"
        return f"{self.ip}:{self.port}"

    def to_url_format(self, protocol: Optional[ProxyProtocol] = None) -> str:
        """
        Convert to URL format: protocol://[user:pass@]ip:port

        Args:
            protocol: Override protocol (default: use detected protocol)
        """
        proto = protocol or self.protocol

        if self.has_auth:
            return f"{proto.value}://{self.username}:{self.password}@{self.ip}:{self.port}"
        return f"{proto.value}://{self.ip}:{self.port}"

    def to_at_format(self) -> str:
        """Convert to @ format: ip:port@user:pass or user:pass@ip:port"""
        if self.has_auth:
            return f"{self.ip}:{self.port}@{self.username}:{self.password}"
        return f"{self.ip}:{self.port}"


class ProxyParser:
    """Universal proxy parser supporting multiple formats"""

    # Regex patterns for different formats
    # Format 1: protocol://[user:pass@]ip:port
    PATTERN_URL = re.compile(
        r'^(?P<protocol>https?|socks5?)://'
        r'(?:(?P<username>[^:]+):(?P<password>[^@]+)@)?'
        r'(?P<ip>\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'
        r':(?P<port>\d{1,5})$'
    )

    # Format 2: user:pass@ip:port
    PATTERN_USER_AT_HOST = re.compile(
        r'^(?P<username>[^:]+):(?P<password>[^@]+)@'
        r'(?P<ip>\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'
        r':(?P<port>\d{1,5})$'
    )

    # Format 3: ip:port@user:pass
    PATTERN_HOST_AT_USER = re.compile(
        r'^(?P<ip>\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'
        r':(?P<port>\d{1,5})@'
        r'(?P<username>[^:]+):(?P<password>.+)$'
    )

    # Format 4: ip:port:user:pass (current format)
    PATTERN_COLON_AUTH = re.compile(
        r'^(?P<ip>\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'
        r':(?P<port>\d{1,5})'
        r':(?P<username>[^:]+)'
        r':(?P<password>.+)$'
    )

    # Format 5: ip:port (no auth)
    PATTERN_NO_AUTH = re.compile(
        r'^(?P<ip>\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'
        r':(?P<port>\d{1,5})$'
    )

    @classmethod
    def parse(cls, proxy_string: str) -> Optional[ParsedProxy]:
        """
        Parse proxy string in any supported format.

        Args:
            proxy_string: Proxy string to parse

        Returns:
            ParsedProxy object or None if parsing failed

        Examples:
            >>> parser = ProxyParser()
            >>> proxy = parser.parse("http://user:pass@192.168.1.1:8080")
            >>> proxy.ip
            '192.168.1.1'
            >>> proxy.username
            'user'
        """
        if not proxy_string:
            return None

        proxy_string = proxy_string.strip()

        # Try URL format first (most specific)
        match = cls.PATTERN_URL.match(proxy_string)
        if match:
            return cls._create_from_match(match, proxy_string)

        # Try user:pass@ip:port
        match = cls.PATTERN_USER_AT_HOST.match(proxy_string)
        if match:
            return cls._create_from_match(match, proxy_string)

        # Try ip:port@user:pass
        match = cls.PATTERN_HOST_AT_USER.match(proxy_string)
        if match:
            return cls._create_from_match(match, proxy_string)

        # Try ip:port:user:pass (current format)
        match = cls.PATTERN_COLON_AUTH.match(proxy_string)
        if match:
            return cls._create_from_match(match, proxy_string)

        # Try ip:port (no auth)
        match = cls.PATTERN_NO_AUTH.match(proxy_string)
        if match:
            return cls._create_from_match(match, proxy_string)

        return None

    @classmethod
    def _create_from_match(cls, match: re.Match, original: str) -> ParsedProxy:
        """Create ParsedProxy from regex match"""
        data = match.groupdict()

        # Validate port
        port = int(data['port'])
        if not (1 <= port <= 65535):
            return None

        # Validate IP (basic check)
        ip_parts = data['ip'].split('.')
        if any(int(part) > 255 for part in ip_parts):
            return None

        # Detect protocol
        protocol = ProxyProtocol.HTTP
        if 'protocol' in data and data['protocol']:
            proto_str = data['protocol'].lower()
            if 'socks' in proto_str:
                protocol = ProxyProtocol.SOCKS5

        return ParsedProxy(
            ip=data['ip'],
            port=port,
            username=data.get('username'),
            password=data.get('password'),
            protocol=protocol,
            original=original
        )

    @classmethod
    def parse_list(cls, proxy_strings: list[str]) -> Tuple[list[ParsedProxy], list[str]]:
        """
        Parse list of proxy strings.

        Args:
            proxy_strings: List of proxy strings

        Returns:
            Tuple of (successfully_parsed, failed_strings)
        """
        parsed = []
        failed = []

        for proxy_str in proxy_strings:
            proxy_str = proxy_str.strip()
            if not proxy_str:
                continue

            result = cls.parse(proxy_str)
            if result:
                parsed.append(result)
            else:
                failed.append(proxy_str)

        return parsed, failed

    @classmethod
    def normalize(cls, proxy_string: str, output_format: str = 'standard') -> Optional[str]:
        """
        Normalize proxy string to specified format.

        Args:
            proxy_string: Input proxy string
            output_format: Output format ('standard', 'url', 'at')

        Returns:
            Normalized proxy string or None if parsing failed
        """
        parsed = cls.parse(proxy_string)
        if not parsed:
            return None

        if output_format == 'standard':
            return parsed.to_standard_format()
        elif output_format == 'url':
            return parsed.to_url_format()
        elif output_format == 'at':
            return parsed.to_at_format()

        return None


# Convenience functions
def parse_proxy(proxy_string: str) -> Optional[ParsedProxy]:
    """Convenience function to parse single proxy"""
    return ProxyParser.parse(proxy_string)


def parse_proxies(proxy_strings: list[str]) -> Tuple[list[ParsedProxy], list[str]]:
    """Convenience function to parse multiple proxies"""
    return ProxyParser.parse_list(proxy_strings)


def normalize_proxy(proxy_string: str, output_format: str = 'standard') -> Optional[str]:
    """Convenience function to normalize proxy format"""
    return ProxyParser.normalize(proxy_string, output_format)
```

---

### 2. Интеграция с моделью Proxy

**Изменения в bot/models/proxy.py:**

```python
from dataclasses import dataclass, field
from datetime import datetime, date
from typing import List, Optional
from bot.utils.proxy_parser import parse_proxy, ParsedProxy


@dataclass
class Proxy:
    """Модель прокси"""
    proxy: str  # Стандартный формат: ip:port или ip:port:user:pass
    country: str
    added_date: date
    expires_date: date
    used_for: List[str] = field(default_factory=list)
    row_index: Optional[int] = None
    proxy_type: str = "http"

    # Кешируем распарсенный прокси
    _parsed: Optional[ParsedProxy] = field(default=None, init=False, repr=False)

    @property
    def parsed(self) -> Optional[ParsedProxy]:
        """Get parsed proxy object (cached)"""
        if self._parsed is None:
            self._parsed = parse_proxy(self.proxy)
        return self._parsed

    @property
    def ip(self) -> str:
        """Получить IP из прокси строки"""
        if self.parsed:
            return self.parsed.ip
        # Fallback to old method
        return self.proxy.split(":")[0]

    @property
    def ip_short(self) -> str:
        """Получить сокращённый IP (первые два октета)"""
        parts = self.ip.split(".")
        if len(parts) >= 2:
            return f"{parts[0]}.{parts[1]}.."
        return self.ip

    @property
    def port(self) -> Optional[int]:
        """Получить порт из прокси строки"""
        if self.parsed:
            return self.parsed.port
        # Fallback to old method
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
        if self.parsed:
            return self.parsed.auth_string
        # Fallback to old method
        parts = self.proxy.split(":")
        if len(parts) >= 4:
            return f"{parts[2]}:{parts[3]}"
        return ""

    @property
    def has_auth(self) -> bool:
        """Check if proxy has authentication"""
        if self.parsed:
            return self.parsed.has_auth
        return bool(self.auth)

    def get_http_proxy(self) -> str:
        """Получить HTTP вариант прокси с полным URL"""
        if self.parsed:
            # Если тип прокси SOCKS5, меняем порт на HTTP (порт - 1)
            if self.proxy_type == "socks5":
                # Создаем копию с измененным портом
                http_port = self.parsed.port - 1
                if self.parsed.has_auth:
                    return f"http://{self.parsed.username}:{self.parsed.password}@{self.parsed.ip}:{http_port}"
                return f"http://{self.parsed.ip}:{http_port}"
            # Иначе используем стандартный URL формат
            from bot.utils.proxy_parser import ProxyProtocol
            return self.parsed.to_url_format(ProxyProtocol.HTTP)

        # Fallback to old method
        port = self.port
        if port is None:
            return f"http://{self.proxy}"

        if self.proxy_type == "socks5":
            http_port = port - 1
        else:
            http_port = port

        auth = self.auth
        if auth:
            return f"http://{auth}@{self.ip}:{http_port}"
        return f"http://{self.ip}:{http_port}"

    def get_socks5_proxy(self) -> str:
        """Получить SOCKS5 вариант прокси с полным URL"""
        if self.parsed:
            # Если тип прокси HTTP, меняем порт на SOCKS5 (порт + 1)
            if self.proxy_type == "http":
                socks5_port = self.parsed.port + 1
                if self.parsed.has_auth:
                    return f"socks5://{self.parsed.username}:{self.parsed.password}@{self.parsed.ip}:{socks5_port}"
                return f"socks5://{self.parsed.ip}:{socks5_port}"
            # Иначе используем стандартный URL формат
            from bot.utils.proxy_parser import ProxyProtocol
            return self.parsed.to_url_format(ProxyProtocol.SOCKS5)

        # Fallback to old method
        port = self.port
        if port is None:
            return f"socks5://{self.proxy}"

        if self.proxy_type == "http":
            socks5_port = port + 1
        else:
            socks5_port = port

        auth = self.auth
        if auth:
            return f"socks5://{auth}@{self.ip}:{socks5_port}"
        return f"socks5://{self.ip}:{socks5_port}"

    # Остальные методы остаются без изменений
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
```

---

### 3. Интеграция с сервисом

**Изменения в bot/services/proxy_service.py:**

```python
from bot.utils.proxy_parser import parse_proxies, normalize_proxy


class ProxyService:
    # ... existing code ...

    def extract_ip(self, proxy: str) -> str:
        """Extract IP from proxy string (with new parser)"""
        from bot.utils.proxy_parser import parse_proxy
        parsed = parse_proxy(proxy)
        if parsed:
            return parsed.ip
        # Fallback to old method
        parts = proxy.split(":")
        return parts[0] if parts else proxy

    async def add_proxies(
        self,
        proxies: List[str],
        resources: List[str],
        duration_days: int,
        proxy_type: str = "http",
    ) -> List[Dict]:
        """
        Add list of proxies to the table.

        NOW WITH UNIVERSAL PARSING!
        """
        ws = await self._get_worksheet()
        results = []
        today = date.today()
        expires = today + timedelta(days=duration_days)

        # Format resources as comma-separated string
        used_for_str = ",".join([r.lower() for r in resources])

        # Parse and normalize proxies
        parsed_proxies, failed_proxies = parse_proxies(proxies)

        if failed_proxies:
            logger.warning(f"Failed to parse {len(failed_proxies)} proxies: {failed_proxies}")

        if not parsed_proxies:
            return []

        # Detect countries in parallel for all IPs
        async def get_country(parsed_proxy) -> tuple:
            country = await self.get_country_by_ip(parsed_proxy.ip)
            return parsed_proxy, country

        # Limit parallelism to avoid bans
        semaphore = asyncio.Semaphore(5)

        async def limited_get_country(parsed_proxy) -> tuple:
            async with semaphore:
                return await get_country(parsed_proxy)

        # Get all countries in parallel
        country_tasks = [limited_get_country(p) for p in parsed_proxies]
        country_results = await asyncio.gather(*country_tasks)

        # Format all rows for batch add
        rows_to_add = []
        for parsed_proxy, country in country_results:
            # Normalize to standard format for storage
            normalized = parsed_proxy.to_standard_format()

            row_data = [
                normalized,  # Store in standard format
                country,
                today.strftime("%d.%m.%y"),
                expires.strftime("%d.%m.%y"),
                used_for_str,
                proxy_type,
            ]
            rows_to_add.append(row_data)

            results.append({
                "proxy": normalized,
                "country": country,
                "country_flag": get_country_flag(country),
                "expires": expires.strftime("%d.%m.%y"),
            })

        # Batch add all rows in one API request
        if rows_to_add:
            # ... existing batch update code ...
            async with sheets_rate_limiter:
                all_values = await ws.get_all_values()

            last_filled_row = 1
            for i, row in enumerate(all_values, start=1):
                if row and any(cell.strip() for cell in row if cell):
                    last_filled_row = i

            start_row = last_filled_row + 1
            end_row = start_row + len(rows_to_add) - 1
            range_str = f"A{start_row}:F{end_row}"

            async with sheets_rate_limiter:
                await ws.update(range_str, rows_to_add, value_input_option="USER_ENTERED")

            logger.info(f"Batch added {len(rows_to_add)} proxies to range {range_str}")

            # Invalidate cache after adding
            async with self._cache_lock:
                self._cache.invalidate()

        return results
```

---

### 4. Интеграция с обработчиком

**Изменения в bot/handlers/proxy.py:**

```python
from bot.utils.proxy_parser import parse_proxies


@router.message(ProxyStates.add_waiting_proxy)
async def add_proxy_receive(message: Message, state: FSMContext):
    """Получение текста с прокси - с валидацией"""
    text = message.text.strip()

    if not text:
        await message.answer(
            "❌ Отправьте список прокси",
            reply_markup=get_proxy_back_keyboard("type"),
        )
        return

    # Парсим прокси (каждая строка = отдельный прокси)
    raw_proxies = [line.strip() for line in text.split("\n") if line.strip()]

    if not raw_proxies:
        await message.answer(
            "❌ Не удалось распознать прокси",
            reply_markup=get_proxy_back_keyboard("type"),
        )
        return

    # Parse and validate using universal parser
    parsed_proxies, failed_proxies = parse_proxies(raw_proxies)

    if not parsed_proxies:
        # All proxies failed to parse
        error_lines = ["❌ Не удалось распознать ни одного прокси\n"]
        error_lines.append("<b>Поддерживаемые форматы:</b>")
        error_lines.append("• <code>http://user:pass@ip:port</code>")
        error_lines.append("• <code>socks5://user:pass@ip:port</code>")
        error_lines.append("• <code>user:pass@ip:port</code>")
        error_lines.append("• <code>ip:port@user:pass</code>")
        error_lines.append("• <code>ip:port:user:pass</code>")
        error_lines.append("• <code>ip:port</code>")

        await message.answer(
            "\n".join(error_lines),
            reply_markup=get_proxy_back_keyboard("type"),
            parse_mode="HTML",
        )
        return

    # Convert to standard format for storage
    normalized_proxies = [p.to_standard_format() for p in parsed_proxies]

    # Show parsing results
    result_lines = [f"✅ Распознано прокси: <b>{len(parsed_proxies)}</b>"]

    if failed_proxies:
        result_lines.append(f"⚠️ Не распознано: <b>{len(failed_proxies)}</b>")
        result_lines.append("\n<b>Примеры ошибок:</b>")
        for failed in failed_proxies[:3]:  # Show first 3
            result_lines.append(f"• <code>{failed[:50]}</code>")

    result_lines.append("\nПродолжить с распознанными прокси?")

    # Сохраняем в state (нормализованные)
    await state.update_data(proxies=normalized_proxies, selected_resources=[])
    await state.set_state(ProxyStates.add_selecting_resources)

    await message.answer(
        "\n".join(result_lines),
        parse_mode="HTML",
    )

    await message.answer(
        f"📝 Получено прокси: <b>{len(normalized_proxies)}</b>\n\n"
        "Выберите ресурсы, для которых использовались:\n"
        "<i>(можно выбрать несколько)</i>",
        reply_markup=get_proxy_resource_multi_keyboard([]),
        parse_mode="HTML",
    )
```

---

## Преимущества предложенного решения

### 1. Универсальность
- Поддержка 6+ форматов прокси
- Автоматическое определение формата
- Нормализация к единому формату хранения

### 2. Надежность
- Валидация IP и портов
- Проверка корректности формата
- Обработка ошибок с понятной обратной связью

### 3. Расширяемость
- Легко добавить новые форматы (просто добавить regex)
- Отделение логики парсинга от бизнес-логики
- Кеширование распарсенных объектов

### 4. Обратная совместимость
- Fallback на старые методы
- Поддержка текущего формата хранения
- Постепенная миграция без breaking changes

### 5. Производительность
- Кеширование распарсенных объектов
- Эффективные regex паттерны
- Минимальные overhead

---

## План внедрения

### Этап 1: Создание парсера (1-2 часа)
1. Создать `bot/utils/proxy_parser.py`
2. Написать юнит-тесты для всех форматов
3. Проверить edge cases

### Этап 2: Интеграция с моделью (30 минут)
1. Обновить `bot/models/proxy.py`
2. Добавить кеширование ParsedProxy
3. Протестировать обратную совместимость

### Этап 3: Интеграция с сервисом (1 час)
1. Обновить `bot/services/proxy_service.py`
2. Добавить нормализацию при добавлении прокси
3. Обновить `extract_ip()` для использования парсера

### Этап 4: Интеграция с обработчиком (1 час)
1. Обновить `bot/handlers/proxy.py`
2. Добавить валидацию с обратной связью
3. Показывать пользователю какие прокси не распознались

### Этап 5: Тестирование (1-2 часа)
1. E2E тесты с разными форматами
2. Проверка в production-подобном окружении
3. Проверка миграции существующих прокси

**Общее время: 4-6 часов**

---

## Примеры использования

### Пример 1: Добавление прокси в разных форматах
```python
# Пользователь вставляет в бот:
"""
http://user1:pass1@192.168.1.1:8080
socks5://admin:secret@10.0.0.1:1080
user2:pass2@192.168.1.2:3128
192.168.1.3:8080@user3:pass3
192.168.1.4:8080:user4:pass4
192.168.1.5:8080
"""

# Результат:
# ✅ Распознано прокси: 6
# Все прокси нормализуются к формату:
# 192.168.1.1:8080:user1:pass1
# 10.0.0.1:1080:admin:secret
# 192.168.1.2:3128:user2:pass2
# 192.168.1.3:8080:user3:pass3
# 192.168.1.4:8080:user4:pass4
# 192.168.1.5:8080
```

### Пример 2: Получение прокси
```python
# При выдаче пользователю:
proxy = await service.try_take_proxy(row_index, resource, user_id)

# Автоматически генерируются оба формата:
http_proxy = proxy.get_http_proxy()
# http://user1:pass1@192.168.1.1:8080

socks5_proxy = proxy.get_socks5_proxy()
# socks5://user1:pass1@192.168.1.1:1081
```

### Пример 3: Программная обработка
```python
from bot.utils.proxy_parser import parse_proxy

# Парсинг любого формата
proxy = parse_proxy("http://user:pass@192.168.1.1:8080")

# Доступ к компонентам
print(proxy.ip)        # 192.168.1.1
print(proxy.port)      # 8080
print(proxy.username)  # user
print(proxy.password)  # pass

# Конвертация форматов
standard = proxy.to_standard_format()  # 192.168.1.1:8080:user:pass
url = proxy.to_url_format()            # http://user:pass@192.168.1.1:8080
```

---

## Тестовые случаи

### Позитивные тесты
```python
test_cases = [
    "http://user:pass@192.168.1.1:8080",
    "socks5://admin:secret@10.0.0.1:1080",
    "user:pass@192.168.1.1:8080",
    "192.168.1.1:8080@user:pass",
    "192.168.1.1:8080:user:pass",
    "192.168.1.1:8080",
    "http://192.168.1.1:8080",
    "socks5://192.168.1.1:1080",
]
```

### Негативные тесты
```python
invalid_cases = [
    "not-a-proxy",
    "192.168.1.1",  # no port
    "192.168.1.1:99999",  # invalid port
    "999.999.999.999:8080",  # invalid IP
    "http://192.168.1.1",  # no port in URL
    "",  # empty string
    "   ",  # whitespace only
]
```

---

## Метрики успеха

1. **Покрытие форматов**: Поддержка всех 6+ популярных форматов
2. **Скорость парсинга**: < 1ms на прокси
3. **Точность**: 100% корректность для валидных форматов
4. **Обратная связь**: Понятные сообщения об ошибках для пользователя
5. **Совместимость**: 0 breaking changes для существующих данных

---

## Заключение

Предложенная архитектура решает все текущие проблемы парсинга прокси:

1. ✅ Поддерживает все требуемые форматы
2. ✅ Валидирует входные данные
3. ✅ Предоставляет понятную обратную связь
4. ✅ Обратно совместима с текущей реализацией
5. ✅ Расширяема для новых форматов
6. ✅ Производительна и надежна

Рекомендуется внедрение в 5 этапов с общим временем реализации 4-6 часов.
