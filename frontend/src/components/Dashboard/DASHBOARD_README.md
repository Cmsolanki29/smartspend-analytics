# Dashboard layout

The main surface is `Dashboard.tsx`. Rows are ordered to tell the story: **safety → money → growth → AI guardian**.

| Row | Purpose | Key components |
|-----|---------|----------------|
| 0 | Shell (outside this file) | `Sidebar.jsx`, `TopBar.jsx`, `MasteryJourneyRail` (12-phase strip), `AuroraBackground` in `App.jsx` |
| 1 | Hero + KPIs + health gauge | `KPITile`, `HealthScoreGauge` (`variant="hero"`), `ShieldMark` (ambient) |
| 2 | Guardian strip | `GuardianPill` ×4 (FraudShield, Subscriptions, Dark Patterns, EMI) |
| 3 | Spending story | `MonthlyTrendChart`, `SpendingPieChart` |
| 4 | AI Guardian | `AIInsightsPanel` (`presentation="chat"`), `ScenarioSimulator` (`presentation="compact"`) |
| 5 | Risk + ledger | `AnomalyList` (`compact`), `TransactionTable` (`presentation="dashboard"`) |
| 6 | Growth doorways | Subscription preview, `FestivalDashboardWidget`, `PurchaseDashboardWidget`, goals placeholder |
| 7 | Footer | Refresh affordance, build id, trust chips |

## Adding a new widget

1. Decide which narrative row it belongs to (avoid creating a “misc” bucket).
2. If it needs glass + motion, wrap with `GlassCard` from `src/components/intro/GlassCard.tsx` or compose `KPITile` / `GuardianPill`.
3. Prefer existing hooks (`useSmartSpend`, `services/api`); do not change API contracts from the dashboard layer.
4. Keep **intro/auth routes untouched**; dashboard-only assets stay under `components/Dashboard/`.

## Design tokens

See `frontend/DESIGN_SYSTEM.md` (Tailwind `ease-brand`, `ss-*` / `exiqo-*` colors, `GlassCard` recipe).

## Mastery journey (12 phases)

The strip lives in `App.jsx` (not inside `Dashboard.tsx`) so it stays visible across tabs. Progress is stored per user in `localStorage` under `ss_mastery_journey_<userId>` when you use **Mark this milestone complete** (honor-system until a backend field exists).

**Demo motion (phases 1 → 2 → 3 loop):** open the app with query `?journeyDemo=1` (e.g. `http://localhost:3000/?journeyDemo=1` after sign-in). Demo mode does not write `localStorage`.
