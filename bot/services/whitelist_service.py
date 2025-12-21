"""Сервис для управления whitelist пользователей (внутреннее хранение)"""
import json
import logging
from pathlib import Path
from typing import Optional, Dict, List
from dataclasses import dataclass, asdict

from bot.models.user import User

logger = logging.getLogger(__name__)

# Путь к файлу whitelist
WHITELIST_FILE = Path(__file__).parent.parent.parent / "data" / "whitelist.json"


class WhitelistService:
    """
    Сервис для работы с whitelist пользователей.
    Хранит данные локально в JSON файле.
    """

    def __init__(self):
        # {telegram_id: {"stage": str, "is_approved": bool}}
        self._users: Dict[int, dict] = {}
        self._load()

    def _load(self) -> None:
        """Загрузить whitelist из файла"""
        try:
            if WHITELIST_FILE.exists():
                with open(WHITELIST_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    # Конвертируем ключи обратно в int
                    self._users = {int(k): v for k, v in data.items()}
                logger.info(f"Whitelist loaded: {len(self._users)} users")
            else:
                self._users = {}
                self._save()
                logger.info("Created new whitelist file")
        except Exception as e:
            logger.error(f"Error loading whitelist: {e}")
            self._users = {}

    def _save(self) -> None:
        """Сохранить whitelist в файл"""
        try:
            WHITELIST_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(WHITELIST_FILE, "w", encoding="utf-8") as f:
                json.dump(self._users, f, ensure_ascii=False, indent=2)
            logger.debug(f"Whitelist saved: {len(self._users)} users")
        except Exception as e:
            logger.error(f"Error saving whitelist: {e}")

    def get_user(self, telegram_id: int) -> Optional[User]:
        """Получить пользователя по Telegram ID"""
        user_data = self._users.get(telegram_id)
        if user_data:
            return User(
                telegram_id=telegram_id,
                stage=user_data.get("stage", ""),
                is_approved=user_data.get("is_approved", False),
            )
        return None

    def add_user(self, user: User) -> None:
        """Добавить пользователя в whitelist"""
        self._users[user.telegram_id] = {
            "stage": user.stage,
            "is_approved": user.is_approved,
        }
        self._save()
        logger.info(f"User {user.telegram_id} added to whitelist (stage: {user.stage})")

    def approve_user(self, telegram_id: int) -> bool:
        """Одобрить пользователя"""
        if telegram_id in self._users:
            self._users[telegram_id]["is_approved"] = True
            self._save()
            logger.info(f"User {telegram_id} approved")
            return True
        return False

    def reject_user(self, telegram_id: int) -> bool:
        """Отклонить и удалить пользователя"""
        if telegram_id in self._users:
            del self._users[telegram_id]
            self._save()
            logger.info(f"User {telegram_id} rejected and removed")
            return True
        return False

    def get_all_users(self) -> List[User]:
        """Получить всех пользователей"""
        return [
            User(
                telegram_id=tid,
                stage=data.get("stage", ""),
                is_approved=data.get("is_approved", False),
            )
            for tid, data in self._users.items()
        ]

    def get_pending_users(self) -> List[User]:
        """Получить пользователей, ожидающих одобрения"""
        return [
            User(
                telegram_id=tid,
                stage=data.get("stage", ""),
                is_approved=False,
            )
            for tid, data in self._users.items()
            if not data.get("is_approved", False)
        ]

    def import_users(self, users: List[dict]) -> int:
        """
        Импортировать пользователей из внешнего источника.

        Args:
            users: Список словарей с ключами telegram_id, stage, is_approved

        Returns:
            Количество импортированных пользователей
        """
        count = 0
        for user_data in users:
            tid = user_data.get("telegram_id")
            if tid and tid not in self._users:
                self._users[tid] = {
                    "stage": user_data.get("stage", ""),
                    "is_approved": user_data.get("is_approved", False),
                }
                count += 1

        if count > 0:
            self._save()
            logger.info(f"Imported {count} users to whitelist")

        return count


# Глобальный экземпляр сервиса
whitelist_service = WhitelistService()
