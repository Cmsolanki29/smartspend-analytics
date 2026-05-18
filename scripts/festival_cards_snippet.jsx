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
