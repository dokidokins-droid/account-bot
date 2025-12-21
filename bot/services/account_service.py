import asyncio
import json
import logging
import os
import time
import uuid
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field, asdict
from collections import deque
from pathlib import Path

from bot.services.sheets_service import sheets_service
from bot.services.fallback_storage import fallback_storage
from bot.models.enums import Resource, Gender

logger = logging.getLogger(__name__)

# Файл для сохранения состояния кэша
CACHE_STATE_FILE = Path(__file__).parent.parent.parent / "data" / "cache_state.json"

# Сколько аккаунтов загружать за раз
LOAD_BATCH_SIZE = 15
# Минимум доступных для выдачи (не pending) для триггера пополнения
REFILL_THRESHOLD = 5
# Интервал записи в таблицу выданных (секунды)
WRITE_BUFFER_INTERVAL = 30
# Автоподтверждение через 10 минут
AUTO_CONFIRM_TIMEOUT = 600
# Интервал автосохранения состояния (секунды)
STATE_SAVE_INTERVAL = 60


@dataclass
class PendingAccount:
    """Аккаунт, выданный пользователю, ждёт feedback"""
    account_id: str
    resource: Resource
    gender: Gender
    region: str
    employee_stage: str
    account: Any
    issued_at: float = field(default_factory=time.time)


@dataclass
class ConfirmedAccount:
    """Аккаунт с feedback, ждёт записи в таблицу"""
    resource: Resource
    gender: Gender
    account_data: List[str]
    region: str
    employee_stage: str
    status: str


class AccountCache:
    """
    Двухуровневый кэш аккаунтов:
    - available: готовы к выдаче (уже удалены из "Базы")
    - pending: выданы, ждут feedback
    - write_buffer: подтверждены, ждут записи в "Выданные"
    """

    def __init__(self):
        # Доступные для выдачи {key: deque of accounts}
        self._available: Dict[str, deque] = {}
        # Выданные, ждут feedback {account_id: PendingAccount}
        self._pending: Dict[str, PendingAccount] = {}
        # Буфер записи {key: list of ConfirmedAccount}
        self._write_buffer: Dict[str, List[ConfirmedAccount]] = {}

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

    def _get_key(self, resource: Resource, gender: Gender) -> str:
        return f"{resource.value}_{gender.value}"

    async def _get_lock(self, locks_dict: Dict[str, asyncio.Lock], key: str) -> asyncio.Lock:
        """Потокобезопасное получение блокировки для ключа"""
        async with self._meta_lock:
            if key not in locks_dict:
                locks_dict[key] = asyncio.Lock()
            return locks_dict[key]

    def _get_available_count(self, key: str) -> int:
        """Количество доступных для выдачи (не pending)"""
        return len(self._available.get(key, deque()))

    # ==================== ЗАГРУЗКА ====================

    async def _load_accounts(self, resource: Resource, gender: Gender, force: bool = False) -> int:
        """
        Загрузить аккаунты из Sheets → удалить из "Базы" → добавить в available.
        Возвращает количество загруженных.
        force=True пропускает проверку достаточности.
        """
        key = self._get_key(resource, gender)

        # Проверяем, нужна ли загрузка
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

            # Повторная проверка после получения блокировки
            current_available = len(self._available.get(key, deque()))
            if not force and current_available >= LOAD_BATCH_SIZE:
                return 0

            self._loading[key] = True
            try:
                logger.info(f"Loading accounts for {key} (current: {current_available})...")

                # Получаем аккаунты из Sheets
                accounts = await sheets_service.get_accounts(resource, gender, LOAD_BATCH_SIZE)

                if not accounts:
                    logger.info(f"No accounts available in Sheets for {key}")
                    return 0

                # Удаляем из исходной таблицы (batch)
                row_indices = [acc.row_index for acc in accounts]
                await sheets_service.delete_account_rows_batch(resource, gender, row_indices)

                # Добавляем в available кэш
                if key not in self._available:
                    self._available[key] = deque()

                for acc in accounts:
                    self._available[key].append(acc)

                logger.info(f"Loaded {len(accounts)} accounts for {key}, available: {len(self._available[key])}")
                return len(accounts)

            except Exception as e:
                logger.error(f"Error loading accounts for {key}: {e}")
                return 0
            finally:
                self._loading[key] = False

    # ==================== ВЫДАЧА ====================

    async def get_accounts(
        self,
        resource: Resource,
        gender: Gender,
        quantity: int,
        region: str,
        employee_stage: str,
    ) -> List[Dict[str, Any]]:
        """Получить аккаунты мгновенно из кэша"""
        key = self._get_key(resource, gender)
        issue_lock = await self._get_lock(self._issue_locks, key)

        async with issue_lock:
            available = self._available.get(key, deque())

            # Если не хватает — загружаем
            if len(available) < quantity:
                await self._load_accounts(resource, gender)
                available = self._available.get(key, deque())

            # Забираем из available → переносим в pending
            result = []
            for _ in range(min(quantity, len(available))):
                if not available:
                    break

                account = available.popleft()
                account_id = f"acc_{uuid.uuid4().hex[:12]}"

                pending = PendingAccount(
                    account_id=account_id,
                    resource=resource,
                    gender=gender,
                    region=region,
                    employee_stage=employee_stage,
                    account=account,
                )
                self._pending[account_id] = pending

                result.append({
                    "account": account,
                    "account_id": account_id,
                })

            # Триггер пополнения если мало осталось
            if len(available) < REFILL_THRESHOLD:
                asyncio.create_task(self._background_refill(resource, gender))

            return result

    async def _background_refill(self, resource: Resource, gender: Gender) -> None:
        """Фоновое пополнение кэша"""
        try:
            await self._load_accounts(resource, gender)
        except Exception as e:
            logger.error(f"Background refill error: {e}")

    # ==================== FEEDBACK ====================

    def confirm_account(self, account_id: str, status: str) -> bool:
        """
        Подтвердить аккаунт (мгновенно).
        Перемещает из pending в write_buffer.
        """
        pending = self._pending.pop(account_id, None)
        if not pending:
            logger.warning(f"Account {account_id} not found in pending")
            return False

        key = self._get_key(pending.resource, pending.gender)

        # Готовим данные для записи
        account_data = self._get_account_data_list(pending.resource, pending.account)

        confirmed = ConfirmedAccount(
            resource=pending.resource,
            gender=pending.gender,
            account_data=account_data,
            region=pending.region,
            employee_stage=pending.employee_stage,
            status=status,
        )

        # Добавляем в буфер записи
        if key not in self._write_buffer:
            self._write_buffer[key] = []
        self._write_buffer[key].append(confirmed)

        logger.debug(f"Account {account_id} confirmed with status {status}, added to write buffer")
        return True

    def _get_account_data_list(self, resource: Resource, account) -> List[str]:
        """Данные аккаунта как список"""
        if resource == Resource.VK:
            return [account.login, account.password]
        elif resource == Resource.MAMBA:
            return [account.login, account.password, account.email_password, account.confirmation_link]
        elif resource == Resource.OK:
            return [account.login, account.password]
        elif resource == Resource.GMAIL:
            return [account.login, account.password, account.backup_email or ""]
        return []

    # ==================== ФОНОВЫЕ ЗАДАЧИ ====================

    async def start_background_tasks(self) -> None:
        """Запустить фоновые задачи"""
        if self._write_task is None or self._write_task.done():
            self._write_task = asyncio.create_task(self._write_buffer_loop())
            logger.info("Write buffer task started")

        if self._auto_confirm_task is None or self._auto_confirm_task.done():
            self._auto_confirm_task = asyncio.create_task(self._auto_confirm_loop())
            logger.info("Auto-confirm task started")

        if self._save_task is None or self._save_task.done():
            self._save_task = asyncio.create_task(self._save_state_loop())
            logger.info("State save task started")

    async def shutdown(self) -> None:
        """Корректное завершение — сохраняем всё"""
        logger.info("Shutting down account cache...")

        # Останавливаем задачи
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
        logger.info("Account cache shutdown complete")

    async def _write_buffer_loop(self) -> None:
        """Цикл записи буфера в Sheets"""
        while True:
            try:
                await asyncio.sleep(WRITE_BUFFER_INTERVAL)
                await self._flush_write_buffer()
            except asyncio.CancelledError:
                # При остановке — финальный flush
                await self._flush_write_buffer()
                break
            except Exception as e:
                logger.error(f"Write buffer error: {e}")

    async def _flush_write_buffer(self) -> None:
        """Записать буфер в таблицу "Выданные" """
        for key, accounts in list(self._write_buffer.items()):
            if not accounts:
                continue

            # Забираем и очищаем
            to_write = accounts.copy()
            self._write_buffer[key] = []

            if not to_write:
                continue

            # Группируем по resource+gender (уже сгруппировано по key)
            resource = to_write[0].resource
            gender = to_write[0].gender

            try:
                batch_data = [
                    (acc.account_data, acc.region, acc.employee_stage, acc.status)
                    for acc in to_write
                ]
                await sheets_service.add_issued_accounts_batch(resource, gender, batch_data)
                logger.info(f"Flushed {len(to_write)} accounts for {key} to Sheets")
            except Exception as e:
                logger.error(f"Error flushing write buffer for {key}: {e}")
                # Возвращаем обратно в буфер
                if key not in self._write_buffer:
                    self._write_buffer[key] = []
                self._write_buffer[key].extend(to_write)

    async def _auto_confirm_loop(self) -> None:
        """Автоподтверждение просроченных аккаунтов"""
        while True:
            try:
                await asyncio.sleep(60)
                await self._process_expired_pending()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Auto-confirm error: {e}")

    async def _process_expired_pending(self) -> None:
        """Подтвердить просроченные pending как "good" """
        now = time.time()
        expired = [
            acc_id for acc_id, pending in list(self._pending.items())
            if now - pending.issued_at > AUTO_CONFIRM_TIMEOUT
        ]

        for account_id in expired:
            logger.info(f"Auto-confirming expired account {account_id}")
            self.confirm_account(account_id, "good")

    # ==================== ПЕРСИСТЕНТНОСТЬ ====================

    def _account_to_dict(self, account) -> Dict[str, Any]:
        """Сериализация аккаунта в dict"""
        return {
            "login": account.login,
            "password": account.password,
            "row_index": account.row_index,
            # Дополнительные поля для разных типов
            "email_password": getattr(account, "email_password", None),
            "confirmation_link": getattr(account, "confirmation_link", None),
            "backup_email": getattr(account, "backup_email", None),
        }

    def _dict_to_account(self, resource: Resource, data: Dict[str, Any]):
        """Десериализация dict в аккаунт"""
        from bot.models.account import VKAccount, MambaAccount, OKAccount, GmailAccount

        if resource == Resource.VK:
            return VKAccount(login=data["login"], password=data["password"], row_index=data["row_index"])
        elif resource == Resource.MAMBA:
            return MambaAccount(
                login=data["login"], password=data["password"], row_index=data["row_index"],
                email_password=data.get("email_password", ""),
                confirmation_link=data.get("confirmation_link", ""),
            )
        elif resource == Resource.OK:
            return OKAccount(login=data["login"], password=data["password"], row_index=data["row_index"])
        elif resource == Resource.GMAIL:
            return GmailAccount(
                login=data["login"], password=data["password"], row_index=data["row_index"],
                backup_email=data.get("backup_email"),
            )
        return None

    def save_state(self) -> None:
        """Сохранить состояние кэша в файл"""
        try:
            CACHE_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)

            state = {
                "available": {},
                "pending": {},
                "write_buffer": {},
                "saved_at": time.time(),
            }

            # Сохраняем available
            for key, accounts in self._available.items():
                resource_str, gender_str = key.split("_", 1)
                resource = Resource(resource_str)
                state["available"][key] = [self._account_to_dict(acc) for acc in accounts]

            # Сохраняем pending
            for acc_id, pending in self._pending.items():
                state["pending"][acc_id] = {
                    "resource": pending.resource.value,
                    "gender": pending.gender.value,
                    "region": pending.region,
                    "employee_stage": pending.employee_stage,
                    "account": self._account_to_dict(pending.account),
                    "issued_at": pending.issued_at,
                }

            # Сохраняем write_buffer
            for key, accounts in self._write_buffer.items():
                state["write_buffer"][key] = [
                    {
                        "resource": acc.resource.value,
                        "gender": acc.gender.value,
                        "account_data": acc.account_data,
                        "region": acc.region,
                        "employee_stage": acc.employee_stage,
                        "status": acc.status,
                    }
                    for acc in accounts
                ]

            with open(CACHE_STATE_FILE, "w", encoding="utf-8") as f:
                json.dump(state, f, ensure_ascii=False, indent=2)

            total = (
                sum(len(v) for v in state["available"].values()) +
                len(state["pending"]) +
                sum(len(v) for v in state["write_buffer"].values())
            )
            logger.debug(f"State saved: {total} items")

        except Exception as e:
            logger.error(f"Error saving state: {e}")

    def load_state(self) -> bool:
        """Загрузить состояние кэша из файла"""
        if not CACHE_STATE_FILE.exists():
            logger.info("No saved state found")
            return False

        try:
            with open(CACHE_STATE_FILE, "r", encoding="utf-8") as f:
                state = json.load(f)

            # Загружаем available
            for key, accounts_data in state.get("available", {}).items():
                resource_str, gender_str = key.split("_", 1)
                resource = Resource(resource_str)
                self._available[key] = deque()
                for acc_data in accounts_data:
                    acc = self._dict_to_account(resource, acc_data)
                    if acc:
                        self._available[key].append(acc)

            # Загружаем pending
            for acc_id, pending_data in state.get("pending", {}).items():
                resource = Resource(pending_data["resource"])
                gender = Gender(pending_data["gender"])
                account = self._dict_to_account(resource, pending_data["account"])
                if account:
                    self._pending[acc_id] = PendingAccount(
                        account_id=acc_id,
                        resource=resource,
                        gender=gender,
                        region=pending_data["region"],
                        employee_stage=pending_data["employee_stage"],
                        account=account,
                        issued_at=pending_data["issued_at"],
                    )

            # Загружаем write_buffer
            for key, accounts_data in state.get("write_buffer", {}).items():
                self._write_buffer[key] = []
                for acc_data in accounts_data:
                    self._write_buffer[key].append(ConfirmedAccount(
                        resource=Resource(acc_data["resource"]),
                        gender=Gender(acc_data["gender"]),
                        account_data=acc_data["account_data"],
                        region=acc_data["region"],
                        employee_stage=acc_data["employee_stage"],
                        status=acc_data["status"],
                    ))

            total = (
                sum(len(v) for v in self._available.values()) +
                len(self._pending) +
                sum(len(v) for v in self._write_buffer.values())
            )
            saved_at = state.get("saved_at", 0)
            age_min = (time.time() - saved_at) / 60

            logger.info(f"State loaded: {total} items (saved {age_min:.1f} min ago)")
            return True

        except Exception as e:
            logger.error(f"Error loading state: {e}")
            return False

    async def _save_state_loop(self) -> None:
        """Периодическое сохранение состояния"""
        while True:
            try:
                await asyncio.sleep(STATE_SAVE_INTERVAL)
                self.save_state()
            except asyncio.CancelledError:
                self.save_state()  # Финальное сохранение
                break
            except Exception as e:
                logger.error(f"State save error: {e}")

    # ==================== ПРЕДЗАГРУЗКА ====================

    async def preload_all(self) -> None:
        """Предзагрузить аккаунты всех типов при старте"""
        # Сначала пробуем загрузить сохранённое состояние
        state_loaded = self.load_state()

        # Проверяем, нужно ли дозагружать из Sheets
        need_load = []
        for resource in Resource:
            for gender in Gender:
                # Пропускаем неподходящие комбинации
                if resource == Resource.GMAIL and gender in (Gender.MALE, Gender.FEMALE, Gender.NONE):
                    continue
                if resource in (Resource.VK, Resource.OK) and gender != Gender.NONE:
                    continue
                if resource == Resource.MAMBA and gender in (Gender.ANY, Gender.GMAIL_DOMAIN, Gender.NONE):
                    continue

                key = self._get_key(resource, gender)
                available = len(self._available.get(key, deque()))

                if available < REFILL_THRESHOLD:
                    need_load.append((resource, gender, available))

        if not need_load:
            logger.info("All account types have enough in cache, skipping Sheets preload")
            return

        logger.info(f"Need to load {len(need_load)} account types from Sheets...")

        tasks = []
        for resource, gender, current in need_load:
            logger.info(f"  - {resource.value}_{gender.value}: {current} available")
            tasks.append(self._load_accounts(resource, gender))

        results = await asyncio.gather(*tasks, return_exceptions=True)
        total = sum(r for r in results if isinstance(r, int))
        logger.info(f"Preload complete: {total} accounts loaded from Sheets")

    def get_stats(self) -> Dict[str, Any]:
        """Статистика кэша"""
        stats = {}
        for key in set(list(self._available.keys()) + list(self._write_buffer.keys())):
            stats[key] = {
                "available": len(self._available.get(key, deque())),
                "pending": sum(1 for p in self._pending.values()
                              if self._get_key(p.resource, p.gender) == key),
                "write_buffer": len(self._write_buffer.get(key, [])),
            }
        return stats

    def clear_cache(self, key: str = None, clear_type: str = "all") -> Dict[str, int]:
        """
        Очистить кэш.

        Args:
            key: Ключ ресурса (например "vk_none") или None для всех
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
                    acc_id for acc_id, p in self._pending.items()
                    if self._get_key(p.resource, p.gender) == key
                ]
                for acc_id in to_remove:
                    del self._pending[acc_id]
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
        logger.info(f"Cache cleared: key={key}, type={clear_type}, cleared={cleared}")

        return cleared


# Глобальный кэш
account_cache = AccountCache()


class AccountService:
    """Бизнес-логика выдачи аккаунтов"""

    async def issue_accounts(
        self,
        resource: Resource,
        region: str,
        quantity: int,
        gender: Gender,
        employee_stage: str,
    ) -> List[Dict[str, Any]]:
        """Выдать аккаунты мгновенно"""
        return await account_cache.get_accounts(
            resource=resource,
            gender=gender,
            quantity=quantity,
            region=region,
            employee_stage=employee_stage,
        )

    def confirm_feedback(self, account_id: str, status: str) -> bool:
        """Подтвердить feedback (мгновенно)"""
        return account_cache.confirm_account(account_id, status)

    async def get_available_count(self, resource: Resource, gender: Gender) -> int:
        """Количество доступных аккаунтов"""
        try:
            return await sheets_service.get_accounts_count(resource, gender)
        except Exception:
            return 0


account_service = AccountService()
