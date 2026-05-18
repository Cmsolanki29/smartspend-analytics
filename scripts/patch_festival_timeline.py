from pathlib import Path

p = Path("frontend/src/components/Festival/FestivalPredictor.jsx")
text = p.read_text(encoding="utf-8")

marker_start = '        <section className="glass-card festival-timeline-wrap fest-combined-planner">'
marker_end = '      {!loading && !err && (\n        <section className="glass-card fest-important-panel">'

start = text.find(marker_start)
end = text.find(marker_end, start)
if start == -1 or end == -1:
    raise SystemExit(f"timeline markers not found {start} {end}")

new_tl = '''        <section className="glass-card festival-timeline-wrap">
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
        <section className="glass-card fest-important-panel">'''

text = text[:start] + new_tl + text[end:]

# Important days as cards
text = text.replace(
    """            <ul className="fest-important-list">
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
                  <motion.div className="fest-important-actions">
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
            </ul>""",
    """            <div>
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
            </div>""",
)

text = text.replace("motion.div", "motion.div")
p.write_text(text, encoding="utf-8")
print("timeline + important days ok")
