"""Сервис для работы с почтовыми аккаунтами (Gmail, Рамблер) с кэшированием"""
import asyncio
import json
import logging
import time
import uuid
from typing import List, Dict, Any, Optional
from datetime import datetime
from dataclasses import dataclass, field
from collections import deque
from pathlib import Path

from bot.models.enums import EmailResource, Gender, AccountStatus
from bot.services.sheets_service import agcm
from bot.config import settings

logger = logging.getLogger(__name__)

# Файл для сохранения состояния кэша
EMAIL_CACHE_STATE_FILE = Path(__file__).parent.parent.parent / "data" / "email_cache_state.json"

# Настройки кэша
LOAD_BATCH_SIZE = 15  # Сколько почт загружать за раз
REFILL_THRESHOLD = 5  # Минимум для триггера пополнения
WRITE_BUFFER_INTERVAL = 30  # Интервал записи в таблицу выданных (секунды)
AUTO_CONFIRM_TIMEOUT = 600  # Автоподтверждение через 10 минут
STATE_SAVE_INTERVAL = 60  # Интервал автосохранения состояния


@dataclass
class CachedEmail:
    """Почта в кэше"""
    login: str
    password: str
    extra_info: str  # backup_email для Gmail, пусто для Рамблер
    row_index: int


@dataclass
class PendingEmail:
    """Почта, выданная пользователю, ждёт feedback"""
    email_id: str
    email_resource: EmailResource
    email_type: Optional[Gender]
    sheet_name: str
    login: str
    password: str
    extra_info: str
    region: str
    employee_stage: str
    issued_at: float = field(default_factory=time.time)


@dataclass
class ConfirmedEmail:
    """Почта с feedback, ждёт записи в таблицу"""
    email_resource: EmailResource
    email_type: Optional[Gender]
    sheet_name: str
    login: str
    password: str
    extra_info: str
    region: str
    employee_stage: str
    status: str


class EmailCache:
    """
    Двухуровневый кэш почт (аналогично AccountCache):
    - available: готовы к выдаче (уже удалены из "Базы")
    - pending: выданы, ждут feedback
    - write_buffer: подтверждены, ждут записи в "Выданные"
    """

    def __init__(self):
        # Доступные для выдачи {key: deque of CachedEmail}
        self._available: Dict[str, deque] = {}
        # Выданные, ждут feedback {email_id: PendingEmail}
        self._pending: Dict[str, PendingEmail] = {}
        # Буфер записи {key: list of ConfirmedEmail}
        self._write_buffer: Dict[str, List[ConfirmedEmail]] = {}

        # Мета-блокировка для создания других блокировок (fix race condition)
        self._meta_lock = asyncio.Lock()

        # Блокировки
        self._load_locks: Dict[str, asyncio.Lock] = {}
        self._issue_locks: Dict[str, asyncio.Lock] = {}
        self._loading: Dict[str, bool] = {}

        # Фоновые задачи
        self._write_task: Optional[asyncio.Task] = None
        self._auto_confirm_task: Optional[asyncio.Task] = None
        self._save_task: Optional[asyncio.Task] = None

    def _get_key(self, email_resource: EmailResource, email_type: Optional[Gender]) -> str:
        type_val = email_type.value if email_type else "none"
        return f"{email_resource.value}_{type_val}"

    def _get_sheet_name(self, email_resource: EmailResource, email_type: Optional[Gender]) -> str:
        if email_resource == EmailResource.GMAIL:
            if email_type == Gender.GMAIL_DOMAIN:
                return settings.SHEET_NAMES.get("gmail_domain", "Гугл Гмейл")
            else:
                return settings.SHEET_NAMES.get("gmail_any", "Гугл Обыч")
        elif email_resource == EmailResource.RAMBLER:
            return settings.SHEET_NAMES.get("rambler_none", "Рамблер")
        return "Unknown"

    async def _get_lock(self, locks_dict: Dict[str, asyncio.Lock], key: str) -> asyncio.Lock:
        """Потокобезопасное получение блокировки для ключа"""
        async with self._meta_lock:
            if key not in locks_dict:
                locks_dict[key] = asyncio.Lock()
            return locks_dict[key]

    # ==================== ЗАГРУЗКА ====================

    async def _load_emails(
        self,
        email_resource: EmailResource,
        email_type: Optional[Gender],
        force: bool = False
    ) -> int:
        """
        Загрузить почты из Sheets → удалить из "Базы" → добавить в available.
        Возвращает количество загруженных.
        """
        key = self._get_key(email_resource, email_type)
        sheet_name = self._get_sheet_name(email_resource, email_type)

        current_available = len(self._available.get(key, deque()))
        if not force and current_available >= LOAD_BATCH_SIZE:
            logger.debug(f"Skipping load for {key}: already have {current_available} available")
            return 0

        load_lock = await self._get_lock(self._load_locks, key)

        if self._loading.get(key):
            return 0

        async with load_lock:
            if self._loading.get(key):
                return 0

            current_available = len(self._available.get(key, deque()))
            if not force and current_available >= LOAD_BATCH_SIZE:
                return 0

            self._loading[key] = True
            try:
                logger.info(f"Loading emails for {key} (current: {current_available})...")

                gc = await agcm.authorize()
                spreadsheet = await gc.open_by_key(settings.SPREADSHEET_ACCOUNTS)

                try:
                    worksheet = await spreadsheet.worksheet(sheet_name)
                except Exception as e:
                    logger.error(f"Sheet '{sheet_name}' not found: {e}")
                    return 0

                all_values = await worksheet.get_all_values()

                if not all_values or len(all_values) < 2:
                    logger.info(f"No emails available in sheet '{sheet_name}'")
                    return 0

                # Собираем почты для загрузки
                emails_to_load = []
                rows_to_delete = []

                for idx, row in enumerate(all_values[1:], start=2):
                    if len(emails_to_load) >= LOAD_BATCH_SIZE:
                        break

                    if len(row) < 3:
                        continue

                    login = row[1]
                    password = row[2]
                    extra_info = row[3] if len(row) > 3 else ""

                    if not login or not password:
                        continue

                    emails_to_load.append(CachedEmail(
                        login=login,
                        password=password,
                        extra_info=extra_info,
                        row_index=idx,
                    ))
                    rows_to_delete.append(idx)

                if not emails_to_load:
                    logger.info(f"No valid emails found in sheet '{sheet_name}'")
                    return 0

                # Удаляем строки из базы (группируя смежные для меньшего числа API вызовов)
                sorted_indices = sorted(rows_to_delete, reverse=True)
                groups = []
                current_group = [sorted_indices[0]]

                for idx in sorted_indices[1:]:
                    # Если смежный (idx на 1 меньше последнего в группе)
                    if current_group[-1] - idx == 1:
                        current_group.append(idx)
                    else:
                        groups.append(current_group)
                        current_group = [idx]
                groups.append(current_group)

                # Удаляем группами (один API вызов на группу смежных строк)
                for group in groups:
                    start_idx = min(group)
                    end_idx = max(group)
                    await worksheet.delete_rows(start_idx, end_idx)

                logger.debug(f"Deleted {len(rows_to_delete)} rows from '{sheet_name}' ({len(groups)} API calls)")

                # Добавляем в available кэш
                if key not in self._available:
                    self._available[key] = deque()

                for email in emails_to_load:
                    self._available[key].append(email)

                logger.info(f"Loaded {len(emails_to_load)} emails for {key}, available: {len(self._available[key])}")
                return len(emails_to_load)

            except Exception as e:
                logger.error(f"Error loading emails for {key}: {e}")
                return 0
            finally:
                self._loading[key] = False

    # ==================== ВЫДАЧА ====================

    async def get_emails(
        self,
        email_resource: EmailResource,
        email_type: Optional[Gender],
        quantity: int,
        region: str,
        employee_stage: str,
    ) -> List[Dict[str, Any]]:
        """Получить почты мгновенно из кэша"""
        key = self._get_key(email_resource, email_type)
        sheet_name = self._get_sheet_name(email_resource, email_type)
        issue_lock = await self._get_lock(self._issue_locks, key)

        async with issue_lock:
            available = self._available.get(key, deque())

            # Если не хватает — загружаем
            if len(available) < quantity:
                await self._load_emails(email_resource, email_type)
                available = self._available.get(key, deque())

            # Забираем из available → переносим в pending
            result = []
            for _ in range(min(quantity, len(available))):
                if not available:
                    break

                cached_email = available.popleft()
                email_id = f"email_{uuid.uuid4().hex[:12]}"

                pending = PendingEmail(
                    email_id=email_id,
                    email_resource=email_resource,
                    email_type=email_type,
                    sheet_name=sheet_name,
                    login=cached_email.login,
                    password=cached_email.password,
                    extra_info=cached_email.extra_info,
                    region=region,
                    employee_stage=employee_stage,
                )
                self._pending[email_id] = pending

                result.append({
                    "email_id": email_id,
                    "login": cached_email.login,
                    "password": cached_email.password,
                    "extra_info": cached_email.extra_info,
                    "region": region,
                })

            # Триггер пополнения если мало осталось
            if len(available) < REFILL_THRESHOLD:
                asyncio.create_task(self._background_refill(email_resource, email_type))

            return result

    async def _background_refill(self, email_resource: EmailResource, email_type: Optional[Gender]) -> None:
        """Фоновое пополнение кэша"""
        try:
            await self._load_emails(email_resource, email_type)
        except Exception as e:
            logger.error(f"Background refill error: {e}")

    # ==================== FEEDBACK ====================

    def confirm_email(self, email_id: str, status: str) -> bool:
        """
        Подтвердить почту (мгновенно).
        Перемещает из pending в write_buffer.
        """
        pending = self._pending.pop(email_id, None)
        if not pending:
            logger.warning(f"Email {email_id} not found in pending")
            return False

        key = self._get_key(pending.email_resource, pending.email_type)

        confirmed = ConfirmedEmail(
            email_resource=pending.email_resource,
            email_type=pending.email_type,
            sheet_name=pending.sheet_name,
            login=pending.login,
            password=pending.password,
            extra_info=pending.extra_info,
            region=pending.region,
            employee_stage=pending.employee_stage,
            status=status,
        )

        if key not in self._write_buffer:
            self._write_buffer[key] = []
        self._write_buffer[key].append(confirmed)

        logger.debug(f"Email {email_id} confirmed with status {status}, added to write buffer")
        return True

    # ==================== ФОНОВЫЕ ЗАДАЧИ ====================

    async def start_background_tasks(self) -> None:
        """Запустить фоновые задачи"""
        if self._write_task is None or self._write_task.done():
            self._write_task = asyncio.create_task(self._write_buffer_loop())
            logger.info("Email write buffer task started")

        if self._auto_confirm_task is None or self._auto_confirm_task.done():
            self._auto_confirm_task = asyncio.create_task(self._auto_confirm_loop())
            logger.info("Email auto-confirm task started")

        if self._save_task is None or self._save_task.done():
            self._save_task = asyncio.create_task(self._save_state_loop())
            logger.info("Email state save task started")

    async def shutdown(self) -> None:
        """Корректное завершение — сохраняем всё"""
        logger.info("Shutting down email cache...")

        for task in [self._write_task, self._auto_confirm_task, self._save_task]:
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        # Финальный flush буфера записи
        await self._flush_write_buffer()

        # Финальное сохранение состояния
        self.save_state()
        logger.info("Email cache shutdown complete")

    async def _write_buffer_loop(self) -> None:
        """Цикл записи буфера в Sheets"""
        while True:
            try:
                await asyncio.sleep(WRITE_BUFFER_INTERVAL)
                await self._flush_write_buffer()
            except asyncio.CancelledError:
                await self._flush_write_buffer()
                break
            except Exception as e:
                logger.error(f"Email write buffer error: {e}")

    async def _flush_write_buffer(self) -> None:
        """Записать буфер в таблицы выдачи"""
        for key, emails in list(self._write_buffer.items()):
            if not emails:
                continue

            to_write = emails.copy()
            self._write_buffer[key] = []

            if not to_write:
                continue

            # Группируем по листу выдачи
            by_sheet: Dict[str, List[ConfirmedEmail]] = {}
            for email in to_write:
                if email.email_resource == EmailResource.GMAIL:
                    issued_sheet_name = email.sheet_name
                else:
                    issued_sheet_name = f"{email.sheet_name} Выдано"

                if issued_sheet_name not in by_sheet:
                    by_sheet[issued_sheet_name] = []
                by_sheet[issued_sheet_name].append(email)

            try:
                gc = await agcm.authorize()
                issued_spreadsheet = await gc.open_by_key(settings.SPREADSHEET_ISSUED)

                for sheet_name, sheet_emails in by_sheet.items():
                    try:
                        try:
                            worksheet = await issued_spreadsheet.worksheet(sheet_name)
                        except Exception:
                            worksheet = await issued_spreadsheet.add_worksheet(
                                title=sheet_name, rows=1000, cols=10
                            )
                            await worksheet.update("A1:G1", [[
                                "Дата выдачи", "Логин", "Пароль", "Доп инфа", "Регион", "Employee", "Статус"
                            ]])

                        current_date = datetime.now().strftime("%d.%m.%y")
                        rows = []
                        status_colors = []

                        for email in sheet_emails:
                            try:
                                status_enum = AccountStatus(email.status)
                                status_text = status_enum.table_name
                                bg_color = status_enum.background_color
                            except ValueError:
                                status_text = email.status
                                bg_color = None

                            rows.append([
                                current_date,
                                email.login,
                                email.password,
                                email.extra_info,
                                email.region,
                                email.employee_stage,
                                status_text,
                            ])
                            status_colors.append(bg_color)

                        if rows:
                            all_values = await worksheet.get_all_values()

                            # Находим последнюю ЗАПОЛНЕННУЮ строку (игнорируем пустые)
                            last_filled_row = 1  # Минимум заголовок
                            for i, row in enumerate(all_values, start=1):
                                if row and any(cell.strip() for cell in row if cell):
                                    last_filled_row = i

                            # Записываем в конкретный диапазон после последней заполненной строки
                            start_row = last_filled_row + 1
                            end_row = start_row + len(rows) - 1
                            range_str = f"A{start_row}:G{end_row}"

                            await worksheet.update(range_str, rows, value_input_option="USER_ENTERED")

                            # Форматируем все ячейки со статусами за один batch запрос
                            formats_to_apply = []
                            for idx, bg_color in enumerate(status_colors):
                                if bg_color:
                                    cell_address = f"G{start_row + idx}"
                                    formats_to_apply.append({
                                        "range": cell_address,
                                        "format": {"backgroundColor": bg_color}
                                    })

                            if formats_to_apply:
                                await worksheet.batch_format(formats_to_apply)

                        logger.info(f"Flushed {len(sheet_emails)} emails to '{sheet_name}'")

                    except Exception as e:
                        logger.error(f"Error flushing emails to '{sheet_name}': {e}")
                        # Возвращаем в буфер
                        if key not in self._write_buffer:
                            self._write_buffer[key] = []
                        self._write_buffer[key].extend(sheet_emails)

            except Exception as e:
                logger.error(f"Error flushing write buffer for {key}: {e}")
                if key not in self._write_buffer:
                    self._write_buffer[key] = []
                self._write_buffer[key].extend(to_write)

    async def _auto_confirm_loop(self) -> None:
        """Автоподтверждение просроченных почт"""
        while True:
            try:
                await asyncio.sleep(60)
                await self._process_expired_pending()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Email auto-confirm error: {e}")

    async def _process_expired_pending(self) -> None:
        """Подтвердить просроченные pending как 'good'"""
        now = time.time()
        expired = [
            email_id for email_id, pending in list(self._pending.items())
            if now - pending.issued_at > AUTO_CONFIRM_TIMEOUT
        ]

        for email_id in expired:
            logger.info(f"Auto-confirming expired email {email_id}")
            self.confirm_email(email_id, "good")

    # ==================== ПЕРСИСТЕНТНОСТЬ ====================

    def save_state(self) -> None:
        """Сохранить состояние кэша в файл"""
        try:
            EMAIL_CACHE_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)

            state = {
                "available": {},
                "pending": {},
                "write_buffer": {},
                "saved_at": time.time(),
            }

            # Сохраняем available
            for key, emails in self._available.items():
                state["available"][key] = [
                    {
                        "login": e.login,
                        "password": e.password,
                        "extra_info": e.extra_info,
                        "row_index": e.row_index,
                    }
                    for e in emails
                ]

            # Сохраняем pending
            for email_id, pending in self._pending.items():
                state["pending"][email_id] = {
                    "email_resource": pending.email_resource.value,
                    "email_type": pending.email_type.value if pending.email_type else None,
                    "sheet_name": pending.sheet_name,
                    "login": pending.login,
                    "password": pending.password,
                    "extra_info": pending.extra_info,
                    "region": pending.region,
                    "employee_stage": pending.employee_stage,
                    "issued_at": pending.issued_at,
                }

            # Сохраняем write_buffer
            for key, emails in self._write_buffer.items():
                state["write_buffer"][key] = [
                    {
                        "email_resource": e.email_resource.value,
                        "email_type": e.email_type.value if e.email_type else None,
                        "sheet_name": e.sheet_name,
                        "login": e.login,
                        "password": e.password,
                        "extra_info": e.extra_info,
                        "region": e.region,
                        "employee_stage": e.employee_stage,
                        "status": e.status,
                    }
                    for e in emails
                ]

            with open(EMAIL_CACHE_STATE_FILE, "w", encoding="utf-8") as f:
                json.dump(state, f, ensure_ascii=False, indent=2)

            total = (
                sum(len(v) for v in state["available"].values()) +
                len(state["pending"]) +
                sum(len(v) for v in state["write_buffer"].values())
            )
            logger.debug(f"Email state saved: {total} items")

        except Exception as e:
            logger.error(f"Error saving email state: {e}")

    def load_state(self) -> bool:
        """Загрузить состояние кэша из файла"""
        if not EMAIL_CACHE_STATE_FILE.exists():
            logger.info("No saved email state found")
            return False

        try:
            with open(EMAIL_CACHE_STATE_FILE, "r", encoding="utf-8") as f:
                state = json.load(f)

            # Загружаем available
            for key, emails_data in state.get("available", {}).items():
                self._available[key] = deque()
                for data in emails_data:
                    self._available[key].append(CachedEmail(
                        login=data["login"],
                        password=data["password"],
                        extra_info=data.get("extra_info", ""),
                        row_index=data["row_index"],
                    ))

            # Загружаем pending
            for email_id, data in state.get("pending", {}).items():
                email_type = Gender(data["email_type"]) if data.get("email_type") else None
                self._pending[email_id] = PendingEmail(
                    email_id=email_id,
                    email_resource=EmailResource(data["email_resource"]),
                    email_type=email_type,
                    sheet_name=data["sheet_name"],
                    login=data["login"],
                    password=data["password"],
                    extra_info=data.get("extra_info", ""),
                    region=data["region"],
                    employee_stage=data["employee_stage"],
                    issued_at=data["issued_at"],
                )

            # Загружаем write_buffer
            for key, emails_data in state.get("write_buffer", {}).items():
                self._write_buffer[key] = []
                for data in emails_data:
                    email_type = Gender(data["email_type"]) if data.get("email_type") else None
                    self._write_buffer[key].append(ConfirmedEmail(
                        email_resource=EmailResource(data["email_resource"]),
                        email_type=email_type,
                        sheet_name=data["sheet_name"],
                        login=data["login"],
                        password=data["password"],
                        extra_info=data.get("extra_info", ""),
                        region=data["region"],
                        employee_stage=data["employee_stage"],
                        status=data["status"],
                    ))

            total = (
                sum(len(v) for v in self._available.values()) +
                len(self._pending) +
                sum(len(v) for v in self._write_buffer.values())
            )
            saved_at = state.get("saved_at", 0)
            age_min = (time.time() - saved_at) / 60

            logger.info(f"Email state loaded: {total} items (saved {age_min:.1f} min ago)")
            return True

        except Exception as e:
            logger.error(f"Error loading email state: {e}")
            return False

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
                logger.error(f"Email state save error: {e}")

    # ==================== ПРЕДЗАГРУЗКА ====================

    async def preload_all(self) -> None:
        """Предзагрузить почты всех типов при старте"""
        # Сначала пробуем загрузить сохранённое состояние
        state_loaded = self.load_state()

        # Проверяем, нужно ли дозагружать из Sheets
        need_load = []

        # Gmail типы
        for email_type in [Gender.ANY, Gender.GMAIL_DOMAIN]:
            key = self._get_key(EmailResource.GMAIL, email_type)
            available = len(self._available.get(key, deque()))
            if available < REFILL_THRESHOLD:
                need_load.append((EmailResource.GMAIL, email_type, available))

        # Рамблер
        key = self._get_key(EmailResource.RAMBLER, None)
        available = len(self._available.get(key, deque()))
        if available < REFILL_THRESHOLD:
            need_load.append((EmailResource.RAMBLER, None, available))

        if not need_load:
            logger.info("All email types have enough in cache, skipping Sheets preload")
            return

        logger.info(f"Need to load {len(need_load)} email types from Sheets...")

        tasks = []
        for email_resource, email_type, current in need_load:
            key = self._get_key(email_resource, email_type)
            logger.info(f"  - {key}: {current} available")
            tasks.append(self._load_emails(email_resource, email_type))

        results = await asyncio.gather(*tasks, return_exceptions=True)
        total = sum(r for r in results if isinstance(r, int))
        logger.info(f"Email preload complete: {total} emails loaded from Sheets")

    def get_stats(self) -> Dict[str, Any]:
        """Статистика кэша"""
        stats = {}
        all_keys = set(
            list(self._available.keys()) +
            list(self._write_buffer.keys()) +
            [self._get_key(p.email_resource, p.email_type) for p in self._pending.values()]
        )
        for key in all_keys:
            stats[key] = {
                "available": len(self._available.get(key, deque())),
                "pending": sum(
                    1 for p in self._pending.values()
                    if self._get_key(p.email_resource, p.email_type) == key
                ),
                "write_buffer": len(self._write_buffer.get(key, [])),
            }
        return stats

    def clear_cache(self, key: str = None, clear_type: str = "all") -> Dict[str, int]:
        """
        Очистить кэш почт.

        Args:
            key: Ключ ресурса (например "gmail_any") или None для всех
            clear_type: Что очищать - "available", "pending", "write_buffer" или "all"

        Returns:
            Словарь с количеством удалённых элементов по каждому типу
        """
        cleared = {"available": 0, "pending": 0, "write_buffer": 0}

        if clear_type in ("available", "all"):
            if key:
                if key in self._available:
                    cleared["available"] = len(self._available[key])
                    self._available[key] = deque()
            else:
                for k in list(self._available.keys()):
                    cleared["available"] += len(self._available[k])
                    self._available[k] = deque()

        if clear_type in ("pending", "all"):
            if key:
                to_remove = [
                    email_id for email_id, p in self._pending.items()
                    if self._get_key(p.email_resource, p.email_type) == key
                ]
                for email_id in to_remove:
                    del self._pending[email_id]
                cleared["pending"] = len(to_remove)
            else:
                cleared["pending"] = len(self._pending)
                self._pending.clear()

        if clear_type in ("write_buffer", "all"):
            if key:
                if key in self._write_buffer:
                    cleared["write_buffer"] = len(self._write_buffer[key])
                    self._write_buffer[key] = []
            else:
                for k in list(self._write_buffer.keys()):
                    cleared["write_buffer"] += len(self._write_buffer[k])
                    self._write_buffer[k] = []

        # Сохраняем состояние после очистки
        self.save_state()
        logger.info(f"Email cache cleared: key={key}, type={clear_type}, cleared={cleared}")

        return cleared


# Глобальный кэш
email_cache = EmailCache()


class EmailService:
    """Бизнес-логика выдачи почт"""

    async def issue_emails(
        self,
        email_resource: EmailResource,
        region: str,
        quantity: int,
        employee_stage: str,
        email_type: Gender = None,
    ) -> List[Dict[str, Any]]:
        """Выдать почты мгновенно из кэша"""
        # Для Gmail требуется тип
        if email_resource == EmailResource.GMAIL and not email_type:
            logger.error("Gmail requires email_type (ANY or GMAIL_DOMAIN)")
            return []

        return await email_cache.get_emails(
            email_resource=email_resource,
            email_type=email_type,
            quantity=quantity,
            region=region,
            employee_stage=employee_stage,
        )

    def confirm_email_feedback(self, email_id: str, status: str) -> bool:
        """Подтвердить feedback (мгновенно)"""
        return email_cache.confirm_email(email_id, status)

    async def start_background_tasks(self) -> None:
        """Запустить фоновые задачи"""
        await email_cache.start_background_tasks()

    async def shutdown(self) -> None:
        """Корректное завершение"""
        await email_cache.shutdown()

    async def preload_all(self) -> None:
        """Предзагрузка почт"""
        await email_cache.preload_all()


# Глобальный инстанс сервиса
email_service = EmailService()
