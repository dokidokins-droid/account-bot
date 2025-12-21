import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand

from bot.config import settings
from bot.handlers import start, admin, account_flow, feedback, statistic, proxy, numbers, email_flow
from bot.middlewares.auth import WhitelistMiddleware
from bot.services.account_service import account_cache
from bot.services.proxy_service import init_proxy_service, get_proxy_service
from bot.services.sheets_service import agcm
from bot.services.number_service import number_service, number_cache
from bot.services.email_service import email_service

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

    # Инициализируем сервис прокси и запускаем очистку резерваций
    proxy_service = init_proxy_service(agcm)
    await proxy_service.start_cleanup_task()
    logger.info("Proxy service initialized with cleanup task")

    # Создаём листы для номеров если их нет
    await number_service.ensure_sheets_exist()
    logger.info("Number sheets initialized")

    # Предзагрузка аккаунтов в кэш (удаляются из "Базы" сразу)
    logger.info("Preloading accounts into cache...")
    await account_cache.preload_all()

    # Предзагрузка почт в кэш
    logger.info("Preloading emails into cache...")
    await email_service.preload_all()

    # Предзагрузка номеров в кэш
    logger.info("Preloading numbers into cache...")
    await number_cache.preload()

    # Запуск фоновых задач (запись в Sheets, автоподтверждение, сохранение состояния)
    await account_cache.start_background_tasks()
    await email_service.start_background_tasks()
    await number_cache.start_background_tasks()


async def on_shutdown(bot: Bot):
    """Действия при остановке бота"""
    # Останавливаем фоновые задачи прокси
    try:
        await get_proxy_service().stop_cleanup_task()
    except RuntimeError:
        pass  # Сервис не был инициализирован

    # Корректное завершение кэшей (сохранение состояния, flush буферов)
    await account_cache.shutdown()
    await email_service.shutdown()
    await number_cache.shutdown()

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
    dp.include_router(email_flow.router)

    return dp


async def main():
    """Запуск бота в режиме polling"""
    bot = Bot(
        token=settings.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    dp = create_dispatcher()

    # Регистрируем startup/shutdown
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    logger.info("Starting bot in polling mode...")

    # Удаляем webhook если он был установлен ранее
    try:
        webhook_info = await bot.get_webhook_info()
        if webhook_info.url:
            logger.warning(f"Active webhook detected: {webhook_info.url}")
            logger.info("Deleting webhook...")
            await bot.delete_webhook(drop_pending_updates=True)
            logger.info("Webhook deleted successfully")
    except Exception as e:
        logger.error(f"Error checking/deleting webhook: {e}")

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
