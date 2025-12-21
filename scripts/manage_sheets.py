"""
Скрипт для управления листами в Google Sheets.
Создаёт новые листы для VK/OK и удаляет старые.
"""
import asyncio
import sys
import os

# Добавляем корень проекта в путь
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bot.config import settings
from bot.services.sheets_service import agcm
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def create_sheet_if_not_exists(spreadsheet, sheet_name: str, headers: list):
    """Создать лист если не существует"""
    try:
        ws = await spreadsheet.worksheet(sheet_name)
        logger.info(f"Лист '{sheet_name}' уже существует")
        return ws
    except Exception:
        logger.info(f"Создаю лист '{sheet_name}'...")
        ws = await spreadsheet.add_worksheet(title=sheet_name, rows=1000, cols=20)
        if headers:
            await ws.append_row(headers, value_input_option="USER_ENTERED")
        logger.info(f"Лист '{sheet_name}' создан")
        return ws


async def delete_sheet_if_exists(spreadsheet, sheet_name: str):
    """Удалить лист если существует"""
    try:
        ws = await spreadsheet.worksheet(sheet_name)
        await spreadsheet.del_worksheet(ws)
        logger.info(f"Лист '{sheet_name}' удалён")
        return True
    except Exception as e:
        logger.info(f"Лист '{sheet_name}' не найден или ошибка: {e}")
        return False


async def main():
    """Основная функция"""
    logger.info("Подключаюсь к Google Sheets...")

    agc = await agcm.authorize()

    # Открываем обе таблицы
    ss_base = await agc.open_by_key(settings.SPREADSHEET_ACCOUNTS)
    ss_issued = await agc.open_by_key(settings.SPREADSHEET_ISSUED)

    logger.info(f"База: {ss_base.title}")
    logger.info(f"Выдача: {ss_issued.title}")

    # === Создаём новые листы ===

    # Заголовки для листов
    base_headers = ["Дата", "Логин", "Пароль"]
    issued_headers = ["Дата выдачи", "Логин", "Пароль", "Регион", "Employee", "Статус"]

    # ВКонтакте
    logger.info("\n=== ВКонтакте ===")
    await create_sheet_if_not_exists(ss_base, "ВКонтакте", base_headers)
    await create_sheet_if_not_exists(ss_issued, "ВКонтакте", issued_headers)

    # Одноклассники
    logger.info("\n=== Одноклассники ===")
    await create_sheet_if_not_exists(ss_base, "Одноклассники", base_headers)
    await create_sheet_if_not_exists(ss_issued, "Одноклассники", issued_headers)

    # Рамблер
    logger.info("\n=== Рамблер ===")
    await create_sheet_if_not_exists(ss_base, "Рамблер", base_headers)
    await create_sheet_if_not_exists(ss_issued, "Рамблер Выдано", issued_headers)

    # === Удаляем старые листы ===

    old_sheets = ["ВК Муж", "ВК Жен", "ОК Муж", "ОК Жен"]

    logger.info("\n=== Удаление старых листов ===")
    for sheet_name in old_sheets:
        logger.info(f"\nУдаление '{sheet_name}'...")
        await delete_sheet_if_exists(ss_base, sheet_name)
        await delete_sheet_if_exists(ss_issued, sheet_name)

    logger.info("\n=== Готово! ===")

    # Выводим список листов
    logger.info("\nЛисты в Базе:")
    worksheets = await ss_base.worksheets()
    for ws in worksheets:
        logger.info(f"  - {ws.title}")

    logger.info("\nЛисты в Выдаче:")
    worksheets = await ss_issued.worksheets()
    for ws in worksheets:
        logger.info(f"  - {ws.title}")


if __name__ == "__main__":
    asyncio.run(main())
