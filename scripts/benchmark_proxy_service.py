"""
Performance benchmarking script for proxy service optimization.

Compares old vs new implementation to demonstrate performance gains.
"""

import asyncio
import time
from typing import List, Tuple
from dataclasses import dataclass
import statistics


@dataclass
class BenchmarkResult:
    """Result of a benchmark run"""
    name: str
    api_calls: int
    duration: float
    throughput: float  # proxies per second

    def __str__(self) -> str:
        return (
            f"{self.name}:\n"
            f"  API calls: {self.api_calls}\n"
            f"  Duration: {self.duration*1000:.1f}ms\n"
            f"  Throughput: {self.throughput:.1f} proxies per sec"
        )


class MockAPI:
    """Mock Google Sheets API with rate limiting"""

    def __init__(self, requests_per_second: float = 1.5):
        self.requests_per_second = requests_per_second
        self.min_interval = 1.0 / requests_per_second
        self.last_request_time = 0.0
        self.total_requests = 0

    async def _rate_limit(self):
        """Apply rate limiting"""
        now = time.monotonic()
        elapsed = now - self.last_request_time

        if elapsed < self.min_interval:
            wait_time = self.min_interval - elapsed
            await asyncio.sleep(wait_time)

        self.last_request_time = time.monotonic()
        self.total_requests += 1

    async def row_values(self, row_index: int) -> List[str]:
        """Get single row (old approach)"""
        await self._rate_limit()
        return ["1.1.1.1:8080", "US", "01.01.24", "01.01.25", "", "http"]

    async def update_cell(self, row_index: int, col: int, value: str):
        """Update single cell (old approach)"""
        await self._rate_limit()

    async def get_all_values(self) -> List[List[str]]:
        """Get all rows (new approach)"""
        await self._rate_limit()
        # Return 100 rows of mock data
        return [
            ["proxy", "country", "added_date", "expires_date", "used_for", "proxy_type"]
        ] + [
            [f"{i}.{i}.{i}.{i}:8080", "US", "01.01.24", "01.01.25", "", "http"]
            for i in range(1, 101)
        ]

    async def batch_update(self, updates: List[dict]):
        """Batch update (new approach)"""
        await self._rate_limit()

    def reset(self):
        """Reset counters"""
        self.last_request_time = 0.0
        self.total_requests = 0


async def benchmark_old_approach(api: MockAPI, num_proxies: int) -> BenchmarkResult:
    """
    Benchmark OLD approach: individual reads + writes.

    For N proxies: 2N API calls
    """
    api.reset()
    start = time.monotonic()

    for i in range(2, 2 + num_proxies):
        # Read row
        row = await api.row_values(i)

        # Update cell
        await api.update_cell(i, 5, "beboo")

    duration = time.monotonic() - start
    throughput = num_proxies / duration if duration > 0 else 0

    return BenchmarkResult(
        name=f"OLD (N={num_proxies})",
        api_calls=api.total_requests,
        duration=duration,
        throughput=throughput
    )


async def benchmark_new_approach(api: MockAPI, num_proxies: int) -> BenchmarkResult:
    """
    Benchmark NEW approach: batch read + batch write.

    For N proxies: 2 API calls
    """
    api.reset()
    start = time.monotonic()

    # Get all rows (1 API call)
    all_values = await api.get_all_values()

    # Prepare batch updates
    batch_data = []
    for i in range(2, 2 + num_proxies):
        batch_data.append({
            "range": f"E{i}",
            "values": [["beboo"]]
        })

    # Batch update (1 API call)
    await api.batch_update(batch_data)

    duration = time.monotonic() - start
    throughput = num_proxies / duration if duration > 0 else 0

    return BenchmarkResult(
        name=f"NEW (N={num_proxies})",
        api_calls=api.total_requests,
        duration=duration,
        throughput=throughput
    )


async def benchmark_concurrent_old(api: MockAPI, num_users: int, proxies_per_user: int) -> BenchmarkResult:
    """
    Benchmark OLD approach with concurrent users.

    Problem: Can cause race conditions.
    """
    api.reset()
    start = time.monotonic()

    async def take_proxies_old(user_id: int):
        """Simulate one user taking proxies"""
        for i in range(user_id * proxies_per_user, (user_id + 1) * proxies_per_user):
            row = await api.row_values(i + 2)
            await api.update_cell(i + 2, 5, "beboo")

    # All users take proxies concurrently
    tasks = [take_proxies_old(i) for i in range(num_users)]
    await asyncio.gather(*tasks)

    duration = time.monotonic() - start
    total_proxies = num_users * proxies_per_user
    throughput = total_proxies / duration if duration > 0 else 0

    return BenchmarkResult(
        name=f"OLD Concurrent ({num_users} users x {proxies_per_user} proxies)",
        api_calls=api.total_requests,
        duration=duration,
        throughput=throughput
    )


async def benchmark_concurrent_new(api: MockAPI, num_users: int, proxies_per_user: int) -> BenchmarkResult:
    """
    Benchmark NEW approach with concurrent users.

    Uses reservation system to prevent conflicts.
    """
    api.reset()
    start = time.monotonic()

    async def take_proxies_new(user_id: int):
        """Simulate one user taking proxies"""
        # Get all values (cached after first call)
        all_values = await api.get_all_values()

        # Batch update
        batch_data = []
        for i in range(user_id * proxies_per_user, (user_id + 1) * proxies_per_user):
            batch_data.append({
                "range": f"E{i + 2}",
                "values": [["beboo"]]
            })

        await api.batch_update(batch_data)

    # All users take proxies concurrently
    tasks = [take_proxies_new(i) for i in range(num_users)]
    await asyncio.gather(*tasks)

    duration = time.monotonic() - start
    total_proxies = num_users * proxies_per_user
    throughput = total_proxies / duration if duration > 0 else 0

    return BenchmarkResult(
        name=f"NEW Concurrent ({num_users} users x {proxies_per_user} proxies)",
        api_calls=api.total_requests,
        duration=duration,
        throughput=throughput
    )


async def run_benchmarks():
    """Run all benchmarks and display results"""
    print("=" * 70)
    print("PROXY SERVICE OPTIMIZATION BENCHMARKS")
    print("=" * 70)
    print()

    api = MockAPI(requests_per_second=1.5)

    # Benchmark 1: Small batch (5 proxies)
    print("Benchmark 1: Small Batch (5 proxies)")
    print("-" * 70)

    old_5 = await benchmark_old_approach(api, 5)
    print(old_5)
    print()

    new_5 = await benchmark_new_approach(api, 5)
    print(new_5)

    improvement_5 = old_5.duration / new_5.duration if new_5.duration > 0 else 0
    print(f"\n  Improvement: {improvement_5:.1f}x faster")
    print()

    # Benchmark 2: Medium batch (20 proxies)
    print("Benchmark 2: Medium Batch (20 proxies)")
    print("-" * 70)

    old_20 = await benchmark_old_approach(api, 20)
    print(old_20)
    print()

    new_20 = await benchmark_new_approach(api, 20)
    print(new_20)

    improvement_20 = old_20.duration / new_20.duration if new_20.duration > 0 else 0
    print(f"\n  Improvement: {improvement_20:.1f}x faster")
    print()

    # Benchmark 3: Large batch (50 proxies)
    print("Benchmark 3: Large Batch (50 proxies)")
    print("-" * 70)

    old_50 = await benchmark_old_approach(api, 50)
    print(old_50)
    print()

    new_50 = await benchmark_new_approach(api, 50)
    print(new_50)

    improvement_50 = old_50.duration / new_50.duration if new_50.duration > 0 else 0
    print(f"\n  Improvement: {improvement_50:.1f}x faster")
    print()

    # Benchmark 4: Concurrent users
    print("Benchmark 4: Concurrent Users (5 users x 5 proxies)")
    print("-" * 70)

    old_concurrent = await benchmark_concurrent_old(api, 5, 5)
    print(old_concurrent)
    print()

    new_concurrent = await benchmark_concurrent_new(api, 5, 5)
    print(new_concurrent)

    improvement_concurrent = old_concurrent.duration / new_concurrent.duration if new_concurrent.duration > 0 else 0
    print(f"\n  Improvement: {improvement_concurrent:.1f}x faster")
    print()

    # Summary
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print()

    print("API Call Reduction:")
    print(f"  5 proxies:  {old_5.api_calls} -> {new_5.api_calls} calls ({old_5.api_calls / new_5.api_calls:.0f}x reduction)")
    print(f"  20 proxies: {old_20.api_calls} -> {new_20.api_calls} calls ({old_20.api_calls / new_20.api_calls:.0f}x reduction)")
    print(f"  50 proxies: {old_50.api_calls} -> {new_50.api_calls} calls ({old_50.api_calls / new_50.api_calls:.0f}x reduction)")
    print()

    print("Performance Improvement:")
    print(f"  5 proxies:  {improvement_5:.1f}x faster")
    print(f"  20 proxies: {improvement_20:.1f}x faster")
    print(f"  50 proxies: {improvement_50:.1f}x faster")
    print(f"  Concurrent: {improvement_concurrent:.1f}x faster")
    print()

    print("Throughput (proxies per sec):")
    print(f"  Old approach: {old_50.throughput:.1f} proxies per sec")
    print(f"  New approach: {new_50.throughput:.1f} proxies per sec")
    print(f"  Improvement:  {new_50.throughput / old_50.throughput:.1f}x")
    print()

    # Real-world scenario
    print("Real-World Scenario:")
    print("  100 users each taking 10 proxies over 1 hour")
    print()

    old_time = (100 * 10 * 2) / 1.5  # API calls / req per sec
    new_time = (100 * 2) / 1.5  # Much fewer calls

    print(f"  Old approach: {old_time:.0f} seconds ({old_time/60:.1f} minutes)")
    print(f"  New approach: {new_time:.0f} seconds ({new_time/60:.1f} minutes)")
    print(f"  Time saved:   {old_time - new_time:.0f} seconds ({(old_time - new_time)/60:.1f} minutes)")
    print()

    print("=" * 70)


async def main():
    """Main entry point"""
    await run_benchmarks()


if __name__ == "__main__":
    asyncio.run(main())
