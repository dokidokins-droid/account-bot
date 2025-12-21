"""
Скрипт для миграции whitelist из Google Sheets во внутреннее хранение.
Также удаляет лист whitelist из таблицы.
"""
import asyncio
import sys
import os

# Добавляем корень проекта в путь
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bot.config import settings
from bot.services.sheets_service import agcm
from bot.services.whitelist_service import whitelist_service
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main():
    """Миграция whitelist из Sheets во внутреннее хранение"""
    logger.info("Начинаю миграцию whitelist...")

    try:
        agc = await agcm.authorize()
        ss = await agc.open_by_key(settings.SPREADSHEET_ACCOUNTS)

        # Получаем лист whitelist
        try:
            ws = await ss.worksheet("whitelist")
        except Exception as e:
            logger.error(f"Лист 'whitelist' не найден: {e}")
            return

        # Читаем все записи
        records = await ws.get_all_records()
        logger.info(f"Найдено {len(records)} записей в whitelist")

        # Мигрируем пользователей
        users_to_import = []
        for record in records:
            telegram_id = record.get("telegram_id")
            if not telegram_id:
                continue

            # Парсим is_approved
            approved_value = record.get("approved", False)
            if isinstance(approved_value, bool):
                is_approved = approved_value
            elif isinstance(approved_value, str):
                is_approved = approved_value.lower() in ("true", "1", "yes")
            else:
                is_approved = bool(approved_value)

            users_to_import.append({
                "telegram_id": int(telegram_id),
                "stage": record.get("stage", ""),
                "is_approved": is_approved,
            })

        if users_to_import:
            # Импортируем пользователей
            count = whitelist_service.import_users(users_to_import)
            logger.info(f"Импортировано {count} новых пользователей")

            # Показываем всех пользователей
            all_users = whitelist_service.get_all_users()
            logger.info(f"Всего пользователей в whitelist: {len(all_users)}")
            for user in all_users:
                status = "✅" if user.is_approved else "⏳"
                logger.info(f"  {status} {user.telegram_id} - {user.stage}")
        else:
            logger.info("Нет пользователей для импорта")

        # Удаляем лист whitelist
        logger.info("\nУдаляю лист 'whitelist' из таблицы...")
        try:
            await ss.del_worksheet(ws)
            logger.info("Лист 'whitelist' удалён")
        except Exception as e:
            logger.error(f"Ошибка при удалении листа: {e}")

        logger.info("\n=== Миграция завершена! ===")

    except Exception as e:
        logger.error(f"Ошибка миграции: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())
