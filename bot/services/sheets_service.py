import asyncio
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
from bot.models.enums import Resource, Gender, EmailResource, NumberResource

logger = logging.getLogger(__name__)


# ==================== RATE LIMITER ====================

class SheetsRateLimiter:
    """
    Rate limiter для Google Sheets API.

    Лимиты API:
    - 100 запросов за 100 секунд на пользователя
    - 500 запросов за 100 секунд на проект

    Стратегия:
    - Семафор ограничивает параллельные запросы
    - Token bucket для контроля частоты
    """

    def __init__(
        self,
        max_concurrent: int = 10,     # Макс параллельных запросов
        requests_per_second: float = 1.5,  # ~90 запросов в 60 сек (лимит 100/100сек)
    ):
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._min_interval = 1.0 / requests_per_second
        self._last_request_time = 0.0
        self._lock = asyncio.Lock()

        # Статистика
        self._total_requests = 0
        self._total_wait_time = 0.0

    async def acquire(self) -> None:
        """Получить разрешение на запрос"""
        await self._semaphore.acquire()

        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_request_time

            if elapsed < self._min_interval:
                wait_time = self._min_interval - elapsed
                self._total_wait_time += wait_time
                await asyncio.sleep(wait_time)

            self._last_request_time = time.monotonic()
            self._total_requests += 1

    def release(self) -> None:
        """Освободить слот"""
        self._semaphore.release()

    async def __aenter__(self):
        await self.acquire()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self.release()
        return False

    def get_stats(self) -> Dict[str, Any]:
        """Получить статистику"""
        return {
            "total_requests": self._total_requests,
            "total_wait_time": round(self._total_wait_time, 2),
            "avg_wait_time": round(self._total_wait_time / max(1, self._total_requests), 3),
        }


# Глобальный rate limiter (один на всё приложение)
sheets_rate_limiter = SheetsRateLimiter()


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


@dataclass
class NumberStatistics:
    """Статистика по номерам телефонов"""
    total: int = 0  # Всего номеров
    beboo: int = 0  # Сколько зарегано Beboo
    loloo: int = 0  # Сколько зарегано Loloo
    tabor: int = 0  # Сколько зарегано Tabor
    # Статусы
    working: int = 0
    reset: int = 0
    registered: int = 0
    tg_kicked: int = 0
    no_status: int = 0


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


# ==================== RATE-LIMITED WRAPPERS ====================

async def rate_limited_call(coro):
    """Обёртка для rate-limited вызова API"""
    async with sheets_rate_limiter:
        return await coro


async def batch_update_cells(worksheet, updates: List[Dict[str, Any]]) -> None:
    """
    Batch обновление ячеек за один API запрос.

    Args:
        worksheet: gspread worksheet
        updates: список {"row": int, "col": int, "value": str}
    """
    if not updates:
        return

    # Группируем обновления по диапазонам для batch_update
    cells_data = []
    for upd in updates:
        row, col, value = upd["row"], upd["col"], upd["value"]
        # Конвертируем в A1 нотацию
        col_letter = chr(ord('A') + col - 1) if col <= 26 else 'Z'
        cell_range = f"{col_letter}{row}"
        cells_data.append({
            "range": cell_range,
            "values": [[value]]
        })

    if cells_data:
        async with sheets_rate_limiter:
            await worksheet.batch_update(cells_data, value_input_option="USER_ENTERED")


class SheetsService:
    """Сервис для работы с Google Sheets"""

    def _get_sheet_name(self, resource: Resource, gender: Gender) -> str:
        """Получить название листа по ресурсу и полу"""
        key = f"{resource.value}_{gender.value}"
        return settings.SHEET_NAMES.get(key, key)

    async def _get_client(self):
        """Получение авторизованного клиента (rate-limited)"""
        async with sheets_rate_limiter:
            return await agcm.authorize()

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

    async def append_accounts_to_base(
        self, resource: Resource, gender: Gender, rows_data: List[List[str]]
    ) -> None:
        """
        Добавить аккаунты в конец таблицы базы (для функции освобождения).

        Args:
            resource: Тип ресурса
            gender: Пол
            rows_data: Список строк данных (без даты - она добавляется автоматически)
        """
        if not rows_data:
            return

        try:
            agc = await self._get_client()
            ss = await agc.open_by_key(settings.SPREADSHEET_ACCOUNTS)

            sheet_name = self._get_sheet_name(resource, gender)
            ws = await ss.worksheet(sheet_name)

            # Получаем все данные
            all_values = await ws.get_all_values()

            # Находим последнюю ЗАПОЛНЕННУЮ строку
            last_filled_row = 1  # Минимум заголовок
            for i, row in enumerate(all_values, start=1):
                if row and any(cell.strip() for cell in row if cell):
                    last_filled_row = i

            start_row = last_filled_row + 1

            # Добавляем дату к каждой строке
            date_str = datetime.now().strftime("%d.%m.%y")
            rows_with_date = [[date_str] + row for row in rows_data]

            # Вычисляем диапазон
            end_row = start_row + len(rows_with_date) - 1
            max_cols = max(len(row) for row in rows_with_date)
            end_col = chr(ord('A') + max_cols - 1)
            range_str = f"A{start_row}:{end_col}{end_row}"

            # Записываем все строки одним batch запросом
            await ws.update(range_str, rows_with_date, value_input_option="USER_ENTERED")

            logger.info(f"Appended {len(rows_with_date)} accounts to {sheet_name} (rows {start_row}-{end_row})")

        except Exception as e:
            logger.error(f"Error appending accounts to base: {e}")
            raise

    async def add_issued_accounts_batch(
        self,
        resource: Resource,
        gender: Gender,
        accounts_data: List[tuple],  # [(account_data, region, employee_stage, status), ...]
    ) -> None:
        """Добавить несколько записей в таблицу выданных с цветами статусов"""
        if not accounts_data:
            return

        try:
            from bot.models.enums import AccountStatus

            agc = await self._get_client()
            ss = await agc.open_by_key(settings.SPREADSHEET_ISSUED)

            sheet_name = self._get_sheet_name(resource, gender)
            ws = await ss.worksheet(sheet_name)

            date_str = datetime.now().strftime("%d.%m.%y")

            # Получаем текущие данные для расчёта позиций новых строк
            all_values = await ws.get_all_values()

            # Находим последнюю ЗАПОЛНЕННУЮ строку (игнорируем пустые)
            last_filled_row = 1  # Минимум заголовок
            for i, row in enumerate(all_values, start=1):
                if row and any(cell.strip() for cell in row if cell):
                    last_filled_row = i

            start_row = last_filled_row + 1

            # Подготавливаем строки и информацию о цветах
            rows = []
            status_colors = []  # [(row_index, color), ...]

            for idx, (account_data, region, employee_stage, status) in enumerate(accounts_data):
                # Конвертируем статус в русское название
                try:
                    status_enum = AccountStatus(status)
                    status_text = status_enum.table_name
                    bg_color = status_enum.background_color
                except ValueError:
                    status_text = status
                    bg_color = None

                row = [date_str] + account_data + [region, employee_stage, status_text]
                rows.append(row)

                if bg_color:
                    status_colors.append((start_row + idx, bg_color))

            # Записываем в конкретный диапазон после последней заполненной строки
            if rows:
                end_row = start_row + len(rows) - 1
                # Определяем количество колонок по первой строке
                num_cols = len(rows[0])
                end_col = chr(ord('A') + num_cols - 1) if num_cols <= 26 else 'Z'
                range_str = f"A{start_row}:{end_col}{end_row}"

                await ws.update(range_str, rows, value_input_option="USER_ENTERED")

            # Применяем цвета к ячейкам статуса
            # Находим колонку статуса (последняя)
            # Форматируем все ячейки со статусами за один batch запрос
            if status_colors and rows:
                status_col = len(rows[0])
                col_letter = chr(ord('A') + status_col - 1) if status_col <= 26 else 'Z'

                formats_to_apply = []
                for row_index, bg_color in status_colors:
                    cell_address = f"{col_letter}{row_index}"
                    formats_to_apply.append({
                        "range": cell_address,
                        "format": {"backgroundColor": bg_color}
                    })

                if formats_to_apply:
                    try:
                        await ws.batch_format(formats_to_apply)
                    except Exception as e:
                        logger.warning(f"Failed to batch format cells: {e}")

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

            # table_range гарантирует что строка добавится сразу после данных
            await ws.append_row(
                row_data,
                value_input_option="USER_ENTERED",
                table_range="A1:Z"
            )

            # Получаем ID записи (номер последней строки)
            all_values = await ws.get_all_values()
            return f"{resource.value}_{gender.value}_{len(all_values)}"
        except Exception as e:
            logger.error(f"Error adding issued account: {e}")
            raise

    async def update_account_status(
        self, account_id: str, status: str
    ) -> None:
        """Обновить статус выданного аккаунта с цветом фона"""
        try:
            # Парсим account_id: resource_gender_rownum
            parts = account_id.rsplit("_", 1)
            if len(parts) != 2:
                logger.error(f"Invalid account_id format: {account_id}")
                return

            sheet_key = parts[0]  # например "vk_none"
            row_index = int(parts[1])

            # Получаем название листа
            sheet_name = settings.SHEET_NAMES.get(sheet_key, sheet_key)

            agc = await self._get_client()
            ss = await agc.open_by_key(settings.SPREADSHEET_ISSUED)
            ws = await ss.worksheet(sheet_name)

            # Получаем количество колонок чтобы найти последнюю (status)
            header = await ws.row_values(1)
            status_col = len(header)  # Последняя колонка - status

            # Получаем table_name статуса (без эмодзи) и цвет
            from bot.models.enums import AccountStatus
            try:
                status_enum = AccountStatus(status)
                status_text = status_enum.table_name
                bg_color = status_enum.background_color
            except ValueError:
                status_text = status
                bg_color = None

            await ws.update_cell(row_index, status_col, status_text)

            # Применяем цвет фона если есть
            if bg_color:
                # Конвертируем номер колонки в букву (A=1, B=2, ...)
                col_letter = chr(ord('A') + status_col - 1) if status_col <= 26 else 'Z'
                cell_address = f"{col_letter}{row_index}"
                await ws.format(cell_address, {
                    "backgroundColor": bg_color
                })

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

    # === Статистика почт ===

    def _get_email_sheet_name(self, email_resource: EmailResource, email_type: Optional[Gender]) -> str:
        """Получить название листа выдачи для почт"""
        if email_resource == EmailResource.GMAIL:
            if email_type == Gender.GMAIL_DOMAIN:
                return settings.SHEET_NAMES.get("gmail_gmail_domain", "Гугл Гмейл")
            else:
                return settings.SHEET_NAMES.get("gmail_any", "Гугл Любые")
        elif email_resource == EmailResource.RAMBLER:
            return settings.SHEET_NAMES.get("rambler_issued", "Рамблер Выдано")
        return "Unknown"

    async def get_email_statistics(
        self,
        email_resource: EmailResource,
        email_type: Optional[Gender],  # None для Rambler
        region: Optional[str],  # None для всех регионов
        period: str,
    ) -> AccountStatistics:
        """Получить статистику выданных почт за период"""
        try:
            agc = await self._get_client()
            ss = await agc.open_by_key(settings.SPREADSHEET_ISSUED)

            sheet_name = self._get_email_sheet_name(email_resource, email_type)
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

            if len(all_values) < 2:
                return stats

            # Формат почт: Дата выдачи | Логин | Пароль | Доп инфа | Регион | Employee | Статус
            # Индексы:        0           1        2         3         4        5         6
            date_col = 0
            region_col = 4
            status_col = 6

            for row in all_values[1:]:
                if not row or not row[0]:
                    continue

                try:
                    row_date = parse_date(row[date_col])
                except (ValueError, IndexError):
                    continue

                if row_date < start_date:
                    continue

                # Проверяем регион
                if region and region != "all":
                    try:
                        row_region = row[region_col] if len(row) > region_col else ""
                        if row_region != region:
                            continue
                    except IndexError:
                        continue

                stats.total += 1

                try:
                    status = row[status_col].lower().strip() if len(row) > status_col else ""
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
            logger.error(f"Error getting email statistics: {e}")
            return AccountStatistics()

    async def get_email_statistics_by_regions(
        self,
        email_resource: EmailResource,
        email_type: Optional[Gender],
        regions: List[str],
        period: str,
    ) -> Dict[str, AccountStatistics]:
        """Получить статистику почт по каждому региону отдельно"""
        try:
            agc = await self._get_client()
            ss = await agc.open_by_key(settings.SPREADSHEET_ISSUED)

            sheet_name = self._get_email_sheet_name(email_resource, email_type)
            ws = await ss.worksheet(sheet_name)

            all_values = await ws.get_all_values()

            now = datetime.now()
            if period == "day":
                start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
            elif period == "week":
                start_date = now - timedelta(days=7)
            elif period == "month":
                start_date = now - timedelta(days=30)
            else:
                start_date = now - timedelta(days=1)

            stats_by_region: Dict[str, AccountStatistics] = {
                region: AccountStatistics() for region in regions
            }

            if len(all_values) < 2:
                return stats_by_region

            date_col = 0
            region_col = 4
            status_col = 6

            for row in all_values[1:]:
                if not row or not row[0]:
                    continue

                try:
                    row_date = parse_date(row[date_col])
                except (ValueError, IndexError):
                    continue

                if row_date < start_date:
                    continue

                try:
                    row_region = row[region_col] if len(row) > region_col else ""
                except IndexError:
                    continue

                if row_region not in stats_by_region:
                    continue

                stats = stats_by_region[row_region]
                stats.total += 1

                try:
                    status = row[status_col].lower().strip() if len(row) > status_col else ""
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
            logger.error(f"Error getting email statistics by regions: {e}")
            return {region: AccountStatistics() for region in regions}

    # === Статистика номеров ===

    async def get_number_statistics(
        self,
        region: Optional[str],  # None для всех регионов
        period: str,
    ) -> NumberStatistics:
        """
        Получить статистику выданных номеров за период.

        Считает:
        - Общее количество номеров
        - Сколько каждого ресурса было зарегистрировано (Beboo, Loloo, Tabor)
        - Статусы номеров
        """
        try:
            agc = await self._get_client()
            ss = await agc.open_by_key(settings.SPREADSHEET_ISSUED)

            sheet_name = settings.SHEET_NAMES.get("numbers_issued", "Номера Выдано")
            ws = await ss.worksheet(sheet_name)

            all_values = await ws.get_all_values()

            now = datetime.now()
            if period == "day":
                start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
            elif period == "week":
                start_date = now - timedelta(days=7)
            elif period == "month":
                start_date = now - timedelta(days=30)
            else:
                start_date = now - timedelta(days=1)

            stats = NumberStatistics()

            if len(all_values) < 2:
                return stats

            # Формат номеров: Дата выдачи | Номер | Регионы | Employee | Ресурсы | Статус
            # Индексы:            0          1        2          3         4        5
            date_col = 0
            region_col = 2
            resources_col = 4
            status_col = 5

            for row in all_values[1:]:
                if not row or not row[0]:
                    continue

                try:
                    row_date = parse_date(row[date_col])
                except (ValueError, IndexError):
                    continue

                if row_date < start_date:
                    continue

                # Проверяем регион (в номерах регионы через запятую)
                if region and region != "all":
                    try:
                        row_regions = row[region_col] if len(row) > region_col else ""
                        regions_list = [r.strip() for r in row_regions.split(",")]
                        if region not in regions_list:
                            continue
                    except IndexError:
                        continue

                stats.total += 1

                # Парсим ресурсы и считаем каждый
                try:
                    resources_str = row[resources_col].lower() if len(row) > resources_col else ""
                    if "beboo" in resources_str:
                        stats.beboo += 1
                    if "loloo" in resources_str:
                        stats.loloo += 1
                    if "табор" in resources_str or "tabor" in resources_str:
                        stats.tabor += 1
                except IndexError:
                    pass

                # Парсим статус
                try:
                    status = row[status_col].lower().strip() if len(row) > status_col else ""
                except IndexError:
                    status = ""

                if status == "рабочий" or status == "working":
                    stats.working += 1
                elif status == "сброс" or status == "reset":
                    stats.reset += 1
                elif status == "зареган" or status == "registered":
                    stats.registered += 1
                elif status == "выбило тг" or status == "tg_kicked":
                    stats.tg_kicked += 1
                else:
                    stats.no_status += 1

            return stats

        except Exception as e:
            logger.error(f"Error getting number statistics: {e}")
            return NumberStatistics()

    async def get_number_statistics_by_regions(
        self,
        regions: List[str],
        period: str,
    ) -> Dict[str, NumberStatistics]:
        """Получить статистику номеров по каждому региону отдельно"""
        try:
            agc = await self._get_client()
            ss = await agc.open_by_key(settings.SPREADSHEET_ISSUED)

            sheet_name = settings.SHEET_NAMES.get("numbers_issued", "Номера Выдано")
            ws = await ss.worksheet(sheet_name)

            all_values = await ws.get_all_values()

            now = datetime.now()
            if period == "day":
                start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
            elif period == "week":
                start_date = now - timedelta(days=7)
            elif period == "month":
                start_date = now - timedelta(days=30)
            else:
                start_date = now - timedelta(days=1)

            stats_by_region: Dict[str, NumberStatistics] = {
                region: NumberStatistics() for region in regions
            }

            if len(all_values) < 2:
                return stats_by_region

            date_col = 0
            region_col = 2
            resources_col = 4
            status_col = 5

            for row in all_values[1:]:
                if not row or not row[0]:
                    continue

                try:
                    row_date = parse_date(row[date_col])
                except (ValueError, IndexError):
                    continue

                if row_date < start_date:
                    continue

                # Номер может быть связан с несколькими регионами
                try:
                    row_regions = row[region_col] if len(row) > region_col else ""
                    regions_list = [r.strip() for r in row_regions.split(",")]
                except IndexError:
                    continue

                # Считаем для каждого региона из записи
                for row_region in regions_list:
                    if row_region not in stats_by_region:
                        continue

                    stats = stats_by_region[row_region]
                    stats.total += 1

                    # Ресурсы
                    try:
                        resources_str = row[resources_col].lower() if len(row) > resources_col else ""
                        if "beboo" in resources_str:
                            stats.beboo += 1
                        if "loloo" in resources_str:
                            stats.loloo += 1
                        if "табор" in resources_str or "tabor" in resources_str:
                            stats.tabor += 1
                    except IndexError:
                        pass

                    # Статус
                    try:
                        status = row[status_col].lower().strip() if len(row) > status_col else ""
                    except IndexError:
                        status = ""

                    if status == "рабочий" or status == "working":
                        stats.working += 1
                    elif status == "сброс" or status == "reset":
                        stats.reset += 1
                    elif status == "зареган" or status == "registered":
                        stats.registered += 1
                    elif status == "выбило тг" or status == "tg_kicked":
                        stats.tg_kicked += 1
                    else:
                        stats.no_status += 1

            return stats_by_region

        except Exception as e:
            logger.error(f"Error getting number statistics by regions: {e}")
            return {region: NumberStatistics() for region in regions}


sheets_service = SheetsService()
