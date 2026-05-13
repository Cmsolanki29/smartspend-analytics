# SmartSpend / EXIQO — Frontend Design System

Canonical tokens mirror `tailwind.config.js` and intro primitives. **Do not introduce ad-hoc hex colors or new easings** outside this list.

## 1. Color

| Token | Hex / usage |
|-------|----------------|
| `ss-bg-deep` | `#070418` |
| `ss-bg-rise` | `#0F0A2E` |
| `exiqo-purple` | `#7C3AED` |
| `exiqo-dark-purple` | `#5B21B6` |
| `exiqo-pink` | `#EC4899` |
| `exiqo-glow` | `#A78BFA` |
| `exiqo-navy` | `#0A0E27` |
| `exiqo-dark` | `#1A1F3A` |
| `ss-cyan` | `#22D3EE` |
| Semantic rose / amber / emerald | Tailwind `rose-*`, `amber-*`, `emerald-*` at ≤20% fill for surfaces |

Charts and KPI accents use **`bg-ss-brand`** or `from-exiqo-purple to-exiqo-pink` / cyan stops — no extra palette.

## 2. Typography

- **Sans:** `Inter`, system-ui  
- **Display / headings:** `Space Grotesk` via `font-heading`  
- **Money:** `tabular-nums` + `en-IN` formatting with `apiUtils.formatINR`

## 3. Motion

- **Easing:** Tailwind `ease-brand` → `cubic-bezier(0.22, 1, 0.36, 1)`  
- **Intro-aligned:** `animate-ss-mesh`, `animate-ss-shimmer`, `animate-ss-twinkle`, `animate-ss-spin-slow`  
- **Reduced motion:** honor `useReducedMotion()` — replace choreography with short opacity fades only.

## 4. Glass surface (§2.4)

Use `<GlassCard />` from `src/components/intro/GlassCard.tsx`:

- `rounded-2xl border border-white/10 bg-white/5 backdrop-blur-2xl`  
- Raised variant: `elevation="raised"`  
- Do **not** rely on legacy global `.glass-card` for new UI; prefer `GlassCard` + Tailwind tokens above.

## 5. Focus

- `focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/60`  
- Minimum **48px** hit targets on touch.

## 6. Shadows

- `shadow-ss-glass`, `shadow-ss-cta`, `shadow-ss-cta-hover`, `shadow-purple-glow`, `shadow-pink-glow`, `shadow-exiqo-card`

## 7. Components (reuse)

- `AuroraBackground`, `GlassCard`, `GradientButton`, `RocketTrail`, `ShieldMark` — `src/components/intro/`
- **Mastery journey** — `src/components/journey/MasteryJourneyRail.tsx`: glass rail, `ease-brand` connector fills, `from-exiqo-purple` / `to-exiqo-pink` / `ss-cyan` gradient accents only (see `tailwind.config.js` `bg-ss-brand`).
