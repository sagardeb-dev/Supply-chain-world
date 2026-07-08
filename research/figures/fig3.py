# Figure 3 (appendix): seed-1 freeze timeline. Reads ONLY the raw trace.
import re
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

TRACE = (Path(__file__).resolve().parents[2] / "backend" / "runs" / "ladder-v1"
         / "anthropic-claude-sonnet-5" / "seed1-rich.chat.txt")
text = TRACE.read_text()

# start-of-week inventory: WEEK 0 SITUATION line, then "WORLD ADVANCED -> week N ... SITUATION inv X"
inv = {0: int(re.search(r"WEEK 0 SITUATION\s+inv (\d+)", text).group(1))}
for m in re.finditer(r"WORLD ADVANCED -> week (\d+).*?\n\s+SITUATION\s+inv (\d+)", text):
    inv[int(m.group(1))] = int(m.group(2))

# per deciding week: sea order qty and air qty
sea, air = {}, {}
blocks = re.split(r"=+ DECIDING WEEK (\d+) =+", text)
for i in range(1, len(blocks), 2):
    wk, body = int(blocks[i]), blocks[i + 1]
    q = re.search(r"place_order\(qty=(\d+)", body)
    sea[wk] = int(q.group(1)) if q else 0
    a = re.search(r"expedite_air\(qty=(\d+)", body)
    air[wk] = int(a.group(1)) if a else 0

weeks = list(range(26))  # decisions cover weeks 0-25; week-26 row is the end state
assert sorted(inv) == list(range(27)) and len(sea) == 26, (len(inv), len(sea))
zero_weeks = [w for w in weeks if inv[w] == 0]
assert zero_weeks == [21, 22, 23, 24], zero_weeks  # the documented freeze
assert [w for w in range(14, 26) if sea[w] == 0] == [16, 17, 19, 22, 23, 24, 25]

# truth windows for seed 1 (case-studies.md / appendix table)
PORT = (17, 24); SEAS = (20, 26); PROMO = (9, 12)

AGENT = "#C86214"; GRAY = "#4B5563"; BAND = "#9CA3AF"
plt.rcParams.update({"font.family": "sans-serif", "font.size": 7,
                     "axes.edgecolor": "#787880", "axes.linewidth": 0.7})
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(5.5, 2.6), sharex=True,
                               gridspec_kw={"height_ratios": [1.4, 1], "hspace": 0.18})

for ax in (ax1, ax2):
    ax.axvspan(PORT[0], PORT[1] + 1, color=BAND, alpha=0.22, zorder=0, lw=0)
    ax.spines[["top", "right"]].set_visible(False)
    ax.set_xlim(-0.5, 27.8)

# regime windows as rugs above the top panel (clip_on=False keeps them outside)
for (a, b), lab, y in ((PROMO, "demand: promo", 113),
                       (SEAS, "demand: seasonal lift", 113)):
    ax1.plot([a, b + 1], [y, y], color=GRAY, lw=2.5, solid_capstyle="butt",
             clip_on=False)
    ax1.text((a + b + 1) / 2, y + 5, lab, ha="center", fontsize=5.8,
             color=GRAY, clip_on=False)
ax1.text((PORT[0] + PORT[1] + 1) / 2, 132, "port congested (wk 17–24)",
         ha="center", fontsize=5.8, color="#6B7280", clip_on=False)

ax1.plot(weeks + [26], [inv[w] for w in weeks] + [inv[26]], color=AGENT,
         lw=1.6, marker="o", ms=2.6, mec="none")
ax1.scatter(zero_weeks, [0] * 4, s=26, facecolors="none",
            edgecolors="#B3261E", lw=1.0, zorder=5)
ax1.annotate("4 weeks at zero inventory", xy=(22.5, 2), xytext=(17.0, 62),
             fontsize=6, color="#B3261E", ha="center",
             arrowprops=dict(arrowstyle="-", color="#B3261E", lw=0.6))
ax1.annotate("congestion clears:\ntrapped pipeline\nlands", xy=(25.7, 98),
             xytext=(27.0, 30), fontsize=6, color="#333", ha="center",
             arrowprops=dict(arrowstyle="-", color="#333", lw=0.6))
ax1.set_ylabel("on-hand units", fontsize=6.5)
ax1.set_ylim(-6, 118)

ax2.bar(weeks, [sea[w] for w in weeks], width=0.62, color=GRAY, label="sea order")
ax2.bar(weeks, [air[w] for w in weeks], width=0.62,
        bottom=[sea[w] for w in weeks], color=AGENT, label="air expedite")
ax2.annotate("wk 16: diagnoses congestion,\nskips the sea order", xy=(16.4, 21),
             xytext=(14.0, 38), fontsize=6, color="#333", ha="center",
             arrowprops=dict(arrowstyle="-", color="#333", lw=0.6))
ax2.annotate("wk 22–24: no sea orders\nwhile stocked out", xy=(23, 21),
             xytext=(24.8, 38), fontsize=6, color="#B3261E", ha="center",
             arrowprops=dict(arrowstyle="-", color="#B3261E", lw=0.6))
ax2.set_ylabel("units ordered", fontsize=6.5)
ax2.set_xlabel("week", fontsize=6.5)
ax2.set_ylim(0, 46)
ax2.set_xticks(range(0, 26, 5))
ax2.legend(fontsize=6, frameon=False, loc="upper left", handlelength=1.2,
           borderpad=0.1, labelspacing=0.2)

fig.savefig(Path(__file__).parent / "fig3.pdf", bbox_inches="tight")
fig.savefig(Path(__file__).parent / "fig3-preview.png", dpi=200, bbox_inches="tight")
print("written fig3.pdf; zero weeks", zero_weeks)
