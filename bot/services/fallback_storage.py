import json
import logging
from typing import Dict, List
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

FALLBACK_FILE = Path("data/fallback.json")


class FallbackStorage:
    """Локальное хранилище при недоступности Google Sheets"""

    def __init__(self):
        self._ensure_file_exists()

    def _ensure_file_exists(self):
        """Создать файл если не существует"""
        FALLBACK_FILE.parent.mkdir(parents=True, exist_ok=True)
        if not FALLBACK_FILE.exists():
            self._save_data(
                {
                    "pending_users": [],
                    "issued_accounts": [],
                    "pending_feedback": [],
                }
            )

    def _load_data(self) -> Dict:
        """Загрузить данные из файла"""
        try:
            with open(FALLBACK_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading fallback data: {e}")
            return {"pending_users": [], "issued_accounts": [], "pending_feedback": []}

    def _save_data(self, data: Dict):
        """Сохранить данные в файл"""
        try:
            with open(FALLBACK_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Error saving fallback data: {e}")

    async def add_pending_user(self, telegram_id: int, stage: str):
        """Добавить пользователя в очередь на одобрение"""
        data = self._load_data()
        data["pending_users"].append(
            {
                "telegram_id": telegram_id,
                "stage": stage,
                "timestamp": datetime.now().isoformat(),
            }
        )
        self._save_data(data)
        logger.info(f"Added pending user to fallback: {telegram_id}")

    async def add_issued_account(
        self,
        account_data: List[str],
        region: str,
        employee_stage: str,
        resource: str,
        gender: str,
    ) -> str:
        """Добавить выданный аккаунт в локальное хранилище"""
        data = self._load_data()
        account_id = f"local_{len(data['issued_accounts']) + 1}"

        data["issued_accounts"].append(
            {
                "id": account_id,
                "date": datetime.now().isoformat(),
                "data": account_data,
                "region": region,
                "employee": employee_stage,
                "resource": resource,
                "gender": gender,
                "status": None,
            }
        )
        self._save_data(data)
        logger.info(f"Added issued account to fallback: {account_id}")
        return account_id

    async def add_pending_feedback(self, account_id: str, status: str):
        """Добавить отложенный feedback для синхронизации"""
        data = self._load_data()
        data["pending_feedback"].append(
            {
                "account_id": account_id,
                "status": status,
                "timestamp": datetime.now().isoformat(),
            }
        )
        self._save_data(data)
        logger.info(f"Added pending feedback to fallback: {account_id} -> {status}")

    def get_pending_data(self) -> Dict:
        """Получить все отложенные данные для синхронизации"""
        return self._load_data()

    def clear_synced_data(self):
        """Очистить синхронизированные данные"""
        self._save_data(
            {
                "pending_users": [],
                "issued_accounts": [],
                "pending_feedback": [],
            }
        )
        logger.info("Cleared fallback storage after sync")


fallback_storage = FallbackStorage()
