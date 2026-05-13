import React, { useCallback, useEffect, useState } from "react";
import {
  deletePurchaseGoal,
  getPurchases,
  postPurchaseAddGoal,
  putPurchaseUpdateSavings,
} from "../../services/api";
import { useToast } from "../common/Toast";
import { EmptyState } from "../common/EmptyState";
import { ErrorCard } from "../common/ErrorCard";
import { SkeletonCard } from "../common/SkeletonCard";
import { PageHeader } from "../Dashboard/shared/PageHeader";
import { HeroKpiTile } from "../Dashboard/shared/HeroKpiTile";
import { inr } from "../../lib/format";

const ACCENT = "#38BDF8";

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

  const onTrackCount  = goals.filter((g) => Number(g.progress_pct || 0) >= (Number(g.months_to_deadline || 1) > 0 ? 50 : 0)).length;
  const totalCommitted = goals.reduce((s, g) => s + Number(g.target_amount || 0), 0);

  return (
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
      />

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
          <h3>Monthly targets</h3>
          {goals.map((g) => (
            <div key={g.goal_id} className="purchase-pri-row">
              <span>
                {g.priority === "HIGH" ? "🔴" : g.priority === "MEDIUM" ? "🟡" : "🟢"} {g.priority}: {g.item_name}
              </span>
              <strong>{fmt(g.monthly_target)}/mo</strong>
            </div>
          ))}
          <p>
            Total needed: {fmt(data?.total_monthly_saving_needed)}/mo · You save ~{fmt(data?.current_savings_rate_monthly)}
            /mo · Gap {fmt(data?.gap_monthly)}
          </p>
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

      <div className="purchase-grid">
        {!loading &&
          !err &&
          goals.map((g) => (
            <article key={g.goal_id} className="glass-card purchase-card">
              <header className="purchase-card-head">
                <div>
                  <h3>
                    🛒 {g.item_name}{" "}
                    <span className="purchase-pri">{g.priority === "HIGH" ? "HIGH 🔴" : g.priority}</span>
                  </h3>
                  <p className="muted small">
                    Target {fmt(g.target_amount)} · by {g.target_date}
                  </p>
                </div>
              </header>

              <div className="purchase-progress">
                <div className="purchase-progress-bar" style={{ width: "100%" }}>
                  <span
                    className="purchase-progress-fill"
                    style={{ width: `${Math.min(100, g.progress_pct)}%` }}
                  />
                </div>
                <p>
                  {fmt(g.saved_amount)} saved of {fmt(g.target_amount)} ({g.progress_pct}%)
                </p>
              </div>

              <p>
                📅 {g.months_remaining} months left · 💰 Save {fmt(g.monthly_target)}/mo
                {g.on_track ? " · ✅ On track" : " · ⚠️ Gap " + fmt(g.gap_per_month) + "/mo"}
              </p>

              <div className="purchase-best-buy">
                <strong>🏷️ Best time to buy</strong>
                <p>{g.best_buy_month?.month}</p>
                <p className="muted small">{g.best_buy_month?.reason}</p>
                <p>Effective ~{fmt(g.best_buy_month?.effective_cost)} after typical discount</p>
              </div>

              <div className="purchase-emi">
                <strong>💳 EMI vs 💵 cash</strong>
                <p>Cash total {fmt(g.emi_vs_cash?.cash?.total)} — interest {fmt(g.emi_vs_cash?.cash?.interest)}</p>
                <p>
                  EMI 12m: {fmt(g.emi_vs_cash?.emi_12?.monthly)}/mo · total {fmt(g.emi_vs_cash?.emi_12?.total)}
                </p>
                <p>
                  EMI 24m: {fmt(g.emi_vs_cash?.emi_24?.monthly)}/mo · total {fmt(g.emi_vs_cash?.emi_24?.total)}
                </p>
              </div>

              <div className="purchase-sac">
                <strong>✂️ Suggested cuts (from your real spending)</strong>
                <ul className="card-list">
                  {(g.sacrifice_plan || []).map((s, i) => (
                    <li key={i}>
                      {s.category}: cut ~{fmt(s.suggested_cut)}/mo (was {fmt(s.current_spend)}) — {s.impact}
                    </li>
                  ))}
                  {(!g.sacrifice_plan || g.sacrifice_plan.length === 0) && (
                    <li className="muted">Not enough category history — keep logging transactions.</li>
                  )}
                </ul>
              </div>

              {g.ai_advice && (
                <blockquote className="purchase-ai feature-card">
                  <strong>🤖 AI</strong>
                  <p>{g.ai_advice}</p>
                </blockquote>
              )}

              {/* Milestones Timeline */}
              <div style={{ marginTop: "20px" }}>
                <h4
                  style={{
                    color: "#94a3b8",
                    fontSize: "13px",
                    marginBottom: "12px",
                    textTransform: "uppercase",
                    letterSpacing: "0.5px",
                  }}
                >
                  Savings Milestones
                </h4>

                <div
                  style={{
                    overflowX: "auto",
                    paddingBottom: "8px",
                  }}
                >
                  <div
                    style={{
                      display: "flex",
                      alignItems: "flex-start",
                      gap: "0px",
                      minWidth: "fit-content",
                      position: "relative",
                      padding: "0 8px",
                    }}
                  >
                    {g.milestones && g.milestones.length > 0 && (
                      <div
                        style={{
                          position: "absolute",
                          top: "16px",
                          left: "28px",
                          right: "28px",
                          height: "2px",
                          background: "linear-gradient(90deg, #3b82f6, #8b5cf6)",
                          zIndex: 0,
                        }}
                      />
                    )}

                    {g.milestones &&
                      g.milestones.map((milestone, index) => (
                        <div
                          key={index}
                          style={{
                            display: "flex",
                            flexDirection: "column",
                            alignItems: "center",
                            flex: "1",
                            minWidth: "90px",
                            maxWidth: "110px",
                            position: "relative",
                            zIndex: 1,
                          }}
                        >
                          <div
                            style={{
                              width: "32px",
                              height: "32px",
                              borderRadius: "50%",
                              background:
                                index === g.milestones.length - 1
                                  ? "linear-gradient(135deg, #f97316, #ef4444)"
                                  : "#3b82f6",
                              display: "flex",
                              alignItems: "center",
                              justifyContent: "center",
                              fontSize: "14px",
                              border: "2px solid #1e293b",
                              flexShrink: 0,
                            }}
                          >
                            {index === g.milestones.length - 1 ? "🎯" : "●"}
                          </div>

                          <div
                            style={{
                              fontSize: "11px",
                              color: "#94a3b8",
                              marginTop: "6px",
                              textAlign: "center",
                              lineHeight: "1.3",
                              whiteSpace: "nowrap",
                            }}
                          >
                            {milestone.month?.split(" ")[0] || `Month ${index + 1}`}
                          </div>

                          <div
                            style={{
                              fontSize: "12px",
                              fontWeight: "700",
                              color: index === g.milestones.length - 1 ? "#f97316" : "#f1f5f9",
                              marginTop: "2px",
                              textAlign: "center",
                              whiteSpace: "nowrap",
                            }}
                          >
                            ₹{(milestone.amount / 1000).toFixed(0)}k
                          </div>

                          <div
                            style={{
                              fontSize: "10px",
                              color: index === g.milestones.length - 1 ? "#f97316" : "#64748b",
                              textAlign: "center",
                              marginTop: "2px",
                              maxWidth: "80px",
                              lineHeight: "1.2",
                            }}
                          >
                            {milestone.label}
                          </div>
                        </div>
                      ))}
                  </div>
                </div>
              </div>

              <div className="purchase-actions">
                <label className="muted small">
                  Log savings
                  <input
                    type="number"
                    min="0"
                    placeholder="₹"
                    value={saveInput[g.goal_id] || ""}
                    onChange={(e) => setSaveInput((s) => ({ ...s, [g.goal_id]: e.target.value }))}
                  />
                </label>
                <button
                  type="button"
                  className="btn-primary"
                  disabled={savingId === g.goal_id}
                  onClick={() => bumpSavings(g.goal_id, g.progress_pct)}
                >
                  Update progress
                </button>
                <button type="button" className="btn-outline" onClick={() => removeGoal(g.goal_id)}>
                  🗑️ Cancel goal
                </button>
              </div>
            </article>
          ))}
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
    </div>
  );
};

export default PurchasePlanner;
