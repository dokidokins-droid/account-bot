"""Сервис для работы с номерами телефонов"""
import json
import logging
from datetime import datetime, date
from pathlib import Path
from typing import List, Dict, Any, Set

import gspread_asyncio

from bot.config import settings

logger = logging.getLogger(__name__)


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


def parse_used_for(used_for_str: str) -> Set[str]:
    """Парсинг списка ресурсов из строки (через запятую)"""
    if not used_for_str or not used_for_str.strip():
        return set()
    return {r.strip().lower() for r in used_for_str.split(",") if r.strip()}


def format_used_for(resources: Set[str]) -> str:
    """Форматирование списка ресурсов в строку"""
    return ",".join(sorted(resources))


# Путь к файлу настроек номеров
NUMBERS_SETTINGS_FILE = Path(__file__).parent.parent.parent / "data" / "numbers_settings.json"


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


class NumberService:
    """
    Сервис для работы с номерами телефонов.

    Номера могут переиспользоваться для разных ресурсов (Beboo, Loloo, Табор).
    Один номер можно взять на Beboo, и он останется доступен для Loloo/Tabor.

    Формат таблицы База (лист "Номера"):
        дата | номер | used_for (ресурсы через запятую)

    Формат таблицы Выдача (лист "Номера Выдано"):
        дата_выдачи | номер | регион | employee | ресурсы
    """

    def __init__(self):
        self._today_only: bool = True  # По умолчанию только сегодняшние
        self._load_settings()

    def _load_settings(self) -> None:
        """Загрузить настройки из файла"""
        try:
            if NUMBERS_SETTINGS_FILE.exists():
                with open(NUMBERS_SETTINGS_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self._today_only = data.get("today_only", True)
                    logger.info(f"Numbers settings loaded: today_only={self._today_only}")
            else:
                self._save_settings()
                logger.info("Created new numbers settings file")
        except Exception as e:
            logger.error(f"Error loading numbers settings: {e}")
            self._today_only = True

    def _save_settings(self) -> None:
        """Сохранить настройки в файл"""
        try:
            NUMBERS_SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(NUMBERS_SETTINGS_FILE, "w", encoding="utf-8") as f:
                json.dump({"today_only": self._today_only}, f, ensure_ascii=False, indent=2)
            logger.info(f"Numbers settings saved: today_only={self._today_only}")
        except Exception as e:
            logger.error(f"Error saving numbers settings: {e}")

    @property
    def today_only(self) -> bool:
        """Получить текущий режим"""
        return self._today_only

    def set_today_only(self, value: bool) -> None:
        """Установить режим today_only"""
        self._today_only = value
        self._save_settings()

    async def _get_client(self):
        """Получение авторизованного клиента"""
        return await agcm.authorize()

    async def issue_numbers(
        self,
        resources: List[str],  # Список ресурсов (beboo, loloo, tabor)
        region: str,
        quantity: int,
        employee_stage: str,
    ) -> List[Dict[str, Any]]:
        """
        Выдать номера из общей таблицы.

        Номера НЕ удаляются из Базы, а помечаются в колонке used_for.
        Номер доступен, если он не использован для ВСЕХ запрошенных ресурсов.

        Формат таблицы База: дата | номер | used_for
        Формат таблицы Выдача: дата_выдачи | номер | регион | employee | ресурсы
        """
        issued_numbers = []
        today = date.today()
        today_str = today.strftime("%d.%m.%y")
        requested_resources = {r.lower() for r in resources}

        try:
            agc = await self._get_client()
            ss_base = await agc.open_by_key(settings.SPREADSHEET_ACCOUNTS)
            ss_issued = await agc.open_by_key(settings.SPREADSHEET_ISSUED)

            # Получаем лист с номерами
            sheet_name = settings.SHEET_NAMES.get("numbers", "Номера")
            ws = await ss_base.worksheet(sheet_name)
            all_values = await ws.get_all_values()

            # Собираем доступные номера
            # Формат: дата | номер | used_for
            available_numbers = []
            for idx, row in enumerate(all_values[1:], start=2):  # Пропускаем заголовок
                if not row or len(row) < 2:
                    continue

                row_date_str = row[0].strip()
                number = row[1].strip()
                used_for_str = row[2].strip() if len(row) > 2 else ""

                if not number:
                    continue

                # Проверяем дату если включен режим today_only
                if self._today_only:
                    row_date = parse_date(row_date_str)
                    if row_date != today:
                        continue

                # Проверяем что номер не использован для запрошенных ресурсов
                used_for = parse_used_for(used_for_str)

                # Номер доступен если НИ ОДИН из запрошенных ресурсов ещё не использовал его
                if requested_resources & used_for:
                    # Есть пересечение — номер уже использован для какого-то из ресурсов
                    continue

                available_numbers.append({
                    "row_index": idx,
                    "date": row_date_str,
                    "number": number,
                    "used_for": used_for,
                })

            # Берём нужное количество
            numbers_to_issue = available_numbers[:quantity]

            if not numbers_to_issue:
                return []

            # Добавляем в таблицу выдачи
            issued_sheet_name = settings.SHEET_NAMES.get("numbers_issued", "Номера Выдано")
            try:
                ws_issued = await ss_issued.worksheet(issued_sheet_name)
            except Exception:
                # Создаём лист если не существует
                ws_issued = await ss_issued.add_worksheet(
                    title=issued_sheet_name, rows=1000, cols=10
                )
                await ws_issued.append_row(
                    ["Дата выдачи", "Номер", "Регион", "Employee", "Ресурсы"],
                    value_input_option="USER_ENTERED",
                )

            # Формируем строку ресурсов для записи
            from bot.models.enums import NumberResource
            resources_display = ", ".join(NumberResource(r).display_name for r in resources)

            # Записываем выданные номера в Выдачу и обновляем used_for в Базе
            rows_to_add = []

            for item in numbers_to_issue:
                # Формат Выдача: дата_выдачи | номер | регион | employee | ресурсы
                rows_to_add.append([
                    today_str,
                    item["number"],
                    region,
                    employee_stage,
                    resources_display,
                ])

                # Обновляем used_for в Базе
                new_used_for = item["used_for"] | requested_resources
                await ws.update_cell(item["row_index"], 3, format_used_for(new_used_for))

                issued_numbers.append({
                    "number": item["number"],
                    "date_added": item["date"],
                })

            # Добавляем в выдачу одним запросом
            if rows_to_add:
                await ws_issued.append_rows(rows_to_add, value_input_option="USER_ENTERED")

            logger.info(f"Issued {len(issued_numbers)} numbers for resources {resources}")
            return issued_numbers

        except Exception as e:
            logger.error(f"Error issuing numbers: {e}")
            return []

    async def get_available_count(self, resources: List[str] = None) -> int:
        """
        Получить количество доступных номеров для указанных ресурсов.

        Если resources не указан, считает номера которые ещё не использованы
        ни для одного ресурса (полностью свободные).
        """
        today = date.today()
        count = 0

        if resources:
            requested_resources = {r.lower() for r in resources}
        else:
            requested_resources = set()

        try:
            agc = await self._get_client()
            ss = await agc.open_by_key(settings.SPREADSHEET_ACCOUNTS)

            sheet_name = settings.SHEET_NAMES.get("numbers", "Номера")
            try:
                ws = await ss.worksheet(sheet_name)
            except Exception:
                return 0

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

                # Проверяем доступность
                used_for = parse_used_for(used_for_str)

                if requested_resources:
                    # Считаем доступные для конкретных ресурсов
                    if not (requested_resources & used_for):
                        count += 1
                else:
                    # Считаем полностью свободные
                    if not used_for:
                        count += 1

            return count

        except Exception as e:
            logger.error(f"Error getting available count: {e}")
            return 0

    async def ensure_sheets_exist(self) -> None:
        """Создать листы для номеров если их нет"""
        try:
            agc = await self._get_client()

            # Лист в таблице База
            ss_base = await agc.open_by_key(settings.SPREADSHEET_ACCOUNTS)
            sheet_name = settings.SHEET_NAMES.get("numbers", "Номера")
            try:
                await ss_base.worksheet(sheet_name)
            except Exception:
                ws = await ss_base.add_worksheet(title=sheet_name, rows=1000, cols=10)
                await ws.append_row(
                    ["Дата", "Номер", "Использован для"],
                    value_input_option="USER_ENTERED"
                )
                logger.info(f"Created sheet '{sheet_name}' in База")

            # Лист в таблице Выдача
            ss_issued = await agc.open_by_key(settings.SPREADSHEET_ISSUED)
            issued_sheet_name = settings.SHEET_NAMES.get("numbers_issued", "Номера Выдано")
            try:
                await ss_issued.worksheet(issued_sheet_name)
            except Exception:
                ws = await ss_issued.add_worksheet(title=issued_sheet_name, rows=1000, cols=10)
                await ws.append_row(
                    ["Дата выдачи", "Номер", "Регион", "Employee", "Ресурсы"],
                    value_input_option="USER_ENTERED",
                )
                logger.info(f"Created sheet '{issued_sheet_name}' in Выдача")

        except Exception as e:
            logger.error(f"Error ensuring sheets exist: {e}")


# Глобальный экземпляр сервиса
number_service = NumberService()
