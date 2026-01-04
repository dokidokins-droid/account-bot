"""
Сервис для отслеживания pending сообщений и их редактирования при автоподтверждении.

При выдаче ресурса (почты, аккаунта, номера) хэндлер регистрирует сообщение.
При автоподтверждении (через 10 минут) сервис редактирует сообщение,
убирая кнопки и добавляя статус.
"""
import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Dict, Optional, TYPE_CHECKING

from aiogram import Bot

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# Таймаут автоподтверждения (10 минут)
AUTO_CONFIRM_TIMEOUT = 600


@dataclass
class PendingMessage:
    """Информация о pending сообщении"""
    entity_type: str  # "email", "account", "number"
    entity_id: str  # ID сущности (email_id, account_id, number_id)
    chat_id: int
    message_id: int
    original_text: str
    issued_at: float = field(default_factory=time.time)


class PendingMessagesManager:
    """
    Менеджер pending сообщений.

    Отслеживает сообщения с кнопками feedback и редактирует их при автоподтверждении.
    """

    def __init__(self):
        # {entity_id: PendingMessage}
        self._messages: Dict[str, PendingMessage] = {}
        self._bot: Optional[Bot] = None
        self._check_task: Optional[asyncio.Task] = None

    def set_bot(self, bot: Bot) -> None:
        """Установить бота для редактирования сообщений"""
        self._bot = bot

    def register(
        self,
        entity_type: str,
        entity_id: str,
        chat_id: int,
        message_id: int,
        original_text: str,
    ) -> None:
        """
        Зарегистрировать pending сообщение.

        Вызывается из хэндлера после отправки сообщения с кнопками.
        """
        self._messages[entity_id] = PendingMessage(
            entity_type=entity_type,
            entity_id=entity_id,
            chat_id=chat_id,
            message_id=message_id,
            original_text=original_text,
        )
        logger.debug(f"Registered pending message: {entity_type}/{entity_id}")

    def unregister(self, entity_id: str) -> Optional[PendingMessage]:
        """
        Снять сообщение с отслеживания (при ручном feedback).

        Возвращает PendingMessage если было зарегистрировано.
        """
        msg = self._messages.pop(entity_id, None)
        if msg:
            logger.debug(f"Unregistered pending message: {entity_id}")
        return msg

    async def start_check_task(self) -> None:
        """Запустить задачу проверки просроченных сообщений"""
        if self._check_task is None or self._check_task.done():
            self._check_task = asyncio.create_task(self._check_loop())
            logger.info("Pending messages check task started")

    async def stop_check_task(self) -> None:
        """Остановить задачу проверки"""
        if self._check_task and not self._check_task.done():
            self._check_task.cancel()
            try:
                await self._check_task
            except asyncio.CancelledError:
                pass

    async def _check_loop(self) -> None:
        """Цикл проверки просроченных сообщений"""
        while True:
            try:
                await asyncio.sleep(60)  # Проверяем каждую минуту
                await self._process_expired()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Pending messages check error: {e}")

    async def _process_expired(self) -> None:
        """Обработать просроченные сообщения (автоподтверждение)"""
        if not self._bot:
            return

        now = time.time()
        expired = [
            entity_id
            for entity_id, msg in list(self._messages.items())
            if now - msg.issued_at > AUTO_CONFIRM_TIMEOUT
        ]

        for entity_id in expired:
            msg = self._messages.pop(entity_id, None)
            if not msg:
                continue

            await self._auto_confirm_message(msg)

    async def _auto_confirm_message(self, msg: PendingMessage) -> None:
        """Автоподтвердить сообщение - изменить текст и убрать кнопки"""
        try:
            # Формируем новый текст с добавлением статуса
            status_text = "✅ Хороший"  # Автоподтверждение всегда "good"
            auto_label = "⏰ <i>Авто</i>"

            # Добавляем статус к тексту
            new_text = f"{msg.original_text}\n\n{status_text} {auto_label}"

            # Редактируем сообщение
            await self._bot.edit_message_text(
                chat_id=msg.chat_id,
                message_id=msg.message_id,
                text=new_text,
                parse_mode="HTML",
                reply_markup=None,  # Убираем кнопки
            )

            logger.info(
                f"Auto-confirmed message: {msg.entity_type}/{msg.entity_id} "
                f"(chat={msg.chat_id}, msg={msg.message_id})"
            )

        except Exception as e:
            # Сообщение могло быть удалено или недоступно
            logger.warning(f"Failed to auto-confirm message {msg.entity_id}: {e}")

    def get_stats(self) -> Dict[str, int]:
        """Статистика по pending сообщениям"""
        stats = {"total": len(self._messages)}
        for msg in self._messages.values():
            key = msg.entity_type
            stats[key] = stats.get(key, 0) + 1
        return stats


# Глобальный менеджер
pending_messages = PendingMessagesManager()
