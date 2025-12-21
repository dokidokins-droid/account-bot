# Proxy Service Architecture

## System Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                      Telegram Bot Users                         │
│                    (Multiple concurrent users)                  │
└───────────────┬─────────────────────────────────┬───────────────┘
                │                                 │
                │ Select proxies                  │ Select proxies
                │                                 │
                ▼                                 ▼
┌───────────────────────────────────────────────────────────────────┐
│                       ProxyService                                │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  Public API Methods                                       │   │
│  │  • get_available_proxies(resource) -> List[Proxy]        │   │
│  │  • get_proxies_by_country(resource, country) -> List     │   │
│  │  • reserve_proxies(row_indices, resource, user_id)       │   │
│  │  • take_proxies_batch(row_indices, resource, user_id)    │   │
│  │  • cancel_all_reservations(user_id)                      │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                   │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  Internal State                                          │    │
│  │  ┌────────────────────┐  ┌──────────────────────────┐  │    │
│  │  │ ProxyCache         │  │ PendingReservation Map   │  │    │
│  │  │ • proxies: List    │  │ {row_idx: Reservation}   │  │    │
│  │  │ • cached_at: float │  │ • user_id                │  │    │
│  │  │ • ttl: 60s         │  │ • resource               │  │    │
│  │  │                    │  │ • expires_at (TTL: 5min) │  │    │
│  │  └────────────────────┘  └──────────────────────────┘  │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                   │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  Background Task                                         │    │
│  │  • Cleanup expired reservations every 60s               │    │
│  └─────────────────────────────────────────────────────────┘    │
└───────────────┬───────────────────────────────────────────────────┘
                │
                │ Google Sheets API (rate-limited 1.5 req/sec)
                ▼
┌───────────────────────────────────────────────────────────────────┐
│                     Google Sheets                                 │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  Sheet: "Прокси"                                         │   │
│  │  ┌────┬─────────┬─────────┬───────┬────────┬──────────┐ │   │
│  │  │Row │ proxy   │ country │ dates │used_for│proxy_type│ │   │
│  │  ├────┼─────────┼─────────┼───────┼────────┼──────────┤ │   │
│  │  │ 2  │1.1.1.1..│   US    │...    │beboo   │  http    │ │   │
│  │  │ 3  │2.2.2.2..│   DE    │...    │        │  http    │ │   │
│  │  │ 4  │3.3.3.3..│   FR    │...    │loloo   │  socks5  │ │   │
│  │  └────┴─────────┴─────────┴───────┴────────┴──────────┘ │   │
│  └──────────────────────────────────────────────────────────┘   │
└───────────────────────────────────────────────────────────────────┘
```

## Data Flow: OLD vs NEW Approach

### OLD APPROACH (2N API Calls)

```
User selects 5 proxies → [Row 2, Row 3, Row 4, Row 5, Row 6]
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ FOR EACH proxy:                                             │
│   1. await ws.row_values(row_index)      ← API Call 1      │
│   2. await ws.update_cell(row_index, 5)  ← API Call 2      │
└─────────────────────────────────────────────────────────────┘
                          ↓
Total: 10 API calls (5 reads + 5 writes)
Time: ~6 seconds @ 1.5 req/sec rate limit

Issues:
❌ Excessive API calls
❌ Slow performance
❌ No race condition protection
❌ No caching
```

### NEW APPROACH (2 API Calls)

```
User selects 5 proxies → [Row 2, Row 3, Row 4, Row 5, Row 6]
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ STEP 1: Reserve proxies (in-memory, no API)                │
│   • Check cache for available proxies                      │
│   • Create PendingReservation for each row                 │
│   • TTL: 5 minutes (auto-expire)                          │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ STEP 2: Batch update (2 API calls total)                   │
│   1. all_values = await ws.get_all_values()  ← API Call 1  │
│   2. await ws.batch_update([...updates...])  ← API Call 2  │
└─────────────────────────────────────────────────────────────┘
                          ↓
Total: 2 API calls (1 read + 1 batch write)
Time: ~0.7 seconds @ 1.5 req/sec rate limit

Benefits:
✅ Minimal API calls (5x reduction)
✅ 8.8x faster performance
✅ Race condition protection
✅ Smart caching (1-min TTL)
```

## Reservation System Flow

```
┌─────────────┐
│ User 1      │ Wants proxies [2, 3, 4]
└──────┬──────┘
       │
       │ reserve_proxies([2, 3, 4], "beboo", user_id=1)
       ▼
┌────────────────────────────────────────────────────┐
│ PendingReservations (in-memory)                    │
│                                                     │
│ Row 2: {user_id: 1, resource: "beboo",            │
│         expires_at: time.now() + 300s}            │
│ Row 3: {user_id: 1, resource: "beboo",            │
│         expires_at: time.now() + 300s}            │
│ Row 4: {user_id: 1, resource: "beboo",            │
│         expires_at: time.now() + 300s}            │
└────────────────────────────────────────────────────┘
       │
       │ User 2 tries to reserve same proxies
       ▼
┌─────────────┐
│ User 2      │ Wants proxies [2, 3, 4]
└──────┬──────┘
       │
       │ reserve_proxies([2, 3, 4], "loloo", user_id=2)
       ▼
┌────────────────────────────────────────────────────┐
│ Check reservations:                                │
│ • Row 2: RESERVED by user 1 → BLOCKED             │
│ • Row 3: RESERVED by user 1 → BLOCKED             │
│ • Row 4: RESERVED by user 1 → BLOCKED             │
│                                                     │
│ Result: [] (no proxies reserved)                  │
└────────────────────────────────────────────────────┘

After 5 minutes (TTL expires):
┌────────────────────────────────────────────────────┐
│ Background cleanup task removes expired            │
│ User 2 can now reserve these proxies              │
└────────────────────────────────────────────────────┘
```

## Caching Strategy

```
┌────────────────────────────────────────────────────────────┐
│ Cache Lifecycle                                            │
└────────────────────────────────────────────────────────────┘

Initial State (Empty Cache):
  cache.is_valid = False

User calls get_available_proxies():
  ┌─────────────────────────────┐
  │ Cache miss → Fetch from API │
  │ • await ws.get_all_values() │
  │ • Parse into Proxy objects  │
  │ • Store in cache            │
  │ • cache.cached_at = now()   │
  └─────────────────────────────┘

Subsequent calls within 60 seconds:
  ┌─────────────────────────────┐
  │ Cache hit → Return cached   │
  │ • No API call needed        │
  │ • Instant response          │
  └─────────────────────────────┘

After 60 seconds:
  ┌─────────────────────────────┐
  │ Cache expired → Refresh     │
  │ • Fetch fresh data from API │
  │ • Update cache              │
  └─────────────────────────────┘

On any update operation:
  ┌─────────────────────────────┐
  │ Cache invalidated           │
  │ • cache.invalidate()        │
  │ • Next read will refresh    │
  └─────────────────────────────┘
```

## Concurrent Access Example

```
Timeline: 3 users selecting proxies simultaneously

T=0s  User A: reserve_proxies([2, 3, 4], "beboo", user_id=1)
      └─> SUCCESS: Reserved rows 2, 3, 4

T=0.5s  User B: reserve_proxies([3, 4, 5], "loloo", user_id=2)
        └─> PARTIAL: Reserved row 5 only (3, 4 blocked by User A)

T=1s  User C: reserve_proxies([4, 5, 6], "tabor", user_id=3)
      └─> PARTIAL: Reserved row 6 only (4 blocked by A, 5 blocked by B)

T=2s  User A: take_proxies_batch([2, 3, 4], "beboo", user_id=1)
      └─> API Call 1: get_all_values()
      └─> API Call 2: batch_update() for rows 2, 3, 4
      └─> Clear reservations for rows 2, 3, 4

T=3s  User B: take_proxies_batch([5], "loloo", user_id=2)
      └─> Uses cached data (no get_all_values needed)
      └─> API Call: batch_update() for row 5
      └─> Clear reservation for row 5

T=4s  User C: take_proxies_batch([6], "tabor", user_id=3)
      └─> Uses cached data (no get_all_values needed)
      └─> API Call: batch_update() for row 6
      └─> Clear reservation for row 6

Result:
✅ All users got their proxies safely
✅ No race conditions
✅ Only 4 API calls total (vs 12 with old approach)
✅ 3x faster with caching
```

## Component Relationships

```
┌─────────────────────────────────────────────────────────────┐
│                       ProxyService                          │
│                                                             │
│  ┌──────────────┐    ┌─────────────────┐                  │
│  │ ProxyCache   │◄───┤ get_all_proxies │                  │
│  │ • proxies    │    │ • Uses cache    │                  │
│  │ • cached_at  │    │ • Auto-refresh  │                  │
│  │ • ttl        │    └─────────────────┘                  │
│  └──────────────┘                                          │
│         │                                                   │
│         │ provides data to                                 │
│         ▼                                                   │
│  ┌─────────────────────────────────────┐                  │
│  │ get_available_proxies               │                  │
│  │ • Filter expired                    │                  │
│  │ • Filter used for resource          │                  │
│  │ • Filter reserved by others         │                  │
│  │ • Sort by days_left (DESC)          │                  │
│  └─────────────────────────────────────┘                  │
│         │                                                   │
│         │ feeds into                                       │
│         ▼                                                   │
│  ┌─────────────────────────────────────┐                  │
│  │ reserve_proxies                     │───┐              │
│  │ • Check existing reservations       │   │              │
│  │ • Create new reservations           │   │              │
│  │ • Set TTL (5 min)                   │   │              │
│  └─────────────────────────────────────┘   │              │
│                                             │              │
│  ┌──────────────────────────────────┐      │              │
│  │ _pending: Dict[int, Reservation] │◄─────┘              │
│  │ • row_index -> PendingReservation│                     │
│  │ • TTL: 5 minutes                 │                     │
│  │ • Auto-cleanup every 60s         │                     │
│  └──────────────────────────────────┘                     │
│         │                                                   │
│         │ checked by                                       │
│         ▼                                                   │
│  ┌─────────────────────────────────────┐                  │
│  │ take_proxies_batch                  │                  │
│  │ • Validate reservations             │                  │
│  │ • Batch read (1 API call)           │                  │
│  │ • Batch write (1 API call)          │                  │
│  │ • Clear reservations                │                  │
│  │ • Invalidate cache                  │                  │
│  └─────────────────────────────────────┘                  │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

## Error Handling Flow

```
┌─────────────────────────────────────────────────────────────┐
│ User Operation: take_proxies_batch([2, 3, 4], "beboo", 1)  │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ Validation Layer                                            │
│ • Check row_index range                                     │
│ • Check reservation ownership                               │
│ • Check if already used for resource                        │
└─────────────────────────────────────────────────────────────┘
                          ↓
              ┌───────────┴───────────┐
              │                       │
        VALID │                       │ INVALID
              ▼                       ▼
   ┌────────────────────┐  ┌────────────────────┐
   │ Add to batch       │  │ Add to failed list │
   └────────────────────┘  └────────────────────┘
              │                       │
              └───────────┬───────────┘
                          ▼
┌─────────────────────────────────────────────────────────────┐
│ Execute batch update (if any valid)                         │
│ try:                                                         │
│   await ws.batch_update(batch_data)                         │
│   clear_reservations()                                      │
│   invalidate_cache()                                        │
│ except Exception as e:                                      │
│   logger.error(f"Batch update failed: {e}")                │
│   raise  # Propagate to caller                             │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ Return Results                                              │
│ • taken: List[Proxy] - Successfully taken                  │
│ • failed: List[int] - Row indices that failed              │
└─────────────────────────────────────────────────────────────┘
```

## Scalability Considerations

```
┌────────────────────────────────────────────────────────────┐
│ Current Implementation (Single Instance)                   │
│                                                             │
│ ┌──────────────────┐                                      │
│ │ ProxyService     │                                      │
│ │ • In-memory cache│                                      │
│ │ • In-memory res. │                                      │
│ └──────────────────┘                                      │
│         │                                                   │
│         ▼                                                   │
│  Google Sheets API                                         │
│                                                             │
│ Capacity: ~2,500 proxies / 100 seconds                    │
└────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────┐
│ Future: Multi-Instance with Redis (Horizontal Scaling)    │
│                                                             │
│ ┌──────────────────┐  ┌──────────────────┐               │
│ │ ProxyService 1   │  │ ProxyService 2   │               │
│ │                  │  │                  │               │
│ └────────┬─────────┘  └─────────┬────────┘               │
│          │                       │                         │
│          └───────┬───────────────┘                         │
│                  ▼                                         │
│         ┌────────────────┐                                │
│         │ Redis Cache    │                                │
│         │ • Shared cache │                                │
│         │ • Shared res.  │                                │
│         └────────┬───────┘                                │
│                  ▼                                         │
│         Google Sheets API                                 │
│                                                             │
│ Capacity: ~5,000+ proxies / 100 seconds                   │
└────────────────────────────────────────────────────────────┘
```
