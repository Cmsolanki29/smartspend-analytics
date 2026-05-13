import React, { useEffect, useState } from "react";
import { getFestivals } from "../../services/api";
import { SkeletonCard } from "../common/SkeletonCard";

const fmt = (n) =>
  new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 0,
  }).format(Number(n || 0));

const FestivalDashboardWidget = ({ userId, onPlanNow }) => {
  const [d, setD] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let c = false;
    (async () => {
      setLoading(true);
      try {
        const data = await getFestivals(userId);
        if (!c) setD(data);
      } catch {
        if (!c) setD(null);
      } finally {
        if (!c) setLoading(false);
      }
    })();
    return () => {
      c = true;
    };
  }, [userId]);

  const n = d?.next_festival;
  const full = (d?.upcoming_festivals || []).find((x) => x.festival_name === n?.name);

  if (loading) {
    return (
      <section className="glass-card festival-dash-widget hover-glow feature-card">
        <div className="panel-head">
          <h3>Next festival</h3>
        </div>
        <p className="muted small" style={{ marginBottom: 10 }}>
          Loading festival snapshot…
        </p>
        <SkeletonCard lines={3} height={100} />
      </section>
    );
  }

  if (!n) {
    return (
      <section className="glass-card festival-dash-widget hover-glow feature-card">
        <div className="panel-head">
          <h3>Next festival</h3>
        </div>
        <p className="muted small">No upcoming festivals in window — open planner for full calendar.</p>
        <button type="button" className="btn-outline fest-dash-btn" onClick={onPlanNow}>
          Plan now →
        </button>
      </section>
    );
  }

  return (
    <section className="glass-card festival-dash-widget hover-glow feature-card">
      <div className="panel-head">
        <h3>Next festival</h3>
      </div>
      <p>
        <strong>{n.name}</strong> in {n.days_remaining} days
        {n.urgency === "CRITICAL" || n.urgency === "URGENT" ? " · Urgent" : ""}
      </p>
      <p className="muted small">
        Last year: {fmt(full?.last_year_spent)} · Saved: {fmt(full?.saved_so_far)}
      </p>
      <p>
        Indicative: <strong>{fmt(full?.daily_saving_needed)}</strong>/day to close gap
      </p>
      <button type="button" className="btn-outline fest-dash-btn" onClick={onPlanNow}>
        Plan now →
      </button>
    </section>
  );
};

export default FestivalDashboardWidget;
