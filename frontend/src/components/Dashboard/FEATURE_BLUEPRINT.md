# SmartSpend Feature Blueprint
Single source of truth for per-feature accent, hero metric, and endpoints.

| # | Feature | Route | Accent Hex | Tailwind | Hero metric | Hero endpoint |
|---|---------|-------|------------|----------|-------------|---------------|
| 1 | Dashboard | /dashboard | `#7C3AED` (brand) | `bg-ss-brand` | ₹ Saved this year | computed from all savings |
| 2 | Transactions | /transactions | `#22D3EE` | `text-cyan-400` | Transactions analysed | `GET /transactions/{uid}/summary` |
| 3 | FraudShield | /fraud-shield | `#F43F5E` | `text-rose-400` | Threats blocked | `GET /fraud-shield/{uid}/stats` |
| 4 | Insights (AI) | /insights | `#A78BFA` | `text-violet-300` | Health score | `GET /health-score/{uid}` |
| 5 | Subscriptions | /subscriptions | `#F59E0B` | `text-amber-400` | ₹ wasted/year | `GET /subscriptions/{uid}` |
| 6 | EMI Trap | /emi-trap | `#DC2626` | `text-red-500` | Traps detected | `GET /emi/{uid}` |
| 7 | Analytics | /analytics | `#10B981` | `text-emerald-400` | Patterns detected | `GET /dark-patterns/{uid}` |
| 8 | Festivals | /festivals | `#EC4899` | `text-pink-400` | Days to next | `GET /festivals/{uid}` |
| 9 | Purchase Planner | /purchase | `#38BDF8` | `text-sky-400` | Goals on track | `GET /purchases/{uid}` |

## Shared Primitives (`/src/components/dashboard/shared/`)

| Component | Purpose |
|-----------|---------|
| `PageHeader` | Eyebrow + gradient title + subtitle + right KPI slot |
| `HeroKpiTile` | The "3-second judge" tile — value count-up, delta chip, accent glow |
| `DeltaChip` | +N% / −N% pill with icon, emerald/rose |
| `SectionTitle` | h2 + optional eyebrow + actions slot |
| `ChartFrame` | GlassCard wrapper for Recharts charts |
| `EmptyHero` | Illustrated empty state with CTA |
| `ConfettiBurst` | 18-particle canvas burst for milestones |

## Format Utilities (`/src/lib/format.ts`)

| Export | Description |
|--------|-------------|
| `inr(value)` | Indian locale currency: ₹1,00,000 |
| `inrCompact(value)` | Short: ₹12.5L, ₹2.1Cr, ₹4.5K |
| `useCountUp(target, duration?)` | Count-up hook 0→target, ease-out cubic, respects prefers-reduced-motion |

## Recharts Global Theme

```tsx
<CartesianGrid stroke="rgba(255,255,255,0.05)" strokeDasharray="2 6" />
<XAxis tick={{ fill: "rgba(255,255,255,0.5)", fontSize: 11 }} />
<YAxis tick={{ fill: "rgba(255,255,255,0.5)", fontSize: 11 }} />
<Tooltip
  contentStyle={{
    background: "rgba(7,4,24,0.85)",
    backdropFilter: "blur(12px)",
    border: "1px solid rgba(255,255,255,0.1)",
    borderRadius: 16,
    fontSize: 13,
  }}
/>
// animationDuration={900} animationEasing="ease-out" on each data component
```

## Accent Usage Rules (do not deviate)

The signature accent for each page is used ONLY on:
1. `HeroKpiTile` value gradient
2. Hero icon halo / badge
3. Primary chart bar/line/area fill
4. Active-state highlights (border, ring)
5. `PageHeader` eyebrow text and identity bar

**Never** use another page's accent. Body, glass, typography stay identical across all pages.
