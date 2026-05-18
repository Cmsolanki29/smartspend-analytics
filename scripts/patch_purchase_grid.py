from pathlib import Path

p = Path("frontend/src/components/Purchase/PurchasePlanner.jsx")
text = p.read_text(encoding="utf-8")

start = text.find('      <motion.div className="purchase-grid">')
if start == -1:
    start = text.find('      <div className="purchase-grid">')
end = text.find("      {modal &&", start)
assert start != -1 and end != -1

cards = Path("scripts/purchase_cards_snippet.jsx").read_text(encoding="utf-8")
cards = cards.replace("motion.div", "motion.div")
text = text[:start] + cards + text[end:]

old_sum = """      {!loading && !err && goals.length > 1 && (
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
      )}"""

new_sum = Path("scripts/purchase_summary_snippet.jsx").read_text(encoding="utf-8")
if old_sum in text:
    text = text.replace(old_sum, new_sum)
    print("summary ok")

text = text.replace(
    '      await load();\n      showToast("Goal added successfully! ✅");',
    '      await load();\n      dispatchPlannerSync(userId);\n      showToast("Goal added successfully! ✅");',
)

if "postponeGoal &&" not in text:
    text = text.replace(
        "    </div>\n  );\n};\n\nexport default PurchasePlanner;",
        Path("scripts/purchase_postpone_modal.jsx").read_text(encoding="utf-8"),
    )
    print("modal ok")

text = text.replace("motion.div", "motion.div")
p.write_text(text, encoding="utf-8")
print("done")
