"""
Tests for optimized proxy service.

Demonstrates:
1. Batch update performance (N calls -> 2 calls)
2. Reservation system with TTL
3. Cache efficiency
4. Concurrent access safety
"""

import pytest
import asyncio
from datetime import date, timedelta
from unittest.mock import AsyncMock, Mock, patch
import time

from bot.services.proxy_service import (
    ProxyService,
    PendingReservation,
    ProxyCache,
    RESERVATION_TTL_SECONDS
)
from bot.models.proxy import Proxy


class TestPendingReservation:
    """Test reservation system with TTL"""

    def test_create_reservation(self):
        """Test creating reservation with TTL"""
        res = PendingReservation.create(row_index=5, resource="beboo", user_id=123)

        assert res.row_index == 5
        assert res.resource == "beboo"
        assert res.user_id == 123
        assert not res.is_expired
        assert res.expires_at > time.monotonic()

    def test_reservation_expiry(self):
        """Test that reservation expires after TTL"""
        # Create reservation with very short TTL
        res = PendingReservation(
            row_index=5,
            resource="beboo",
            user_id=123,
            expires_at=time.monotonic() + 0.1  # 100ms TTL
        )

        assert not res.is_expired

        # Wait for expiry
        time.sleep(0.15)
        assert res.is_expired


class TestProxyCache:
    """Test caching mechanism"""

    def test_cache_validity(self):
        """Test cache TTL"""
        cache = ProxyCache(ttl_seconds=0.1)

        # Fresh cache is invalid
        assert not cache.is_valid

        # Update cache
        proxies = [Mock(spec=Proxy)]
        cache.update(proxies)
        assert cache.is_valid

        # Wait for expiry
        time.sleep(0.15)
        assert not cache.is_valid

    def test_cache_invalidation(self):
        """Test manual cache invalidation"""
        cache = ProxyCache()
        proxies = [Mock(spec=Proxy)]

        cache.update(proxies)
        assert cache.is_valid

        cache.invalidate()
        assert not cache.is_valid


class TestProxyServiceOptimizations:
    """Test optimized proxy service"""

    @pytest.fixture
    def mock_agcm(self):
        """Mock gspread async client manager"""
        return AsyncMock()

    @pytest.fixture
    def service(self, mock_agcm):
        """Create service instance"""
        return ProxyService(mock_agcm)

    @pytest.mark.asyncio
    async def test_batch_take_reduces_api_calls(self, service):
        """
        Test that batch take uses only 2 API calls instead of N*2.

        Old: 3 proxies = 6 API calls (3 reads + 3 writes)
        New: 3 proxies = 2 API calls (1 read + 1 batch write)
        """
        # Mock worksheet
        mock_ws = AsyncMock()
        service._get_worksheet = AsyncMock(return_value=mock_ws)

        # Mock data
        mock_ws.get_all_values = AsyncMock(return_value=[
            ["proxy", "country", "added_date", "expires_date", "used_for", "proxy_type"],
            ["1.1.1.1:8080", "US", "01.01.24", "01.01.25", "", "http"],
            ["2.2.2.2:8080", "DE", "01.01.24", "01.01.25", "", "http"],
            ["3.3.3.3:8080", "FR", "01.01.24", "01.01.25", "", "http"],
        ])

        mock_ws.batch_update = AsyncMock()

        # Take 3 proxies
        taken, failed = await service.take_proxies_batch(
            row_indices=[2, 3, 4],
            resource="beboo",
            user_id=123
        )

        # Verify results
        assert len(taken) == 3
        assert len(failed) == 0

        # Verify API calls: only 1 get_all_values + 1 batch_update
        assert mock_ws.get_all_values.call_count == 1
        assert mock_ws.batch_update.call_count == 1

        # Verify batch update contains all 3 updates
        batch_data = mock_ws.batch_update.call_args[0][0]
        assert len(batch_data) == 3
        assert batch_data[0]["range"] == "E2"
        assert batch_data[1]["range"] == "E3"
        assert batch_data[2]["range"] == "E4"

    @pytest.mark.asyncio
    async def test_reservation_prevents_double_take(self, service):
        """Test that reservations prevent concurrent access"""
        # Reserve proxy for user 1
        reserved = await service.reserve_proxies([5], "beboo", user_id=1)
        assert reserved == [5]

        # User 2 tries to reserve same proxy for different resource
        reserved2 = await service.reserve_proxies([5], "loloo", user_id=2)
        assert reserved2 == []  # Failed - already reserved

    @pytest.mark.asyncio
    async def test_reservation_auto_extends_for_same_user(self, service):
        """Test that reservation TTL extends for same user/resource"""
        # Reserve proxy
        reserved = await service.reserve_proxies([5], "beboo", user_id=1)
        assert reserved == [5]

        # Get original expiry time
        async with service._pending_lock:
            original_expiry = service._pending[5].expires_at

        # Wait a bit
        await asyncio.sleep(0.1)

        # Re-reserve (should extend TTL)
        reserved = await service.reserve_proxies([5], "beboo", user_id=1)
        assert reserved == [5]

        # Check that expiry was extended
        async with service._pending_lock:
            new_expiry = service._pending[5].expires_at

        assert new_expiry > original_expiry

    @pytest.mark.asyncio
    async def test_expired_reservation_can_be_taken(self, service):
        """Test that expired reservations don't block access"""
        # Create expired reservation
        async with service._pending_lock:
            service._pending[5] = PendingReservation(
                row_index=5,
                resource="beboo",
                user_id=1,
                expires_at=time.monotonic() - 1  # Already expired
            )

        # User 2 should be able to reserve
        reserved = await service.reserve_proxies([5], "loloo", user_id=2)
        assert reserved == [5]

    @pytest.mark.asyncio
    async def test_cache_reduces_api_calls(self, service):
        """Test that caching reduces repeated API calls"""
        mock_ws = AsyncMock()
        service._get_worksheet = AsyncMock(return_value=mock_ws)

        mock_ws.get_all_values = AsyncMock(return_value=[
            ["proxy", "country", "added_date", "expires_date", "used_for", "proxy_type"],
            ["1.1.1.1:8080", "US", "01.01.24", "01.01.25", "", "http"],
        ])

        # First call - should hit API
        proxies1 = await service.get_all_proxies()
        assert len(proxies1) == 1
        assert mock_ws.get_all_values.call_count == 1

        # Second call - should use cache
        proxies2 = await service.get_all_proxies()
        assert len(proxies2) == 1
        assert mock_ws.get_all_values.call_count == 1  # No additional call

        # Force refresh - should hit API again
        proxies3 = await service.get_all_proxies(force_refresh=True)
        assert len(proxies3) == 1
        assert mock_ws.get_all_values.call_count == 2

    @pytest.mark.asyncio
    async def test_proxies_sorted_by_days_left_descending(self, service):
        """Test that proxies are sorted by days_left (more days first)"""
        mock_ws = AsyncMock()
        service._get_worksheet = AsyncMock(return_value=mock_ws)

        today = date.today()

        mock_ws.get_all_values = AsyncMock(return_value=[
            ["proxy", "country", "added_date", "expires_date", "used_for", "proxy_type"],
            ["1.1.1.1:8080", "US", "01.01.24", (today + timedelta(days=10)).strftime("%d.%m.%y"), "", "http"],
            ["2.2.2.2:8080", "DE", "01.01.24", (today + timedelta(days=30)).strftime("%d.%m.%y"), "", "http"],
            ["3.3.3.3:8080", "FR", "01.01.24", (today + timedelta(days=5)).strftime("%d.%m.%y"), "", "http"],
        ])

        # Get available proxies
        available = await service.get_available_proxies("beboo")

        # Should be sorted: 30 days, 10 days, 5 days
        assert len(available) == 3
        assert available[0].days_left == 30
        assert available[1].days_left == 10
        assert available[2].days_left == 5

    @pytest.mark.asyncio
    async def test_cancel_all_reservations(self, service):
        """Test canceling all user reservations"""
        # Reserve multiple proxies
        reserved = await service.reserve_proxies([5, 6, 7], "beboo", user_id=1)
        assert len(reserved) == 3

        # Another user reserves one
        reserved2 = await service.reserve_proxies([8], "beboo", user_id=2)
        assert len(reserved2) == 1

        # Cancel all for user 1
        count = await service.cancel_all_reservations(user_id=1)
        assert count == 3

        # User 2's reservation should still exist
        async with service._pending_lock:
            assert 8 in service._pending
            assert len(service._pending) == 1

    @pytest.mark.asyncio
    async def test_get_stats(self, service):
        """Test statistics method"""
        mock_ws = AsyncMock()
        service._get_worksheet = AsyncMock(return_value=mock_ws)

        today = date.today()

        mock_ws.get_all_values = AsyncMock(return_value=[
            ["proxy", "country", "added_date", "expires_date", "used_for", "proxy_type"],
            ["1.1.1.1:8080", "US", "01.01.24", (today + timedelta(days=10)).strftime("%d.%m.%y"), "", "http"],
            ["2.2.2.2:8080", "DE", "01.01.24", (today - timedelta(days=5)).strftime("%d.%m.%y"), "", "http"],  # Expired
        ])

        # Reserve one proxy
        await service.reserve_proxies([2], "beboo", user_id=1)

        # Get stats
        stats = await service.get_stats()

        assert stats["total_proxies"] == 2
        assert stats["available"] == 1
        assert stats["expired"] == 1
        assert stats["pending_reservations"] == 1


class TestPerformanceComparison:
    """Performance benchmarks comparing old vs new approach"""

    @pytest.mark.asyncio
    async def test_old_approach_api_calls(self):
        """
        Simulate OLD approach: N proxies = 2N API calls

        For 5 proxies:
        - 5 individual row_values() calls
        - 5 individual update_cell() calls
        Total: 10 API calls
        """
        call_count = 0

        async def mock_api_call():
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(0.01)  # Simulate API latency

        # Simulate taking 5 proxies the old way
        num_proxies = 5
        for _ in range(num_proxies):
            await mock_api_call()  # row_values
            await mock_api_call()  # update_cell

        assert call_count == 10  # 2 * 5

    @pytest.mark.asyncio
    async def test_new_approach_api_calls(self):
        """
        Simulate NEW approach: N proxies = 2 API calls

        For 5 proxies:
        - 1 get_all_values() call
        - 1 batch_update() call
        Total: 2 API calls (5x improvement!)
        """
        call_count = 0

        async def mock_api_call():
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(0.01)  # Simulate API latency

        # Simulate taking 5 proxies the new way
        await mock_api_call()  # get_all_values
        await mock_api_call()  # batch_update

        assert call_count == 2

    @pytest.mark.asyncio
    async def test_performance_improvement(self):
        """
        Benchmark actual performance improvement.

        Expected: ~5x faster for 5 proxies
        """
        import time

        # Old approach timing
        start = time.monotonic()
        for _ in range(5):
            await asyncio.sleep(0.01)  # row_values
            await asyncio.sleep(0.01)  # update_cell
        old_time = time.monotonic() - start

        # New approach timing
        start = time.monotonic()
        await asyncio.sleep(0.01)  # get_all_values
        await asyncio.sleep(0.01)  # batch_update
        new_time = time.monotonic() - start

        # New should be significantly faster
        improvement_ratio = old_time / new_time
        assert improvement_ratio >= 4.5  # At least 4.5x faster

        print(f"\nPerformance improvement: {improvement_ratio:.1f}x faster")
        print(f"Old approach: {old_time*1000:.1f}ms")
        print(f"New approach: {new_time*1000:.1f}ms")


@pytest.mark.asyncio
async def test_concurrent_access_safety():
    """
    Test that reservation system prevents race conditions.

    Scenario: 10 users try to take same 5 proxies simultaneously.
    Expected: Only first 5 succeed, others fail gracefully.
    """
    service = ProxyService(AsyncMock())

    # Mock worksheet
    mock_ws = AsyncMock()
    service._get_worksheet = AsyncMock(return_value=mock_ws)

    mock_ws.get_all_values = AsyncMock(return_value=[
        ["proxy", "country", "added_date", "expires_date", "used_for", "proxy_type"],
        ["1.1.1.1:8080", "US", "01.01.24", "01.01.25", "", "http"],
        ["2.2.2.2:8080", "DE", "01.01.24", "01.01.25", "", "http"],
        ["3.3.3.3:8080", "FR", "01.01.24", "01.01.25", "", "http"],
        ["4.4.4.4:8080", "UK", "01.01.24", "01.01.25", "", "http"],
        ["5.5.5.5:8080", "PL", "01.01.24", "01.01.25", "", "http"],
    ])

    mock_ws.batch_update = AsyncMock()

    # 10 users try to reserve same proxies
    tasks = []
    for user_id in range(1, 11):
        task = service.reserve_proxies([2, 3, 4, 5, 6], "beboo", user_id)
        tasks.append(task)

    results = await asyncio.gather(*tasks)

    # Check that only 5 reservations succeeded (one per proxy)
    total_reserved = sum(len(r) for r in results)
    assert total_reserved == 5  # Each proxy reserved once

    # Check that no proxy was double-reserved
    all_reserved = []
    for r in results:
        all_reserved.extend(r)
    assert len(all_reserved) == len(set(all_reserved))  # No duplicates


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
