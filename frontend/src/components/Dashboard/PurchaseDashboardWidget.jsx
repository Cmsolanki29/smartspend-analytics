import React, { useEffect, useState } from "react";
import { getPurchases } from "../../services/api";
import { SkeletonCard } from "../common/SkeletonCard";

const fmt = (n) =>
  new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 0,
  }).format(Number(n || 0));

const PurchaseDashboardWidget = ({ userId, onOpenPlanner }) => {
  const [goal, setGoal] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let c = false;
    (async () => {
      setLoading(true);
      try {
        const data = await getPurchases(userId);
        const goals = data?.goals || [];
        const hi = goals.find((g) => g.priority === "HIGH") || goals[0];
        if (!c) setGoal(hi || null);
      } catch {
        if (!c) setGoal(null);
      } finally {
        if (!c) setLoading(false);
      }
    })();
    return () => {
      c = true;
    };
  }, [userId]);

  if (loading) {
    return (
      <section className="glass-card purchase-dash-widget hover-glow feature-card">
        <div className="panel-head">
          <h3>Purchase goal</h3>
        </div>
        <p className="muted small" style={{ marginBottom: 10 }}>
          Loading purchase goals…
        </p>
        <SkeletonCard lines={3} height={100} />
      </section>
    );
  }

  if (!goal) {
    return (
      <section className="glass-card purchase-dash-widget hover-glow feature-card">
        <div className="panel-head">
          <h3>Purchase goal</h3>
        </div>
        <p className="muted small">No active goals yet.</p>
        <button type="button" className="btn-outline" onClick={onOpenPlanner}>
          Add goal →
        </button>
      </section>
    );
  }

  return (
    <section className="glass-card purchase-dash-widget hover-glow feature-card">
      <div className="panel-head">
        <h3>{goal.item_name}</h3>
      </div>
      <p>
        {fmt(goal.saved_amount)} / {fmt(goal.target_amount)} ({goal.progress_pct}%)
      </p>
      <div className="purchase-progress-bar wide">
        <span className="purchase-progress-fill" style={{ width: `${Math.min(100, goal.progress_pct)}%` }} />
      </div>
      <p className="muted small">
        {goal.months_remaining} months left · {fmt(goal.monthly_target)}/mo target
      </p>
      <button type="button" className="btn-outline" onClick={onOpenPlanner}>
        Update savings →
      </button>
    </section>
  );
};

export default PurchaseDashboardWidget;
