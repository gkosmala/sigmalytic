from pathlib import Path

path = Path("frontend/campaign_tab.py")

terms = [
    "Day",
    "Decay",
    "Adv",
    "Fail",
    "transition_advance_prob",
    "transition_failure_prob",
    "decay_score",
    "duration_days",
    "campaign_age_days",
]

lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
out = []

for i, line in enumerate(lines, start=1):
    if any(t in line for t in terms):
        out.append("")
        out.append(f"--- line {i} ---")
        for j in range(max(1, i - 2), min(len(lines), i + 2) + 1):
            out.append(f"{j}: {lines[j - 1]}")

Path("campaign_zero_lines.txt").write_text("\n".join(out), encoding="utf-8")
print("created campaign_zero_lines.txt")
