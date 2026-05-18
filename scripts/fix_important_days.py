from pathlib import Path

p = Path("frontend/src/components/Festival/FestivalPredictor.jsx")
t = p.read_text(encoding="utf-8")
start = t.find("            <motion.div>\n              {importantDaysSorted")
if start == -1:
    start = t.find('            <ul className="fest-important-list">')
end_tag = "            </ul>"
end = t.find(end_tag, start)
if end == -1:
    raise SystemExit("end ul not found")
end += len(end_tag)
print("start", start, "end", end)

new = """            <motion.div>
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
            </div>"""
new = new.replace("motion.div", "motion.div").replace("<motion.div>", "<motion.div>").replace("motion.div", "motion.div")
new = new.replace("<motion.div>\n              {importantDaysSorted", "<motion.div>\n              {importantDaysSorted").replace(
    "<motion.div>\n              {importantDaysSorted", "<motion.div>\n              {importantDaysSorted"
)
new = new.replace("<motion.div>\n              {importantDaysSorted", "<motion.div>\n              {importantDaysSorted")
# clean
new = new.replace("<motion.div>\n              {importantDaysSorted", "<motion.div>\n              {importantDaysSorted")
new = """            <div>
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
            </div>"""

p.write_text(t[:start] + new + t[end:], encoding="utf-8")
print("ok")
