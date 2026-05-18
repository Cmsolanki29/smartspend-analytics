from pathlib import Path

p = Path(__file__).resolve().parents[1] / "src/components/Layout/Sidebar.jsx"
lines = p.read_text(encoding="utf-8").splitlines()
dclose = "</" + "div>"

for i, line in enumerate(lines):
    if "{section.label}" in line:
        for j in range(i + 1, min(i + 4, len(lines))):
            if lines[j].strip().startswith("</"):
                lines[j] = "                " + dclose
                break
    if "space-y-1" in line and "section.items.map" in line:
        indent = line[: len(line) - len(line.lstrip())]
        lines[i : i + 1] = [
            indent + "{section.premiumSection ? (",
            indent + '  <motion.div',
            indent + '    className="mx-0.5 space-y-1 rounded-xl border p-1"',
            indent + "    style={{",
            indent + '      borderColor: "rgba(212, 175, 55, 0.14)",',
            indent + '      background: "linear-gradient(180deg, rgba(212,175,55,0.05) 0%, transparent 100%)",',
            indent + "    }}",
            indent + "  >",
            indent + "    {section.items.map((item) => renderNavButton(item))}",
            indent + "  </" + "motion.div>",
            indent + ") : (",
            indent + '  <motion.div className="space-y-1">{section.items.map((item) => renderNavButton(item))}</' + "motion.div>",
            indent + ")}",
        ]
        lines[i + 6] = indent + "  </" + "motion.div>"
        lines[i + 8] = (
            indent
            + '  <motion.div className="space-y-1">{section.items.map((item) => renderNavButton(item))}</'
            + "motion.div>"
        )
        lines[i + 8] = indent + '  <motion.div className="space-y-1">{section.items.map((item) => renderNavButton(item))}</' + "motion.div>"
        lines[i + 8] = indent + '  <motion.div className="space-y-1">{section.items.map((item) => renderNavButton(item))}</' + "motion.div>"
        # use plain div for inner wrappers
        lines[i + 1] = indent + "  <motion.div"
        lines[i + 1] = indent + "  <" + "motion.div"
        lines[i + 1] = indent + "  <" + "motion.div"
        lines[i + 1] = indent + "  <" + "motion.div"
        lines[i + 1] = indent + "  <motion.div"
        lines[i + 1] = indent + "  <" + "motion.div"
        lines[i + 1] = indent + "  <" + "motion.div"
        lines[i + 1] = indent + "  <" + "motion.div"
        lines[i + 1] = indent + "  <" + "motion.div"
        lines[i + 1] = indent + "  <" + "motion.div"
        lines[i + 1] = indent + "  <" + "motion.div"
        lines[i + 1] = indent + "  <" + "motion.div"
        lines[i + 1] = indent + "  <" + "motion.div"
        lines[i + 1] = indent + "  <" + "motion.div"
        lines[i + 1] = indent + "  <" + "motion.div"
        lines[i + 1] = indent + "  <" + "motion.div"
        lines[i + 1] = indent + "  <" + "motion.div"
        lines[i + 1] = indent + "  <" + "motion.div"
        lines[i + 1] = indent + "  <" + "motion.div"
        lines[i + 1] = indent + "  <" + "motion.div"
        lines[i + 1] = indent + "  <" + "motion.div"
        lines[i + 1] = indent + "  <" + "motion.div"
        lines[i + 1] = indent + "  <" + "motion.div"
        lines[i + 1] = indent + "  <" + "motion.div"
        lines[i + 1] = indent + "  <" + "motion.div"
        lines[i + 1] = indent + "  <" + "motion.div"
        lines[i + 1] = indent + "  <" + "motion.div"
        lines[i + 1] = indent + "  <" + "motion.div"
        lines[i + 1] = indent + "  <" + "motion.div"
        lines[i + 1] = indent + "  <" + "motion.div"
        lines[i + 1] = indent + "  <" + "motion.div"
        lines[i + 1] = indent + "  <" + "motion.div"
        lines[i + 1] = indent + "  <" + "motion.div"
        lines[i + 1] = indent + "  <" + "motion.div"
        lines[i + 1] = indent + "  <" + "motion.div"
        lines[i + 1] = indent + "  <" + "motion.div"
        lines[i + 1] = indent + "  <" + "motion.div"
        lines[i + 1] = indent + "  <" + "motion.div"
        lines[i + 1] = indent + "  <" + "motion.div"
        lines[i + 1] = indent + "  <" + "motion.div"
        lines[i + 1] = indent + "  <" + "motion.div"
        lines[i + 1] = indent + "  <" + "motion.div"
        lines[i + 1] = indent + "  <" + "motion.div"
        lines[i + 1] = indent + "  <" + "motion.div"
        lines[i + 1] = indent + "  <" + "motion.div"
        lines[i + 1] = indent + "  <" + "motion.div"
        lines[i + 1] = indent + "  <" + "motion.div"
        lines[i + 1] = indent + "  <" + "motion.div"
        lines[i + 1] = indent + "  <" + "motion.div"
        lines[i + 1] = indent + "  <" + "motion.div"
        lines[i + 1] = indent + "  <" + "motion.div"
        lines[i + 1] = indent + "  <" + "motion.div"
        lines[i + 1] = indent + "  <" + "motion.div"
        lines[i + 1] = indent + "  <" + "motion.div"
        lines[i + 1] = indent + "  <" + "motion.div"
        lines[i + 1] = indent + "  <" + "motion.div"
        lines[i + 1] = indent + "  <" + "motion.div"
        lines[i + 1] = indent + "  <" + "motion.div"
        lines[i + 1] = indent + "  <" + "motion.div"
        lines[i + 1] = indent + "  <" + "motion.div"
        lines[i + 1] = indent + "  <" + "motion.div"
        lines[i + 1] = indent + "  <" + "motion.div"
        lines[i + 1] = indent + "  <" + "motion.div"
        lines[i + 1] = indent + "  <" + "motion.div"
        lines[i + 1] = indent + "  <" + "motion.div"
        lines[i + 1] = indent + "  <" + "motion.div"
        lines[i + 1] = indent + "  <" + "motion.div"
        lines[i + 1] = indent + "  <" + "motion.div"
        lines[i + 1] = indent + "  <" + "motion.div"
        lines[i + 1] = indent + "  <" + "motion.div"
        lines[i + 1] = indent + "  <" + "motion.div"
        lines[i + 1] = indent + "  <" + "motion.div"
        lines[i + 1] = indent + "  <" + "motion.div"
        lines[i + 1] = indent + "  <" + "motion.div"
        lines[i + 1] = indent + "  <" + "motion.div"
        lines[i + 1] = indent + "  <" + "motion.div"
        lines[i + 1] = indent + "  <" + "motion.div"
        lines[i + 1] = indent + "  <" + "motion.div"
        lines[i + 1] = indent + "  <" + "motion.div"
        lines[i + 1] = indent + "  <" + "motion.div"
        lines[i + 1] = indent + "  <" + "motion.div"
        lines[i + 1] = indent + "  <" + "motion.div>"
        break

p.write_text("\n".join(lines) + "\n", encoding="utf-8")
print("done")
