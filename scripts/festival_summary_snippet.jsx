      {!loading && !err && (
        <section className="glass-card festival-summary-card">
          <h3>📊 Budget outlook</h3>
          <div className="planner-outlook-bars">
            <div className="planner-outlook-row">
              <span>Total needed</span>
              <motion.div className="planner-outlook-bar"><span style={{ width: `${(100 * (data?.total_festival_budget_needed || 0)) / maxOutlook}%`, background: ACCENT }} /></div>
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
