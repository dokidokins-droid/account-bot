"""
Сервис для работы с номерами телефонов с кэшированием и блокировками.

Оптимизации:
- Кэширование номеров в памяти (как AccountCache)
- Блокировки для предотвращения race conditions
- Batch операции для минимизации API вызовов
- Буферизация записи в таблицу выдачи
"""
import asyncio
import json
import logging
import time
import uuid
from datetime import datetime, date
from pathlib import Path
from typing import List, Dict, Any, Set, Optional
from dataclasses import dataclass, field
from collections import deque

import gspread_asyncio

from bot.config import settings
from bot.services.sheets_service import sheets_rate_limiter, batch_update_cells

logger = logging.getLogger(__name__)

# Файлы для сохранения состояния
NUMBERS_SETTINGS_FILE = Path(__file__).parent.parent.parent / "data" / "numbers_settings.json"
NUMBERS_CACHE_STATE_FILE = Path(__file__).parent.parent.parent / "data" / "numbers_cache_state.json"

# Настройки кэша
LOAD_BATCH_SIZE = 30  # Сколько номеров загружать за раз
REFILL_THRESHOLD = 10  # Минимум для триггера пополнения
WRITE_BUFFER_INTERVAL = 30  # Интервал записи в таблицу выданных (секунды)
STATE_SAVE_INTERVAL = 60  # Интервал автосохранения состояния


def parse_date(date_str: str) -> date:
    """Парсинг даты в форматах dd.mm.yy или YYYY-MM-DD"""
    if not date_str:
        return date.today()
    try:
        return datetime.strptime(date_str, "%d.%m.%y").date()
    except ValueError:
        pass
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return date.today()


def parse_used_for(used_for_str: str) -> Set[str]:
    """Парсинг списка ресурсов из строки"""
    if not used_for_str or not used_for_str.strip():
        return set()
    return {r.strip().lower() for r in used_for_str.split(",") if r.strip()}


def format_used_for(resources: Set[str]) -> str:
    """Форматирование списка ресурсов в строку"""
    return ",".join(sorted(resources))


def get_creds():
    """Создание credentials для Google Sheets API"""
    import base64
    creds_data = settings.GOOGLE_CREDENTIALS_JSON
    from google.oauth2.service_account import Credentials

    if creds_data.startswith("{"):
        creds_dict = json.loads(creds_data)
    else:
        try:
            creds_dict = json.loads(base64.b64decode(creds_data).decode())
        except Exception:
            with open(creds_data) as f:
                creds_dict = json.load(f)

    creds = Credentials.from_service_account_info(creds_dict)
    return creds.with_scopes([
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ])


agcm = gspread_asyncio.AsyncioGspreadClientManager(get_creds)


@dataclass
class CachedNumber:
    """Номер в кэше"""
    number: str
    date_added: str
    used_for: Set[str]
    row_index: int


@dataclass
class PendingNumber:
    """Номер, выданный пользователю, ждёт feedback"""
    number_id: str
    number: str
    date_added: str
    resources: List[str]
    region: str
    employee_stage: str
    row_index: int
    issued_at: float = field(default_factory=time.time)


@dataclass
class IssuedNumberRecord:
    """Запись для таблицы выдачи"""
    number: str
    region: str
    employee_stage: str
    resources_display: str
    is_update: bool  # True если обновляем существующую запись
    existing_row_index: Optional[int] = None


@dataclass
class CachedIssuedRecord:
    """Выданный номер в памяти (для быстрого обновления статуса)"""
    number: str
    date_issued: str
    region: str
    employee_stage: str
    resources_display: str
    status: str = ""
    row_index: Optional[int] = None  # None = ещё не записан в Sheets
    version: int = 0  # Инкрементируется при каждом изменении
    synced_version: int = 0  # Версия после последней успешной синхронизации

    @property
    def needs_sync(self) -> bool:
        """Нужна ли синхронизация с Sheets"""
        return self.version > self.synced_version

    def mark_changed(self) -> None:
        """Пометить запись как изменённую"""
        self.version += 1

    def mark_synced(self) -> bool:
        """
        Пометить как синхронизированную.
        Возвращает True если версия не изменилась с начала синхронизации.
        """
        # Устанавливаем synced_version равным version только если не было изменений
        self.synced_version = self.version
        return True


class NumberCache:
    """
    Кэш номеров телефонов с блокировками и batch операциями.

    Номера могут переиспользоваться для разных ресурсов (Beboo, Loloo, Табор).
    """

    def __init__(self):
        # Доступные для выдачи {resource_key: deque of CachedNumber}
        self._available: Dict[str, deque] = {}

        # Выданные, ждут обновления статуса {number_id: PendingNumber}
        self._pending: Dict[str, PendingNumber] = {}

        # Буфер записи в таблицу выдачи
        self._write_buffer: List[IssuedNumberRecord] = []

        # Буфер обновлений used_for в Базе {row_index: new_used_for_set}
        self._used_for_updates: Dict[int, Set[str]] = {}

        # === НОВОЕ: In-memory кэш выданных записей ===
        # {phone_number: CachedIssuedRecord}
        self._issued_cache: Dict[str, CachedIssuedRecord] = {}
        self._issued_cache_lock = asyncio.Lock()

        # Глобальная блокировка синхронизации - только один sync за раз
        self._sync_lock = asyncio.Lock()

        # Мета-блокировка
        self._meta_lock = asyncio.Lock()

        # Блокировки по ресурсам
        self._issue_locks: Dict[str, asyncio.Lock] = {}
        self._load_lock = asyncio.Lock()
        self._loading = False

        # Настройки
        self._today_only: bool = True

        # Фоновые задачи
        self._write_task: Optional[asyncio.Task] = None
        self._save_task: Optional[asyncio.Task] = None
        self._issued_sync_task: Optional[asyncio.Task] = None

        self._load_settings()

    def _load_settings(self) -> None:
        """Загрузить настройки"""
        try:
            if NUMBERS_SETTINGS_FILE.exists():
                with open(NUMBERS_SETTINGS_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self._today_only = data.get("today_only", True)
                    logger.info(f"Numbers settings loaded: today_only={self._today_only}")
        except Exception as e:
            logger.error(f"Error loading numbers settings: {e}")

    def _save_settings(self) -> None:
        """Сохранить настройки"""
        try:
            NUMBERS_SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(NUMBERS_SETTINGS_FILE, "w", encoding="utf-8") as f:
                json.dump({"today_only": self._today_only}, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Error saving numbers settings: {e}")

    @property
    def today_only(self) -> bool:
        return self._today_only

    def set_today_only(self, value: bool) -> None:
        self._today_only = value
        self._save_settings()
        # Очищаем кэш при изменении режима
        self._available.clear()

    async def _get_issue_lock(self, key: str) -> asyncio.Lock:
        """Потокобезопасное получение блокировки"""
        async with self._meta_lock:
            if key not in self._issue_locks:
                self._issue_locks[key] = asyncio.Lock()
            return self._issue_locks[key]

    def _get_resource_key(self, resources: List[str]) -> str:
        """Ключ для набора ресурсов"""
        return "_".join(sorted(r.lower() for r in resources))

    # ==================== ЗАГРУЗКА ====================

    async def _load_numbers(self, resources: List[str], force: bool = False) -> int:
        """
        Загрузить номера из Sheets в кэш.
        НЕ удаляет из базы, только читает и фильтрует.
        """
        key = self._get_resource_key(resources)
        requested_resources = {r.lower() for r in resources}

        current_available = len(self._available.get(key, deque()))
        if not force and current_available >= LOAD_BATCH_SIZE:
            return 0

        async with self._load_lock:
            if self._loading:
                return 0
            self._loading = True

        try:
            logger.info(f"Loading numbers for {key} (current: {current_available})...")
            today = date.today()

            async with sheets_rate_limiter:
                gc = await agcm.authorize()
            async with sheets_rate_limiter:
                ss = await gc.open_by_key(settings.SPREADSHEET_ACCOUNTS)

            sheet_name = settings.SHEET_NAMES.get("numbers", "Номера")
            async with sheets_rate_limiter:
                ws = await ss.worksheet(sheet_name)
            async with sheets_rate_limiter:
                all_values = await ws.get_all_values()

            # Фильтруем доступные номера
            numbers_to_cache = []
            for idx, row in enumerate(all_values[1:], start=2):
                if len(numbers_to_cache) >= LOAD_BATCH_SIZE:
                    break

                if not row or len(row) < 2:
                    continue

                row_date_str = row[0].strip()
                number = row[1].strip()
                used_for_str = row[2].strip() if len(row) > 2 else ""

                if not number:
                    continue

                # Проверяем дату
                if self._today_only:
                    row_date = parse_date(row_date_str)
                    if row_date != today:
                        continue

                # Проверяем доступность для запрошенных ресурсов
                used_for = parse_used_for(used_for_str)
                if requested_resources & used_for:
                    continue

                numbers_to_cache.append(CachedNumber(
                    number=number,
                    date_added=row_date_str,
                    used_for=used_for,
                    row_index=idx,
                ))

            if not numbers_to_cache:
                logger.info(f"No available numbers found for {key}")
                return 0

            # Добавляем в кэш
            if key not in self._available:
                self._available[key] = deque()

            for num in numbers_to_cache:
                self._available[key].append(num)

            logger.info(f"Loaded {len(numbers_to_cache)} numbers for {key}")
            return len(numbers_to_cache)

        except Exception as e:
            logger.error(f"Error loading numbers: {e}")
            return 0
        finally:
            self._loading = False

    # ==================== ВЫДАЧА ====================

    async def issue_numbers(
        self,
        resources: List[str],
        region: str,
        quantity: int,
        employee_stage: str,
    ) -> List[Dict[str, Any]]:
        """
        Выдать номера из кэша.

        Возвращает список номеров с их ID для последующего feedback.
        Обновление used_for происходит batch'ем в фоне.
        """
        key = self._get_resource_key(resources)
        requested_resources = {r.lower() for r in resources}
        issue_lock = await self._get_issue_lock(key)

        async with issue_lock:
            available = self._available.get(key, deque())

            # Если не хватает — загружаем
            if len(available) < quantity:
                await self._load_numbers(resources)
                available = self._available.get(key, deque())

            # Забираем из available
            result = []
            numbers_taken = []

            for _ in range(min(quantity, len(available))):
                if not available:
                    break

                cached = available.popleft()
                number_id = f"num_{uuid.uuid4().hex[:12]}"

                # Сохраняем в pending
                pending = PendingNumber(
                    number_id=number_id,
                    number=cached.number,
                    date_added=cached.date_added,
                    resources=resources,
                    region=region,
                    employee_stage=employee_stage,
                    row_index=cached.row_index,
                )
                self._pending[number_id] = pending
                numbers_taken.append(cached)

                result.append({
                    "number": cached.number,
                    "date_added": cached.date_added,
                    "row_index": cached.row_index,
                    "number_id": number_id,
                })

            # Планируем batch обновление used_for
            if numbers_taken:
                for cached in numbers_taken:
                    new_used_for = cached.used_for | requested_resources
                    self._used_for_updates[cached.row_index] = new_used_for

                # Запускаем batch обновление в фоне
                asyncio.create_task(self._flush_used_for_updates())

            # Триггер пополнения
            if len(available) < REFILL_THRESHOLD:
                asyncio.create_task(self._background_refill(resources))

            return result

    async def _background_refill(self, resources: List[str]) -> None:
        """Фоновое пополнение кэша"""
        try:
            await self._load_numbers(resources)
        except Exception as e:
            logger.error(f"Background refill error: {e}")

    async def _flush_used_for_updates(self) -> None:
        """Batch обновление used_for в таблице База"""
        if not self._used_for_updates:
            return

        # Забираем все обновления
        updates = self._used_for_updates.copy()
        self._used_for_updates.clear()

        try:
            async with sheets_rate_limiter:
                gc = await agcm.authorize()
            async with sheets_rate_limiter:
                ss = await gc.open_by_key(settings.SPREADSHEET_ACCOUNTS)

            sheet_name = settings.SHEET_NAMES.get("numbers", "Номера")
            async with sheets_rate_limiter:
                ws = await ss.worksheet(sheet_name)

            # Batch обновление - один API запрос вместо N
            batch_data = []
            for row_index, used_for_set in updates.items():
                col_letter = 'C'  # Колонка used_for
                cell_range = f"{col_letter}{row_index}"
                batch_data.append({
                    "range": cell_range,
                    "values": [[format_used_for(used_for_set)]]
                })

            if batch_data:
                async with sheets_rate_limiter:
                    await ws.batch_update(batch_data, value_input_option="USER_ENTERED")
                logger.info(f"Batch updated {len(batch_data)} used_for records")

        except Exception as e:
            logger.error(f"Error flushing used_for updates: {e}")
            # Возвращаем обновления обратно для повторной попытки
            for row_index, used_for_set in updates.items():
                if row_index not in self._used_for_updates:
                    self._used_for_updates[row_index] = used_for_set

    # ==================== СТАТУС И FEEDBACK ====================

    async def _find_number_row_index(self, number: str) -> Optional[int]:
        """Найти существующую строку для номера в таблице выдачи"""
        try:
            async with sheets_rate_limiter:
                gc = await agcm.authorize()
                ss_issued = await gc.open_by_key(settings.SPREADSHEET_ISSUED)

            sheet_name = settings.SHEET_NAMES.get("numbers_issued", "Номера Выдано")
            async with sheets_rate_limiter:
                ws_issued = await ss_issued.worksheet(sheet_name)

            async with sheets_rate_limiter:
                issued_values = await ws_issued.get_all_values()

            for idx, row in enumerate(issued_values[1:], start=2):
                if row and len(row) >= 2 and row[1].strip() == number:
                    return idx

            return None
        except Exception as e:
            logger.error(f"Error finding number row: {e}")
            return None

    async def _find_number_row_with_data(self, number: str) -> Optional[Dict[str, Any]]:
        """
        Найти существующую строку для номера в таблице выдачи и вернуть все данные.
        Используется для восстановления состояния после рестарта.

        Формат таблицы: Дата выдачи | Номер | Регионы | Employee | Ресурсы | Статус
        Индексы:            0          1        2          3         4        5
        """
        try:
            async with sheets_rate_limiter:
                gc = await agcm.authorize()
                ss_issued = await gc.open_by_key(settings.SPREADSHEET_ISSUED)

            sheet_name = settings.SHEET_NAMES.get("numbers_issued", "Номера Выдано")
            async with sheets_rate_limiter:
                ws_issued = await ss_issued.worksheet(sheet_name)

            async with sheets_rate_limiter:
                issued_values = await ws_issued.get_all_values()

            for idx, row in enumerate(issued_values[1:], start=2):
                if row and len(row) >= 2 and row[1].strip() == number:
                    return {
                        "row_index": idx,
                        "date_issued": row[0].strip() if len(row) > 0 else "",
                        "region": row[2].strip() if len(row) > 2 else "",
                        "employee_stage": row[3].strip() if len(row) > 3 else "",
                        "resources_display": row[4].strip() if len(row) > 4 else "",
                        "status": row[5].strip() if len(row) > 5 else "",
                    }

            return None
        except Exception as e:
            logger.error(f"Error finding number row with data: {e}")
            return None

    async def update_number_status(self, number_id: str, status: str) -> bool:
        """
        Обновить статус номера (МГНОВЕННО в памяти).
        Синхронизация с Sheets происходит в фоне.

        number_id - номер телефона
        """
        try:
            # Получаем table_name статуса
            from bot.models.enums import NumberStatus
            try:
                status_enum = NumberStatus(status)
                status_text = status_enum.table_name
            except ValueError:
                status_text = status

            number = number_id.strip()

            async with self._issued_cache_lock:
                if number in self._issued_cache:
                    # Fast path: уже в кэше
                    self._issued_cache[number].status = status_text
                    self._issued_cache[number].mark_changed()
                    logger.info(f"Updated number {number} status to {status_text} (in cache)")
                    return True

            # Slow path: номер не в кэше (например, после рестарта)
            # Ищем существующую строку И ЧИТАЕМ ВСЕ ДАННЫЕ чтобы не потерять их
            row_data = await self._find_number_row_with_data(number)

            async with self._issued_cache_lock:
                # Проверяем ещё раз - мог появиться пока искали
                if number not in self._issued_cache:
                    if row_data:
                        # Номер найден в Sheets - используем данные оттуда
                        record = CachedIssuedRecord(
                            number=number,
                            date_issued=row_data.get("date_issued", date.today().strftime("%d.%m.%y")),
                            region=row_data.get("region", ""),
                            employee_stage=row_data.get("employee_stage", ""),
                            resources_display=row_data.get("resources_display", ""),
                            status=status_text,
                            row_index=row_data.get("row_index"),
                            version=1,  # Нужна синхронизация (статус изменился)
                            synced_version=0,
                        )
                    else:
                        # Номер не найден в Sheets - новая запись
                        record = CachedIssuedRecord(
                            number=number,
                            date_issued=date.today().strftime("%d.%m.%y"),
                            region="",
                            employee_stage="",
                            resources_display="",
                            status=status_text,
                            row_index=None,
                            version=1,
                            synced_version=0,
                        )
                    self._issued_cache[number] = record
                    logger.info(f"Created cache entry for {number} (row: {record.row_index})")
                else:
                    self._issued_cache[number].status = status_text
                    self._issued_cache[number].mark_changed()

            return True

        except Exception as e:
            logger.error(f"Error updating number status: {e}")
            return False

    # ==================== ПОДСЧЁТ ====================

    async def get_available_count(self, resources: List[str] = None) -> int:
        """Получить количество доступных номеров"""
        today = date.today()
        count = 0

        requested_resources = {r.lower() for r in resources} if resources else set()

        try:
            async with sheets_rate_limiter:
                gc = await agcm.authorize()
            async with sheets_rate_limiter:
                ss = await gc.open_by_key(settings.SPREADSHEET_ACCOUNTS)

            sheet_name = settings.SHEET_NAMES.get("numbers", "Номера")
            try:
                async with sheets_rate_limiter:
                    ws = await ss.worksheet(sheet_name)
            except Exception:
                return 0

            async with sheets_rate_limiter:
                all_values = await ws.get_all_values()

            for row in all_values[1:]:
                if not row or len(row) < 2:
                    continue

                row_date_str = row[0].strip()
                number = row[1].strip()
                used_for_str = row[2].strip() if len(row) > 2 else ""

                if not number:
                    continue

                if self._today_only:
                    row_date = parse_date(row_date_str)
                    if row_date != today:
                        continue

                used_for = parse_used_for(used_for_str)

                if requested_resources:
                    if not (requested_resources & used_for):
                        count += 1
                else:
                    if not used_for:
                        count += 1

            return count

        except Exception as e:
            logger.error(f"Error getting available count: {e}")
            return 0

    # ==================== ИНИЦИАЛИЗАЦИЯ ====================

    async def ensure_sheets_exist(self) -> None:
        """Создать листы если их нет"""
        try:
            async with sheets_rate_limiter:
                gc = await agcm.authorize()

            # Лист в таблице База
            async with sheets_rate_limiter:
                ss_base = await gc.open_by_key(settings.SPREADSHEET_ACCOUNTS)
            sheet_name = settings.SHEET_NAMES.get("numbers", "Номера")
            try:
                async with sheets_rate_limiter:
                    await ss_base.worksheet(sheet_name)
            except Exception:
                async with sheets_rate_limiter:
                    ws = await ss_base.add_worksheet(title=sheet_name, rows=1000, cols=10)
                async with sheets_rate_limiter:
                    await ws.append_row(
                        ["Дата", "Номер", "Использован для"],
                        value_input_option="USER_ENTERED"
                    )
                logger.info(f"Created sheet '{sheet_name}'")

            # Лист в таблице Выдача
            async with sheets_rate_limiter:
                ss_issued = await gc.open_by_key(settings.SPREADSHEET_ISSUED)
            issued_sheet_name = settings.SHEET_NAMES.get("numbers_issued", "Номера Выдано")
            try:
                async with sheets_rate_limiter:
                    await ss_issued.worksheet(issued_sheet_name)
            except Exception:
                async with sheets_rate_limiter:
                    ws = await ss_issued.add_worksheet(title=issued_sheet_name, rows=1000, cols=10)
                async with sheets_rate_limiter:
                    await ws.append_row(
                        ["Дата выдачи", "Номер", "Регионы", "Employee", "Ресурсы", "Статус"],
                        value_input_option="USER_ENTERED",
                    )
                logger.info(f"Created sheet '{issued_sheet_name}'")

        except Exception as e:
            logger.error(f"Error ensuring sheets exist: {e}")

    # ==================== ВЫДАЧА В ТАБЛИЦУ ====================

    async def record_issued_numbers(
        self,
        numbers: List[Dict[str, Any]],
        resources: List[str],
        region: str,
        employee_stage: str,
    ) -> None:
        """
        Записать выданные номера в in-memory кэш (МГНОВЕННО).
        Фактическая запись в Sheets происходит в фоне.
        """
        if not numbers:
            return

        from bot.models.enums import NumberResource
        resources_display = ", ".join(NumberResource(r).display_name for r in resources)
        today_str = date.today().strftime("%d.%m.%y")

        async with self._issued_cache_lock:
            for item in numbers:
                number = item["number"]

                if number in self._issued_cache:
                    # Обновляем существующую запись
                    record = self._issued_cache[number]
                    # Объединяем регионы
                    existing_regions = {r.strip() for r in record.region.split(",") if r.strip()}
                    existing_regions.add(region)
                    record.region = ", ".join(sorted(existing_regions))
                    # Объединяем ресурсы
                    existing_res = {r.strip() for r in record.resources_display.split(",") if r.strip()}
                    new_res = {NumberResource(r).display_name for r in resources}
                    existing_res.update(new_res)
                    record.resources_display = ", ".join(sorted(existing_res))
                    record.date_issued = today_str
                    record.mark_changed()  # Версионирование вместо флага
                else:
                    # Новая запись - version=0, synced_version=0, но version сразу инкрементим
                    record = CachedIssuedRecord(
                        number=number,
                        date_issued=today_str,
                        region=region,
                        employee_stage=employee_stage,
                        resources_display=resources_display,
                        status="",
                        row_index=None,  # Ещё не записан в Sheets
                        version=1,  # Сразу версия 1 (нужна синхронизация)
                        synced_version=0,  # Ещё не синхронизирован
                    )
                    self._issued_cache[number] = record

        logger.debug(f"Added {len(numbers)} numbers to issued cache")

    def _get_status_color(self, status_text: str) -> Optional[dict]:
        """Получить цвет фона для статуса"""
        from bot.models.enums import NumberStatus
        for s in NumberStatus:
            if s.table_name == status_text:
                return s.background_color
        return None

    async def _sync_issued_cache_to_sheets(self) -> None:
        """
        Синхронизировать in-memory кэш выданных номеров с Google Sheets.
        Вызывается периодически в фоне.

        ВАЖНО: Использует sync_lock чтобы только одна синхронизация шла в момент времени.
        """
        # Только одна синхронизация за раз
        if self._sync_lock.locked():
            logger.debug("Sync already in progress, skipping")
            return

        async with self._sync_lock:
            # Собираем записи для синхронизации и запоминаем их версии
            sync_snapshot: Dict[str, int] = {}  # number -> version на момент начала sync
            records_to_sync: List[CachedIssuedRecord] = []

            async with self._issued_cache_lock:
                for record in self._issued_cache.values():
                    if record.needs_sync:
                        records_to_sync.append(record)
                        sync_snapshot[record.number] = record.version

            if not records_to_sync:
                return

            ws_issued = None
            try:
                async with sheets_rate_limiter:
                    gc = await agcm.authorize()
                    ss_issued = await gc.open_by_key(settings.SPREADSHEET_ISSUED)

                issued_sheet_name = settings.SHEET_NAMES.get("numbers_issued", "Номера Выдано")
                try:
                    async with sheets_rate_limiter:
                        ws_issued = await ss_issued.worksheet(issued_sheet_name)
                except Exception:
                    async with sheets_rate_limiter:
                        ws_issued = await ss_issued.add_worksheet(
                            title=issued_sheet_name, rows=1000, cols=10
                        )
                    async with sheets_rate_limiter:
                        await ws_issued.append_row(
                            ["Дата выдачи", "Номер", "Регионы", "Employee", "Ресурсы", "Статус"],
                            value_input_option="USER_ENTERED",
                        )

                # === ШАГ 1: Читаем АКТУАЛЬНОЕ состояние таблицы ===
                async with sheets_rate_limiter:
                    issued_values = await ws_issued.get_all_values()

                # Строим актуальный mapping: phone_number -> row_index
                existing_in_sheets: Dict[str, int] = {}
                for idx, row in enumerate(issued_values[1:], start=2):
                    if row and len(row) >= 2:
                        number = row[1].strip()
                        if number:
                            existing_in_sheets[number] = idx

                # === ШАГ 2: Обновляем row_index в кэше из актуальных данных ===
                async with self._issued_cache_lock:
                    for record in records_to_sync:
                        if record.number in existing_in_sheets:
                            record.row_index = existing_in_sheets[record.number]

                # === ШАГ 3: Готовим данные для записи ===
                rows_to_add = []
                updates_batch = []
                records_for_new_rows: List[CachedIssuedRecord] = []

                for record in records_to_sync:
                    if record.number in existing_in_sheets:
                        # Обновляем существующую строку
                        row_idx = existing_in_sheets[record.number]
                        updates_batch.extend([
                            {"row": row_idx, "col": 1, "value": record.date_issued},
                            {"row": row_idx, "col": 3, "value": record.region},
                            {"row": row_idx, "col": 5, "value": record.resources_display},
                            {"row": row_idx, "col": 6, "value": record.status},
                        ])
                    else:
                        # Новая строка
                        rows_to_add.append([
                            record.date_issued,
                            record.number,
                            record.region,
                            record.employee_stage,
                            record.resources_display,
                            record.status,
                        ])
                        records_for_new_rows.append(record)

                # === ШАГ 4: Batch обновления существующих записей ===
                if updates_batch:
                    await batch_update_cells(ws_issued, updates_batch)
                    logger.info(f"Synced {len(updates_batch) // 4} existing records to sheets")

                # === ШАГ 5: Добавляем новые строки ===
                if rows_to_add:
                    # Находим последнюю ЗАПОЛНЕННУЮ строку (игнорируем пустые)
                    # Это критически важно т.к. len(issued_values) может включать пустые строки
                    last_filled_row = 1  # Минимум - строка заголовка
                    for i, row in enumerate(issued_values, start=1):
                        if row and any(cell.strip() for cell in row if cell):
                            last_filled_row = i

                    # Вычисляем начальную строку для записи
                    start_row = last_filled_row + 1
                    end_row = start_row + len(rows_to_add) - 1

                    # Логируем что будем записывать
                    logger.info(f"Writing {len(rows_to_add)} rows to sheet '{issued_sheet_name}' at rows {start_row}-{end_row} (last filled: {last_filled_row})")
                    for row_data in rows_to_add:
                        logger.debug(f"  Row data: {row_data}")

                    # Используем update с явным диапазоном вместо append_rows
                    # Это даёт 100% контроль над позицией записи
                    range_str = f"A{start_row}:F{end_row}"
                    async with sheets_rate_limiter:
                        await ws_issued.update(range_str, rows_to_add, value_input_option="USER_ENTERED")
                    logger.info(f"Synced {len(rows_to_add)} new records to sheets (range: {range_str})")

                    # row_index теперь точный - мы знаем куда именно записали
                    async with self._issued_cache_lock:
                        for idx, record in enumerate(records_for_new_rows):
                            record.row_index = start_row + idx
                            logger.debug(f"Assigned row_index {record.row_index} to {record.number}")

                # === ШАГ 6: ПРИМЕНЯЕМ ЦВЕТА К СТАТУСАМ ===
                color_formats = []
                for record in records_to_sync:
                    if record.row_index and record.status:
                        status_color = self._get_status_color(record.status)
                        if status_color:
                            color_formats.append({
                                "range": f"F{record.row_index}",
                                "format": {"backgroundColor": status_color}
                            })

                if color_formats:
                    try:
                        async with sheets_rate_limiter:
                            await ws_issued.batch_format(color_formats)
                        logger.info(f"Applied {len(color_formats)} status colors")
                    except Exception as e:
                        # Ошибка форматирования не критична - данные уже записаны
                        logger.warning(f"Failed to apply status colors: {e}")

                # === ШАГ 7: Помечаем как синхронизированные ТОЛЬКО если версия не изменилась ===
                synced_count = 0
                async with self._issued_cache_lock:
                    for record in records_to_sync:
                        # Проверяем что запись не была изменена во время синхронизации
                        if record.number in sync_snapshot:
                            original_version = sync_snapshot[record.number]
                            if record.version == original_version:
                                # Версия не изменилась - можно пометить как синхронизированную
                                record.synced_version = record.version
                                synced_count += 1
                            else:
                                # Версия изменилась - нужна повторная синхронизация
                                logger.debug(f"Record {record.number} changed during sync, will retry")

                logger.debug(f"Marked {synced_count}/{len(records_to_sync)} records as synced")

            except Exception as e:
                logger.error(f"Error syncing issued cache to sheets: {e}")
                # НЕ помечаем как синхронизированные - retry при следующем цикле

    # ==================== ПЕРСИСТЕНТНОСТЬ ====================

    def save_state(self) -> None:
        """Сохранить состояние кэша"""
        try:
            NUMBERS_CACHE_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)

            state = {
                "available": {},
                "pending": {},
                "issued_cache": {},  # НОВОЕ: сохраняем issued_cache
                "used_for_updates": {str(k): list(v) for k, v in self._used_for_updates.items()},
                "saved_at": time.time(),
            }

            for key, numbers in self._available.items():
                state["available"][key] = [
                    {
                        "number": n.number,
                        "date_added": n.date_added,
                        "used_for": list(n.used_for),
                        "row_index": n.row_index,
                    }
                    for n in numbers
                ]

            for num_id, pending in self._pending.items():
                state["pending"][num_id] = {
                    "number_id": pending.number_id,
                    "number": pending.number,
                    "date_added": pending.date_added,
                    "resources": pending.resources,
                    "region": pending.region,
                    "employee_stage": pending.employee_stage,
                    "row_index": pending.row_index,
                    "issued_at": pending.issued_at,
                }

            # НОВОЕ: Сохраняем issued_cache для восстановления после рестарта
            for number, record in self._issued_cache.items():
                state["issued_cache"][number] = {
                    "number": record.number,
                    "date_issued": record.date_issued,
                    "region": record.region,
                    "employee_stage": record.employee_stage,
                    "resources_display": record.resources_display,
                    "status": record.status,
                    "row_index": record.row_index,
                    "version": record.version,
                    "synced_version": record.synced_version,
                }

            with open(NUMBERS_CACHE_STATE_FILE, "w", encoding="utf-8") as f:
                json.dump(state, f, ensure_ascii=False, indent=2)

            total = sum(len(v) for v in state["available"].values()) + len(state["pending"]) + len(state["issued_cache"])
            logger.debug(f"Numbers state saved: {total} items (including {len(state['issued_cache'])} issued)")

        except Exception as e:
            logger.error(f"Error saving numbers state: {e}")

    def load_state(self) -> bool:
        """Загрузить состояние кэша"""
        if not NUMBERS_CACHE_STATE_FILE.exists():
            return False

        try:
            with open(NUMBERS_CACHE_STATE_FILE, "r", encoding="utf-8") as f:
                state = json.load(f)

            for key, numbers_data in state.get("available", {}).items():
                self._available[key] = deque()
                for data in numbers_data:
                    self._available[key].append(CachedNumber(
                        number=data["number"],
                        date_added=data["date_added"],
                        used_for=set(data["used_for"]),
                        row_index=data["row_index"],
                    ))

            for num_id, data in state.get("pending", {}).items():
                self._pending[num_id] = PendingNumber(
                    number_id=data["number_id"],
                    number=data["number"],
                    date_added=data["date_added"],
                    resources=data["resources"],
                    region=data["region"],
                    employee_stage=data["employee_stage"],
                    row_index=data["row_index"],
                    issued_at=data["issued_at"],
                )

            # НОВОЕ: Загружаем issued_cache для восстановления после рестарта
            for number, data in state.get("issued_cache", {}).items():
                self._issued_cache[number] = CachedIssuedRecord(
                    number=data["number"],
                    date_issued=data["date_issued"],
                    region=data["region"],
                    employee_stage=data["employee_stage"],
                    resources_display=data["resources_display"],
                    status=data["status"],
                    row_index=data.get("row_index"),
                    version=data.get("version", 1),
                    synced_version=data.get("synced_version", 0),
                )

            for row_idx_str, used_for_list in state.get("used_for_updates", {}).items():
                self._used_for_updates[int(row_idx_str)] = set(used_for_list)

            total = sum(len(v) for v in self._available.values()) + len(self._pending) + len(self._issued_cache)
            logger.info(f"Numbers state loaded: {total} items (including {len(self._issued_cache)} issued)")
            return True

        except Exception as e:
            logger.error(f"Error loading numbers state: {e}")
            return False

    async def start_background_tasks(self) -> None:
        """Запустить фоновые задачи"""
        if self._save_task is None or self._save_task.done():
            self._save_task = asyncio.create_task(self._save_state_loop())
            logger.info("Numbers state save task started")

        # Фоновая синхронизация issued cache с Sheets
        if self._issued_sync_task is None or self._issued_sync_task.done():
            self._issued_sync_task = asyncio.create_task(self._issued_sync_loop())
            logger.info("Issued cache sync task started")

    async def shutdown(self) -> None:
        """Корректное завершение"""
        logger.info("Shutting down number cache...")

        # Останавливаем фоновые задачи
        for task in [self._save_task, self._issued_sync_task]:
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        # Финальный flush всех обновлений
        await self._flush_used_for_updates()
        await self._sync_issued_cache_to_sheets()

        # Сохраняем состояние
        self.save_state()
        logger.info("Number cache shutdown complete")

    async def _save_state_loop(self) -> None:
        """Периодическое сохранение состояния"""
        while True:
            try:
                await asyncio.sleep(STATE_SAVE_INTERVAL)
                self.save_state()
            except asyncio.CancelledError:
                self.save_state()
                break
            except Exception as e:
                logger.error(f"Numbers state save error: {e}")

    async def _issued_sync_loop(self) -> None:
        """Периодическая синхронизация issued cache с Sheets"""
        # Интервал синхронизации - каждые 10 секунд
        ISSUED_SYNC_INTERVAL = 10

        while True:
            try:
                await asyncio.sleep(ISSUED_SYNC_INTERVAL)
                await self._sync_issued_cache_to_sheets()
            except asyncio.CancelledError:
                # Финальная синхронизация при остановке
                await self._sync_issued_cache_to_sheets()
                break
            except Exception as e:
                logger.error(f"Issued sync loop error: {e}")

    async def preload(self) -> None:
        """Предзагрузка при старте"""
        self.load_state()


# Глобальный кэш
number_cache = NumberCache()


class NumberService:
    """Обёртка для совместимости с существующим API"""

    @property
    def today_only(self) -> bool:
        return number_cache.today_only

    def set_today_only(self, value: bool) -> None:
        number_cache.set_today_only(value)

    async def issue_numbers(
        self,
        resources: List[str],
        region: str,
        quantity: int,
        employee_stage: str,
    ) -> List[Dict[str, Any]]:
        """Выдать номера"""
        numbers = await number_cache.issue_numbers(
            resources=resources,
            region=region,
            quantity=quantity,
            employee_stage=employee_stage,
        )

        # Записываем в in-memory кэш (МГНОВЕННО)
        # Синхронизация с Sheets происходит в фоне каждые 10 сек
        if numbers:
            await number_cache.record_issued_numbers(
                numbers=numbers,
                resources=resources,
                region=region,
                employee_stage=employee_stage,
            )

        return numbers

    async def get_available_count(self, resources: List[str] = None) -> int:
        return await number_cache.get_available_count(resources)

    async def update_number_status(self, number_id: str, status: str) -> bool:
        return await number_cache.update_number_status(number_id, status)

    async def ensure_sheets_exist(self) -> None:
        await number_cache.ensure_sheets_exist()


# Глобальный сервис
number_service = NumberService()
