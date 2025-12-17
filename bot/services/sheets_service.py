import json
import base64
import logging
import time
from typing import List, Optional, Any, Dict
from datetime import datetime

import gspread_asyncio
from google.oauth2.service_account import Credentials

from bot.config import settings
from bot.models.account import VKAccount, MambaAccount, OKAccount, GmailAccount
from bot.models.user import User
from bot.models.enums import Resource, Gender

logger = logging.getLogger(__name__)

# Время жизни кэша пользователей (5 минут)
USER_CACHE_TTL = 300


def get_creds():
    """Создание credentials для Google Sheets API"""
    creds_data = settings.GOOGLE_CREDENTIALS_JSON

    # Поддержка JSON строки или Base64
    if creds_data.startswith("{"):
        creds_dict = json.loads(creds_data)
    else:
        # Декодируем Base64
        try:
            creds_dict = json.loads(base64.b64decode(creds_data).decode())
        except Exception:
            # Путь к файлу
            with open(creds_data) as f:
                creds_dict = json.load(f)

    creds = Credentials.from_service_account_info(creds_dict)
    scoped = creds.with_scopes(
        [
            "https://spreadsheets.google.com/feeds",
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]
    )
    return scoped


# Глобальный менеджер клиента
agcm = gspread_asyncio.AsyncioGspreadClientManager(get_creds)


class SheetsService:
    """Сервис для работы с Google Sheets"""

    def __init__(self):
        # Кэш пользователей: {telegram_id: (User, timestamp)}
        self._user_cache: Dict[int, tuple[Optional[User], float]] = {}

    def _get_sheet_name(self, resource: Resource, gender: Gender) -> str:
        """Получить название листа по ресурсу и полу"""
        key = f"{resource.value}_{gender.value}"
        return settings.SHEET_NAMES.get(key, key)

    async def _get_client(self):
        """Получение авторизованного клиента"""
        return await agcm.authorize()

    def _invalidate_user_cache(self, telegram_id: int) -> None:
        """Инвалидировать кэш пользователя"""
        if telegram_id in self._user_cache:
            del self._user_cache[telegram_id]
        logger.debug(f"User cache invalidated for {telegram_id}")

    def _get_cached_user(self, telegram_id: int) -> tuple[Optional[User], bool]:
        """Получить пользователя из кэша. Возвращает (user, found_in_cache)"""
        if telegram_id in self._user_cache:
            user, timestamp = self._user_cache[telegram_id]
            if time.time() - timestamp < USER_CACHE_TTL:
                logger.debug(f"User {telegram_id} found in cache")
                return user, True
            # Кэш устарел
            del self._user_cache[telegram_id]
        return None, False

    def _cache_user(self, telegram_id: int, user: Optional[User]) -> None:
        """Сохранить пользователя в кэш"""
        self._user_cache[telegram_id] = (user, time.time())
        logger.debug(f"User {telegram_id} cached")

    # === Whitelist ===

    async def get_user_by_telegram_id(self, telegram_id: int) -> Optional[User]:
        """Получить пользователя из whitelist по Telegram ID"""
        # Проверяем кэш
        cached_user, found = self._get_cached_user(telegram_id)
        if found:
            return cached_user

        try:
            agc = await self._get_client()
            ss = await agc.open_by_key(settings.SPREADSHEET_ACCOUNTS)
            ws = await ss.worksheet(settings.SHEET_NAMES["whitelist"])

            records = await ws.get_all_records()
            for idx, record in enumerate(records, start=2):
                if record.get("telegram_id") == telegram_id:
                    user = User(
                        telegram_id=telegram_id,
                        stage=record.get("stage", ""),
                        is_approved=bool(record.get("approved", False)),
                        row_index=idx,
                    )
                    self._cache_user(telegram_id, user)
                    return user

            # Пользователь не найден - кэшируем None
            self._cache_user(telegram_id, None)
            return None
        except Exception as e:
            logger.error(f"Error getting user: {e}")
            raise

    async def add_user_to_whitelist(self, user: User) -> None:
        """Добавить пользователя в whitelist (ожидает одобрения)"""
        try:
            agc = await self._get_client()
            ss = await agc.open_by_key(settings.SPREADSHEET_ACCOUNTS)
            ws = await ss.worksheet(settings.SHEET_NAMES["whitelist"])

            await ws.append_row(
                [user.telegram_id, user.stage, user.is_approved],
                value_input_option="USER_ENTERED",
            )
            # Инвалидируем кэш
            self._invalidate_user_cache(user.telegram_id)
        except Exception as e:
            logger.error(f"Error adding user to whitelist: {e}")
            raise

    async def approve_user(self, telegram_id: int) -> bool:
        """Одобрить пользователя"""
        try:
            user = await self.get_user_by_telegram_id(telegram_id)
            if user and user.row_index:
                agc = await self._get_client()
                ss = await agc.open_by_key(settings.SPREADSHEET_ACCOUNTS)
                ws = await ss.worksheet(settings.SHEET_NAMES["whitelist"])

                # Колонка C - approved
                await ws.update_cell(user.row_index, 3, True)
                # Инвалидируем кэш
                self._invalidate_user_cache(telegram_id)
                return True
            return False
        except Exception as e:
            logger.error(f"Error approving user: {e}")
            raise

    # === Аккаунты ===

    async def get_accounts(
        self, resource: Resource, gender: Gender, quantity: int
    ) -> List[Any]:
        """Получить аккаунты из таблицы"""
        try:
            agc = await self._get_client()
            ss = await agc.open_by_key(settings.SPREADSHEET_ACCOUNTS)

            sheet_name = self._get_sheet_name(resource, gender)
            ws = await ss.worksheet(sheet_name)

            all_values = await ws.get_all_values()

            accounts = []
            # Начинаем с индекса 1 (пропускаем заголовок), row_index = 2 для первой строки данных
            for idx, row in enumerate(all_values[1:], start=2):
                if len(accounts) >= quantity:
                    break
                if not row or not row[0]:
                    continue

                account = self._parse_account(resource, row, idx)
                if account:
                    accounts.append(account)

            return accounts
        except Exception as e:
            logger.error(f"Error getting accounts: {e}")
            raise

    def _parse_account(self, resource: Resource, row: List[str], row_index: int):
        """Парсинг строки в объект аккаунта"""
        try:
            if resource == Resource.VK:
                return VKAccount(
                    login=row[0],
                    password=row[1],
                    row_index=row_index,
                )
            elif resource == Resource.MAMBA:
                return MambaAccount(
                    login=row[0],
                    password=row[1],
                    email_password=row[2] if len(row) > 2 else "",
                    confirmation_link=row[3] if len(row) > 3 else "",
                    row_index=row_index,
                )
            elif resource == Resource.OK:
                return OKAccount(
                    login=row[0],
                    password=row[1],
                    row_index=row_index,
                )
            elif resource == Resource.GMAIL:
                return GmailAccount(
                    login=row[0],
                    password=row[1],
                    backup_email=row[2] if len(row) > 2 and row[2] else None,
                    row_index=row_index,
                )
        except IndexError as e:
            logger.error(f"Error parsing account row {row_index}: {e}")
            return None

    async def delete_account_row(
        self, resource: Resource, gender: Gender, row_index: int
    ) -> None:
        """Удалить строку аккаунта из исходной таблицы"""
        try:
            agc = await self._get_client()
            ss = await agc.open_by_key(settings.SPREADSHEET_ACCOUNTS)

            sheet_name = self._get_sheet_name(resource, gender)
            ws = await ss.worksheet(sheet_name)

            await ws.delete_rows(row_index)
        except Exception as e:
            logger.error(f"Error deleting account row: {e}")
            raise

    async def delete_account_rows_batch(
        self, resource: Resource, gender: Gender, row_indices: List[int]
    ) -> None:
        """Удалить несколько строк аккаунтов (группируя смежные для меньшего числа API вызовов)"""
        if not row_indices:
            return

        try:
            agc = await self._get_client()
            ss = await agc.open_by_key(settings.SPREADSHEET_ACCOUNTS)

            sheet_name = self._get_sheet_name(resource, gender)
            ws = await ss.worksheet(sheet_name)

            # Сортируем по убыванию и группируем смежные
            sorted_indices = sorted(row_indices, reverse=True)
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
            api_calls = 0
            for group in groups:
                start_idx = min(group)  # Начало диапазона
                end_idx = max(group)    # Конец диапазона
                # delete_rows(start, end) удаляет строки с start по end включительно
                await ws.delete_rows(start_idx, end_idx)
                api_calls += 1

            logger.info(f"Deleted {len(row_indices)} rows from {sheet_name} ({api_calls} API calls)")
        except Exception as e:
            logger.error(f"Error batch deleting account rows: {e}")
            raise

    async def add_issued_accounts_batch(
        self,
        resource: Resource,
        gender: Gender,
        accounts_data: List[tuple],  # [(account_data, region, employee_stage, status), ...]
    ) -> None:
        """Добавить несколько записей в таблицу выданных"""
        if not accounts_data:
            return

        try:
            agc = await self._get_client()
            ss = await agc.open_by_key(settings.SPREADSHEET_ISSUED)

            sheet_name = self._get_sheet_name(resource, gender)
            ws = await ss.worksheet(sheet_name)

            date_str = datetime.now().strftime("%Y-%m-%d")

            rows = []
            for account_data, region, employee_stage, status in accounts_data:
                row = [date_str] + account_data + [region, employee_stage, status]
                rows.append(row)

            # Добавляем все строки за один запрос
            await ws.append_rows(rows, value_input_option="USER_ENTERED")
            logger.info(f"Added {len(rows)} issued accounts to {sheet_name}")

        except Exception as e:
            logger.error(f"Error batch adding issued accounts: {e}")
            raise

    # === Выданные аккаунты ===

    async def add_issued_account(
        self,
        resource: Resource,
        gender: Gender,
        account_data: List[str],
        region: str,
        employee_stage: str,
    ) -> str:
        """Добавить запись в таблицу выданных, вернуть ID записи"""
        try:
            agc = await self._get_client()
            ss = await agc.open_by_key(settings.SPREADSHEET_ISSUED)

            sheet_name = self._get_sheet_name(resource, gender)
            ws = await ss.worksheet(sheet_name)

            date_str = datetime.now().strftime("%Y-%m-%d")

            # Формируем строку: date | данные аккаунта... | region | employee | status
            row_data = [date_str] + account_data + [region, employee_stage, ""]

            await ws.append_row(row_data, value_input_option="USER_ENTERED")

            # Получаем ID записи (номер последней строки)
            all_values = await ws.get_all_values()
            return f"{resource.value}_{gender.value}_{len(all_values)}"
        except Exception as e:
            logger.error(f"Error adding issued account: {e}")
            raise

    async def update_account_status(
        self, account_id: str, status: str
    ) -> None:
        """Обновить статус выданного аккаунта"""
        try:
            # Парсим account_id: resource_gender_rownum
            parts = account_id.rsplit("_", 1)
            if len(parts) != 2:
                logger.error(f"Invalid account_id format: {account_id}")
                return

            sheet_key = parts[0]  # например "vk_male"
            row_index = int(parts[1])

            # Получаем название листа
            sheet_name = settings.SHEET_NAMES.get(sheet_key, sheet_key)

            agc = await self._get_client()
            ss = await agc.open_by_key(settings.SPREADSHEET_ISSUED)
            ws = await ss.worksheet(sheet_name)

            # Получаем количество колонок чтобы найти последнюю (status)
            header = await ws.row_values(1)
            status_col = len(header)  # Последняя колонка - status

            await ws.update_cell(row_index, status_col, status)
        except Exception as e:
            logger.error(f"Error updating account status: {e}")
            raise

    async def get_accounts_count(self, resource: Resource, gender: Gender) -> int:
        """Получить количество доступных аккаунтов"""
        try:
            agc = await self._get_client()
            ss = await agc.open_by_key(settings.SPREADSHEET_ACCOUNTS)

            sheet_name = self._get_sheet_name(resource, gender)
            ws = await ss.worksheet(sheet_name)

            all_values = await ws.get_all_values()
            # Минус заголовок, минус пустые строки
            count = sum(1 for row in all_values[1:] if row and row[0])
            return count
        except Exception as e:
            logger.error(f"Error getting accounts count: {e}")
            return 0


sheets_service = SheetsService()
