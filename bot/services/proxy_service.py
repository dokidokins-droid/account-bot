"""
Optimized Proxy Service with batch updates and reservation system.

Key improvements:
1. PendingReservation system with TTL for multi-user safety
2. Batch update operations to reduce API calls
3. Cached proxy data with smart invalidation
4. Sorted by days_left (descending) for better UX
5. Support for multi-proxy selection
"""

import logging
import asyncio
import aiohttp
from typing import List, Optional, Dict, Set, Tuple
from datetime import datetime, date, timedelta
from collections import defaultdict
from dataclasses import dataclass, field
import time

import gspread_asyncio

from bot.config import settings
from bot.models.proxy import Proxy
from bot.models.enums import get_country_flag
from bot.services.sheets_service import sheets_rate_limiter

logger = logging.getLogger(__name__)

# Sheet name for proxies
PROXY_SHEET_NAME = "Прокси"

# Reservation TTL (auto-expire if not confirmed)
RESERVATION_TTL_SECONDS = 300  # 5 minutes


@dataclass
class PendingReservation:
    """
    Pending proxy reservation with TTL.

    Prevents race conditions when multiple users select proxies simultaneously.
    """
    row_index: int
    resource: str
    user_id: int
    expires_at: float  # monotonic time

    @property
    def is_expired(self) -> bool:
        """Check if reservation has expired"""
        return time.monotonic() > self.expires_at

    @classmethod
    def create(cls, row_index: int, resource: str, user_id: int) -> "PendingReservation":
        """Create new reservation with TTL"""
        return cls(
            row_index=row_index,
            resource=resource,
            user_id=user_id,
            expires_at=time.monotonic() + RESERVATION_TTL_SECONDS
        )


@dataclass
class ProxyCache:
    """
    Cache for proxy data to reduce API calls.

    Invalidates automatically after TTL or on updates.
    """
    proxies: List[Proxy] = field(default_factory=list)
    cached_at: float = 0.0
    ttl_seconds: float = 60.0  # Cache for 1 minute

    @property
    def is_valid(self) -> bool:
        """Check if cache is still valid"""
        return (time.monotonic() - self.cached_at) < self.ttl_seconds

    def update(self, proxies: List[Proxy]) -> None:
        """Update cache with new data"""
        self.proxies = proxies
        self.cached_at = time.monotonic()

    def invalidate(self) -> None:
        """Force cache invalidation"""
        self.cached_at = 0.0


def parse_date(date_str: str) -> date:
    """Parse date in formats dd.mm.yy or YYYY-MM-DD"""
    if not date_str:
        return date.today()

    # Try new format dd.mm.yy
    try:
        return datetime.strptime(date_str, "%d.%m.%y").date()
    except ValueError:
        pass

    # Try old format YYYY-MM-DD
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return date.today()


class ProxyService:
    """
    Optimized service for working with proxies.

    Features:
    - Batch updates to reduce API calls
    - Pending reservation system with TTL
    - Smart caching with invalidation
    - Sorted results by days_left (descending)
    - Multi-proxy selection support
    """

    def __init__(self, agcm):
        self.agcm = agcm

        # Pending reservations: {row_index: PendingReservation}
        self._pending: Dict[int, PendingReservation] = {}
        self._pending_lock = asyncio.Lock()

        # Cache for all proxies
        self._cache = ProxyCache()
        self._cache_lock = asyncio.Lock()

        # Background task for cleanup
        self._cleanup_task: Optional[asyncio.Task] = None

    async def start_cleanup_task(self) -> None:
        """Start background task for cleaning expired reservations"""
        if self._cleanup_task is None:
            self._cleanup_task = asyncio.create_task(self._cleanup_expired_reservations())
            logger.info("Started proxy reservation cleanup task")

    async def stop_cleanup_task(self) -> None:
        """Stop background cleanup task"""
        if self._cleanup_task is not None:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            self._cleanup_task = None
            logger.info("Stopped proxy reservation cleanup task")

    async def _cleanup_expired_reservations(self) -> None:
        """Periodically cleanup expired reservations"""
        while True:
            try:
                await asyncio.sleep(60)  # Check every minute

                async with self._pending_lock:
                    expired_keys = [
                        row_idx for row_idx, res in self._pending.items()
                        if res.is_expired
                    ]
                    for row_idx in expired_keys:
                        del self._pending[row_idx]

                    if expired_keys:
                        logger.info(f"Cleaned up {len(expired_keys)} expired proxy reservations")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in cleanup task: {e}")

    async def _get_client(self):
        """Get authorized client (rate-limited)"""
        async with sheets_rate_limiter:
            return await self.agcm.authorize()

    async def _get_worksheet(self):
        """Get worksheet for proxies (rate-limited)"""
        agc = await self._get_client()
        async with sheets_rate_limiter:
            ss = await agc.open_by_key(settings.SPREADSHEET_ACCOUNTS)
        try:
            async with sheets_rate_limiter:
                ws = await ss.worksheet(PROXY_SHEET_NAME)
        except gspread_asyncio.gspread.exceptions.WorksheetNotFound:
            # Create sheet if not exists
            async with sheets_rate_limiter:
                ws = await ss.add_worksheet(PROXY_SHEET_NAME, rows=1000, cols=10)
            # Add headers
            async with sheets_rate_limiter:
                await ws.append_row(
                    ["proxy", "country", "added_date", "expires_date", "used_for", "proxy_type"],
                    value_input_option="USER_ENTERED",
                )
        return ws

    # === Country detection by IP ===

    async def get_country_by_ip(self, ip: str) -> str:
        """Detect country by IP via ip-api.com"""
        try:
            async with aiohttp.ClientSession() as session:
                url = f"http://ip-api.com/json/{ip}?fields=countryCode"
                async with session.get(url, timeout=10) as response:
                    if response.status == 200:
                        data = await response.json()
                        country_code = data.get("countryCode", "UNKNOWN")
                        return country_code if country_code else "UNKNOWN"
        except Exception as e:
            logger.error(f"Error getting country for IP {ip}: {e}")
        return "UNKNOWN"

    def extract_ip(self, proxy: str) -> str:
        """Extract IP from proxy string"""
        parts = proxy.split(":")
        return parts[0] if parts else proxy

    # === Add proxies ===

    async def add_proxies(
        self,
        proxies: List[str],
        resources: List[str],
        duration_days: int,
        proxy_type: str = "http",
    ) -> List[Dict]:
        """
        Add list of proxies to the table.

        Optimized: batch operations + parallel country detection.

        Args:
            proxies: List of proxy strings
            resources: List of resources the proxies are used for
            duration_days: Expiration period in days
            proxy_type: Proxy type (http or socks5)
        """
        ws = await self._get_worksheet()
        results = []
        today = date.today()
        expires = today + timedelta(days=duration_days)

        # Format resources as comma-separated string
        used_for_str = ",".join([r.lower() for r in resources])

        # Filter empty strings
        valid_proxies = [p.strip() for p in proxies if p.strip()]

        if not valid_proxies:
            return []

        # Detect countries in parallel for all IPs
        async def get_country(proxy_str: str) -> tuple:
            ip = self.extract_ip(proxy_str)
            country = await self.get_country_by_ip(ip)
            return proxy_str, country

        # Limit parallelism to avoid bans
        semaphore = asyncio.Semaphore(5)

        async def limited_get_country(proxy_str: str) -> tuple:
            async with semaphore:
                return await get_country(proxy_str)

        # Get all countries in parallel
        country_tasks = [limited_get_country(p) for p in valid_proxies]
        country_results = await asyncio.gather(*country_tasks)
        proxy_countries = {proxy: country for proxy, country in country_results}

        # Format all rows for batch add
        rows_to_add = []
        for proxy_str in valid_proxies:
            country = proxy_countries.get(proxy_str, "UNKNOWN")

            row_data = [
                proxy_str,
                country,
                today.strftime("%d.%m.%y"),
                expires.strftime("%d.%m.%y"),
                used_for_str,
                proxy_type,
            ]
            rows_to_add.append(row_data)

            results.append({
                "proxy": proxy_str,
                "country": country,
                "country_flag": get_country_flag(country),
                "expires": expires.strftime("%d.%m.%y"),
            })

        # Batch add all rows in one API request
        if rows_to_add:
            # Find last FILLED row (ignore empty rows)
            async with sheets_rate_limiter:
                all_values = await ws.get_all_values()

            last_filled_row = 1  # At least header
            for i, row in enumerate(all_values, start=1):
                if row and any(cell.strip() for cell in row if cell):
                    last_filled_row = i

            # Write to specific range after last filled row
            start_row = last_filled_row + 1
            end_row = start_row + len(rows_to_add) - 1
            range_str = f"A{start_row}:F{end_row}"

            async with sheets_rate_limiter:
                await ws.update(range_str, rows_to_add, value_input_option="USER_ENTERED")

            logger.info(f"Batch added {len(rows_to_add)} proxies to range {range_str}")

            # Invalidate cache after adding
            async with self._cache_lock:
                self._cache.invalidate()

        return results

    # === Get proxies (with caching) ===

    async def get_all_proxies(self, force_refresh: bool = False) -> List[Proxy]:
        """
        Get all proxies from table (with caching).

        Args:
            force_refresh: Force cache refresh
        """
        async with self._cache_lock:
            # Return cached if valid and not forcing refresh
            if not force_refresh and self._cache.is_valid:
                logger.debug("Returning cached proxy list")
                return self._cache.proxies

        # Fetch from API
        ws = await self._get_worksheet()
        async with sheets_rate_limiter:
            all_values = await ws.get_all_values()

        proxies = []
        # Skip header
        for idx, row in enumerate(all_values[1:], start=2):
            if not row or not row[0]:
                continue

            try:
                proxy = Proxy(
                    proxy=row[0],
                    country=row[1] if len(row) > 1 else "UNKNOWN",
                    added_date=parse_date(row[2] if len(row) > 2 else ""),
                    expires_date=parse_date(row[3] if len(row) > 3 else ""),
                    used_for=Proxy.parse_used_for(row[4] if len(row) > 4 else ""),
                    row_index=idx,
                    proxy_type=row[5] if len(row) > 5 and row[5] else "http",
                )
                proxies.append(proxy)
            except Exception as e:
                logger.error(f"Error parsing proxy row {idx}: {e}")
                continue

        # Update cache
        async with self._cache_lock:
            self._cache.update(proxies)

        logger.debug(f"Fetched and cached {len(proxies)} proxies")
        return proxies

    async def get_available_proxies(self, resource: str, force_refresh: bool = False) -> List[Proxy]:
        """
        Get available proxies for resource (not used and not expired).

        Sorted by days_left descending (more days = higher priority).
        """
        all_proxies = await self.get_all_proxies(force_refresh=force_refresh)

        available = []
        for proxy in all_proxies:
            # Skip expired
            if proxy.is_expired:
                continue
            # Skip already used for this resource
            if proxy.is_used_for(resource):
                continue
            # Skip pending reservations for other users/resources
            if await self._is_reserved(proxy.row_index, resource):
                continue

            available.append(proxy)

        # Sort by days_left descending (more days first)
        available.sort(key=lambda p: p.days_left, reverse=True)

        return available

    async def _is_reserved(self, row_index: int, resource: str) -> bool:
        """Check if proxy is reserved by someone else"""
        async with self._pending_lock:
            reservation = self._pending.get(row_index)
            if reservation is None:
                return False

            # If expired, remove and return False
            if reservation.is_expired:
                del self._pending[row_index]
                return False

            # Reserved if for different resource
            return reservation.resource.lower() != resource.lower()

    async def get_countries_with_counts(self, resource: str) -> Dict[str, int]:
        """Get dictionary of countries with count of available proxies"""
        proxies = await self.get_available_proxies(resource)

        counts = defaultdict(int)
        for proxy in proxies:
            counts[proxy.country] += 1

        return dict(counts)

    async def get_proxies_by_country(
        self,
        resource: str,
        country: str,
        limit: Optional[int] = None
    ) -> List[Proxy]:
        """
        Get proxies for resource by country.

        Args:
            resource: Resource name
            country: Country code
            limit: Optional limit on number of proxies returned
        """
        proxies = await self.get_available_proxies(resource)
        filtered = [p for p in proxies if p.country.upper() == country.upper()]

        if limit is not None:
            filtered = filtered[:limit]

        return filtered

    async def get_proxies_for_user(
        self,
        resource: str,
        country: str,
        user_id: int
    ) -> Tuple[List[Proxy], Set[int]]:
        """
        Get proxies for user with their current selections.

        Returns proxies available for selection (excluding other users' reservations)
        and set of row indices that current user has reserved.

        Args:
            resource: Resource name
            country: Country code
            user_id: Current user ID

        Returns:
            Tuple of (available_proxies, user_reserved_rows)
        """
        all_proxies = await self.get_all_proxies()

        available = []
        user_reserved = set()

        async with self._pending_lock:
            # Get user's current reservations
            for row_idx, reservation in self._pending.items():
                if reservation.user_id == user_id and not reservation.is_expired:
                    user_reserved.add(row_idx)

            for proxy in all_proxies:
                # Skip if not matching country
                if proxy.country.upper() != country.upper():
                    continue

                # Skip expired
                if proxy.is_expired:
                    continue

                # Skip already used for this resource
                if proxy.is_used_for(resource):
                    continue

                # Check pending reservations
                reservation = self._pending.get(proxy.row_index)
                if reservation is not None:
                    if reservation.is_expired:
                        del self._pending[proxy.row_index]
                    elif reservation.user_id != user_id:
                        # Reserved by another user - skip
                        continue

                available.append(proxy)

        # Sort by days_left descending
        available.sort(key=lambda p: p.days_left, reverse=True)

        return available, user_reserved

    async def get_user_reservations(self, user_id: int) -> List[int]:
        """Get list of row indices reserved by user"""
        async with self._pending_lock:
            result = []
            for row_idx, reservation in list(self._pending.items()):
                if reservation.is_expired:
                    del self._pending[row_idx]
                    continue
                if reservation.user_id == user_id:
                    result.append(row_idx)
            return result

    # === Reservation system ===

    async def reserve_proxies(
        self,
        row_indices: List[int],
        resource: str,
        user_id: int
    ) -> List[int]:
        """
        Reserve multiple proxies for user.

        Returns list of successfully reserved row indices.
        """
        reserved = []

        async with self._pending_lock:
            for row_idx in row_indices:
                # Check if already reserved
                existing = self._pending.get(row_idx)
                if existing is not None:
                    if existing.is_expired:
                        # Expired, can take over
                        del self._pending[row_idx]
                    elif existing.user_id == user_id and existing.resource.lower() == resource.lower():
                        # Same user, same resource - extend TTL
                        self._pending[row_idx] = PendingReservation.create(row_idx, resource, user_id)
                        reserved.append(row_idx)
                        continue
                    else:
                        # Reserved by someone else
                        continue

                # Create new reservation
                self._pending[row_idx] = PendingReservation.create(row_idx, resource, user_id)
                reserved.append(row_idx)

        logger.info(f"User {user_id} reserved {len(reserved)}/{len(row_indices)} proxies for {resource}")
        return reserved

    async def cancel_reservation(self, row_index: int, user_id: int) -> bool:
        """
        Cancel reservation for a proxy.

        Returns True if cancelled, False if not found or not owned.
        """
        async with self._pending_lock:
            reservation = self._pending.get(row_index)
            if reservation is None:
                return False

            if reservation.user_id != user_id:
                logger.warning(f"User {user_id} tried to cancel reservation owned by {reservation.user_id}")
                return False

            del self._pending[row_index]
            logger.debug(f"Cancelled reservation for row {row_index}")
            return True

    async def cancel_all_reservations(self, user_id: int) -> int:
        """
        Cancel all reservations for a user.

        Returns count of cancelled reservations.
        """
        async with self._pending_lock:
            to_cancel = [
                row_idx for row_idx, res in self._pending.items()
                if res.user_id == user_id
            ]
            for row_idx in to_cancel:
                del self._pending[row_idx]

            if to_cancel:
                logger.info(f"Cancelled {len(to_cancel)} reservations for user {user_id}")

            return len(to_cancel)

    # === Take proxies (batch update) ===

    async def take_proxies_batch(
        self,
        row_indices: List[int],
        resource: str,
        user_id: int
    ) -> Tuple[List[Proxy], List[int]]:
        """
        Take multiple proxies at once with batch update.

        This is the MAIN optimization - reduces N API calls to 2:
        1. Get current data (1 call)
        2. Batch update all proxies (1 call)

        Args:
            row_indices: List of row indices to take
            resource: Resource name
            user_id: User ID taking the proxies

        Returns:
            Tuple of (successfully_taken_proxies, failed_row_indices)
        """
        if not row_indices:
            return [], []

        ws = await self._get_worksheet()

        # Step 1: Get current data for all rows (1 API call)
        async with sheets_rate_limiter:
            all_values = await ws.get_all_values()

        # Step 2: Process each proxy and prepare updates
        updates = []  # List of (row_index, new_used_for, proxy_object)
        taken = []
        failed = []

        for row_idx in row_indices:
            # Validate row exists
            if row_idx < 2 or row_idx > len(all_values):
                failed.append(row_idx)
                continue

            row = all_values[row_idx - 1]  # Convert to 0-based index

            if not row or not row[0]:
                failed.append(row_idx)
                continue

            # Check if already used for this resource
            used_for = Proxy.parse_used_for(row[4] if len(row) > 4 else "")
            if resource.lower() in [r.lower() for r in used_for]:
                logger.warning(f"Proxy at row {row_idx} already used for {resource}")
                failed.append(row_idx)
                continue

            # Check reservation
            async with self._pending_lock:
                reservation = self._pending.get(row_idx)
                if reservation is not None:
                    if reservation.is_expired:
                        del self._pending[row_idx]
                    elif reservation.user_id != user_id or reservation.resource.lower() != resource.lower():
                        logger.warning(f"Row {row_idx} reserved by another user/resource")
                        failed.append(row_idx)
                        continue

            # Prepare update
            used_for.append(resource.lower())
            new_used_for = ",".join(used_for)

            # Create proxy object
            proxy = Proxy(
                proxy=row[0],
                country=row[1] if len(row) > 1 else "UNKNOWN",
                added_date=parse_date(row[2] if len(row) > 2 else ""),
                expires_date=parse_date(row[3] if len(row) > 3 else ""),
                used_for=used_for,
                row_index=row_idx,
                proxy_type=row[5] if len(row) > 5 and row[5] else "http",
            )

            updates.append((row_idx, new_used_for))
            taken.append(proxy)

        # Step 3: Batch update all proxies (1 API call)
        if updates:
            # Build batch update data
            batch_data = []
            for row_idx, new_used_for in updates:
                # Column E = 5 (used_for)
                cell_range = f"E{row_idx}"
                batch_data.append({
                    "range": cell_range,
                    "values": [[new_used_for]]
                })

            # Execute batch update
            async with sheets_rate_limiter:
                await ws.batch_update(batch_data, value_input_option="USER_ENTERED")

            logger.info(f"User {user_id} took {len(taken)} proxies for {resource} (batch update)")

            # Clear reservations for taken proxies
            async with self._pending_lock:
                for row_idx, _ in updates:
                    self._pending.pop(row_idx, None)

            # Invalidate cache
            async with self._cache_lock:
                self._cache.invalidate()

        return taken, failed

    async def try_take_proxy(self, row_index: int, resource: str, user_id: int) -> Optional[Proxy]:
        """
        Take a single proxy (convenience method).

        Uses batch update internally for consistency.
        """
        taken, failed = await self.take_proxies_batch([row_index], resource, user_id)
        return taken[0] if taken else None

    async def get_proxy_by_row(self, row_index: int) -> Optional[Proxy]:
        """Get proxy by row index (rate-limited)"""
        try:
            ws = await self._get_worksheet()
            async with sheets_rate_limiter:
                row = await ws.row_values(row_index)

            if not row or not row[0]:
                return None

            return Proxy(
                proxy=row[0],
                country=row[1] if len(row) > 1 else "UNKNOWN",
                added_date=parse_date(row[2] if len(row) > 2 else ""),
                expires_date=parse_date(row[3] if len(row) > 3 else ""),
                used_for=Proxy.parse_used_for(row[4] if len(row) > 4 else ""),
                row_index=row_index,
                proxy_type=row[5] if len(row) > 5 and row[5] else "http",
            )
        except Exception as e:
            logger.error(f"Error getting proxy by row {row_index}: {e}")
            return None

    # === Statistics ===

    async def get_stats(self) -> Dict:
        """Get service statistics"""
        all_proxies = await self.get_all_proxies()

        async with self._pending_lock:
            pending_count = len(self._pending)
            # Clean up expired
            expired_keys = [
                row_idx for row_idx, res in self._pending.items()
                if res.is_expired
            ]
            for row_idx in expired_keys:
                del self._pending[row_idx]

        expired_count = sum(1 for p in all_proxies if p.is_expired)
        available_count = sum(1 for p in all_proxies if not p.is_expired)

        return {
            "total_proxies": len(all_proxies),
            "available": available_count,
            "expired": expired_count,
            "pending_reservations": pending_count,
            "cache_valid": self._cache.is_valid,
            "cache_age_seconds": round(time.monotonic() - self._cache.cached_at, 1),
        }


# Global service instance
_proxy_service: Optional[ProxyService] = None


def init_proxy_service(agcm):
    """Initialize proxy service"""
    global _proxy_service
    _proxy_service = ProxyService(agcm)
    return _proxy_service


def get_proxy_service() -> ProxyService:
    """Get proxy service instance"""
    if _proxy_service is None:
        raise RuntimeError("Proxy service not initialized. Call init_proxy_service first.")
    return _proxy_service
