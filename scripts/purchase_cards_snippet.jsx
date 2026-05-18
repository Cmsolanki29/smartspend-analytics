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
