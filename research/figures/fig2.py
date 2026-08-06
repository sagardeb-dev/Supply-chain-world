# Figure 2: detection uniform vs skill divergent. Reads ONLY from runs files.
# Freeze #2 era (2026-07-15): four models, all 50 seeds each. Skill from
# skill_scores.csv (seed 11 excluded — negative oracle headroom, skill
# undefined); detection from belief_metrics.csv (283 episodes per model).
import csv, sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

BACKEND = Path(__file__).resolve().parents[2] / "backend"
ROOT = BACKEND / "runs" / "ladder-v1"

MODELS = ["sonnet-5", "gpt-5.4", "deepseek-v4-pro", "grok-4.5"]
CSVKEY = {"sonnet-5": "anthropic-claude-sonnet-5", "gpt-5.4": "openai-gpt-5.4",
          "deepseek-v4-pro": "deepseek-deepseek-v4-pro", "grok-4.5": "x-ai-grok-4.5"}
KEY2M = {v: k for k, v in CSVKEY.items()}
EXCLUDE = {11}  # skill undefined (floor beats oracle); results.md metric property

# ---- per-seed skill straight from the canonical CSV ----
skill = {m: {} for m in MODELS}   # model -> seed -> skill
group_of = {}
with open(ROOT / "skill_scores.csv") as f:
    for row in csv.DictReader(f):
        seed = int(row["seed"])
        if seed in EXCLUDE or row["model"] not in KEY2M:
            continue
        skill[KEY2M[row["model"]]][seed] = float(row["skill"])
        group_of[seed] = row["group"]
for m in MODELS:
    assert len(skill[m]) == 49, f"{m}: {len(skill[m])} scoreable seeds"

GROUPS = {g: sorted(s for s, gg in group_of.items() if gg == g)
          for g in ("ISOLATED", "PERSISTENT", "COMPOUND")}
assert tuple(len(GROUPS[g]) for g in GROUPS) == (11, 15, 23)

# ---- cross-validate group means against results.md Table 1 ----
EXPECT = {  # from research/results.md (script-computed there, freeze #2 2026-07-15)
    "sonnet-5": {"ISOLATED": 0.54, "PERSISTENT": 0.70, "COMPOUND": 0.33},
    "gpt-5.4": {"ISOLATED": 0.21, "PERSISTENT": 0.55, "COMPOUND": 0.86},
    "deepseek-v4-pro": {"ISOLATED": -0.62, "PERSISTENT": -0.68, "COMPOUND": 0.24},
    "grok-4.5": {"ISOLATED": -0.14, "PERSISTENT": -0.24, "COMPOUND": -0.06},
}
for m in MODELS:
    for g, seeds in GROUPS.items():
        vals = [skill[m][s] for s in seeds if s in skill[m]]
        mean = sum(vals) / len(vals)
        assert abs(mean - EXPECT[m][g]) < 0.006, f"{m}/{g}: {mean:.3f} != {EXPECT[m][g]}"
print("cross-validation vs results.md: OK")

# ---- detection rate from belief_metrics.csv (all four models, full 50) ----
missed, episodes = {m: 0 for m in MODELS}, {m: 0 for m in MODELS}
with open(ROOT / "belief_metrics.csv") as f:
    for row in csv.DictReader(f):
        m = KEY2M.get(row["model"])
        if m is None:
            continue
        missed[m] += int(row["n_never_detected"])
        episodes[m] += int(row["n_episodes"])
for m in MODELS:
    # D2b fix 2026-07-30: 266 detectable episodes (283 minus 17 final-week
    # onsets, undetectable by construction, excluded at the grader)
    assert episodes[m] == 266, f"{m}: {episodes[m]} episodes"
det = {m: (episodes[m] - missed[m]) / episodes[m] for m in MODELS}
print("detection:", {m: round(det[m], 3) for m in MODELS})

# ---- plot ----
C = {"sonnet-5": "#C86214", "gpt-5.4": "#2F6DA3",
     "deepseek-v4-pro": "#4B5563", "grok-4.5": "#2A7F62"}
NAME = {"sonnet-5": "Claude Sonnet 5", "gpt-5.4": "GPT-5.4",
        "deepseek-v4-pro": "DeepSeek-V4-Pro", "grok-4.5": "Grok 4.5"}
plt.rcParams.update({"font.family": "sans-serif", "font.size": 7,
                     "axes.edgecolor": "#787880", "axes.linewidth": 0.7})
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(5.5, 1.95),
                               gridspec_kw={"width_ratios": [0.8, 1.6], "wspace": 0.32})

# panel (a): detection rate (uniform)
xs = range(len(MODELS))
ax1.bar(xs, [det[m] * 100 for m in MODELS], width=0.6,
        color=[C[m] for m in MODELS], edgecolor="none")
for x, m in zip(xs, MODELS):
    ax1.text(x, det[m] * 100 + 2, f"{det[m]*100:.0f}%", ha="center", fontsize=6.5, color="#333")
ax1.set_xticks(list(xs)); ax1.set_xticklabels(["Sonnet", "GPT", "DS", "Grok"], fontsize=6.5)
ax1.set_ylim(0, 112); ax1.set_ylabel("stress episodes detected (%)", fontsize=6.5)
ax1.set_title("(a) Detection", fontsize=7.5, loc="left")
ax1.spines[["top", "right"]].set_visible(False)

# panel (b): slopegraph of group means, faint per-seed dots behind
order = ["ISOLATED", "PERSISTENT", "COMPOUND"]
JIT = {"sonnet-5": -0.15, "gpt-5.4": -0.05, "deepseek-v4-pro": 0.05, "grok-4.5": 0.15}
ax2.axhspan(0, 1, color="#000000", alpha=0.045, zorder=0)
ax2.axhline(0, color="#888", lw=0.7, ls=(0, (4, 3)))
ax2.axhline(1, color="#7A5FA8", lw=0.7, ls=(0, (4, 3)))
LABY = {"gpt-5.4": 1.60, "sonnet-5": 0.80, "deepseek-v4-pro": 0.15, "grok-4.5": -0.55}
for m in MODELS:
    means = []
    for gi, g in enumerate(order):
        ys = [skill[m][s] for s in GROUPS[g] if s in skill[m]]
        ax2.scatter([gi + JIT[m]] * len(ys), ys, s=8, color=C[m], alpha=0.30,
                    edgecolors="none", zorder=2)
        means.append(sum(ys) / len(ys))
    ax2.plot(range(3), means, color=C[m], lw=1.8, zorder=4,
             marker="o", ms=4.5, mec="white", mew=0.6)
    ly = LABY[m]
    ax2.plot([2.06, 2.27], [means[-1], ly], color=C[m], lw=0.6, alpha=0.6, zorder=3)
    ax2.text(2.31, ly, NAME[m], fontsize=6.5, color=C[m], va="center")
ax2.text(-0.35, 1.0, "oracle = 1", fontsize=5.5, color="#7A5FA8", va="bottom", ha="left")
ax2.text(-0.35, 0.0, "floor = 0", fontsize=5.5, color="#777", va="top", ha="left")
ax2.set_xticks(range(3))
ax2.set_xticklabels(["Isolated", "Persistent", "Compound"], fontsize=6.5)
ax2.set_xlim(-0.40, 3.35); ax2.set_ylim(-3.6, 2.8)
ax2.set_yticks([-3, -2, -1, 0, 1, 2])
ax2.set_ylabel("skill score", fontsize=6.5, labelpad=1)
ax2.set_title("(b) Skill by stress profile", fontsize=7.5, loc="left")
ax2.spines[["top", "right"]].set_visible(False)

fig.savefig(Path(__file__).parent / "fig2.pdf", bbox_inches="tight")
fig.savefig(Path(__file__).parent / "fig2-preview.png", dpi=200, bbox_inches="tight")
print("written fig2.pdf")
