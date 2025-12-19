import json
import base64
import logging
import time
from typing import List, Optional, Any, Dict
from datetime import datetime, timedelta
from dataclasses import dataclass

import gspread_asyncio
from google.oauth2.service_account import Credentials

from bot.config import settings
from bot.models.account import VKAccount, MambaAccount, OKAccount, GmailAccount
from bot.models.user import User
from bot.models.enums import Resource, Gender

logger = logging.getLogger(__name__)

# Время жизни кэша пользователей (5 минут)
USER_CACHE_TTL = 300


def parse_date(date_str: str) -> datetime:
    """Парсинг даты в форматах dd.mm.yy или YYYY-MM-DD (для совместимости)"""
    if not date_str:
        return datetime.now()

    # Сначала пробуем новый формат dd.mm.yy
    try:
        return datetime.strptime(date_str, "%d.%m.%y")
    except ValueError:
        pass

    # Затем старый формат YYYY-MM-DD
    try:
        return datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        return datetime.now()


@dataclass
class AccountStatistics:
    """Статистика по аккаунтам"""
    total: int = 0
    good: int = 0
    block: int = 0
    defect: int = 0
    no_status: int = 0  # без статуса (пустой)


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
                    # Правильно парсим is_approved (может быть True/False/TRUE/FALSE/"TRUE"/"FALSE"/1/0)
                    approved_value = record.get("approved", False)
                    if isinstance(approved_value, bool):
                        is_approved = approved_value
                    elif isinstance(approved_value, str):
                        is_approved = approved_value.lower() in ("true", "1", "yes")
                    else:
                        is_approved = bool(approved_value)

                    user = User(
                        telegram_id=telegram_id,
                        stage=record.get("stage", ""),
                        is_approved=is_approved,
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

    async def reject_user(self, telegram_id: int) -> bool:
        """Отклонить и удалить пользователя из whitelist (чтобы мог подать заявку заново)"""
        try:
            user = await self.get_user_by_telegram_id(telegram_id)
            if user and user.row_index:
                agc = await self._get_client()
                ss = await agc.open_by_key(settings.SPREADSHEET_ACCOUNTS)
                ws = await ss.worksheet(settings.SHEET_NAMES["whitelist"])

                # Удаляем строку пользователя
                await ws.delete_rows(user.row_index)
                # Инвалидируем кэш
                self._invalidate_user_cache(telegram_id)
                return True
            return False
        except Exception as e:
            logger.error(f"Error rejecting user: {e}")
            raise

    # === Аккаунты ===

    async def get_accounts(
        self, resource: Resource, gender: Gender, quantity: int
    ) -> List[Any]:
        """
        Получить аккаунты из таблицы.

        Формат таблицы База: дата | логин | пароль | ...
        """
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
                # Проверяем наличие логина (колонка 1, т.к. колонка 0 — дата)
                if not row or len(row) < 2 or not row[1]:
                    continue

                account = self._parse_account(resource, row, idx)
                if account:
                    accounts.append(account)

            return accounts
        except Exception as e:
            logger.error(f"Error getting accounts: {e}")
            raise

    def _parse_account(self, resource: Resource, row: List[str], row_index: int):
        """
        Парсинг строки в объект аккаунта.

        Формат таблицы База: дата | логин | пароль | ...
        Индексы: [0]=дата, [1]=логин, [2]=пароль, [3+]=доп. поля
        """
        try:
            # Пропускаем первую колонку (дата)
            if resource == Resource.VK:
                return VKAccount(
                    login=row[1],
                    password=row[2],
                    row_index=row_index,
                )
            elif resource == Resource.MAMBA:
                return MambaAccount(
                    login=row[1],
                    password=row[2],
                    email_password=row[3] if len(row) > 3 else "",
                    confirmation_link=row[4] if len(row) > 4 else "",
                    row_index=row_index,
                )
            elif resource == Resource.OK:
                return OKAccount(
                    login=row[1],
                    password=row[2],
                    row_index=row_index,
                )
            elif resource == Resource.GMAIL:
                return GmailAccount(
                    login=row[1],
                    password=row[2],
                    backup_email=row[3] if len(row) > 3 and row[3] else None,
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

            date_str = datetime.now().strftime("%d.%m.%y")

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

            date_str = datetime.now().strftime("%d.%m.%y")

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
        """
        Получить количество доступных аккаунтов.

        Формат таблицы: дата | логин | пароль | ...
        """
        try:
            agc = await self._get_client()
            ss = await agc.open_by_key(settings.SPREADSHEET_ACCOUNTS)

            sheet_name = self._get_sheet_name(resource, gender)
            ws = await ss.worksheet(sheet_name)

            all_values = await ws.get_all_values()
            # Минус заголовок, минус пустые строки (проверяем колонку логина)
            count = sum(1 for row in all_values[1:] if row and len(row) > 1 and row[1])
            return count
        except Exception as e:
            logger.error(f"Error getting accounts count: {e}")
            return 0

    # === Статистика ===

    async def get_statistics(
        self,
        resource: Resource,
        gender: Gender,
        region: Optional[str],  # None означает все регионы
        period: str,  # day, week, month
    ) -> AccountStatistics:
        """Получить статистику выданных аккаунтов за период"""
        try:
            agc = await self._get_client()
            ss = await agc.open_by_key(settings.SPREADSHEET_ISSUED)

            sheet_name = self._get_sheet_name(resource, gender)
            ws = await ss.worksheet(sheet_name)

            all_values = await ws.get_all_values()

            # Определяем дату начала периода
            now = datetime.now()
            if period == "day":
                start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
            elif period == "week":
                start_date = now - timedelta(days=7)
            elif period == "month":
                start_date = now - timedelta(days=30)
            else:
                start_date = now - timedelta(days=1)

            stats = AccountStatistics()

            # Формат таблицы выданных: date | account_data... | region | employee | status
            # Заголовок в первой строке
            if len(all_values) < 2:
                return stats

            header = all_values[0]

            # Находим индексы нужных колонок
            # Предполагаем: date (0), region (-3), employee (-2), status (-1)
            date_col = 0
            # Находим индекс колонки региона и статуса
            region_col = len(header) - 3 if len(header) >= 3 else -1
            status_col = len(header) - 1 if len(header) >= 1 else -1

            for row in all_values[1:]:
                if not row or not row[0]:
                    continue

                # Парсим дату (поддержка dd.mm.yy и YYYY-MM-DD)
                try:
                    row_date = parse_date(row[date_col])
                except (ValueError, IndexError):
                    continue

                # Проверяем период
                if row_date < start_date:
                    continue

                # Проверяем регион (если указан)
                if region and region != "all":
                    try:
                        row_region = row[region_col] if region_col >= 0 and len(row) > region_col else ""
                        if row_region != region:
                            continue
                    except IndexError:
                        continue

                # Подсчитываем статистику
                stats.total += 1

                try:
                    status = row[status_col].lower().strip() if status_col >= 0 and len(row) > status_col else ""
                except IndexError:
                    status = ""

                if status == "good" or status == "хороший":
                    stats.good += 1
                elif status == "block" or status == "блок":
                    stats.block += 1
                elif status == "defect" or status == "дефектный":
                    stats.defect += 1
                else:
                    stats.no_status += 1

            return stats

        except Exception as e:
            logger.error(f"Error getting statistics: {e}")
            return AccountStatistics()

    async def get_statistics_by_regions(
        self,
        resource: Resource,
        gender: Gender,
        regions: List[str],  # Список регионов для подсчёта
        period: str,  # day, week, month
    ) -> Dict[str, AccountStatistics]:
        """Получить статистику по каждому региону отдельно"""
        try:
            agc = await self._get_client()
            ss = await agc.open_by_key(settings.SPREADSHEET_ISSUED)

            sheet_name = self._get_sheet_name(resource, gender)
            ws = await ss.worksheet(sheet_name)

            all_values = await ws.get_all_values()

            # Определяем дату начала периода
            now = datetime.now()
            if period == "day":
                start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
            elif period == "week":
                start_date = now - timedelta(days=7)
            elif period == "month":
                start_date = now - timedelta(days=30)
            else:
                start_date = now - timedelta(days=1)

            # Инициализируем статистику для каждого региона
            stats_by_region: Dict[str, AccountStatistics] = {
                region: AccountStatistics() for region in regions
            }

            if len(all_values) < 2:
                return stats_by_region

            header = all_values[0]
            date_col = 0
            region_col = len(header) - 3 if len(header) >= 3 else -1
            status_col = len(header) - 1 if len(header) >= 1 else -1

            for row in all_values[1:]:
                if not row or not row[0]:
                    continue

                # Парсим дату (поддержка dd.mm.yy и YYYY-MM-DD)
                try:
                    row_date = parse_date(row[date_col])
                except (ValueError, IndexError):
                    continue

                # Проверяем период
                if row_date < start_date:
                    continue

                # Получаем регион строки
                try:
                    row_region = row[region_col] if region_col >= 0 and len(row) > region_col else ""
                except IndexError:
                    continue

                # Если регион не в списке - пропускаем
                if row_region not in stats_by_region:
                    continue

                # Подсчитываем статистику для этого региона
                stats = stats_by_region[row_region]
                stats.total += 1

                try:
                    status = row[status_col].lower().strip() if status_col >= 0 and len(row) > status_col else ""
                except IndexError:
                    status = ""

                if status == "good" or status == "хороший":
                    stats.good += 1
                elif status == "block" or status == "блок":
                    stats.block += 1
                elif status == "defect" or status == "дефектный":
                    stats.defect += 1
                else:
                    stats.no_status += 1

            return stats_by_region

        except Exception as e:
            logger.error(f"Error getting statistics by regions: {e}")
            return {region: AccountStatistics() for region in regions}


sheets_service = SheetsService()
