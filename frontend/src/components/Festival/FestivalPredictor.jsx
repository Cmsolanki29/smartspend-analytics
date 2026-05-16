import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  deleteFestivalImportantDay,
  getFestivals,
  getFestivalImportantDays,
  postFestivalImportantDay,
  postFestivalSetBudget,
  putFestivalImportantDay,
} from "../../services/api";
import { useToast } from "../common/Toast";
import { EmptyState } from "../common/EmptyState";
import { ErrorCard } from "../common/ErrorCard";
import { SkeletonCard } from "../common/SkeletonCard";
import { PageHeader } from "../Dashboard/shared/PageHeader";
import { HeroKpiTile } from "../Dashboard/shared/HeroKpiTile";
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

  const daysAway      = nf?.days_remaining ?? nf?.days_away ?? null;
  const festivalName  = nf?.festival_name ?? "Next festival";
  const suggestedBudget = nf?.recommended_budget ?? 0;

  return (
    <div className="festival-page fade-in">
      <PageHeader
        eyebrow="FESTIVALS"
        title="Plan the Celebration"
        subtitle="Save before festivals hit. Budget smarter, celebrate guilt-free, no financial hangover."
        accentHex={ACCENT}
        rightSlot={
          <HeroKpiTile
            label="Days to next festival"
            value={daysAway != null ? String(daysAway) : "—"}
            caption={`${festivalName} · suggested ${inr(suggestedBudget)}`}
            accentHex={ACCENT}
            loading={loading}
          />
        }
      />

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
        <section className="glass-card festival-timeline-wrap fest-combined-planner">
          <h3>Timeline (next 6 months)</h3>
          <p className="muted small fest-combined-lede">
            SmartSpend festivals and your own dates in the same planning window (~6 months). Festival dates are fixed;
            your entries are private to your account.
          </p>

          <div className="fest-timeline-stack">
            <div className="fest-tl-lane">
              <span className="fest-tl-lane-label">Festivals</span>
              <div className="festival-timeline">
                {upcoming.length === 0 ? (
                  <span className="muted small">No festivals in this window.</span>
                ) : (
                  upcoming.map((f) => (
                    <div key={f.festival_name} className={`fest-tl-node ${urgencyClass(f.urgency)}`}>
                      <span className="fest-tl-name">🪔 {f.festival_name}</span>
                      <span className="fest-tl-d">{f.days_remaining}d</span>
                    </div>
                  ))
                )}
              </div>
            </div>

            <div className="fest-tl-lane">
              <span className="fest-tl-lane-label">Your important days</span>
              <div className="festival-timeline">
                {importantDays.filter((d) => d.in_timeline_window).length === 0 ? (
                  <span className="muted small">None in this window yet — add in the section below.</span>
                ) : (
                  importantDays
                    .filter((d) => d.in_timeline_window)
                    .map((d) => (
                      <div key={d.id} className="fest-tl-node fest-tl-node-personal">
                        <span className="fest-tl-name">📌 {d.title}</span>
                        <span className="fest-tl-d">{d.days_until != null ? `${d.days_until}d` : "—"}</span>
                      </div>
                    ))
                )}
              </div>
            </div>

            <div className="fest-tl-lane fest-tl-lane-merged">
              <span className="fest-tl-lane-label">All at a glance (soonest → later)</span>
              <div className="festival-timeline fest-tl-merged-row">
                {mergedTimelineItems.length === 0 ? (
                  <span className="muted small">Nothing in the combined view for this window.</span>
                ) : (
                  mergedTimelineItems.map((item) =>
                    item.kind === "festival" ? (
                      <div
                        key={item.key}
                        className={`fest-tl-node fest-tl-node-merged ${urgencyClass(item.festival.urgency)}`}
                      >
                        <span className="fest-tl-tag fest-tl-tag-fest">Fest</span>
                        <span className="fest-tl-name">{item.festival.festival_name}</span>
                        <span className="fest-tl-d">{item.festival.days_remaining}d</span>
                      </div>
                    ) : (
                      <div key={item.key} className="fest-tl-node fest-tl-node-merged fest-tl-node-personal">
                        <span className="fest-tl-tag fest-tl-tag-you">You</span>
                        <span className="fest-tl-name">{item.day.title}</span>
                        <span className="fest-tl-d">{item.day.days_until}d</span>
                      </div>
                    ),
                  )
                )}
              </div>
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
            <ul className="fest-important-list">
              {importantDaysSorted.map((d) => (
                <li key={d.id} className="fest-important-row">
                  <div className="fest-important-main">
                    <strong>{d.title}</strong>
                    <span className="fest-important-meta">
                      {d.repeats_yearly ? "Every year" : "One-time"} · on calendar:{" "}
                      {new Date(`${d.event_date}T12:00:00`).toLocaleDateString("en-IN", {
                        day: "numeric",
                        month: "short",
                        year: "numeric",
                      })}
                      {d.repeats_yearly && d.effective_date ? (
                        <>
                          {" "}
                          · next:{" "}
                          {new Date(`${d.effective_date}T12:00:00`).toLocaleDateString("en-IN", {
                            day: "numeric",
                            month: "short",
                            year: "numeric",
                          })}
                        </>
                      ) : null}
                      {!d.in_timeline_window ? (
                        <span className="fest-important-pill">Outside 6-mo strip</span>
                      ) : null}
                    </span>
                    {d.notes ? <p className="muted small fest-important-notes">{d.notes}</p> : null}
                  </div>
                  <div className="fest-important-actions">
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
                </li>
              ))}
            </ul>
          )}
        </section>
      )}

      {!loading && !err && (
        <section className="glass-card festival-summary-card">
          <h3>📊 Your festival budget outlook</h3>
          <p>Total planned need (sum of recommendations): {fmt(data?.total_festival_budget_needed)}</p>
          <p>Monthly saving target (sum per festival): {fmt(data?.monthly_total_target)}/mo</p>
          <p>Your recent avg savings: {fmt(data?.current_savings_rate_monthly)}/mo</p>
          <p>
            Gap: <strong>{fmt(data?.gap_vs_current_savings_monthly)}</strong>/mo more needed
          </p>
          {(data?.gap_close_suggestions || []).map((s, i) => (
            <p key={i} className="muted small">
              • {s}
            </p>
          ))}
          <p className="muted small">Biggest line item festival: {data?.biggest_festival || "—"}</p>
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

      <div className="festival-grid">
        {!loading &&
          !err &&
          upcoming.map((f) => (
            <article key={f.festival_name} className={`glass-card festival-card ${urgencyClass(f.urgency)}`}>
              <header className="fest-card-head">
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
                <span className="fest-badge">{f.urgency.replace("_", " ")}</span>
              </header>
              <p>
                Last year: {fmt(f.last_year_spent)} · Recommended: {fmt(f.recommended_budget)}
              </p>
              <p>
                Save / month: {fmt(f.monthly_saving_needed)} · week: {fmt(f.weekly_saving_needed)} · day:{" "}
                {fmt(f.daily_saving_needed)}
              </p>
              <div className="fest-cats">
                <strong>Category breakdown</strong>
                <ul>
                  {Object.entries(f.category_breakdown || {}).map(([k, v]) => (
                    <li key={k}>
                      {k}: {fmt(v)}
                    </li>
                  ))}
                  {(!f.category_breakdown || Object.keys(f.category_breakdown).length === 0) && (
                    <li className="muted">No breakdown yet — set a budget to split categories.</li>
                  )}
                </ul>
              </div>
              {f.ai_advice && (
                <blockquote className="fest-ai">
                  <strong>🤖 AI</strong>
                  <p>{f.ai_advice}</p>
                  {f.saving_tip && <p className="fest-tip">{f.saving_tip}</p>}
                  {f.if_no_saving_warning && <p className="fest-warn">{f.if_no_saving_warning}</p>}
                </blockquote>
              )}
              <div className="fest-card-actions">
                <button type="button" className="btn-primary" onClick={() => openBudget(f)}>
                  Set my budget
                </button>
              </div>
            </article>
          ))}
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
