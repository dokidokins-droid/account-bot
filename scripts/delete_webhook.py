"""
Скрипт для удаления webhook перед локальной разработкой.
Запуск: python scripts/delete_webhook.py
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from aiogram import Bot
from bot.config import settings


async def main():
    bot = Bot(token=settings.BOT_TOKEN)

    # Получаем информацию о текущем webhook
    webhook_info = await bot.get_webhook_info()

    if webhook_info.url:
        print(f"Active webhook found: {webhook_info.url}")
        print(f"Pending updates: {webhook_info.pending_update_count}")

        # Удаляем webhook
        await bot.delete_webhook(drop_pending_updates=True)
        print("Webhook deleted successfully!")
    else:
        print("No active webhook found.")

    # Проверяем результат
    webhook_info = await bot.get_webhook_info()
    print(f"Current webhook URL: {webhook_info.url or 'None'}")

    await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
