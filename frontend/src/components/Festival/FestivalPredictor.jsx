import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  deleteFestivalImportantDay,
  getFestivals,
  getFestivalImportantDays,
  postFestivalImportantDay,
  postFestivalSetBudget,
  putFestivalImportantDay,
  putFestivalUpdateSavings,
} from "../../services/api";
import { useToast } from "../common/Toast";
import { EmptyState } from "../common/EmptyState";
import { ErrorCard } from "../common/ErrorCard";
import { SkeletonCard } from "../common/SkeletonCard";
import { PageHeader } from "../Dashboard/shared/PageHeader";
import { inr } from "../../lib/format";

const ACCENT = "#EC4899";

const fmt = (n) =>
  new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 0,
  }).format(Number(n || 0));

const urgencyClass = (u) => {
  if (u === "CRITICAL") return "fest-urgency-critical";
  if (u === "URGENT") return "fest-urgency-urgent";
  if (u === "START_SAVING") return "fest-urgency-start";
  return "fest-urgency-plan";
};

const urgencyPill = (u) => {
  if (u === "CRITICAL") return "critical";
  if (u === "URGENT") return "urgent";
  if (u === "START_SAVING") return "start";
  return "plan";
};

const urgencyDot = (u) => {
  if (u === "CRITICAL") return "urgency-critical";
  if (u === "URGENT") return "urgency-urgent";
  if (u === "START_SAVING") return "urgency-start";
  return "urgency-plan";
};

function dispatchPlannerSync(userId) {
  try {
    window.dispatchEvent(new CustomEvent("smartspend:purchase-goals-changed", { detail: { userId } }));
    window.dispatchEvent(new CustomEvent("smartspend-financial-sync", { detail: { userId } }));
  } catch {
    /* ignore */
  }
}

/** Typical spend lines per festival — mirrors backend calendar hints (user-friendly presets). */
const FESTIVAL_TYPICAL_CATEGORIES = {
  Holi: ["Clothes", "Food", "Colors"],
  "Eid al-Fitr": ["Clothes", "Food", "Gifts"],
  Navratri: ["Clothes", "Jewelry", "Events"],
  Dussehra: ["Shopping", "Food", "Travel"],
  Diwali: ["Gifts", "Shopping", "Food", "Crackers", "Travel"],
  Christmas: ["Gifts", "Food", "Travel"],
  "New Year": ["Party", "Travel", "Shopping"],
};

function newRowId() {
  if (typeof crypto !== "undefined" && crypto.randomUUID) return crypto.randomUUID();
  return `r-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
}

function breakdownToRows(breakdown) {
  const obj = breakdown && typeof breakdown === "object" ? breakdown : {};
  const entries = Object.entries(obj).filter(([k]) => String(k).trim());
  if (!entries.length) return [{ id: newRowId(), name: "", amount: "" }];
  return entries.map(([name, amount]) => ({
    id: newRowId(),
    name: String(name),
    amount: amount === "" || amount == null ? "" : String(Number(amount)),
  }));
}

function typicalForFestival(festivalName) {
  if (!festivalName) return [];
  const direct = FESTIVAL_TYPICAL_CATEGORIES[festivalName];
  if (direct) return direct;
  const key = Object.keys(FESTIVAL_TYPICAL_CATEGORIES).find(
    (k) => k.toLowerCase() === festivalName.toLowerCase(),
  );
  return key ? FESTIVAL_TYPICAL_CATEGORIES[key] : [];
}

const FestivalPredictor = ({ userId }) => {
  const { showToast } = useToast();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");
  const [budgetFest, setBudgetFest] = useState(null);
  const [planned, setPlanned] = useState("");
  const [categoryRows, setCategoryRows] = useState([]);
  const [savingBudget, setSavingBudget] = useState(false);
  const [importantDays, setImportantDays] = useState([]);
  const [dayModal, setDayModal] = useState(null);
  const [savingDay, setSavingDay] = useState(false);
  const [deletingId, setDeletingId] = useState(null);
  const [expanded, setExpanded] = useState({});
  const [festSaveInput, setFestSaveInput] = useState({});
  const [savingFest, setSavingFest] = useState(null);
  const [highlightFest, setHighlightFest] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    setErr("");
    try {
      const [festRes, dayRes] = await Promise.allSettled([
        getFestivals(userId),
        getFestivalImportantDays(userId),
      ]);
      if (festRes.status === "rejected") {
        throw festRes.reason;
      }
      setData(festRes.value);
      if (dayRes.status === "fulfilled") {
        setImportantDays(dayRes.value.important_days || []);
      } else {
        setImportantDays([]);
      }
    } catch (e) {
      setErr(e.message || "Failed to load festivals");
      setData(null);
      setImportantDays([]);
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

  const openBudget = (f) => {
    setBudgetFest(f);
    setPlanned(String(f.recommended_budget ?? ""));
    setCategoryRows(breakdownToRows(f.category_breakdown));
  };

  const suggestedCategories = useMemo(
    () => (budgetFest ? typicalForFestival(budgetFest.festival_name) : []),
    [budgetFest],
  );

  const categoryRowsTotal = useMemo(() => {
    let sum = 0;
    for (const row of categoryRows) {
      const n = parseFloat(String(row.amount).replace(/,/g, ""));
      if (!Number.isFinite(n) || n < 0) continue;
      if (!String(row.name || "").trim()) continue;
      sum += n;
    }
    return sum;
  }, [categoryRows]);

  const plannedNum = parseFloat(String(planned).replace(/,/g, "")) || 0;
  const sumMismatch =
    plannedNum > 0 && categoryRowsTotal > 0 && Math.abs(categoryRowsTotal - plannedNum) > 1;

  const updateCategoryRow = (id, patch) => {
    setCategoryRows((rows) => rows.map((r) => (r.id === id ? { ...r, ...patch } : r)));
  };

  const addCategoryRow = (presetName = "") => {
    setCategoryRows((rows) => [...rows, { id: newRowId(), name: presetName, amount: "" }]);
  };

  const removeCategoryRow = (id) => {
    setCategoryRows((rows) => {
      const next = rows.filter((r) => r.id !== id);
      return next.length ? next : [{ id: newRowId(), name: "", amount: "" }];
    });
  };

  const applySuggestedTemplate = () => {
    const names = suggestedCategories.length ? suggestedCategories : ["Gifts", "Food", "Travel"];
    setCategoryRows(names.map((name) => ({ id: newRowId(), name, amount: "" })));
    showToast("Added suggested categories — enter amounts (or use “Split evenly”).");
  };

  const splitPlannedEvenly = () => {
    const total = parseFloat(String(planned).replace(/,/g, ""));
    if (!Number.isFinite(total) || total <= 0) {
      showToast("Set a planned total first, then split.");
      return;
    }
    const named = categoryRows.filter((r) => String(r.name || "").trim());
    const rowsToUse = named.length ? named : categoryRows;
    if (!rowsToUse.length) {
      showToast("Add at least one category row.");
      return;
    }
    const n = rowsToUse.length;
    const cents = Math.round(total * 100);
    const baseCents = Math.floor(cents / n);
    const rem = cents - baseCents * n;
    const idToAmount = {};
    rowsToUse.forEach((r, i) => {
      const c = baseCents + (i < rem ? 1 : 0);
      idToAmount[r.id] = (c / 100).toFixed(2);
    });
    setCategoryRows((rows) => rows.map((r) => (idToAmount[r.id] != null ? { ...r, amount: idToAmount[r.id] } : r)));
    showToast("Amounts split across category rows.");
  };

  const buildCategoryBudgets = () => {
    const cats = {};
    for (const row of categoryRows) {
      const name = String(row.name || "").trim();
      if (!name) continue;
      const raw = String(row.amount).replace(/,/g, "").trim();
      if (raw === "") continue;
      const n = parseFloat(raw);
      if (!Number.isFinite(n) || n < 0) {
        throw new Error(`Invalid amount for “${name}”. Use numbers only (e.g. 5000).`);
      }
      cats[name] = n;
    }
    return cats;
  };

  const submitBudget = async () => {
    if (!budgetFest) return;
    let cats = {};
    try {
      cats = buildCategoryBudgets();
    } catch (e) {
      showToast(e.message || "Check category amounts");
      return;
    }
    setSavingBudget(true);
    try {
      await postFestivalSetBudget(userId, {
        festival_name: budgetFest.festival_name,
        planned_budget: parseFloat(planned) || 0,
        category_budgets: cats,
      });
      setBudgetFest(null);
      await load();
      dispatchPlannerSync(userId);
      showToast("Budget saved! ✅");
    } catch (e) {
      showToast(e.message || "Save failed");
    } finally {
      setSavingBudget(false);
    }
  };

  const openDayCreate = () => {
    setDayModal({
      mode: "create",
      title: "",
      event_date: "",
      notes: "",
      repeats_yearly: false,
    });
  };

  const openDayEdit = (d) => {
    setDayModal({
      mode: "edit",
      id: d.id,
      title: d.title,
      event_date: (d.event_date || "").slice(0, 10),
      notes: d.notes || "",
      repeats_yearly: !!d.repeats_yearly,
    });
  };

  const submitDayModal = async () => {
    if (!dayModal?.title?.trim()) {
      showToast("Please enter a title");
      return;
    }
    if (!dayModal.event_date) {
      showToast("Please pick a date");
      return;
    }
    setSavingDay(true);
    try {
      const payload = {
        title: dayModal.title.trim(),
        event_date: dayModal.event_date,
        notes: (dayModal.notes || "").trim(),
        repeats_yearly: !!dayModal.repeats_yearly,
      };
      if (dayModal.mode === "create") {
        await postFestivalImportantDay(userId, payload);
        showToast("Saved ✅");
      } else {
        await putFestivalImportantDay(userId, dayModal.id, payload);
        showToast("Updated ✅");
      }
      setDayModal(null);
      await load();
    } catch (e) {
      showToast(e.message || "Could not save");
    } finally {
      setSavingDay(false);
    }
  };

  const confirmDeleteDay = async (d) => {
    if (!window.confirm(`Remove “${d.title}” from your planner?`)) return;
    setDeletingId(d.id);
    try {
      await deleteFestivalImportantDay(userId, d.id);
      showToast("Removed");
      await load();
    } catch (e) {
      showToast(e.message || "Could not delete");
    } finally {
      setDeletingId(null);
    }
  };

  const upcoming = data?.upcoming_festivals || [];
  const next = data?.next_festival;
  const nf = upcoming[0];

  const mergedTimelineItems = useMemo(() => {
    const items = [];
    for (const f of upcoming) {
      items.push({
        key: `fest-${f.festival_name}`,
        kind: "festival",
        festival: f,
        sort: new Date(`${f.festival_date}T12:00:00`).getTime(),
      });
    }
    for (const d of importantDays) {
      if (!d.in_timeline_window || !d.effective_date) continue;
      items.push({
        key: `imp-${d.id}`,
        kind: "personal",
        day: d,
        sort: new Date(`${d.effective_date}T12:00:00`).getTime(),
      });
    }
    items.sort((a, b) => a.sort - b.sort);
    return items;
  }, [upcoming, importantDays]);

  const importantDaysSorted = useMemo(() => {
    return [...importantDays].sort((a, b) => {
      const da = a.effective_date || a.event_date;
      const db = b.effective_date || b.event_date;
      return String(da).localeCompare(String(db));
    });
  }, [importantDays]);

  const toggleExpand = (name) => {
    setExpanded((e) => ({ ...e, [name]: !e[name] }));
  };

  const logFestSavings = async (fest) => {
    const raw = festSaveInput[fest.festival_name];
    const amt = parseFloat(raw);
    if (Number.isNaN(amt) || amt <= 0) return;
    setSavingFest(fest.festival_name);
    try {
      await putFestivalUpdateSavings(userId, {
        festival_name: fest.festival_name,
        amount_saved: amt,
      });
      setFestSaveInput((s) => ({ ...s, [fest.festival_name]: "" }));
      await load();
      dispatchPlannerSync(userId);
      showToast("Festival savings logged! 🎉");
    } catch (e) {
      showToast(e.message || "Could not log savings");
    } finally {
      setSavingFest(null);
    }
  };

  const scrollToFest = (name) => {
    setHighlightFest(name);
    setExpanded((e) => ({ ...e, [name]: true }));
    setTimeout(() => {
      document.getElementById(`fest-card-${name}`)?.scrollIntoView({ behavior: "smooth", block: "center" });
    }, 80);
    setTimeout(() => setHighlightFest(null), 2000);
  };

  const daysAway = nf?.days_remaining ?? null;
  const gapMo = Number(data?.gap_vs_current_savings_monthly || 0);
  const onTrack = data?.on_track ?? gapMo <= 500;
  const maxOutlook = Math.max(
    Number(data?.total_festival_budget_needed || 0),
    Number(data?.monthly_total_target || 0),
    Number(data?.current_savings_rate_monthly || 0),
    1,
  );

  return (
    <div className="festival-page fade-in">
      <PageHeader
        eyebrow="PLANNING · FESTIVALS & EVENTS"
        title="Festivals & Event Planner"
        subtitle="Save before festivals hit. Celebrate guilt-free."
        accentHex={ACCENT}
      />

      {!loading && !err && (
        <div className="planner-kpi-grid">
          <div className="planner-kpi-card glass-card">
            <div className="planner-kpi-label" style={{ color: ACCENT }}>Next</div>
            <div className="planner-kpi-value" style={{ color: ACCENT }}>{nf?.festival_name ?? "—"}</div>
            <div className="planner-kpi-sub">{daysAway != null ? `${daysAway} days` : "—"}</div>
          </div>
          <div className="planner-kpi-card glass-card">
            <div className="planner-kpi-label">Total budget</div>
            <div className="planner-kpi-value">{inr(data?.total_festival_budget_needed ?? 0)}</div>
            <div className="planner-kpi-sub">All upcoming festivals</div>
          </div>
          <div className="planner-kpi-card glass-card">
            <div className="planner-kpi-label">Monthly target</div>
            <div className="planner-kpi-value">{inr(data?.monthly_total_target ?? 0)}</div>
            <div className="planner-kpi-sub">Combined pace</div>
          </div>
          <div className="planner-kpi-card glass-card">
            <div className="planner-kpi-label">On track</div>
            <div className="planner-kpi-value" style={{ color: onTrack ? "#10b981" : "#f59e0b" }}>
              {onTrack ? "✓ Good" : fmt(gapMo)}
            </div>
            <div className="planner-kpi-sub">{onTrack ? "₹0 gap" : "gap / month"}</div>
          </div>
        </div>
      )}

      {loading && (
        <div className="glass-card feature-card" style={{ marginBottom: 14 }}>
          <p className="muted small" style={{ marginBottom: 12 }}>
            Loading festival plan…
          </p>
          <SkeletonCard lines={4} height={160} />
        </div>
      )}
      {err && (
        <div style={{ marginBottom: 14 }}>
          <ErrorCard message={err} onRetry={load} />
        </div>
      )}

      {!loading && !err && nf && (nf.days_remaining < 30 || nf.urgency === "CRITICAL") && (
        <section className={`glass-card festival-alert ${urgencyClass(nf.urgency)}`}>
          <h3>
            ⚠️ {nf.festival_name.toUpperCase()} — {nf.days_remaining} days!
          </h3>
          <p>
            Last year you spent: {fmt(nf.last_year_spent)} · Saved so far: {fmt(nf.saved_so_far)}
          </p>
          <p>
            You need about {fmt(Math.max(0, nf.recommended_budget - nf.saved_so_far))} before the festival.
          </p>
          <p>
            <strong>~{fmt(nf.daily_saving_needed)}/day</strong> if you start now (indicative).
          </p>
        </section>
      )}

      {!loading && !err && (
        <section className="glass-card festival-timeline-wrap">
          <h3>Timeline</h3>
          <p className="muted small">Tap a festival to jump to its card.</p>
          <div className="planner-h-timeline">
            <div className="planner-h-timeline-track" aria-hidden />
            <div className="planner-h-timeline-nodes">
              {mergedTimelineItems.map((item) =>
                item.kind === "festival" ? (
                  <button
                    key={item.key}
                    type="button"
                    className="planner-h-node"
                    onClick={() => scrollToFest(item.festival.festival_name)}
                  >
                    <span className={`planner-h-node-dot ${urgencyDot(item.festival.urgency)}`} />
                    <span className="planner-h-node-name">{item.festival.festival_name}</span>
                    <span className="planner-h-node-meta">{item.festival.days_remaining}d</span>
                  </button>
                ) : (
                  <button key={item.key} type="button" className="planner-h-node" disabled style={{ opacity: 0.85 }}>
                    <span className="planner-h-node-dot personal" />
                    <span className="planner-h-node-name">{item.day.title}</span>
                    <span className="planner-h-node-meta">{item.day.days_until}d</span>
                  </button>
                ),
              )}
            </div>
          </div>
        </section>
      )}

      {!loading && !err && (
        <section className="glass-card fest-important-panel">
          <div className="fest-important-head">
            <div>
              <h3>Your important days</h3>
              <p className="muted small">
                Birthdays, anniversaries, fees, travel — anything you want on your money calendar. Add, edit, or remove
                anytime.
              </p>
            </div>
            <button type="button" className="btn-primary" onClick={openDayCreate}>
              + Add date
            </button>
          </div>

          {importantDaysSorted.length === 0 ? (
            <p className="muted small" style={{ marginTop: 10 }}>
              No dates yet. Tap <strong>+ Add date</strong> to add your first entry.
            </p>
          ) : (
            <div>
              {importantDaysSorted.map((d) => (
                <div key={d.id} className="planner-important-card">
                  <div>
                    <strong>🎂 {d.title}</strong>
                    <p className="muted small">
                      {d.days_until != null ? `${d.days_until} days` : "—"} ·{" "}
                      {d.repeats_yearly ? "repeats yearly" : "one-time"}
                    </p>
                  </div>
                  <div style={{ display: "flex", gap: 8 }}>
                    <button type="button" className="btn-outline" onClick={() => openDayEdit(d)}>
                      Edit
                    </button>
                    <button
                      type="button"
                      className="btn-outline"
                      disabled={deletingId === d.id}
                      onClick={() => confirmDeleteDay(d)}
                    >
                      {deletingId === d.id ? "…" : "Delete"}
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>
      )}

      {!loading && !err && (
        <section className="glass-card festival-summary-card">
          <h3>📊 Budget outlook</h3>
          <div className="planner-outlook-bars">
            <div className="planner-outlook-row">
              <span>Total needed</span>
              <div className="planner-outlook-bar"><span style={{ width: `${(100 * (data?.total_festival_budget_needed || 0)) / maxOutlook}%`, background: ACCENT }} /></div>
              <strong>{fmt(data?.total_festival_budget_needed)}</strong>
            </div>
            <div className="planner-outlook-row">
              <span>Monthly target</span>
              <div className="planner-outlook-bar"><span style={{ width: `${(100 * (data?.monthly_total_target || 0)) / maxOutlook}%`, background: "#f472b6" }} /></div>
              <strong>{fmt(data?.monthly_total_target)}/mo</strong>
            </div>
            <div className="planner-outlook-row">
              <span>Your avg savings</span>
              <div className="planner-outlook-bar"><span style={{ width: `${(100 * (data?.current_savings_rate_monthly || 0)) / maxOutlook}%`, background: "#10b981" }} /></div>
              <strong>{fmt(data?.current_savings_rate_monthly)}/mo</strong>
            </div>
          </div>
          <p style={{ marginTop: 12, color: onTrack ? "#10b981" : "#f59e0b" }}>
            {onTrack ? "✅ You save enough — ₹0 gap." : `⚠️ Gap ${fmt(gapMo)}/mo — trim spend or raise savings pace.`}
          </p>
          {(data?.gap_close_suggestions || []).map((s, i) => (
            <p key={i} className="muted small">💡 {s}</p>
          ))}
        </section>
      )}


      {!loading && !err && upcoming.length === 0 && (
        <div className="glass-card festival-empty feature-card">
          <EmptyState
            icon="🪔"
            title="No upcoming festivals in the next 6 months"
            subtitle="Check back later or extend your planning window when the calendar updates."
          />
        </div>
      )}

      <div className="planner-grid-v2">
        {!loading &&
          !err &&
          upcoming.map((f) => {
            const isOpen = !!expanded[f.festival_name];
            const pct = Math.min(100, Number(f.progress_pct ?? 0));
            const gap = Math.max(0, (f.recommended_budget || 0) - (f.saved_so_far || 0));
            return (
              <article
                key={f.festival_name}
                id={`fest-card-${f.festival_name}`}
                className={`glass-card planner-card-v2 ${isOpen ? "is-expanded" : ""} ${highlightFest === f.festival_name ? "ring-2 ring-pink-400/50" : ""}`}
              >
                {(f.linked_goals || []).length > 0 && (
                  <div className="planner-link-banner fest">
                    🔗 Linked: {(f.linked_goals || []).map((g) => g.item_name).join(", ")}
                  </div>
                )}
                <header
                  className="planner-card-head-v2"
                  onClick={() => toggleExpand(f.festival_name)}
                  onKeyDown={(e) => e.key === "Enter" && toggleExpand(f.festival_name)}
                  role="button"
                  tabIndex={0}
                >
                  <div>
                    <h3>🪔 {f.festival_name}</h3>
                    <p className="muted small">
                      {new Date(f.festival_date + "T12:00:00").toLocaleDateString("en-IN", {
                        day: "numeric",
                        month: "long",
                        year: "numeric",
                      })}{" "}
                      · {f.days_remaining} days
                    </p>
                  </div>
                  <span className={`planner-urgency-pill ${urgencyPill(f.urgency)}`}>
                    {f.urgency.replace("_", " ")}
                  </span>
                </header>
                <div className="planner-progress-wrap">
                  <div className="planner-progress-bar">
                    <span className="planner-progress-fill fest" style={{ width: `${pct}%` }} />
                  </div>
                  <p className="muted small" style={{ marginTop: 6 }}>
                    Budget {fmt(f.recommended_budget)} · Saved {fmt(f.saved_so_far)} · Gap {fmt(gap)}
                  </p>
                </div>
                <div className="planner-card-metrics">
                  <span>Save {fmt(f.monthly_saving_needed)}/mo</span>
                  <span>{fmt(f.weekly_saving_needed)}/wk</span>
                  <span>{fmt(f.daily_saving_needed)}/day</span>
                </div>
                <div className="planner-card-actions-v2">
                  <button type="button" className="btn-primary" onClick={() => openBudget(f)}>
                    Set budget
                  </button>
                  <div className="planner-log-savings">
                    <input
                      type="number"
                      min="0"
                      placeholder="₹ log savings"
                      value={festSaveInput[f.festival_name] || ""}
                      onChange={(e) =>
                        setFestSaveInput((s) => ({ ...s, [f.festival_name]: e.target.value }))
                      }
                    />
                    <button
                      type="button"
                      className="btn-outline"
                      disabled={savingFest === f.festival_name}
                      onClick={() => logFestSavings(f)}
                    >
                      {savingFest === f.festival_name ? "…" : "+ Add"}
                    </button>
                  </div>
                  <button type="button" className="btn-outline" onClick={() => toggleExpand(f.festival_name)}>
                    {isOpen ? "Hide ▲" : "Details ▼"}
                  </button>
                </div>
                {isOpen && (
                  <div className="planner-card-body-v2">
                    {Object.keys(f.category_breakdown || {}).length > 0 && (
                      <div className="planner-chip-row">
                        {Object.entries(f.category_breakdown || {}).map(([k, v]) => (
                          <span key={k} className="planner-chip">
                            {k} {fmt(v)}
                          </span>
                        ))}
                      </div>
                    )}
                    {f.saving_tip && (
                      <p className="muted small">
                        <strong>💡</strong> {f.saving_tip}
                      </p>
                    )}
                    {f.if_no_saving_warning && (
                      <p className="muted small" style={{ color: "#f59e0b" }}>
                        <strong>⚠️</strong> {f.if_no_saving_warning}
                      </p>
                    )}
                    {f.ai_advice && (
                      <p className="muted small" style={{ marginTop: 8 }}>
                        {f.ai_advice}
                      </p>
                    )}
                  </div>
                )}
              </article>
            );
          })}
      </div>
      {dayModal && (
        <div
          className="modal-overlay"
          role="dialog"
          aria-modal="true"
          aria-labelledby="fest-day-title"
          onClick={(e) => e.target === e.currentTarget && setDayModal(null)}
        >
          <div className="modal-card glass-card fest-budget-modal" onClick={(e) => e.stopPropagation()}>
            <h3 id="fest-day-title">
              {dayModal.mode === "create" ? "Add important day" : "Edit important day"}
            </h3>
            <p className="fest-budget-hint">
              For yearly events, pick the next date (or the real date this year). We roll it forward automatically each
              year.
            </p>
            <label className="fraud-field" style={{ marginTop: 12 }}>
              Title
              <input
                value={dayModal.title}
                onChange={(e) => setDayModal({ ...dayModal, title: e.target.value })}
                placeholder="e.g. Mom’s birthday"
                maxLength={200}
                autoComplete="off"
              />
            </label>
            <label className="fraud-field">
              Date
              <input
                type="date"
                value={dayModal.event_date}
                onChange={(e) => setDayModal({ ...dayModal, event_date: e.target.value })}
              />
            </label>
            <label className="fraud-field-checkbox">
              <input
                type="checkbox"
                checked={!!dayModal.repeats_yearly}
                onChange={(e) => setDayModal({ ...dayModal, repeats_yearly: e.target.checked })}
              />
              <span>Repeats every year (birthdays, anniversaries)</span>
            </label>
            <label className="fraud-field">
              Notes (optional)
              <textarea
                rows={3}
                value={dayModal.notes}
                onChange={(e) => setDayModal({ ...dayModal, notes: e.target.value })}
                placeholder="Gift ideas, budget cap, who to invite…"
              />
            </label>
            <div className="fest-card-actions" style={{ display: "flex", justifyContent: "flex-end", gap: 10 }}>
              <button type="button" className="btn-outline" onClick={() => setDayModal(null)}>
                Cancel
              </button>
              <button type="button" className="btn-primary" disabled={savingDay} onClick={submitDayModal}>
                {savingDay ? "Saving…" : "Save"}
              </button>
            </div>
          </div>
        </div>
      )}

      {budgetFest && (
        <div
          className="modal-overlay"
          role="dialog"
          aria-modal="true"
          aria-labelledby="fest-budget-title"
          onClick={(e) => e.target === e.currentTarget && setBudgetFest(null)}
        >
          <div className="modal-card glass-card fest-budget-modal" onClick={(e) => e.stopPropagation()}>
            <h3 id="fest-budget-title">Set budget — {budgetFest.festival_name}</h3>
            <p className="fest-budget-hint">
              Set your total envelope, then split it into real spend lines (gifts, food, travel…). No JSON — just add
              rows.
            </p>

            <label className="fraud-field" style={{ marginTop: 14 }}>
              Planned total (₹)
              <input
                value={planned}
                onChange={(e) => setPlanned(e.target.value)}
                type="number"
                min={0}
                step={100}
                placeholder="e.g. 25000"
              />
            </label>

            <div className="fest-budget-categories">
              <span className="fest-budget-section-label">Category breakdown</span>

              <div className="fest-budget-toolbar">
                <button type="button" className="btn-outline" onClick={() => addCategoryRow("")}>
                  + Add row
                </button>
                {suggestedCategories.length > 0 ? (
                  <button type="button" className="btn-outline" onClick={applySuggestedTemplate}>
                    Use {budgetFest.festival_name} template
                  </button>
                ) : null}
                <button type="button" className="btn-outline" onClick={splitPlannedEvenly}>
                  Split planned total evenly
                </button>
              </div>

              {suggestedCategories.length > 0 ? (
                <div className="fest-budget-toolbar" style={{ marginTop: 0 }}>
                  <span className="muted small" style={{ width: "100%", marginBottom: 4 }}>
                    Quick add:
                  </span>
                  {suggestedCategories.map((c) => (
                    <button key={c} type="button" className="fest-budget-chip" onClick={() => addCategoryRow(c)}>
                      + {c}
                    </button>
                  ))}
                </div>
              ) : null}

              {categoryRows.map((row) => (
                <div key={row.id} className="fest-budget-row">
                  <label className="fraud-field">
                    Category
                    <input
                      value={row.name}
                      onChange={(e) => updateCategoryRow(row.id, { name: e.target.value })}
                      placeholder="e.g. Gifts"
                      autoComplete="off"
                    />
                  </label>
                  <label className="fraud-field">
                    Amount (₹)
                    <input
                      value={row.amount}
                      onChange={(e) => updateCategoryRow(row.id, { amount: e.target.value })}
                      type="number"
                      min={0}
                      step={100}
                      placeholder="0"
                    />
                  </label>
                  <button
                    type="button"
                    className="fest-budget-remove"
                    aria-label={`Remove ${row.name || "row"}`}
                    onClick={() => removeCategoryRow(row.id)}
                  >
                    ×
                  </button>
                </div>
              ))}

              <div className={`fest-budget-sum${sumMismatch ? " fest-budget-sum-warn" : ""}`}>
                <strong>Sum of lines:</strong> {fmt(categoryRowsTotal)}
                {plannedNum > 0 ? (
                  <>
                    {" "}
                    · <strong>Planned total:</strong> {fmt(plannedNum)}
                  </>
                ) : null}
                {sumMismatch ? (
                  <span>
                    {" "}
                    — heads-up: totals differ (ok if you left “misc” unlisted).
                  </span>
                ) : null}
              </div>
            </div>

            <div className="fest-card-actions" style={{ display: "flex", justifyContent: "flex-end", gap: 10 }}>
              <button type="button" className="btn-outline" onClick={() => setBudgetFest(null)}>
                Cancel
              </button>
              <button type="button" className="btn-primary" disabled={savingBudget} onClick={submitBudget}>
                {savingBudget ? "Saving…" : "Save budget"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default FestivalPredictor;
