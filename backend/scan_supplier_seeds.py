"""Find seeds that exercise the masked-distress supplier task.

The spot supplier's reliability arc is exogenous (a function of the seed alone),
so a hold policy reveals it. For each seed we read, per week: the TRUE rel_state,
the DISPLAYED (lagging) scorecard band, and the noisy lead-slip sensor -- then
classify the arc and rank the seeds that make the task discriminating.

What makes a good test seed:
  REAL COLLAPSE  -- spot reaches `defunct`, ideally after a long "masking gap"
                    (weeks the scorecard still reads ontime while spot is already
                    wobbling/degrading). Big gap => reading the books early pays.
  FALSE ALARM    -- a clear scare (wobbling/degraded) that RECOVERS, never dies.
                    Punishes over-reaction; the calibration trap.

  uv run python scan_supplier_seeds.py            # seeds 1..80
  uv run python scan_supplier_seeds.py --n 150
"""

import argparse

from src.world import World, WorldConfig

DISTRESS = ("wobbling", "degraded")


def arc(seed: int, cfg: WorldConfig) -> dict:
    """Drive a hold policy and read the spot supplier's arc off the trace."""
    w = World(cfg)
    w.reset(seed)
    while not w.done:
        w.step({"qty": 0})
    states, bands, slips = [], [], []
    for rec in w.trace:
        st = rec["hidden_states"]["supplier"]["spot"]["rel_state"]
        row = next((r for r in rec["obs"]["suppliers"] if r["id"] == "spot"), {})
        states.append(st)
        bands.append(row.get("band"))
        slips.append(row.get("realized_lead_slip", 0.0))

    collapse_wk = next((i for i, s in enumerate(states) if s == "defunct"), None)
    pre = states[:collapse_wk] if collapse_wk is not None else states
    # masking gap: weeks the supplier is truly distressed but the card reads ontime
    gap = sum(1 for s, b in zip(states, bands)
              if s in DISTRESS and b == "ontime")
    onset = next((i for i, s in enumerate(states) if s != "reliable"), None)
    ever_degraded = "degraded" in pre
    ever_wobbling = "wobbling" in states
    # distinct scares = reliable -> distress onsets
    scares = sum(1 for a, b in zip(states, states[1:])
                 if a == "reliable" and b in DISTRESS)
    return {
        "seed": seed, "states": states, "bands": bands, "slips": slips,
        "collapse_wk": collapse_wk, "gap": gap, "onset": onset,
        "scares": scares, "ever_degraded": ever_degraded,
        "ever_wobbling": ever_wobbling,
        "max_slip": round(max(slips), 1),
    }


def timeline(a: dict) -> str:
    """Compact per-week glyphs: TRUE state over DISPLAYED band, '*' where the
    card masks real distress (the weeks the agent is fooled)."""
    ST = {"reliable": ".", "wobbling": "w", "degraded": "D", "defunct": "X"}
    BD = {"ontime": ".", "slipping": "s", "failing": "f", "defunct": "X", None: "-"}
    top = "".join(ST.get(s, "?") for s in a["states"])
    bot = "".join("*" if s in DISTRESS and b == "ontime" else BD.get(b, "?")
                  for s, b in zip(a["states"], a["bands"]))
    return f"true {top}\n         card {bot}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=80, help="scan seeds 1..n")
    args = ap.parse_args()
    cfg = WorldConfig(sup_mask_otif=True)
    arcs = [arc(s, cfg) for s in range(1, args.n + 1)]

    # REAL COLLAPSE: dies, with warning room (collapse 10..24) and a real gap.
    collapse = sorted(
        (a for a in arcs if a["collapse_wk"] is not None
         and 10 <= a["collapse_wk"] <= 24 and a["gap"] >= 2),
        key=lambda a: (-a["gap"], a["collapse_wk"]))
    # FALSE ALARM: a real scare that recovers (never dies), masked for >=2 wks.
    false_alarm = sorted(
        (a for a in arcs if a["collapse_wk"] is None
         and a["ever_degraded"] and a["gap"] >= 2),
        key=lambda a: (-a["gap"], -a["max_slip"]))
    # MILD SCARE: wobble-only, recovers -- the cheapest false alarm.
    mild = sorted(
        (a for a in arcs if a["collapse_wk"] is None
         and not a["ever_degraded"] and a["ever_wobbling"] and a["scares"] >= 1),
        key=lambda a: (-a["gap"], -a["scares"]))

    def show(title, rows, k=6):
        print(f"\n=== {title} ({len(rows)} found) ===")
        for a in rows[:k]:
            cw = a["collapse_wk"] if a["collapse_wk"] is not None else "-"
            print(f"seed {a['seed']:>3}  onset wk{a['onset']}  collapse wk{cw}  "
                  f"masked_gap {a['gap']}wk  scares {a['scares']}  "
                  f"max_slip {a['max_slip']}")
            print("         " + timeline(a))

    print(f"masked-distress seed scan, seeds 1..{args.n}  "
          f"(lead_slip_sd={cfg.sup_lead_slip_sd}, audit_cost={cfg.audit_cost})")
    print("glyph: true .=reliable w=wobbling D=degraded X=defunct | "
          "card .=ontime s=slipping f=failing *=MASKED(distress shown ontime)")
    show("REAL COLLAPSE  (catch it early via the books)", collapse)
    show("FALSE ALARM    (degraded but recovers -- don't over-react)", false_alarm)
    show("MILD SCARE     (wobble recovers -- the cheap false alarm)", mild)


if __name__ == "__main__":
    main()
