import React, { useCallback, useEffect, useState } from "react";
import {
  deletePurchaseGoal,
  getPurchases,
  postPurchaseAddGoal,
  postPurchasePostponeGoal,
  putPurchaseUpdateSavings,
} from "../../services/api";
import { useToast } from "../common/Toast";
import { EmptyState } from "../common/EmptyState";
import { ErrorCard } from "../common/ErrorCard";
import { SkeletonCard } from "../common/SkeletonCard";
import { PageHeader } from "../Dashboard/shared/PageHeader";
import { inr } from "../../lib/format";

const ACCENT = "#38BDF8";

function dispatchPlannerSync(userId) {
  try {
    window.dispatchEvent(new CustomEvent("smartspend:purchase-goals-changed", { detail: { userId } }));
    window.dispatchEvent(new CustomEvent("smartspend-financial-sync", { detail: { userId } }));
  } catch {
    /* ignore */
  }
}

const fmt = (n) =>
  new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 0,
  }).format(Number(n || 0));

const priorityRank = (p) => (p === "HIGH" ? 0 : p === "MEDIUM" ? 1 : 2);

const PurchasePlanner = ({ userId }) => {
  const { showToast } = useToast();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");
  const [modal, setModal] = useState(false);
  const [itemName, setItemName] = useState("");
  const [targetAmount, setTargetAmount] = useState("");
  const [targetDate, setTargetDate] = useState("");
  const [category, setCategory] = useState("OTHER");
  const [priority, setPriority] = useState("MEDIUM");
  const [adding, setAdding] = useState(false);
  const [savingId, setSavingId] = useState(null);
  const [saveInput, setSaveInput] = useState({});
  const [celebrate, setCelebrate] = useState(null);
  const [expanded, setExpanded] = useState({});
  const [postponeGoal, setPostponeGoal] = useState(null);
  const [postponeMonths, setPostponeMonths] = useState("3");
  const [postponing, setPostponing] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setErr("");
    try {
      const d = await getPurchases(userId);
      setData(d);
    } catch (e) {
      setErr(e.message || "Failed to load goals");
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [userId]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    const onSync = (e) => {
      if (e?.detail?.userId === userId) load();
    };
    window.addEventListener("smartspend-financial-sync", onSync);
    window.addEventListener("smartspend:purchase-goals-changed", onSync);
    return () => {
      window.removeEventListener("smartspend-financial-sync", onSync);
      window.removeEventListener("smartspend:purchase-goals-changed", onSync);
    };
  }, [userId, load]);

  useEffect(() => {
    const handler = () => load();
    window.addEventListener("dashboardModeChanged", handler);
    return () => window.removeEventListener("dashboardModeChanged", handler);
  }, [load]);

  const goals = (data?.goals || []).slice().sort((a, b) => priorityRank(a.priority) - priorityRank(b.priority));

  const quick = (label, cat) => {
    setItemName(label);
    setCategory(cat);
  };

  const addGoal = async () => {
    if (!itemName.trim() || !targetAmount || !targetDate) return;
    setAdding(true);
    try {
      await postPurchaseAddGoal(userId, {
        item_name: itemName.trim(),
        target_amount: parseFloat(targetAmount),
        target_date: targetDate,
        category,
        priority,
      });
      setModal(false);
      setItemName("");
      setTargetAmount("");
      setTargetDate("");
      await load();
      dispatchPlannerSync(userId);
      showToast("Goal added successfully! ✅");
    } catch (e) {
      alert(e.message || "Could not add goal");
    } finally {
      setAdding(false);
    }
  };

  const bumpSavings = async (goalId, prevPct) => {
    const raw = saveInput[goalId];
    const amt = parseFloat(raw);
    if (Number.isNaN(amt) || amt <= 0) return;
    setSavingId(goalId);
    try {
      const updated = await putPurchaseUpdateSavings(userId, goalId, amt);
      setSaveInput((s) => ({ ...s, [goalId]: "" }));
      await load();
      showToast("Savings updated! 🎉");
      const milestones = [25, 50, 75, 100];
      const newPct = Number(updated?.progress_pct ?? 0);
      for (const m of milestones) {
        if (prevPct < m && newPct >= m) {
          setCelebrate({ pct: m, msg: `${m}% milestone!` });
          setTimeout(() => setCelebrate(null), 4500);
          break;
        }
      }
    } catch (e) {
      alert(e.message || "Update failed");
    } finally {
      setSavingId(null);
    }
  };

  const removeGoal = async (goalId) => {
    if (!window.confirm("Cancel this goal?")) return;
    try {
      await deletePurchaseGoal(userId, goalId);
      await load();
    } catch (e) {
      alert(e.message || "Delete failed");
    }
  };

  const onTrackCount = data?.goals_on_track ?? goals.filter((g) => g.on_track === true).length;
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
  };

  return (
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
      )}

      {celebrate && (
        <div className="purchase-confetti-wrap" aria-live="polite">
          <div className="purchase-confetti" />
          <p className="purchase-celebrate-msg">Goal milestone reached!</p>
        </div>
      )}

      {loading && (
        <div className="glass-card feature-card" style={{ marginBottom: 14 }}>
          <p className="muted small" style={{ marginBottom: 12 }}>
            Loading your purchase goals…
          </p>
          <SkeletonCard lines={4} height={180} />
        </div>
      )}
      {err && (
        <div style={{ marginBottom: 14 }}>
          <ErrorCard message={err} onRetry={load} />
        </div>
      )}

      {!loading && !err && goals.length > 1 && (
        <section className="glass-card purchase-priority-summary">
          <h3>📊 Monthly targets</h3>
          <div className="planner-outlook-bars">
            {goals.map((g) => (
              <div key={g.goal_id} className="planner-outlook-row">
                <span>{g.item_name}</span>
                <div className="planner-outlook-bar">
                  <span style={{ width: `${(100 * g.monthly_target) / maxMonthly}%`, background: ACCENT }} />
                </div>
                <strong>{fmt(g.monthly_target)}/mo</strong>
              </div>
            ))}
            <div className="planner-outlook-row">
              <span>Total</span>
              <div className="planner-outlook-bar">
                <span style={{ width: `${(100 * (data?.total_monthly_saving_needed || 0)) / maxMonthly}%`, background: "#818cf8" }} />
              </div>
              <strong>{fmt(data?.total_monthly_saving_needed)}/mo</strong>
            </div>
            <div className="planner-outlook-row">
              <span>You save</span>
              <div className="planner-outlook-bar">
                <span style={{ width: `${(100 * (data?.current_savings_rate_monthly || 0)) / maxMonthly}%`, background: "#10b981" }} />
              </div>
              <strong>~{fmt(data?.current_savings_rate_monthly)}/mo</strong>
            </div>
          </div>
        </section>
      )}


      {!loading && !err && goals.length === 0 && (
        <div className="glass-card purchase-empty feature-card">
          <EmptyState
            icon="🛵"
            title="No purchase goals yet"
            subtitle="Add your first goal — we will map monthly savings, milestones, and EMI vs cash."
            action={
              <button type="button" className="btn-primary" onClick={() => setModal(true)}>
                + Add goal
              </button>
            }
          />
        </div>
      )}

      <div className="planner-grid-v2">
        {!loading &&
          !err &&
          goals.map((g) => {
            const isOpen = !!expanded[g.goal_id];
            const icon =
              g.category === "VEHICLE" ? "🛵" : g.category === "ELECTRONICS" ? "💻" : g.category === "APPLIANCE" ? "❄️" : "🛒";
            return (
              <article key={g.goal_id} className={`glass-card planner-card-v2 ${isOpen ? "is-expanded" : ""}`}>
                {g.festival_link?.label && (
                  <div className="planner-link-banner">
                    🔗 Festival link: {g.festival_link.label}
                  </div>
                )}
                <header
                  className="planner-card-head-v2"
                  onClick={() => toggleExpand(g.goal_id)}
                  onKeyDown={(e) => e.key === "Enter" && toggleExpand(g.goal_id)}
                  role="button"
                  tabIndex={0}
                >
                  <div>
                    <h3>
                      {icon} {g.item_name}{" "}
                      <span className="purchase-pri">{g.priority === "HIGH" ? "HIGH" : g.priority}</span>
                    </h3>
                    <p className="muted small">
                      Target {fmt(g.target_amount)} · by {g.target_date} · {g.months_remaining} months
                    </p>
                  </div>
                  <span style={{ color: g.on_track ? "#10b981" : "#f59e0b", fontSize: 12, fontWeight: 600 }}>
                    {g.on_track ? "✅ On track" : `Gap ${fmt(g.gap_per_month)}/mo`}
                  </span>
                </header>
                <div className="planner-progress-wrap">
                  <div className="planner-progress-bar">
                    <span className="planner-progress-fill purchase" style={{ width: `${Math.min(100, g.progress_pct)}%` }} />
                  </div>
                  <p className="muted small" style={{ marginTop: 6 }}>
                    {fmt(g.saved_amount)} of {fmt(g.target_amount)} ({g.progress_pct}%)
                  </p>
                </div>
                <div className="planner-card-metrics">
                  <span>Save {fmt(g.monthly_target)}/mo</span>
                  <span>🏷️ {g.best_buy_month?.month}</span>
                </div>
                <div className="planner-card-actions-v2">
                  <div className="planner-log-savings">
                    <input
                      type="number"
                      min="0"
                      placeholder="₹ amount"
                      value={saveInput[g.goal_id] || ""}
                      onChange={(e) => setSaveInput((s) => ({ ...s, [g.goal_id]: e.target.value }))}
                    />
                    <button
                      type="button"
                      className="btn-primary"
                      disabled={savingId === g.goal_id}
                      onClick={() => bumpSavings(g.goal_id, g.progress_pct)}
                    >
                      + Add savings
                    </button>
                  </div>
                  <button type="button" className="btn-outline" onClick={() => setPostponeGoal(g)}>
                    Postpone
                  </button>
                  <button type="button" className="btn-outline" onClick={() => toggleExpand(g.goal_id)}>
                    {isOpen ? "Hide ▲" : "Details ▼"}
                  </button>
                </div>
                {isOpen && (
                  <div className="planner-card-body-v2">
                    <div className="planner-emi-compare">
                      <div className="planner-emi-col recommended">
                        <strong>💵 Cash</strong>
                        <p>{fmt(g.emi_vs_cash?.cash?.total)}</p>
                        <p className="muted small">{g.emi_vs_cash?.cash?.verdict}</p>
                      </div>
                      <div className="planner-emi-col">
                        <strong>12m EMI</strong>
                        <p>{fmt(g.emi_vs_cash?.emi_12?.monthly)}/mo</p>
                        <p className="muted small">Total {fmt(g.emi_vs_cash?.emi_12?.total)}</p>
                      </div>
                      <div className="planner-emi-col">
                        <strong>24m EMI</strong>
                        <p>{fmt(g.emi_vs_cash?.emi_24?.monthly)}/mo</p>
                        <p className="muted small">Total {fmt(g.emi_vs_cash?.emi_24?.total)}</p>
                      </div>
                    </div>
                    {(g.sacrifice_plan || []).length > 0 && (
                      <div className="planner-chip-row">
                        {(g.sacrifice_plan || []).map((s, i) => (
                          <span key={i} className="planner-chip">
                            {s.category} −{fmt(s.suggested_cut)}/mo
                          </span>
                        ))}
                      </div>
                    )}
                    {g.ai_advice && (
                      <p className="muted small" style={{ marginTop: 8 }}>
                        💡 {g.ai_advice}
                      </p>
                    )}
                    <div style={{ marginTop: 16 }}>
                      <h4 className="muted small" style={{ textTransform: "uppercase", letterSpacing: "0.05em" }}>
                        Milestones
                      </h4>
                      <div style={{ display: "flex", gap: 4, overflowX: "auto", paddingTop: 8 }}>
                        {(g.milestones || []).map((m, i) => (
                          <div key={i} style={{ textAlign: "center", minWidth: 72, fontSize: 11 }}>
                            <div
                              style={{
                                width: 28,
                                height: 28,
                                borderRadius: "50%",
                                background: i === (g.milestones?.length || 0) - 1 ? "#f97316" : ACCENT,
                                margin: "0 auto 4px",
                                display: "flex",
                                alignItems: "center",
                                justifyContent: "center",
                              }}
                            >
                              {i === (g.milestones?.length || 0) - 1 ? "🎯" : "●"}
                            </div>
                            <div>{m.label}</div>
                            <div style={{ fontWeight: 700 }}>₹{(m.amount / 1000).toFixed(0)}k</div>
                          </div>
                        ))}
                      </div>
                    </div>
                    <button type="button" className="btn-outline" style={{ marginTop: 12 }} onClick={() => removeGoal(g.goal_id)}>
                      Cancel goal
                    </button>
                  </div>
                )}
              </article>
            );
          })}
      </div>
      {modal && (
        <div className="modal-overlay" role="dialog" aria-modal="true">
          <div className="modal-card glass-card purchase-modal">
            <h3>➕ Add purchase goal</h3>
            <label className="fraud-field">
              What do you want to buy?
              <input value={itemName} onChange={(e) => setItemName(e.target.value)} placeholder="Custom name" />
            </label>
            <div className="purchase-quick">
              <button type="button" className="btn-outline" onClick={() => quick("Honda Activa Scooty", "VEHICLE")}>
                🛵 Scooty
              </button>
              <button type="button" className="btn-outline" onClick={() => quick("iPhone 16", "ELECTRONICS")}>
                📱 Phone
              </button>
              <button type="button" className="btn-outline" onClick={() => quick("Split AC 1.5 Ton", "APPLIANCE")}>
                ❄️ AC
              </button>
              <button type="button" className="btn-outline" onClick={() => quick("MacBook Pro", "ELECTRONICS")}>
                🖥️ Laptop
              </button>
              <button type="button" className="btn-outline" onClick={() => quick("Car upgrade", "VEHICLE")}>
                🚗 Car
              </button>
              <button type="button" className="btn-outline" onClick={() => quick("Smart TV 55\"", "ELECTRONICS")}>
                📺 TV
              </button>
            </div>
            <label className="fraud-field">
              Target price (₹)
              <input type="number" value={targetAmount} onChange={(e) => setTargetAmount(e.target.value)} />
            </label>
            <label className="fraud-field">
              Need it by (YYYY-MM-DD)
              <input type="date" value={targetDate} onChange={(e) => setTargetDate(e.target.value)} />
            </label>
            <label className="fraud-field">
              Category
              <select value={category} onChange={(e) => setCategory(e.target.value)}>
                <option value="VEHICLE">VEHICLE</option>
                <option value="ELECTRONICS">ELECTRONICS</option>
                <option value="APPLIANCE">APPLIANCE</option>
                <option value="OTHER">OTHER</option>
              </select>
            </label>
            <label className="fraud-field">
              Priority
              <select value={priority} onChange={(e) => setPriority(e.target.value)}>
                <option value="HIGH">HIGH</option>
                <option value="MEDIUM">MEDIUM</option>
                <option value="LOW">LOW</option>
              </select>
            </label>
            <div className="fest-card-actions">
              <button type="button" className="btn-outline" onClick={() => setModal(false)}>
                Close
              </button>
              <button type="button" className="btn-primary" disabled={adding} onClick={addGoal}>
                {adding ? "Calculating…" : "Calculate my plan →"}
              </button>
            </div>
          </div>
        </div>
      )}

      {postponeGoal && (
        <div
          className="modal-overlay"
          role="dialog"
          aria-modal="true"
          onClick={(e) => e.target === e.currentTarget && setPostponeGoal(null)}
        >
          <div className="modal-card glass-card purchase-modal" onClick={(e) => e.stopPropagation()}>
            <h3>Postpone — {postponeGoal.item_name}</h3>
            <p className="muted small">
              Shifts your target date and lowers monthly savings pace. EMI Tracker and planners will update.
            </p>
            <label className="fraud-field">
              Postpone by (months)
              <input
                type="number"
                min={1}
                max={60}
                value={postponeMonths}
                onChange={(e) => setPostponeMonths(e.target.value)}
              />
            </label>
            <div className="fest-card-actions" style={{ display: "flex", justifyContent: "flex-end", gap: 10 }}>
              <button type="button" className="btn-outline" onClick={() => setPostponeGoal(null)}>
                Cancel
              </button>
              <button type="button" className="btn-primary" disabled={postponing} onClick={handlePostpone}>
                {postponing ? "Updating…" : "Confirm postpone"}
              </button>
            </div>
          </div>
        </div>
      )}

    </div>
  );
};

export default PurchasePlanner;

