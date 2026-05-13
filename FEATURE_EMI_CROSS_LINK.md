# EMI Tracker cross-link (Purchase Planner + Festivals)

## Judge one-liner

> “One new EMI check stress-tests RBI headroom **and** post-goal liquidity; if it fails, we math a **defer-by-N-months** fix on a real purchase goal and apply it in one tap — Purchase Planner updates without a manual refresh.”

## Rahul-style numbers (fixture mental model)

| Line | ₹/mo |
|------|------|
| Income | 60,000 |
| Housing EMI (detected) | 30,000 |
| Bike goal pace (MEDIUM, Purchase Planner) | 5,000 |
| Living buffer (policy) | 2,000 (or `users.monthly_fixed_expenses` when set) |
| New bike EMI (proposed) | 2,500–3,000 |

- **RBI headroom:** `max_new_emi_allowed` from existing `_build_emi_detection` (30% of income minus detected EMIs).
- **Liquidity floor:** `income - existing_emis - goals_monthly - buffer` = cash left before adding **P**.
- **Affordable** iff `P <= max_new_emi_allowed` **and** `P <= liquidity_floor` (float epsilon on server).

If not affordable, the API picks one **deferrable** goal (excludes **HIGH** priority; prefers **VEHICLE / ELECTRONICS / APPLIANCE**; then **LOW** before **MEDIUM**; then earlier **target_date**). It scans **N = 1..60** months added to the goal’s `target_date` with `_add_months`, recomputes required monthly savings from **remaining / months_between(today, new_date)**, and accepts the smallest **N** where **freed_monthly >= shortfall**.

## API contract

### `POST /api/emi/{user_id}/affordability-check`

**Body**

```json
{ "proposed_new_emi": 3000 }
```

**Response (shape)**

```json
{
  "affordable": false,
  "proposed_new_emi": 3000,
  "safe_cap_rbi": 12000,
  "liquidity_floor": 23000,
  "shortfall": 2000,
  "inputs": { "income": 60000, "existing_emi": 30000, "goals_monthly": 5000, "buffer": 2000 },
  "rationale_lines": ["Income (basis)...", "..."],
  "suggestion": {
    "goal_id": 2,
    "item_name": "Honda Activa Scooty",
    "current_target_date": "2026-11-01",
    "suggested_target_date": "2027-02-01",
    "postpone_months": 3,
    "old_monthly_target": 8500,
    "new_monthly_target": 6800,
    "freed_monthly": 1700,
    "linked_festival": { "name": "Dussehra", "date": "2026-10-11" },
    "message": "Defer …",
    "rationale_lines": ["…"]
  }
}
```

`linked_festival` may be `null` if no fuzzy match (calendar / `festival_budgets` / `user_important_days`).

### `POST /api/purchases/{user_id}/{goal_id}/postpone`

**Body**

```json
{ "postpone_months": 3 }
```

**Behaviour:** `target_date := target_date + N months` (`_add_months`), `monthly_target := (target_amount - saved_amount) / max(1, months_between(today, new_target))`, refresh `emi_vs_cash` + `sacrifice_plan` JSON like `add_goal`.

### cURL

```bash
curl -s -X POST http://127.0.0.1:8001/api/emi/1/affordability-check \
  -H "Content-Type: application/json" \
  -d "{\"proposed_new_emi\": 12000}" | jq .

# After a suggestion appears, postpone by N months from the response:
curl -s -X POST http://127.0.0.1:8001/api/purchases/1/<goal_id>/postpone \
  -H "Content-Type: application/json" \
  -d "{\"postpone_months\": 1}" | jq .
```

## Frontend

- **`EMITrapDetector.jsx`** (EMI Tracker tab): `#emi-calculator` split grid, `postEmiAffordabilityCheck`, `postPurchasePostponeGoal`, parallel prefetch of purchases + festivals + important days (soft error banner if link data fails).
- **Events:** `smartspend:purchase-goals-changed` and legacy `smartspend-financial-sync` — **Purchase Planner** and **Festival** screens listen and refetch.

## Auth note

User-scoped routes follow the same pattern as other feature routes today (no JWT guard on these handlers). When auth is enforced globally, add the same `Depends` used elsewhere and assert `user_id` matches the token subject.
