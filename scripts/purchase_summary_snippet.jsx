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
