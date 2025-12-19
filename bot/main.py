import asyncio
import logging
import os

from aiohttp import web

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiogram.types import BotCommand

from bot.config import settings
from bot.handlers import start, admin, account_flow, feedback, statistic, proxy, numbers
from bot.middlewares.auth import WhitelistMiddleware
from bot.services.account_service import account_cache
from bot.services.proxy_service import init_proxy_service
from bot.services.sheets_service import agcm
from bot.services.number_service import number_service

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def on_startup(bot: Bot):
    """Действия при запуске бота"""
    # Устанавливаем команды бота для меню Telegram
    commands = [
        BotCommand(command="start", description="Начать работу / Главное меню"),
        BotCommand(command="statistic", description="Статистика по аккаунтам"),
    ]
    await bot.set_my_commands(commands)
    logger.info("Bot commands set")

    # Инициализируем сервис прокси
    init_proxy_service(agcm)
    logger.info("Proxy service initialized")

    # Создаём листы для номеров если их нет
    await number_service.ensure_sheets_exist()
    logger.info("Number sheets initialized")

    # Предзагрузка аккаунтов в кэш (удаляются из "Базы" сразу)
    logger.info("Preloading accounts into cache...")
    await account_cache.preload_all()

    # Запуск фоновых задач (запись в Sheets, автоподтверждение)
    await account_cache.start_background_tasks()

    if settings.WEBHOOK_URL:
        webhook_url = f"{settings.WEBHOOK_URL}{settings.WEBHOOK_PATH}"
        await bot.set_webhook(
            url=webhook_url,
            drop_pending_updates=True,
        )
        logger.info(f"Webhook set to {webhook_url}")


async def on_shutdown(bot: Bot):
    """Действия при остановке бота"""
    # Корректное завершение кэша (сохранение состояния, flush буферов)
    await account_cache.shutdown()

    if settings.WEBHOOK_URL:
        await bot.delete_webhook()
    await bot.session.close()
    logger.info("Bot stopped")


def create_dispatcher() -> Dispatcher:
    """Создание и настройка диспетчера"""
    dp = Dispatcher(storage=MemoryStorage())

    # Регистрация middleware
    dp.message.middleware(WhitelistMiddleware())
    dp.callback_query.middleware(WhitelistMiddleware())

    # Регистрация роутеров
    dp.include_router(start.router)
    dp.include_router(admin.router)
    dp.include_router(account_flow.router)
    dp.include_router(feedback.router)
    dp.include_router(statistic.router)
    dp.include_router(proxy.router)
    dp.include_router(numbers.router)

    return dp


async def main_polling():
    """Запуск в режиме polling (для разработки)"""
    bot = Bot(
        token=settings.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    dp = create_dispatcher()

    # Регистрируем startup/shutdown для polling режима тоже
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    logger.info("Starting bot in polling mode...")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


def main_webhook():
    """Запуск в режиме webhook (для Render.com)"""
    bot = Bot(
        token=settings.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    dp = create_dispatcher()

    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    app = web.Application()

    webhook_requests_handler = SimpleRequestHandler(
        dispatcher=dp,
        bot=bot,
    )
    webhook_requests_handler.register(app, path=settings.WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)

    # Render.com использует PORT из окружения
    port = int(os.environ.get("PORT", 10000))
    logger.info(f"Starting bot in webhook mode on port {port}...")
    web.run_app(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    if settings.WEBHOOK_URL:
        main_webhook()
    else:
        asyncio.run(main_polling())
