# ADR-001: Introduction of Redis for Session Caching and Catalog Caching

**Status:** Accepted
**Date:** This is a template — interns complete the date and author fields
**Author:** Chinonyerem Eleweke

## Context

Northbridge Commerce serves a growing base of online shoppers across seven
microservices. Two access patterns were identified as disproportionate
contributors to database load:

1. **Session verification.** Every authenticated request to any of the
   seven services calls `auth-service`'s `/api/auth/verify` endpoint to
   validate the bearer token. Prior to this change, verification required
   no database call (JWT signature verification is stateless) — but as
   the platform grows toward features like token revocation lists and
   active session tracking, a pattern was needed that could support those
   features without adding latency to the hot path.

2. **Catalog reads.** The product catalog (~200 SKUs) is read on nearly
   every page view across the storefront. Catalog data changes
   infrequently — prices and descriptions are updated occasionally, stock
   counts change on order completion. The overwhelming majority of reads
   were identical queries against the same small dataset, hitting
   PostgreSQL directly on every request.

## Decision

Introduce Redis as a caching layer for two specific purposes:

- **Session cache** (`auth-service`): Decoded JWT payloads are cached in
  Redis with a TTL matching the token's remaining validity. Repeat
  verification calls within the token's lifetime are served from Redis
  rather than re-verifying the JWT signature on every call. This also
  gives us a foundation for explicit session invalidation (`/api/auth/logout`)
  — something a stateless JWT alone cannot support.

- **Catalog cache** (`catalog-service`): Product list and individual
  product lookups are cached with a 60-second TTL. Writes (new products,
  stock updates) explicitly invalidate the relevant cache keys rather
  than waiting for TTL expiry, so stock changes are reflected immediately
  while read-heavy traffic is served from memory.

Redis is configured with `maxmemory 256mb` and `allkeys-lru` eviction —
if the cache fills, least-recently-used keys are evicted automatically
rather than Redis running out of memory or blocking writes.

## What We Deliberately Did Not Cache

`analytics-service` queries PostgreSQL directly with no Redis layer. The
aggregate queries it runs (order counts, revenue sums) are not on a
user-facing hot path — they are queried by the internal operations
dashboard at a low request rate. Adding caching here would add complexity
(cache invalidation on every new order) without solving a real performance
problem. This is a deliberate exclusion, not an oversight.

## Consequences

**Positive:**
- Reduced PostgreSQL connection pool pressure from the two highest-traffic
  read patterns in the platform.
- p95 latency on `/api/auth/verify` and `/api/catalog/products` improved
  measurably under load (see `docs/load-test-results.md`).
- Explicit session invalidation is now possible (`/api/auth/logout`),
  which was not achievable with stateless JWT verification alone.

**Trade-offs accepted:**
- An additional stateful service to operate, monitor, and back up
  (though Redis here is a cache, not a system of record — data loss on
  Redis restart is acceptable and does not lose any data that PostgreSQL
  does not already hold).
- Cache invalidation logic adds a small amount of complexity to
  `catalog-service` writes — every write path must remember to invalidate
  the relevant keys.
- A new failure mode: if Redis becomes unavailable, `/healthz` on both
  services reports `degraded`. Both services were deliberately NOT
  designed to hard-fail on Redis unavailability — `auth-service` falls
  back to JWT-only verification, `catalog-service` falls back to direct
  PostgreSQL reads. Redis is a performance optimisation, not a
  dependency the platform cannot survive without.

## Alternatives Considered

- **No caching, scale PostgreSQL vertically:** Rejected. Treats the
  symptom (database load) rather than the cause (repeated identical
  reads). Also more expensive at scale than a small Redis instance.
- **In-process caching (e.g. an LRU cache inside each service):** Rejected
  for the catalog use case because Northbridge runs multiple replicas of
  each service in production-equivalent deployments; an in-process cache
  would not be shared across replicas and would not be invalidated
  consistently on writes. Redis gives us a single shared cache visible to
  all replicas.
  adding new line
