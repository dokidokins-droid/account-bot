# Optimized Proxy Service - Usage Guide

## Overview

The optimized proxy service reduces Google Sheets API calls from **2N to 2** when selecting N proxies, using batch updates and a reservation system with TTL.

## Key Improvements

### 1. Batch Updates (Main Optimization)

**Old Approach:** Each proxy selection = 2 API calls
```python
# OLD: 5 proxies = 10 API calls (5 reads + 5 writes)
for row_index in [2, 3, 4, 5, 6]:
    row = await ws.row_values(row_index)  # API call 1
    await ws.update_cell(row_index, 5, new_value)  # API call 2
```

**New Approach:** Multiple proxies = 2 API calls total
```python
# NEW: 5 proxies = 2 API calls (1 read + 1 batch write)
all_values = await ws.get_all_values()  # API call 1
await ws.batch_update(batch_data)  # API call 2
```

**Performance:** ~5x faster for 5 proxies, ~50x faster for 50 proxies!

### 2. Reservation System with TTL

Prevents race conditions when multiple users select proxies simultaneously:
- 5-minute TTL on reservations
- Auto-cleanup of expired reservations
- Prevents double-allocation

### 3. Smart Caching

Reduces redundant API calls:
- 60-second TTL on proxy list
- Auto-invalidation on updates
- Force refresh option available

### 4. Sorted by Days Left

Proxies automatically sorted by `days_left` descending (more days = higher priority).

## Usage Examples

### Basic: Take Single Proxy

```python
from bot.services.proxy_service import get_proxy_service

service = get_proxy_service()

# Take one proxy
proxy = await service.try_take_proxy(
    row_index=5,
    resource="beboo",
    user_id=12345
)

if proxy:
    print(f"Got proxy: {proxy.proxy} ({proxy.country})")
    print(f"Days left: {proxy.days_left}")
else:
    print("Proxy not available")
```

### Advanced: Take Multiple Proxies (Batch)

```python
# Get available proxies for a resource
available = await service.get_available_proxies("beboo")
print(f"Found {len(available)} available proxies")

# Select first 5 proxies (already sorted by days_left DESC)
row_indices = [p.row_index for p in available[:5]]

# Reserve them (prevents other users from taking)
reserved = await service.reserve_proxies(
    row_indices=row_indices,
    resource="beboo",
    user_id=12345
)
print(f"Reserved {len(reserved)}/{len(row_indices)} proxies")

# Take all reserved proxies in ONE batch operation
taken, failed = await service.take_proxies_batch(
    row_indices=reserved,
    resource="beboo",
    user_id=12345
)

print(f"Took {len(taken)} proxies, {len(failed)} failed")

for proxy in taken:
    print(f"- {proxy.proxy} ({proxy.country}, {proxy.days_left} days left)")
```

### Get Proxies by Country

```python
# Get count by country
counts = await service.get_countries_with_counts("beboo")
print(f"Available by country: {counts}")
# Output: {'US': 10, 'DE': 5, 'FR': 3}

# Get all US proxies (sorted by days_left DESC)
us_proxies = await service.get_proxies_by_country(
    resource="beboo",
    country="US"
)

# Get only top 3 US proxies
top_us_proxies = await service.get_proxies_by_country(
    resource="beboo",
    country="US",
    limit=3
)
```

### Reservation Management

```python
# Reserve multiple proxies
reserved = await service.reserve_proxies(
    row_indices=[5, 6, 7],
    resource="beboo",
    user_id=12345
)

# Cancel specific reservation
cancelled = await service.cancel_reservation(
    row_index=5,
    user_id=12345
)

# Cancel all user's reservations (cleanup on error/cancel)
count = await service.cancel_all_reservations(user_id=12345)
print(f"Cancelled {count} reservations")
```

### Cache Control

```python
# Get proxies (uses cache if valid)
proxies = await service.get_all_proxies()

# Force refresh from API
proxies = await service.get_all_proxies(force_refresh=True)

# Available proxies (also uses cache)
available = await service.get_available_proxies("beboo")

# Force refresh available list
available = await service.get_available_proxies("beboo", force_refresh=True)
```

### Statistics

```python
# Get service statistics
stats = await service.get_stats()

print(f"Total proxies: {stats['total_proxies']}")
print(f"Available: {stats['available']}")
print(f"Expired: {stats['expired']}")
print(f"Pending reservations: {stats['pending_reservations']}")
print(f"Cache valid: {stats['cache_valid']}")
print(f"Cache age: {stats['cache_age_seconds']}s")
```

### Background Cleanup Task

```python
# Start cleanup task (in bot startup)
await service.start_cleanup_task()

# Stop cleanup task (in bot shutdown)
await service.stop_cleanup_task()
```

## Integration with Telegram Bot

### Handler Example

```python
from aiogram import Router, F
from aiogram.types import CallbackQuery
from bot.services.proxy_service import get_proxy_service

router = Router()

@router.callback_query(F.data.startswith("proxy_country:"))
async def handle_country_selection(callback: CallbackQuery):
    """User selects country for proxies"""
    country = callback.data.split(":")[1]
    user_id = callback.from_user.id

    service = get_proxy_service()

    # Get available proxies for this country
    proxies = await service.get_proxies_by_country(
        resource="beboo",
        country=country,
        limit=10  # Show top 10
    )

    if not proxies:
        await callback.answer("No proxies available for this country")
        return

    # Show list to user...
    # (User clicks on specific proxies to select)


@router.callback_query(F.data.startswith("proxy_select:"))
async def handle_proxy_selection(callback: CallbackQuery):
    """User selects specific proxies"""
    # Parse selected row indices from callback data
    data = callback.data.split(":")[1]
    row_indices = [int(x) for x in data.split(",")]
    user_id = callback.from_user.id

    service = get_proxy_service()

    # Take proxies in batch (optimized!)
    taken, failed = await service.take_proxies_batch(
        row_indices=row_indices,
        resource="beboo",
        user_id=user_id
    )

    if taken:
        # Format proxy details for user
        proxy_list = "\n".join([
            f"{i+1}. {p.proxy} ({p.country}, {p.days_left} days)"
            for i, p in enumerate(taken)
        ])

        await callback.message.answer(
            f"Successfully allocated {len(taken)} proxies:\n\n{proxy_list}"
        )
    else:
        await callback.answer("Failed to allocate proxies (already taken)")
```

## Performance Benchmarks

### Scenario: User selects 10 proxies

**Old Implementation:**
- API calls: 20 (10 reads + 10 writes)
- Time: ~13 seconds (@ 1.5 req/sec rate limit)

**New Implementation:**
- API calls: 2 (1 read + 1 batch write)
- Time: ~1.3 seconds
- **Improvement: 10x faster!**

### Scenario: 5 users select 5 proxies each (concurrent)

**Old Implementation:**
- API calls: 50 (25 reads + 25 writes)
- Time: ~33 seconds
- Risk: Race conditions, double-allocation

**New Implementation:**
- API calls: 10 (5 reads + 5 batch writes)
- Time: ~6.7 seconds
- Safety: Reservation system prevents conflicts
- **Improvement: 5x faster + thread-safe!**

## API Rate Limits

Google Sheets API limits:
- 100 requests per 100 seconds per user
- 500 requests per 100 seconds per project

With old implementation:
- Can process ~50 proxies per 100 seconds (= 100 / 2)

With new implementation:
- Can process ~2500 proxies per 100 seconds (= 50 batches * 50 proxies)
- **50x higher throughput!**

## Best Practices

1. **Always use batch operations** when taking multiple proxies
2. **Reserve before taking** to prevent race conditions
3. **Cancel reservations** on user cancel/error
4. **Let cache work** - don't force refresh unless necessary
5. **Start cleanup task** on bot startup
6. **Monitor stats** to track system health

## Migration from Old Code

### Before (Old Code)
```python
# Bad: Multiple API calls
for row_index in selected_rows:
    proxy = await service.try_take_proxy(row_index, "beboo", user_id)
    if proxy:
        results.append(proxy)
```

### After (New Code)
```python
# Good: Single batch operation
taken, failed = await service.take_proxies_batch(
    row_indices=selected_rows,
    resource="beboo",
    user_id=user_id
)
results = taken
```

## Error Handling

```python
try:
    taken, failed = await service.take_proxies_batch(
        row_indices=[5, 6, 7],
        resource="beboo",
        user_id=12345
    )

    if failed:
        # Some proxies couldn't be taken
        logger.warning(f"Failed to take proxies at rows: {failed}")

    if not taken:
        # No proxies were taken
        await callback.answer("All selected proxies are unavailable")
        return

    # Process successfully taken proxies
    for proxy in taken:
        # ...

except Exception as e:
    logger.error(f"Error taking proxies: {e}")
    # Cleanup reservations on error
    await service.cancel_all_reservations(user_id=12345)
    raise
```

## Configuration

Adjust constants in `proxy_service.py`:

```python
# Reservation TTL (5 minutes default)
RESERVATION_TTL_SECONDS = 300

# Cache TTL (60 seconds default)
ProxyCache(ttl_seconds=60.0)
```

## Monitoring

```python
# Get current stats
stats = await service.get_stats()

# Log important metrics
logger.info(f"Proxy service stats: {stats}")

# Alert if cache is stale
if not stats["cache_valid"]:
    logger.warning("Proxy cache is invalid")

# Alert if many pending reservations
if stats["pending_reservations"] > 10:
    logger.warning(f"High pending reservations: {stats['pending_reservations']}")
```
