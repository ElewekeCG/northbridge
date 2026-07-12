# Order Flow — Northbridge Commerce

**Deliverable D6** — Traced from live `docker compose logs` output, July 2026.

---

## Overview

Orders Service is the hub. Every checkout request fans out to five downstream
services in a defined sequence. The two-phase reserve/release pattern on
inventory is the critical correctness guarantee: stock is held before payment
is attempted, and released immediately if payment fails, preventing overselling.

---

## Successful Order Flow

**Observed in logs:** Order #5 and #6, product 1 (Wireless Headphones, £149.99), user 4.

### Numbered sequence

1. **Browser** sends `POST /api/orders` with `{ product_id, quantity, card_last4: "4242" }` and `Authorization: Bearer <token>` to `shopn.chickenkiller.com`.

2. **Traefik** matches `Host(shopn...) && PathPrefix(/api/orders)` and proxies to `orders-service:8001`.

3. **orders-service** calls `POST http://auth-service:8000/api/auth/verify` with the bearer token.

4. **auth-service** checks Redis for a cached session. On hit, returns `{ valid: true, user_id, email }` without touching PostgreSQL. Returns `HTTP 200 OK`.

5. **orders-service** calls `GET http://catalog-service:4000/api/catalog/products/1` to fetch product details and price.

6. **orders-service** calls `POST http://inventory-service:8002/api/inventory/reserve` to hold stock before attempting payment.
   - Log: `Reserved 1 units of product 1`

7. **orders-service** calls `POST http://payments-service:4001/api/payments/charge` with the amount and card details.

8. Payment succeeds. **orders-service** calls `PATCH http://catalog-service:4000/api/catalog/products/1/stock` with `delta: -1` to decrement available stock and invalidate the Redis catalog cache.

9. **orders-service** calls `POST http://notifications-service:4002/api/notifications/order-confirmed`.
   - Log: `[NOTIFY] User 4: Order #5 confirmed. Total: £149.99. Thank you for shopping with Northbridge.`

10. **orders-service** writes the order record to PostgreSQL and returns `HTTP 201 Created` to the browser.

---

## Failed Payment Flow (Declined Card)

**Observed in logs:** Declined order, product 2, card_last4: `0000`.

Steps 1–6 are identical to the successful flow — token verified, product fetched, **inventory reserved**.

7. **orders-service** calls `POST http://payments-service:4001/api/payments/charge` with `card_last4: "0000"`.

8. **payments-service** detects the test decline card and returns `HTTP 402 Payment Required`.

9. **orders-service** immediately calls `POST http://inventory-service:8002/api/inventory/release` to return the held stock to available.
   - Log: `Released reservation for product 2`

10. **orders-service** returns `HTTP 402 Payment Required` to the browser. No order record is written. No notification is sent.

---

## Reservation Status Confirmed

Verified via `GET /api/inventory/reservations` immediately after both orders:

| id | product_id | status | meaning |
|----|-----------|--------|---------|
| 14 | 2 | 0 | Released — declined payment, stock returned |
| 15 | 1 | 1 | Held — successful order |
| 16 | 1 | 1 | Held — successful order |

`status: 0` = released, `status: 1` = reserved/confirmed.

The declined payment reservation (id 14, product 2) shows `status: 0` confirming
the release executed correctly and stock was returned to the available pool.

---

## Sequence Diagram

```
Browser       Traefik     orders      auth     catalog   inventory  payments  notifications
   |             |           |          |          |          |          |           |
   |--POST------>|           |          |          |          |          |           |
   |   /api/     |--proxy--->|          |          |          |          |           |
   |   orders    |           |--verify->|          |          |          |           |
   |             |           |<--200----|          |          |          |           |
   |             |           |--GET product------->|          |          |           |
   |             |           |<--product data------|          |          |           |
   |             |           |--POST reserve--------------->  |          |           |
   |             |           |<--200 reserved--------------|  |          |           |
   |             |           |--POST charge---------------------------->  |           |
   |             |           |                              |   200/402  |           |
   |             |           |   [if 402 — decline]        |            |           |
   |             |           |--POST release--------------->|            |           |
   |             |           |<--200 released--------------|             |           |
   |<--402-------|           |                             |             |           |
   |             |           |   [if 200 — success]        |            |           |
   |             |           |--PATCH stock------------>   |            |           |
   |             |           |<--200 OK----------------|   |            |           |
   |             |           |--POST confirmed---------------------------------->    |
   |             |           |<--200 OK--------------------------------------------|
   |<--201-------|           |                             |             |           |
```

---

## Key Architectural Observation

The reserve-before-charge pattern prevents overselling. Without it, a system
under load could allow multiple customers to purchase the last unit simultaneously
— each passes a stock check, each charges successfully, but only one unit exists.

By reserving first and releasing on failure, the double-sell window is eliminated.
The inventory table's `status` column is the audit trail that proves the release
happened — `status: 0` on the declined reservation is the evidence.