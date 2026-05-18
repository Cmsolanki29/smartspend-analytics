from pathlib import Path

p = Path("frontend/src/components/Festival/FestivalPredictor.jsx")
text = p.read_text(encoding="utf-8")
text = text.replace('import { HeroKpiTile } from "../Dashboard/shared/HeroKpiTile";\n', "")

start = text.find('      <div className="festival-grid">')
end = text.find("      {dayModal &&", start)
assert start != -1 and end != -1

new_cards = Path("scripts/festival_cards_snippet.jsx").read_text(encoding="utf-8")
text = text[:start] + new_cards + text[end:]

old_summary = """      {!loading && !err && (
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
      )}"""

new_summary = Path("scripts/festival_summary_snippet.jsx").read_text(encoding="utf-8")
if old_summary in text:
    text = text.replace(old_summary, new_summary)
    print("summary ok")
else:
    print("summary missing")

p.write_text(text, encoding="utf-8")
print("wrote festival predictor")
