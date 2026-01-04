"""
Сервис для работы с почтами с умным распределением.

Новый flow:
1. Пользователь выбирает домен (Gmail/Рамблер)
2. Выбирает регион
3. Выбирает режим: "Новая" или "Эконом"
4. Выбирает целевые ресурсы (мультиселект)
5. Выбирает количество

"Новая" - берётся из таблицы "Базы" (лист соответствующего домена)
- Столбец E содержит регион
- Выдаётся только если регион совпадает

"Эконом" - берётся из таблицы "Выданных"
- Ищутся почты, которые ещё не использовались на выбранных ресурсах
- Добавляются новые ресурсы к существующим

Структура листа "Базы":
A: Дата | B: Логин | C: Пароль | D: Доп инфо | E: Регион

Структура листа "Выданных":
A: Дата | B: Логин | C: Пароль | D: Доп инфо | E: Регион | F: Employee | G: Статус | H: Ресурсы
"""
import asyncio
import json
import logging
import time
import uuid
from typing import List, Dict, Any, Optional, Set
from datetime import datetime
from dataclasses import dataclass, field
from collections import deque
from pathlib import Path

from bot.models.enums import EmailResource, EmailMode, EmailType, EmailTargetResource, AccountStatus
from bot.services.sheets_service import agcm
from bot.config import settings

logger = logging.getLogger(__name__)

# Файл для сохранения состояния кэша
EMAIL_CACHE_STATE_FILE = Path(__file__).parent.parent.parent / "data" / "email_cache_state.json"

# Настройки кэша
LOAD_PER_REGION = 10  # Сколько почт загружать для каждого региона
REFILL_THRESHOLD = 3  # Минимум почт региона для триггера пополнения
WRITE_BUFFER_INTERVAL = 30  # Интервал записи в таблицу выданных (секунды)
AUTO_CONFIRM_TIMEOUT = 600  # Автоподтверждение через 10 минут
STATE_SAVE_INTERVAL = 60  # Интервал автосохранения состояния


def get_base_sheet_name(email_resource: EmailResource, email_type: EmailType = EmailType.ANY) -> str:
    """Получить название листа базы для домена и типа"""
    if email_resource == EmailResource.GMAIL:
        if email_type == EmailType.GMAIL_DOMAIN:
            return settings.SHEET_NAMES.get("gmail_gmail_domain", "Гугл Гмейл")
        else:
            return settings.SHEET_NAMES.get("gmail_any", "Гугл Любые")
    elif email_resource == EmailResource.RAMBLER:
        return settings.SHEET_NAMES.get("rambler_none", "Рамблер")
    return "Unknown"


def get_issued_sheet_name(email_resource: EmailResource, email_type: EmailType = EmailType.ANY) -> str:
    """Получить название листа выданных для домена и типа.

    Используем те же листы что и в базе: "Гугл Гмейл", "Гугл Обыч", "Рамблер"
    (в таблице "Выданные истоки").
    """
    return get_base_sheet_name(email_resource, email_type)


def get_buffer_key(email_resource: EmailResource, email_type: EmailType = EmailType.ANY) -> str:
    """
    Получить ключ буфера для домена и типа.

    Ключи:
    - gmail_any — Gmail любые домены
    - gmail_gmail_domain — Gmail только @gmail.com
    - rambler — Рамблер
    """
    if email_resource == EmailResource.GMAIL:
        if email_type == EmailType.GMAIL_DOMAIN:
            return "gmail_gmail_domain"
        else:
            return "gmail_any"
    else:
        return "rambler"


@dataclass
class CachedEmail:
    """Почта в кэше (для режима "Новая")"""
    login: str
    password: str
    extra_info: str  # backup_email для Gmail, пусто для Рамблер
    region: str
    row_index: int


@dataclass
class EconomyEmail:
    """Почта из выданных (для режима "Эконом")"""
    login: str
    password: str
    extra_info: str
    region: str
    row_index: int  # Строка в листе "Выданные"
    used_for: Set[str] = field(default_factory=set)  # Ресурсы, на которых уже использовалась


@dataclass
class PendingEmail:
    """Почта, выданная пользователю, ждёт feedback"""
    email_id: str
    email_resource: EmailResource
    email_type: EmailType  # Тип Gmail (any/gmail_domain/none)
    email_mode: EmailMode
    login: str
    password: str
    extra_info: str
    region: str
    target_resources: List[str]  # Выбранные целевые ресурсы
    employee_stage: str
    issued_at: float = field(default_factory=time.time)
    # Для эконом режима - индекс строки в выданных для обновления
    issued_row_index: Optional[int] = None


@dataclass
class ConfirmedEmail:
    """Почта с feedback, ждёт записи/обновления в таблице"""
    email_resource: EmailResource
    email_type: EmailType  # Тип Gmail (any/gmail_domain/none)
    email_mode: EmailMode
    login: str
    password: str
    extra_info: str
    region: str
    target_resources: List[str]
    employee_stage: str
    status: str
    # Для эконом режима - индекс строки в выданных для обновления
    issued_row_index: Optional[int] = None


class EmailCache:
    """
    Кэш почт с умным распределением.

    Структура буфера: один буфер на домен (gmail/rambler).
    Почты разных регионов хранятся вместе, фильтруются при выдаче.
    Загрузка ленивая - только при запросе конкретного региона.

    Для режима "Новая":
    - Кэшируем по ключу {domain} (gmail/rambler)
    - При запросе региона загружаем до 10 почт этого региона
    - Загружаем из листа "Базы", удаляем при выдаче
    - Записываем в "Выданные" после feedback

    Для режима "Эконом":
    - Не кэшируем (всегда свежие данные из "Выданных")
    - Ищем почты, которые ещё не использовались на выбранных ресурсах
    - Обновляем список ресурсов в "Выданных"
    """

    def __init__(self):
        # Доступные для выдачи (только для режима "Новая") {domain: deque of CachedEmail}
        # Ключ: домен (gmail/rambler), почты разных регионов хранятся вместе
        self._available: Dict[str, deque] = {}

        # Выданные, ждут feedback {email_id: PendingEmail}
        self._pending: Dict[str, PendingEmail] = {}

        # Буфер записи {domain: list of ConfirmedEmail}
        self._write_buffer: Dict[str, List[ConfirmedEmail]] = {}

        # Буфер обновления (для эконом режима) {domain: list of ConfirmedEmail}
        self._update_buffer: Dict[str, List[ConfirmedEmail]] = {}

        # Мета-блокировка для создания других блокировок
        self._meta_lock = asyncio.Lock()

        # Блокировки по домену
        self._load_locks: Dict[str, asyncio.Lock] = {}
        self._issue_locks: Dict[str, asyncio.Lock] = {}
        # Блокировки загрузки по домену+региону
        self._loading: Dict[str, bool] = {}

        # Фоновые задачи
        self._write_task: Optional[asyncio.Task] = None
        self._auto_confirm_task: Optional[asyncio.Task] = None
        self._save_task: Optional[asyncio.Task] = None

    def _get_buffer_key(self, email_resource: EmailResource, email_type: EmailType) -> str:
        """Ключ для буфера: домен + тип (для Gmail) или просто домен (для Rambler)"""
        return get_buffer_key(email_resource, email_type)

    def _get_load_key(self, email_resource: EmailResource, email_type: EmailType, region: str) -> str:
        """Ключ для отслеживания загрузки конкретного региона"""
        buffer_key = self._get_buffer_key(email_resource, email_type)
        return f"{buffer_key}_{region}"

    async def _get_lock(self, locks_dict: Dict[str, asyncio.Lock], key: str) -> asyncio.Lock:
        """Потокобезопасное получение блокировки для ключа"""
        async with self._meta_lock:
            if key not in locks_dict:
                locks_dict[key] = asyncio.Lock()
            return locks_dict[key]

    # ==================== ЗАГРУЗКА ДЛЯ РЕЖИМА "НОВАЯ" ====================

    def _count_region_emails(self, domain_key: str, region: str) -> int:
        """Подсчитать количество почт конкретного региона в буфере"""
        available = self._available.get(domain_key, deque())
        return sum(1 for e in available if e.region == region)

    async def _load_new_emails(
        self,
        email_resource: EmailResource,
        email_type: EmailType,
        region: str,
        force: bool = False
    ) -> int:
        """
        Загрузить почты из Базы для режима "Новая".
        Загружаем до LOAD_PER_REGION почт указанного региона в буфер.
        """
        buffer_key = self._get_buffer_key(email_resource, email_type)
        load_key = self._get_load_key(email_resource, email_type, region)
        sheet_name = get_base_sheet_name(email_resource, email_type)

        # Проверяем сколько почт этого региона уже в буфере
        current_region_count = self._count_region_emails(buffer_key, region)
        if not force and current_region_count >= LOAD_PER_REGION:
            logger.debug(f"Skipping load for {load_key}: already have {current_region_count} for region {region}")
            return 0

        load_lock = await self._get_lock(self._load_locks, load_key)

        if self._loading.get(load_key):
            return 0

        async with load_lock:
            if self._loading.get(load_key):
                return 0

            # Пересчитываем после получения блокировки
            current_region_count = self._count_region_emails(buffer_key, region)
            need_to_load = LOAD_PER_REGION - current_region_count
            if not force and need_to_load <= 0:
                return 0

            self._loading[load_key] = True
            try:
                logger.info(f"Loading NEW emails for {buffer_key} region {region} (need: {need_to_load})...")

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

                # Собираем почты для загрузки (фильтруем по региону)
                emails_to_load = []
                rows_to_delete = []

                for idx, row in enumerate(all_values[1:], start=2):
                    if len(emails_to_load) >= need_to_load:
                        break

                    if len(row) < 5:  # A:дата, B:логин, C:пароль, D:доп_инфо, E:регион
                        continue

                    login = row[1]
                    password = row[2]
                    extra_info = row[3] if len(row) > 3 else ""
                    email_region = row[4] if len(row) > 4 else ""

                    if not login or not password:
                        continue

                    # Фильтруем по региону
                    if email_region.strip() != region:
                        continue

                    emails_to_load.append(CachedEmail(
                        login=login,
                        password=password,
                        extra_info=extra_info,
                        region=region,
                        row_index=idx,
                    ))
                    rows_to_delete.append(idx)

                if not emails_to_load:
                    logger.info(f"No valid emails found in sheet '{sheet_name}' for region {region}")
                    return 0

                # Удаляем строки из базы (группируя смежные)
                sorted_indices = sorted(rows_to_delete, reverse=True)
                groups = []
                current_group = [sorted_indices[0]]

                for idx in sorted_indices[1:]:
                    if current_group[-1] - idx == 1:
                        current_group.append(idx)
                    else:
                        groups.append(current_group)
                        current_group = [idx]
                groups.append(current_group)

                for group in groups:
                    start_idx = min(group)
                    end_idx = max(group)
                    await worksheet.delete_rows(start_idx, end_idx)

                logger.debug(f"Deleted {len(rows_to_delete)} rows from '{sheet_name}' ({len(groups)} API calls)")

                # Добавляем в буфер
                if buffer_key not in self._available:
                    self._available[buffer_key] = deque()

                for email in emails_to_load:
                    self._available[buffer_key].append(email)

                total_in_buffer = len(self._available[buffer_key])
                logger.info(f"Loaded {len(emails_to_load)} emails for {buffer_key} region {region}, total in buffer: {total_in_buffer}")
                return len(emails_to_load)

            except Exception as e:
                logger.error(f"Error loading NEW emails for {load_key}: {e}")
                return 0
            finally:
                self._loading[load_key] = False

    # ==================== ЗАГРУЗКА ДЛЯ РЕЖИМА "ЭКОНОМ" ====================

    async def _find_economy_emails(
        self,
        email_resource: EmailResource,
        email_type: EmailType,
        region: str,  # Не используется для эконом режима, но оставлен для совместимости
        target_resources: List[str],
        quantity: int,
    ) -> List[EconomyEmail]:
        """
        Найти почты для режима "Эконом" из таблицы Выданных.
        Ищем почты, которые ещё не использовались на выбранных ресурсах.

        Для эконом режима НЕ фильтруем по региону - только по использованным ресурсам.
        Для Gmail - не используем почты старше 3 дней.
        """
        sheet_name = get_issued_sheet_name(email_resource, email_type)

        try:
            gc = await agcm.authorize()
            spreadsheet = await gc.open_by_key(settings.SPREADSHEET_ISSUED)

            try:
                worksheet = await spreadsheet.worksheet(sheet_name)
            except Exception as e:
                logger.error(f"Sheet '{sheet_name}' not found: {e}")
                return []

            all_values = await worksheet.get_all_values()

            if not all_values or len(all_values) < 2:
                logger.info(f"No emails in issued sheet '{sheet_name}'")
                return []

            # Структура: A:дата, B:логин, C:пароль, D:доп_инфо, E:регион, F:employee, G:статус, H:ресурсы
            found_emails = []
            target_set = set(target_resources)

            # Для Gmail - проверяем что почта не старше 3 дней
            is_gmail = email_resource == EmailResource.GMAIL
            if is_gmail:
                from datetime import datetime, timedelta
                three_days_ago = datetime.now() - timedelta(days=3)

            for idx, row in enumerate(all_values[1:], start=2):
                if len(found_emails) >= quantity:
                    break

                if len(row) < 5:
                    continue

                date_str = row[0] if len(row) > 0 else ""
                login = row[1]
                password = row[2]
                extra_info = row[3] if len(row) > 3 else ""
                email_region = row[4] if len(row) > 4 else ""
                status = row[6] if len(row) > 6 else ""
                resources_str = row[7] if len(row) > 7 else ""

                # Для Gmail - не используем почты старше 3 дней
                if is_gmail and date_str:
                    try:
                        # Формат даты: DD.MM.YYYY HH:MM:SS или DD.MM.YYYY
                        date_part = date_str.split()[0] if " " in date_str else date_str
                        email_date = datetime.strptime(date_part, "%d.%m.%Y")
                        if email_date < three_days_ago:
                            continue
                    except (ValueError, IndexError):
                        pass  # Если не можем распарсить дату - пропускаем проверку

                # Пропускаем заблокированные и требующие авторизацию (недоступны для выдачи)
                if status.lower() in ("блок", "block", "авторизация", "auth"):
                    continue

                # Парсим ресурсы, на которых уже использовалась
                used_resources = set()
                if resources_str:
                    used_resources = set(r.strip().lower() for r in resources_str.split(",") if r.strip())

                # Проверяем, что хотя бы один целевой ресурс ещё не использовался
                available_for = target_set - used_resources
                if not available_for:
                    continue

                found_emails.append(EconomyEmail(
                    login=login,
                    password=password,
                    extra_info=extra_info,
                    region=email_region.strip(),  # Сохраняем реальный регион почты
                    row_index=idx,
                    used_for=used_resources,
                ))

            logger.info(f"Found {len(found_emails)} ECONOMY emails for {email_resource.value}")
            return found_emails

        except Exception as e:
            logger.error(f"Error finding ECONOMY emails: {e}")
            return []

    # ==================== ВЫДАЧА ====================

    def _extract_region_emails(self, buffer_key: str, region: str, quantity: int) -> List[CachedEmail]:
        """Извлечь почты конкретного региона из буфера"""
        available = self._available.get(buffer_key, deque())
        extracted = []
        remaining = deque()

        for email in available:
            if email.region == region and len(extracted) < quantity:
                extracted.append(email)
            else:
                remaining.append(email)

        self._available[buffer_key] = remaining
        return extracted

    async def get_new_emails(
        self,
        email_resource: EmailResource,
        email_type: EmailType,
        region: str,
        target_resources: List[str],
        quantity: int,
        employee_stage: str,
    ) -> List[Dict[str, Any]]:
        """Получить НОВЫЕ почты из базы"""
        buffer_key = self._get_buffer_key(email_resource, email_type)
        issue_lock = await self._get_lock(self._issue_locks, buffer_key)

        async with issue_lock:
            # Считаем сколько почт этого региона в буфере
            region_count = self._count_region_emails(buffer_key, region)

            # Если не хватает — загружаем
            if region_count < quantity:
                await self._load_new_emails(email_resource, email_type, region)

            # Извлекаем почты нужного региона из буфера
            region_emails = self._extract_region_emails(buffer_key, region, quantity)

            # Переносим в pending
            result = []
            for cached_email in region_emails:
                email_id = f"email_{uuid.uuid4().hex[:12]}"

                pending = PendingEmail(
                    email_id=email_id,
                    email_resource=email_resource,
                    email_type=email_type,
                    email_mode=EmailMode.NEW,
                    login=cached_email.login,
                    password=cached_email.password,
                    extra_info=cached_email.extra_info,
                    region=region,
                    target_resources=target_resources,
                    employee_stage=employee_stage,
                )
                self._pending[email_id] = pending

                result.append({
                    "email_id": email_id,
                    "login": cached_email.login,
                    "password": cached_email.password,
                    "extra_info": cached_email.extra_info,
                    "region": region,
                    "target_resources": target_resources,
                })

            # Триггер пополнения если мало осталось почт этого региона
            remaining_region_count = self._count_region_emails(buffer_key, region)
            if remaining_region_count < REFILL_THRESHOLD:
                asyncio.create_task(self._background_refill(email_resource, email_type, region))

            return result

    async def get_economy_emails(
        self,
        email_resource: EmailResource,
        email_type: EmailType,
        region: str,
        target_resources: List[str],
        quantity: int,
        employee_stage: str,
    ) -> List[Dict[str, Any]]:
        """Получить ЭКОНОМ почты из выданных"""
        # Для эконом режима не кэшируем - всегда свежие данные
        found = await self._find_economy_emails(
            email_resource=email_resource,
            email_type=email_type,
            region=region,
            target_resources=target_resources,
            quantity=quantity,
        )

        result = []
        for economy_email in found:
            email_id = f"email_{uuid.uuid4().hex[:12]}"

            pending = PendingEmail(
                email_id=email_id,
                email_resource=email_resource,
                email_type=email_type,
                email_mode=EmailMode.ECONOMY,
                login=economy_email.login,
                password=economy_email.password,
                extra_info=economy_email.extra_info,
                region=region,
                target_resources=target_resources,
                employee_stage=employee_stage,
                issued_row_index=economy_email.row_index,  # Сохраняем для обновления
            )
            self._pending[email_id] = pending

            result.append({
                "email_id": email_id,
                "login": economy_email.login,
                "password": economy_email.password,
                "extra_info": economy_email.extra_info,
                "region": region,
                "target_resources": target_resources,
                "already_used_for": list(economy_email.used_for),
            })

        return result

    async def _background_refill(self, email_resource: EmailResource, email_type: EmailType, region: str) -> None:
        """Фоновое пополнение кэша для режима "Новая" """
        try:
            await self._load_new_emails(email_resource, email_type, region)
        except Exception as e:
            logger.error(f"Background refill error: {e}")

    # ==================== FEEDBACK ====================

    def confirm_email(self, email_id: str, status: str) -> bool:
        """
        Подтвердить почту (мгновенно).
        - Для режима "Новая": добавляем в буфер записи
        - Для режима "Эконом": добавляем в буфер обновления
        """
        pending = self._pending.pop(email_id, None)
        if not pending:
            logger.warning(f"Email {email_id} not found in pending")
            return False

        buffer_key = self._get_buffer_key(pending.email_resource, pending.email_type)

        confirmed = ConfirmedEmail(
            email_resource=pending.email_resource,
            email_type=pending.email_type,
            email_mode=pending.email_mode,
            login=pending.login,
            password=pending.password,
            extra_info=pending.extra_info,
            region=pending.region,
            target_resources=pending.target_resources,
            employee_stage=pending.employee_stage,
            status=status,
            issued_row_index=pending.issued_row_index,
        )

        if pending.email_mode == EmailMode.NEW:
            # Для "Новая" - добавляем в буфер записи
            if buffer_key not in self._write_buffer:
                self._write_buffer[buffer_key] = []
            self._write_buffer[buffer_key].append(confirmed)
        else:
            # Для "Эконом" - добавляем в буфер обновления
            if buffer_key not in self._update_buffer:
                self._update_buffer[buffer_key] = []
            self._update_buffer[buffer_key].append(confirmed)

        logger.debug(f"Email {email_id} confirmed with status {status}, mode={pending.email_mode.value}")
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

        # Финальный flush буферов
        await self._flush_write_buffer()
        await self._flush_update_buffer()

        # Финальное сохранение состояния
        self.save_state()
        logger.info("Email cache shutdown complete")

    async def _write_buffer_loop(self) -> None:
        """Цикл записи буферов в Sheets"""
        while True:
            try:
                await asyncio.sleep(WRITE_BUFFER_INTERVAL)
                await self._flush_write_buffer()
                await self._flush_update_buffer()
            except asyncio.CancelledError:
                await self._flush_write_buffer()
                await self._flush_update_buffer()
                break
            except Exception as e:
                logger.error(f"Email write buffer error: {e}")

    async def _flush_write_buffer(self) -> None:
        """Записать новые почты в таблицы выдачи"""
        for buffer_key, emails in list(self._write_buffer.items()):
            if not emails:
                continue

            to_write = emails.copy()
            self._write_buffer[buffer_key] = []

            if not to_write:
                continue

            # Получаем email_resource и email_type из первого email
            first_email = to_write[0]
            email_resource = first_email.email_resource
            email_type = first_email.email_type

            sheet_name = get_issued_sheet_name(email_resource, email_type)

            try:
                gc = await agcm.authorize()
                spreadsheet = await gc.open_by_key(settings.SPREADSHEET_ISSUED)

                try:
                    worksheet = await spreadsheet.worksheet(sheet_name)
                except Exception:
                    worksheet = await spreadsheet.add_worksheet(
                        title=sheet_name, rows=1000, cols=10
                    )
                    await worksheet.update("A1:H1", [[
                        "Дата выдачи", "Логин", "Пароль", "Доп инфа", "Регион", "Employee", "Статус", "Ресурсы"
                    ]])

                current_date = datetime.now().strftime("%d.%m.%y")
                rows = []
                status_colors = []

                for email in to_write:
                    try:
                        status_enum = AccountStatus(email.status)
                        status_text = status_enum.table_name
                        bg_color = status_enum.background_color
                    except ValueError:
                        status_text = email.status
                        bg_color = None

                    resources_str = ",".join(email.target_resources)

                    rows.append([
                        current_date,
                        email.login,
                        email.password,
                        email.extra_info,
                        email.region,
                        email.employee_stage,
                        status_text,
                        resources_str,
                    ])
                    status_colors.append(bg_color)

                if rows:
                    all_values = await worksheet.get_all_values()
                    last_filled_row = 1
                    for i, row in enumerate(all_values, start=1):
                        if row and any(cell.strip() for cell in row if cell):
                            last_filled_row = i

                    start_row = last_filled_row + 1
                    end_row = start_row + len(rows) - 1
                    range_str = f"A{start_row}:H{end_row}"

                    await worksheet.update(range_str, rows, value_input_option="USER_ENTERED")

                    # Форматируем статусы
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

                logger.info(f"Flushed {len(to_write)} NEW emails to '{sheet_name}'")

            except Exception as e:
                logger.error(f"Error flushing write buffer for {buffer_key}: {e}")
                if buffer_key not in self._write_buffer:
                    self._write_buffer[buffer_key] = []
                self._write_buffer[buffer_key].extend(to_write)

    async def _flush_update_buffer(self) -> None:
        """Обновить ресурсы для эконом-почт в таблице выданных"""
        for buffer_key, emails in list(self._update_buffer.items()):
            if not emails:
                continue

            to_update = emails.copy()
            self._update_buffer[buffer_key] = []

            if not to_update:
                continue

            # Получаем email_resource и email_type из первого email
            first_email = to_update[0]
            email_resource = first_email.email_resource
            email_type = first_email.email_type

            sheet_name = get_issued_sheet_name(email_resource, email_type)

            try:
                gc = await agcm.authorize()
                spreadsheet = await gc.open_by_key(settings.SPREADSHEET_ISSUED)

                try:
                    worksheet = await spreadsheet.worksheet(sheet_name)
                except Exception as e:
                    logger.error(f"Sheet '{sheet_name}' not found for update: {e}")
                    continue

                # Получаем текущие данные
                all_values = await worksheet.get_all_values()

                # Обновляем каждую строку
                for email in to_update:
                    if email.issued_row_index is None:
                        continue

                    row_idx = email.issued_row_index
                    if row_idx > len(all_values):
                        continue

                    current_row = all_values[row_idx - 1]  # 0-based index

                    # Получаем текущие значения
                    current_region = current_row[4] if len(current_row) > 4 else ""
                    current_stage = current_row[5] if len(current_row) > 5 else ""
                    current_resources = current_row[7] if len(current_row) > 7 else ""

                    # Объединяем регионы (без дублей)
                    old_regions = set(r.strip() for r in current_region.split(",") if r.strip())
                    old_regions.add(email.region)
                    regions_str = ",".join(sorted(old_regions))

                    # Объединяем стейджи (без дублей)
                    old_stages = set(s.strip() for s in current_stage.split(",") if s.strip())
                    old_stages.add(email.employee_stage)
                    stages_str = ",".join(sorted(old_stages))

                    # Объединяем ресурсы
                    old_resources = set(r.strip().lower() for r in current_resources.split(",") if r.strip())
                    new_resources = set(email.target_resources)
                    all_resources = old_resources | new_resources
                    resources_str = ",".join(sorted(all_resources))

                    # Batch update: E (регион), F (стейдж), H (ресурсы)
                    await worksheet.update(f"E{row_idx}", [[regions_str]], value_input_option="USER_ENTERED")
                    await worksheet.update(f"F{row_idx}", [[stages_str]], value_input_option="USER_ENTERED")
                    await worksheet.update(f"H{row_idx}", [[resources_str]], value_input_option="USER_ENTERED")

                logger.info(f"Updated {len(to_update)} ECONOMY emails in '{sheet_name}'")

            except Exception as e:
                logger.error(f"Error flushing update buffer for {domain_key}: {e}")
                if domain_key not in self._update_buffer:
                    self._update_buffer[domain_key] = []
                self._update_buffer[domain_key].extend(to_update)

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
                "update_buffer": {},
                "saved_at": time.time(),
            }

            # Сохраняем available
            for key, emails in self._available.items():
                state["available"][key] = [
                    {
                        "login": e.login,
                        "password": e.password,
                        "extra_info": e.extra_info,
                        "region": e.region,
                        "row_index": e.row_index,
                    }
                    for e in emails
                ]

            # Сохраняем pending
            for email_id, pending in self._pending.items():
                state["pending"][email_id] = {
                    "email_resource": pending.email_resource.value,
                    "email_type": pending.email_type.value,
                    "email_mode": pending.email_mode.value,
                    "login": pending.login,
                    "password": pending.password,
                    "extra_info": pending.extra_info,
                    "region": pending.region,
                    "target_resources": pending.target_resources,
                    "employee_stage": pending.employee_stage,
                    "issued_at": pending.issued_at,
                    "issued_row_index": pending.issued_row_index,
                }

            # Сохраняем write_buffer
            for key, emails in self._write_buffer.items():
                state["write_buffer"][key] = [
                    {
                        "email_resource": e.email_resource.value,
                        "email_type": e.email_type.value,
                        "email_mode": e.email_mode.value,
                        "login": e.login,
                        "password": e.password,
                        "extra_info": e.extra_info,
                        "region": e.region,
                        "target_resources": e.target_resources,
                        "employee_stage": e.employee_stage,
                        "status": e.status,
                        "issued_row_index": e.issued_row_index,
                    }
                    for e in emails
                ]

            # Сохраняем update_buffer
            for key, emails in self._update_buffer.items():
                state["update_buffer"][key] = [
                    {
                        "email_resource": e.email_resource.value,
                        "email_type": e.email_type.value,
                        "email_mode": e.email_mode.value,
                        "login": e.login,
                        "password": e.password,
                        "extra_info": e.extra_info,
                        "region": e.region,
                        "target_resources": e.target_resources,
                        "employee_stage": e.employee_stage,
                        "status": e.status,
                        "issued_row_index": e.issued_row_index,
                    }
                    for e in emails
                ]

            with open(EMAIL_CACHE_STATE_FILE, "w", encoding="utf-8") as f:
                json.dump(state, f, ensure_ascii=False, indent=2)

            total = (
                sum(len(v) for v in state["available"].values()) +
                len(state["pending"]) +
                sum(len(v) for v in state["write_buffer"].values()) +
                sum(len(v) for v in state["update_buffer"].values())
            )
            logger.debug(f"Email state saved: {total} items")

        except Exception as e:
            logger.error(f"Error saving email state: {e}")

    def _migrate_key(self, old_key: str) -> str:
        """
        Мигрировать старый ключ в новый формат.

        Буферы:
        - gmail_any — любые гугл почты (без изменений)
        - gmail_gmail_domain — только @gmail.com (без изменений)
        - rambler — один объединённый буфер

        Миграция:
        - gmail_any → gmail_any (без изменений)
        - gmail_gmail_domain → gmail_gmail_domain (без изменений)
        - rambler_none → rambler
        - rambler_545 (и другие rambler_*) → rambler
        """
        # Gmail ключи остаются без изменений
        if old_key in ("gmail_any", "gmail_gmail_domain"):
            return old_key

        # Rambler — объединяем все в один буфер
        if old_key == "rambler" or old_key.startswith("rambler_"):
            return "rambler"

        # Неизвестный формат — возвращаем как есть
        logger.warning(f"Unknown key format during migration: {old_key}")
        return old_key

    def _email_type_from_key(self, buffer_key: str) -> EmailType:
        """Определить EmailType из ключа буфера (для миграции старых данных)"""
        if buffer_key == "gmail_any":
            return EmailType.ANY
        elif buffer_key == "gmail_gmail_domain":
            return EmailType.GMAIL_DOMAIN
        else:
            return EmailType.NONE  # rambler и другие

    def load_state(self) -> bool:
        """Загрузить состояние кэша из файла"""
        if not EMAIL_CACHE_STATE_FILE.exists():
            logger.info("No saved email state found")
            return False

        try:
            with open(EMAIL_CACHE_STATE_FILE, "r", encoding="utf-8") as f:
                state = json.load(f)

            # Загружаем available (с миграцией старых ключей)
            for old_key, emails_data in state.get("available", {}).items():
                # Мигрируем ключ в новый формат
                new_key = self._migrate_key(old_key)

                if new_key not in self._available:
                    self._available[new_key] = deque()

                for data in emails_data:
                    self._available[new_key].append(CachedEmail(
                        login=data["login"],
                        password=data["password"],
                        extra_info=data.get("extra_info", ""),
                        region=data.get("region", ""),
                        row_index=data["row_index"],
                    ))

            # Загружаем pending
            for email_id, data in state.get("pending", {}).items():
                # Определяем email_type (для обратной совместимости)
                email_type_str = data.get("email_type", "any")
                try:
                    email_type = EmailType(email_type_str)
                except ValueError:
                    email_type = EmailType.ANY

                self._pending[email_id] = PendingEmail(
                    email_id=email_id,
                    email_resource=EmailResource(data["email_resource"]),
                    email_type=email_type,
                    email_mode=EmailMode(data.get("email_mode", "new")),
                    login=data["login"],
                    password=data["password"],
                    extra_info=data.get("extra_info", ""),
                    region=data.get("region", ""),
                    target_resources=data.get("target_resources", []),
                    employee_stage=data["employee_stage"],
                    issued_at=data["issued_at"],
                    issued_row_index=data.get("issued_row_index"),
                )

            # Загружаем write_buffer (с миграцией старых ключей)
            for old_key, emails_data in state.get("write_buffer", {}).items():
                new_key = self._migrate_key(old_key)
                if new_key not in self._write_buffer:
                    self._write_buffer[new_key] = []
                for data in emails_data:
                    # Определяем email_type из данных или из ключа
                    email_type_str = data.get("email_type")
                    if email_type_str:
                        email_type = EmailType(email_type_str)
                    else:
                        email_type = self._email_type_from_key(new_key)

                    self._write_buffer[new_key].append(ConfirmedEmail(
                        email_resource=EmailResource(data["email_resource"]),
                        email_type=email_type,
                        email_mode=EmailMode(data.get("email_mode", "new")),
                        login=data["login"],
                        password=data["password"],
                        extra_info=data.get("extra_info", ""),
                        region=data.get("region", ""),
                        target_resources=data.get("target_resources", []),
                        employee_stage=data["employee_stage"],
                        status=data["status"],
                        issued_row_index=data.get("issued_row_index"),
                    ))

            # Загружаем update_buffer (с миграцией старых ключей)
            for old_key, emails_data in state.get("update_buffer", {}).items():
                new_key = self._migrate_key(old_key)
                if new_key not in self._update_buffer:
                    self._update_buffer[new_key] = []
                for data in emails_data:
                    # Определяем email_type из данных или из ключа
                    email_type_str = data.get("email_type")
                    if email_type_str:
                        email_type = EmailType(email_type_str)
                    else:
                        email_type = self._email_type_from_key(new_key)

                    self._update_buffer[new_key].append(ConfirmedEmail(
                        email_resource=EmailResource(data["email_resource"]),
                        email_type=email_type,
                        email_mode=EmailMode(data.get("email_mode", "economy")),
                        login=data["login"],
                        password=data["password"],
                        extra_info=data.get("extra_info", ""),
                        region=data.get("region", ""),
                        target_resources=data.get("target_resources", []),
                        employee_stage=data["employee_stage"],
                        status=data["status"],
                        issued_row_index=data.get("issued_row_index"),
                    ))

            total = (
                sum(len(v) for v in self._available.values()) +
                len(self._pending) +
                sum(len(v) for v in self._write_buffer.values()) +
                sum(len(v) for v in self._update_buffer.values())
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
        """Предзагрузить почты при старте"""
        # Сначала пробуем загрузить сохранённое состояние
        self.load_state()
        logger.info("Email preload complete (state loaded from file)")

    def get_stats(self) -> Dict[str, Dict[str, int]]:
        """Статистика кэша в формате {buffer_key: {available, pending, write_buffer}}"""
        # Собираем все ключи буферов (gmail_any, gmail_gmail_domain, rambler)
        all_keys = set()
        all_keys.update(self._available.keys())
        all_keys.update(self._write_buffer.keys())
        all_keys.update(self._update_buffer.keys())

        # Считаем pending по ключам буферов
        pending_by_key: Dict[str, int] = {}
        for email_id, pending in self._pending.items():
            buffer_key = self._get_buffer_key(pending.email_resource, pending.email_type)
            pending_by_key[buffer_key] = pending_by_key.get(buffer_key, 0) + 1
            all_keys.add(buffer_key)

        stats = {}
        for key in all_keys:
            available_count = len(self._available.get(key, []))
            pending_count = pending_by_key.get(key, 0)
            write_buffer_count = len(self._write_buffer.get(key, []))
            # update_buffer учитываем вместе с write_buffer для отображения
            update_buffer_count = len(self._update_buffer.get(key, []))

            stats[key] = {
                "available": available_count,
                "pending": pending_count,
                "write_buffer": write_buffer_count + update_buffer_count,
            }

        return stats

    def clear_cache(self, buffer_key: str = None, clear_type: str = "all") -> Dict[str, int]:
        """
        Очистить кэш почт.
        buffer_key: ключ буфера (gmail_any/gmail_gmail_domain/rambler) или None для всех
        """
        cleared = {"available": 0, "pending": 0, "write_buffer": 0, "update_buffer": 0}

        if clear_type in ("available", "all"):
            if buffer_key:
                if buffer_key in self._available:
                    cleared["available"] = len(self._available[buffer_key])
                    self._available[buffer_key] = deque()
            else:
                for k in list(self._available.keys()):
                    cleared["available"] += len(self._available[k])
                    self._available[k] = deque()

        if clear_type in ("pending", "all"):
            if buffer_key:
                to_remove = [
                    email_id for email_id, p in self._pending.items()
                    if self._get_buffer_key(p.email_resource, p.email_type) == buffer_key
                ]
                for email_id in to_remove:
                    del self._pending[email_id]
                cleared["pending"] = len(to_remove)
            else:
                cleared["pending"] = len(self._pending)
                self._pending.clear()

        if clear_type in ("write_buffer", "all"):
            if buffer_key:
                if buffer_key in self._write_buffer:
                    cleared["write_buffer"] = len(self._write_buffer[buffer_key])
                    self._write_buffer[buffer_key] = []
            else:
                for k in list(self._write_buffer.keys()):
                    cleared["write_buffer"] += len(self._write_buffer[k])
                    self._write_buffer[k] = []

        if clear_type in ("update_buffer", "all"):
            if buffer_key:
                if buffer_key in self._update_buffer:
                    cleared["update_buffer"] = len(self._update_buffer[buffer_key])
                    self._update_buffer[buffer_key] = []
            else:
                for k in list(self._update_buffer.keys()):
                    cleared["update_buffer"] += len(self._update_buffer[k])
                    self._update_buffer[k] = []

        self.save_state()
        logger.info(f"Email cache cleared: buffer_key={buffer_key}, type={clear_type}, cleared={cleared}")
        return cleared

    def clear_cache_by_domain(self, buffer_key: str = None, clear_type: str = "all") -> Dict[str, int]:
        """
        Очистить кэш по ключу буфера (gmail_any/gmail_gmail_domain/rambler).
        Алиас для clear_cache для обратной совместимости с admin.py.
        """
        return self.clear_cache(buffer_key=buffer_key, clear_type=clear_type)

    async def release_to_sheets(self, buffer_key: str = None) -> Dict[str, int]:
        """
        Вернуть почты из available обратно в таблицу базы.

        Args:
            buffer_key: Ключ буфера (gmail_any/gmail_gmail_domain/rambler) или None для всех

        Returns:
            {"available": количество_возвращённых}
        """
        released = {"available": 0}

        # Собираем ключи буферов для освобождения
        keys_to_release = []
        if buffer_key:
            if buffer_key in self._available:
                keys_to_release.append(buffer_key)
        else:
            keys_to_release = list(self._available.keys())

        for key in keys_to_release:
            emails = list(self._available.get(key, []))
            if not emails:
                continue

            # Определяем email_resource и email_type из ключа буфера
            if key == "gmail_any":
                email_resource = EmailResource.GMAIL
                email_type = EmailType.ANY
            elif key == "gmail_gmail_domain":
                email_resource = EmailResource.GMAIL
                email_type = EmailType.GMAIL_DOMAIN
            elif key == "rambler":
                email_resource = EmailResource.RAMBLER
                email_type = EmailType.NONE
            else:
                logger.error(f"Unknown buffer key: {key}")
                continue

            # Получаем лист базы
            sheet_name = get_base_sheet_name(email_resource, email_type)

            try:
                gc = await agcm.authorize()
                spreadsheet = await gc.open_by_key(settings.SPREADSHEET_ACCOUNTS)
                worksheet = await spreadsheet.worksheet(sheet_name)

                # Формируем строки для вставки (дата текущая + данные)
                current_date = datetime.now().strftime("%d.%m.%y")

                rows_to_insert = []
                for email in emails:
                    # Формат: дата | логин | пароль | доп_инфо | регион
                    row = [
                        current_date,
                        email.login,
                        email.password,
                        email.extra_info or "",
                        email.region,
                    ]
                    rows_to_insert.append(row)

                if rows_to_insert:
                    # Вставляем в начало (после заголовка)
                    await worksheet.insert_rows(rows_to_insert, row=2)
                    released["available"] += len(rows_to_insert)
                    logger.info(f"Released {len(rows_to_insert)} emails to {sheet_name}")

                # Очищаем available для этого ключа
                self._available[key] = deque()

            except Exception as e:
                logger.error(f"Error releasing emails for {key}: {e}")

        self.save_state()
        return released


# Глобальный кэш
email_cache = EmailCache()


class EmailService:
    """Бизнес-логика выдачи почт с умным распределением"""

    async def issue_emails(
        self,
        email_resource: EmailResource,
        email_type: EmailType,
        region: str,
        email_mode: EmailMode,
        target_resources: List[str],
        quantity: int,
        employee_stage: str,
    ) -> List[Dict[str, Any]]:
        """
        Выдать почты.

        Args:
            email_resource: Домен (Gmail/Рамблер)
            email_type: Тип Gmail (any/gmail_domain/none)
            region: Регион
            email_mode: Режим (Новая/Эконом)
            target_resources: Целевые ресурсы
            quantity: Количество
            employee_stage: Стадия сотрудника

        Returns:
            Список выданных почт
        """
        if email_mode == EmailMode.NEW:
            return await email_cache.get_new_emails(
                email_resource=email_resource,
                email_type=email_type,
                region=region,
                target_resources=target_resources,
                quantity=quantity,
                employee_stage=employee_stage,
            )
        else:
            return await email_cache.get_economy_emails(
                email_resource=email_resource,
                email_type=email_type,
                region=region,
                target_resources=target_resources,
                quantity=quantity,
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
