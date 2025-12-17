import logging
from typing import Callable, Dict, Any, Awaitable

from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery, TelegramObject

from bot.services.sheets_service import sheets_service
from bot.config import settings

logger = logging.getLogger(__name__)


class WhitelistMiddleware(BaseMiddleware):
    """Middleware для проверки доступа пользователя"""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        user_id = None

        if isinstance(event, Message):
            user_id = event.from_user.id
            # Пропускаем /start для новых пользователей
            if event.text and event.text.startswith("/start"):
                return await handler(event, data)

        elif isinstance(event, CallbackQuery):
            user_id = event.from_user.id
            # Пропускаем callback для админа (одобрение заявок)
            if user_id == settings.ADMIN_ID:
                return await handler(event, data)

            # Пропускаем feedback callbacks (они могут приходить без состояния)
            if event.data and event.data.startswith("fb:"):
                return await handler(event, data)

        if user_id:
            try:
                user = await sheets_service.get_user_by_telegram_id(user_id)

                if not user or not user.is_approved:
                    # Пользователь не авторизован
                    if isinstance(event, Message):
                        await event.answer(
                            "❌ У вас нет доступа.\n\n"
                            "Используйте /start для регистрации."
                        )
                    elif isinstance(event, CallbackQuery):
                        await event.answer(
                            "❌ У вас нет доступа",
                            show_alert=True,
                        )
                    return

            except Exception as e:
                logger.error(f"Error checking whitelist: {e}")
                # При ошибке пропускаем (чтобы не блокировать всех)
                return await handler(event, data)

        return await handler(event, data)
