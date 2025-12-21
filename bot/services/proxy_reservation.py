"""
Система резервации прокси для предотвращения race conditions.

Обеспечивает:
- Pending резервации с TTL (автоосвобождение после таймаута)
- Атомарные операции reserve/confirm/cancel
- Поддержку множественного выбора прокси
- Защиту от выдачи одного прокси разным пользователям
"""

import asyncio
import time
import logging
from typing import Dict, Set, Optional, List, Tuple
from dataclasses import dataclass, field
from collections import defaultdict

logger = logging.getLogger(__name__)


@dataclass
class PendingReservation:
    """Резервация прокси в памяти (до подтверждения)"""
    row_index: int
    user_id: int
    resource: str
    timestamp: float = field(default_factory=time.time)
    ttl: float = 300.0  # 5 минут по умолчанию


class ProxyReservationManager:
    """
    Менеджер резерваций прокси.

    Обеспечивает thread-safe резервацию прокси между:
    - Показом списка и подтверждением выбора
    - Множественными параллельными пользователями

    Паттерн использования:
    1. reserve() - резервируем прокси (без записи в Sheets)
    2. Пользователь подтверждает выбор
    3. confirm() - удаляем из pending после успешной записи

    Или:
    1. reserve()
    2. Пользователь отменяет или истекает TTL
    3. cancel() / автоочистка - освобождаем резервацию
    """

    def __init__(self, default_ttl: float = 300.0):
        self.default_ttl = default_ttl

        # row_index -> PendingReservation
        self._reservations: Dict[int, PendingReservation] = {}

        # user_id -> Set[row_index] (для быстрого поиска резерваций пользователя)
        self._user_reservations: Dict[int, Set[int]] = defaultdict(set)

        # Lock для thread-safe операций
        self._lock = asyncio.Lock()

        # Фоновая задача очистки
        self._cleanup_task: Optional[asyncio.Task] = None

    async def start_cleanup_task(self):
        """Запустить фоновую задачу очистки просроченных резерваций"""
        if self._cleanup_task is None or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())
            logger.info("Proxy reservation cleanup task started")

    async def stop_cleanup_task(self):
        """Остановить фоновую задачу"""
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            logger.info("Proxy reservation cleanup task stopped")

    async def _cleanup_loop(self):
        """Фоновый цикл очистки"""
        while True:
            try:
                await asyncio.sleep(30)  # Проверяем каждые 30 секунд
                await self._cleanup_expired()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in reservation cleanup loop: {e}")

    async def _cleanup_expired(self):
        """Удалить просроченные резервации"""
        async with self._lock:
            now = time.time()
            expired = []

            for row_index, reservation in self._reservations.items():
                if now - reservation.timestamp > reservation.ttl:
                    expired.append(row_index)

            for row_index in expired:
                reservation = self._reservations.pop(row_index)
                self._user_reservations[reservation.user_id].discard(row_index)
                logger.info(
                    f"Expired reservation: user={reservation.user_id} "
                    f"proxy_row={row_index} resource={reservation.resource}"
                )

            if expired:
                logger.debug(f"Cleaned up {len(expired)} expired reservations")

    async def is_reserved(self, row_index: int, exclude_user_id: Optional[int] = None) -> bool:
        """
        Проверить, зарезервирован ли прокси.

        Args:
            row_index: Индекс строки прокси
            exclude_user_id: Исключить резервации этого пользователя (для показа своих)

        Returns:
            True если зарезервирован (другим пользователем)
        """
        async with self._lock:
            if row_index not in self._reservations:
                return False

            reservation = self._reservations[row_index]
            now = time.time()

            # Проверяем срок действия
            if now - reservation.timestamp > reservation.ttl:
                # Просрочена - очищаем
                self._reservations.pop(row_index)
                self._user_reservations[reservation.user_id].discard(row_index)
                return False

            # Если это резервация текущего пользователя - не считаем занятой
            if exclude_user_id and reservation.user_id == exclude_user_id:
                return False

            return True

    async def reserve(
        self,
        row_index: int,
        user_id: int,
        resource: str,
        ttl: Optional[float] = None
    ) -> bool:
        """
        Зарезервировать прокси для пользователя.

        Args:
            row_index: Индекс строки прокси
            user_id: ID пользователя
            resource: Ресурс для которого берётся прокси
            ttl: Время жизни резервации (опционально)

        Returns:
            True если успешно зарезервировано, False если уже занято
        """
        async with self._lock:
            # Проверяем существующую резервацию
            if row_index in self._reservations:
                existing = self._reservations[row_index]
                now = time.time()

                # Если не просрочена и не наша - отказ
                if now - existing.timestamp <= existing.ttl:
                    if existing.user_id != user_id:
                        return False
                    # Наша резервация - обновляем timestamp
                    existing.timestamp = now
                    return True

                # Просрочена - очищаем
                self._user_reservations[existing.user_id].discard(row_index)

            # Создаём новую резервацию
            reservation = PendingReservation(
                row_index=row_index,
                user_id=user_id,
                resource=resource,
                timestamp=time.time(),
                ttl=ttl or self.default_ttl
            )

            self._reservations[row_index] = reservation
            self._user_reservations[user_id].add(row_index)

            logger.debug(
                f"Reserved proxy: user={user_id} row={row_index} "
                f"resource={resource} ttl={reservation.ttl}s"
            )
            return True

    async def cancel(self, row_index: int, user_id: int) -> bool:
        """
        Отменить резервацию (пользователь передумал).

        Returns:
            True если отменена, False если не найдена или чужая
        """
        async with self._lock:
            if row_index not in self._reservations:
                return False

            reservation = self._reservations[row_index]
            if reservation.user_id != user_id:
                return False

            self._reservations.pop(row_index)
            self._user_reservations[user_id].discard(row_index)

            logger.debug(f"Cancelled reservation: user={user_id} row={row_index}")
            return True

    async def cancel_user_reservations(self, user_id: int) -> int:
        """
        Отменить все резервации пользователя.

        Returns:
            Количество отменённых резерваций
        """
        async with self._lock:
            row_indices = list(self._user_reservations.get(user_id, set()))

            for row_index in row_indices:
                self._reservations.pop(row_index, None)

            self._user_reservations.pop(user_id, None)

            if row_indices:
                logger.debug(f"Cancelled {len(row_indices)} reservations for user={user_id}")

            return len(row_indices)

    async def confirm(self, row_index: int, user_id: int) -> bool:
        """
        Подтвердить резервацию (после успешной записи в Sheets).
        Удаляет из pending.

        Returns:
            True если подтверждена, False если не найдена или чужая
        """
        async with self._lock:
            if row_index not in self._reservations:
                return False

            reservation = self._reservations[row_index]
            if reservation.user_id != user_id:
                return False

            self._reservations.pop(row_index)
            self._user_reservations[user_id].discard(row_index)

            logger.debug(f"Confirmed reservation: user={user_id} row={row_index}")
            return True

    async def confirm_batch(self, row_indices: List[int], user_id: int) -> Tuple[List[int], List[int]]:
        """
        Подтвердить несколько резерваций.

        Returns:
            (confirmed_rows, failed_rows)
        """
        confirmed = []
        failed = []

        for row_index in row_indices:
            if await self.confirm(row_index, user_id):
                confirmed.append(row_index)
            else:
                failed.append(row_index)

        return confirmed, failed

    async def get_user_reservations(self, user_id: int) -> List[int]:
        """Получить все активные резервации пользователя"""
        async with self._lock:
            return list(self._user_reservations.get(user_id, set()))

    async def get_reserved_rows(self, exclude_user_id: Optional[int] = None) -> Set[int]:
        """
        Получить все зарезервированные row_index.

        Args:
            exclude_user_id: Исключить резервации этого пользователя

        Returns:
            Set индексов зарезервированных строк
        """
        async with self._lock:
            now = time.time()
            reserved = set()

            for row_index, reservation in self._reservations.items():
                # Пропускаем просроченные
                if now - reservation.timestamp > reservation.ttl:
                    continue
                # Пропускаем свои
                if exclude_user_id and reservation.user_id == exclude_user_id:
                    continue
                reserved.add(row_index)

            return reserved

    async def get_stats(self) -> dict:
        """Статистика резерваций (для мониторинга)"""
        async with self._lock:
            active_users = sum(1 for rows in self._user_reservations.values() if rows)
            return {
                "total_reservations": len(self._reservations),
                "active_users": active_users,
                "max_per_user": max(
                    (len(rows) for rows in self._user_reservations.values()),
                    default=0
                )
            }


# Глобальный singleton
_reservation_manager: Optional[ProxyReservationManager] = None


def get_reservation_manager() -> ProxyReservationManager:
    """Получить глобальный менеджер резерваций"""
    global _reservation_manager
    if _reservation_manager is None:
        _reservation_manager = ProxyReservationManager(default_ttl=300.0)
    return _reservation_manager


async def init_reservation_manager() -> ProxyReservationManager:
    """Инициализировать менеджер и запустить cleanup task"""
    manager = get_reservation_manager()
    await manager.start_cleanup_task()
    logger.info("Proxy reservation manager initialized")
    return manager
