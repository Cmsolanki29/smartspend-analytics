from pathlib import Path

# Read PurchasePlanner and apply targeted replacements
p = Path("frontend/src/components/Purchase/PurchasePlanner.jsx")
text = p.read_text(encoding="utf-8")

text = text.replace(
    """import {
  deletePurchaseGoal,
  getPurchases,
  postPurchaseAddGoal,
  putPurchaseUpdateSavings,
} from "../../services/api";""",
    """import {
  deletePurchaseGoal,
  getPurchases,
  postPurchaseAddGoal,
  postPurchasePostponeGoal,
  putPurchaseUpdateSavings,
} from "../../services/api";""",
)

text = text.replace(
    'import { HeroKpiTile } from "../Dashboard/shared/HeroKpiTile";\n',
    "",
)

if "function dispatchPlannerSync" not in text:
    text = text.replace(
        'const ACCENT = "#38BDF8";',
        '''const ACCENT = "#38BDF8";

function dispatchPlannerSync(userId) {
  try {
    window.dispatchEvent(new CustomEvent("smartspend:purchase-goals-changed", { detail: { userId } }));
    window.dispatchEvent(new CustomEvent("smartspend-financial-sync", { detail: { userId } }));
  } catch {
    /* ignore */
  }
}''',
    )

text = text.replace(
    "  const [celebrate, setCelebrate] = useState(null);",
    """  const [celebrate, setCelebrate] = useState(null);
  const [expanded, setExpanded] = useState({});
  const [postponeGoal, setPostponeGoal] = useState(null);
  const [postponeMonths, setPostponeMonths] = useState("3");
  const [postponing, setPostponing] = useState(false);""",
)

text = text.replace(
    """  const onTrackCount  = goals.filter((g) => Number(g.progress_pct || 0) >= (Number(g.months_to_deadline || 1) > 0 ? 50 : 0)).length;
  const totalCommitted = goals.reduce((s, g) => s + Number(g.target_amount || 0), 0);""",
    """  const onTrackCount = data?.goals_on_track ?? goals.filter((g) => g.on_track === true).length;
  const goalsTotal = data?.goals_total ?? goals.length;
  const totalCommitted = goals.reduce((s, g) => s + Number(g.target_amount || 0), 0);
  const maxMonthly = Math.max(
    Number(data?.total_monthly_saving_needed || 0),
    Number(data?.current_savings_rate_monthly || 0),
    Number(data?.gap_monthly || 0),
    1,
  );

  const toggleExpand = (id) => setExpanded((e) => ({ ...e, [id]: !e[id] }));

  const handlePostpone = async () => {
    if (!postponeGoal) return;
    const n = parseInt(postponeMonths, 10);
    if (!Number.isFinite(n) || n < 1 || n > 60) {
      showToast("Enter months between 1 and 60");
      return;
    }
    setPostponing(true);
    try {
      await postPurchasePostponeGoal(userId, postponeGoal.goal_id, n);
      setPostponeGoal(null);
      await load();
      dispatchPlannerSync(userId);
      showToast("Goal postponed — EMI & planners updated");
    } catch (e) {
      showToast(e.message || "Postpone failed");
    } finally {
      setPostponing(false);
    }
  };""",
)

# Replace PageHeader block through purchase-grid opening
old_header = """  return (
    <div className="purchase-page fade-in">
      <PageHeader
        eyebrow="PURCHASE PLANNER"
        title="Goal-first Spending"
        subtitle="Every purchase decision checked against your goals. Know before you buy, save before you splurge."
        accentHex={ACCENT}
        rightSlot={
          <HeroKpiTile
            label="Goals on track"
            value={loading ? "—" : String(onTrackCount)}
            caption={`Total committed ${inr(totalCommitted)} across ${goals.length} goal${goals.length !== 1 ? "s" : ""}`}
            accentHex={ACCENT}
            loading={loading}
          />
        }
      />"""

new_header = """  return (
    <div className="purchase-page fade-in">
      <PageHeader
        eyebrow="PURCHASE PLANNER"
        title="Goal-first Spending"
        subtitle="Plan big purchases with savings pace, EMI vs cash, and sacrifice hints."
        accentHex={ACCENT}
      />

      <div className="planner-hero-actions">
        <button type="button" className="btn-primary" onClick={() => setModal(true)}>
          + Add new goal
        </button>
      </div>

      {!loading && !err && (
        <div className="planner-kpi-grid">
          <div className="planner-kpi-card glass-card">
            <div className="planner-kpi-label" style={{ color: ACCENT }}>Goals on track</div>
            <div className="planner-kpi-value" style={{ color: ACCENT }}>
              {onTrackCount}/{goalsTotal} {onTrackCount === goalsTotal && goalsTotal > 0 ? "✓" : ""}
            </div>
            <div className="planner-kpi-sub">Using savings pace vs target</div>
          </div>
          <div className="planner-kpi-card glass-card">
            <div className="planner-kpi-label">Total committed</div>
            <div className="planner-kpi-value">{inr(totalCommitted)}</div>
            <div className="planner-kpi-sub">{goals.length} active goal{goals.length !== 1 ? "s" : ""}</div>
          </div>
          <div className="planner-kpi-card glass-card">
            <div className="planner-kpi-label">Monthly needed</div>
            <div className="planner-kpi-value">{inr(data?.total_monthly_saving_needed ?? 0)}</div>
            <div className="planner-kpi-sub">Combined pace</div>
          </div>
          <div className="planner-kpi-card glass-card">
            <div className="planner-kpi-label">Gap</div>
            <div className="planner-kpi-value" style={{ color: (data?.gap_monthly || 0) > 500 ? "#f59e0b" : "#10b981" }}>
              {inr(data?.gap_monthly ?? 0)}
            </div>
            <div className="planner-kpi-sub">vs avg savings /mo</div>
          </div>
        </div>
      )}"""

if old_header in text:
    text = text.replace(old_header, new_header)
    print("header ok")
else:
    print("header miss")

p.write_text(text.replace("motion.div", "motion.div").replace("motion.div", "div"), encoding="utf-8")
print("purchase partial patch done")
