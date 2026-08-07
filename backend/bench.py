"""Benchmark pipeline: run -> oracle -> score -> grade -> report.

One CLI for the whole evaluation flow; every step is resumable (skips work
already on disk). Config (seeds/groups/models) lives in bench_config.py.

Run (from backend/):
    uv run python bench.py run                 # fill missing (model, seed) traces, sequential
    uv run python bench.py oracle              # 20-rep oracle refs -> runs/<exp>/oracle_refs.csv
    uv run python bench.py score               # skill scores -> runs/<exp>/skill_scores.csv
    uv run python bench.py grade --dry-run     # pass-through to runs/grade_beliefs.py
    uv run python bench.py report              # runs/<exp>/report.md + manifest.json
    uv run python bench.py all
"""
import argparse
import csv
import json
import re
import statistics as st
import subprocess
import sys
from datetime import date
from pathlib import Path

import bench_config as C

BACKEND = Path(__file__).parent
RUNS = BACKEND / "runs"


# ---------- pure helpers ----------

def trace_path(exp: str, model_dir: str, seed: int) -> Path:
    return RUNS / exp / model_dir / f"seed{seed}-rich.chat.txt"


def trace_valid(path: Path) -> bool:
    """Episode complete: 26 advanced weeks + the DONE marker (same predicate
    the old bash launchers used)."""
    if not path.is_file():
        return False
    text = path.read_text()
    return text.count("WORLD ADVANCED") >= C.N_WEEKS and "EPISODE DONE" in text


def llm_cost(trace_text: str) -> float:
    """Final cumulative cost from the trace's episode-done line (last match wins)."""
    m = re.findall(r"cum \$(\d+)\s+\*\* EPISODE DONE", trace_text)
    if not m:
        raise ValueError("no 'cum $N ** EPISODE DONE' line in trace")
    return float(m[-1])


def score_row(model_dir: str, seed: int, basestock: float, oracle_mean: float,
              oracle_se: float, cost: float) -> dict:
    gap = basestock - oracle_mean
    return {"model": model_dir, "seed": seed, "group": C.group_of(seed),
            "basestock": round(basestock, 1), "oracle_mean": oracle_mean,
            "oracle_se": oracle_se, "llm_cost": cost, "headroom": round(gap, 1),
            # no headroom -> unscoreable (e.g. seed 11): empty cell, excluded from means
            "skill": round((basestock - cost) / gap, 3) if gap > 0 else ""}


def read_oracle_refs(path: Path) -> dict[int, dict]:
    """oracle_refs.csv -> {seed: row}; only seeds with n >= ORACLE_REPS count as done."""
    refs = {}
    if path.is_file():
        for row in csv.DictReader(open(path)):
            if int(row["n"]) >= C.ORACLE_REPS:
                refs[int(row["seed"])] = row
    return refs


# ---------- subcommands ----------

def cmd_run(args):
    ran = missing = 0
    for mdir, keep in C.MODELS.items():
        if args.models and mdir not in args.models:
            continue
        model = C.openrouter_name(mdir)
        for s in C.all_seeds():
            if keep is not None and s not in keep:
                continue
            if args.seeds and s not in args.seeds:
                continue
            f = trace_path(args.exp, mdir, s)
            if trace_valid(f):
                print(f"skip {mdir} seed{s} (done)")
                continue
            print(f"=== running {model} seed{s} ===", flush=True)
            # ponytail: strictly sequential -- parallel LLM calls hit rate limits
            subprocess.run([sys.executable, "-m", "src.agent.play_agent",
                            "--seed", str(s), "--model", model, "--rich",
                            "--exp", args.exp], cwd=BACKEND, check=False)
            ran += 1
            if not trace_valid(f):
                print(f"!!! INCOMPLETE: {mdir} seed{s} (rerun `bench.py run` to retry)")
                missing += 1
                continue
            # post-episode audit gate (D16 lesson): a trace only counts if the
            # engine replay keeps every documented promise the agent used.
            from analysis.audit_trace import audit as audit_trace
            fails = audit_trace(f, s)
            if fails:
                bad = f.with_suffix(".chat.txt.AUDIT-FAIL")
                f.rename(bad)
                print(f"!!! AUDIT FAIL {mdir} seed{s}: {fails[:3]}... "
                      f"(trace moved to {bad.name}; fix cause, rerun)")
                missing += 1
    print(f"\nrun done: {ran} launched, {missing} incomplete")


def cmd_status(args):
    """Real-time run status: per-model complete/incomplete counts for the exp,
    plus the week the most recently active episode has reached (from the
    newest recorder .log). No more waiting 30 minutes for buffered output."""
    import json as _json
    import time as _time
    for mdir in C.MODELS:
        done = sum(trace_valid(trace_path(args.exp, mdir, s)) for s in C.all_seeds())
        if done or (RUNS / args.exp / mdir).is_dir():
            print(f"{mdir}: {done}/{len(C.all_seeds())} episodes complete")
    logs = sorted(RUNS.glob("*.log"), key=lambda p: p.stat().st_mtime)
    if logs:
        newest = logs[-1]
        weeks = [_json.loads(l)["week"] for l in newest.open()
                 if '"place_order"' in l]
        age = int(_time.time() - newest.stat().st_mtime)
        print(f"active episode: week {max(weeks) if weeks else 0}/26 "
              f"(last event {age}s ago, {newest.name})")


def cmd_oracle(args):
    from oracle_policy import run_oracle  # deferred: imports the world engine
    out = Path(args.out) if args.out else RUNS / args.exp / "oracle_refs.csv"
    done = read_oracle_refs(out)
    todo = [s for s in (args.seeds or C.all_seeds()) if s not in done]
    if not todo:
        print(f"all {len(done)} seeds already in {out}")
        return
    if not args.seeds and len(todo) > 5 and not args.yes:
        sys.exit(f"refusing to compute {len(todo)} seeds (CPU-minutes each) without "
                 f"--seeds or --yes: {todo}")
    new_file = not out.is_file()
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "a", newline="") as f:
        if new_file:
            f.write("seed,mean,se,n,min,max\n")
        for s in todo:
            # NOTE: run_oracle is deterministic per (seed, k) -- refs are
            # byte-reproducible as long as oracle_policy.py avoids hash-order iteration.
            xs = [run_oracle(s, k=k) for k in range(C.ORACLE_K_BASE, C.ORACLE_K_BASE + C.ORACLE_REPS)]
            se = st.stdev(xs) / len(xs) ** 0.5
            f.write(f"{s},{st.mean(xs):.1f},{se:.1f},{len(xs)},{min(xs):.1f},{max(xs):.1f}\n")
            f.flush()
            print(f"seed {s}: mean={st.mean(xs):.1f} se={se:.1f}", flush=True)


def cmd_score(args):
    refs = read_oracle_refs(RUNS / args.exp / "oracle_refs.csv")
    basestock = {int(r["seed"]): float(r["cost_basestock"])
                 for r in csv.DictReader(open(BACKEND / "sweep/results.csv"))}
    rows = []
    for mdir, keep in C.MODELS.items():
        for s in C.all_seeds():
            if keep is not None and s not in keep:
                continue
            if not trace_path(args.exp, mdir, s).exists():
                continue  # model not (fully) run yet, e.g. gemini smoke-test only
            ref = refs[s]
            rows.append(score_row(mdir, s, basestock[s], float(ref["mean"]),
                                  float(ref["se"]),
                                  llm_cost(trace_path(args.exp, mdir, s).read_text())))
    out = RUNS / args.exp / "skill_scores.csv"
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=rows[0].keys())
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {out} ({len(rows)} rows)")
    print("thin headroom (<%d):" % C.THIN_HEADROOM,
          sorted({(r["seed"], r["headroom"]) for r in rows if r["headroom"] < C.THIN_HEADROOM}) or "none")
    for line in summary_lines(rows):
        print(line)


def summary_lines(rows: list[dict]) -> list[str]:
    lines = []
    for mdir in C.MODELS:
        mr = [r for r in rows if r["model"] == mdir]
        if not mr:
            continue
        lines.append(f"\n{mdir} (n={len(mr)})")
        for g in list(C.GROUPS) + ["ALL"]:
            gr = [r["skill"] for r in mr if (g == "ALL" or r["group"] == g) and r["skill"] != ""]
            if not gr:
                continue
            neg = sum(1 for x in gr if x < 0)
            lines.append(f"  {g:<10} n={len(gr):<3} mean={st.mean(gr):+.2f} "
                         f"med={st.median(gr):+.2f} neg={neg}")
    return lines


def cmd_grade(args):
    sys.exit(subprocess.run([sys.executable, "runs/grade_beliefs.py", *args.rest],
                            cwd=BACKEND).returncode)


def cmd_report(args):
    exp_dir = RUNS / args.exp
    rows = list(csv.DictReader(open(exp_dir / "skill_scores.csv")))
    for r in rows:  # csv strings -> the types summary_lines/score math expect
        r["seed"] = int(r["seed"])
        r["headroom"] = float(r["headroom"])
        r["skill"] = float(r["skill"]) if r["skill"] else ""

    lines = [f"# {args.exp} report", "",
             f"Generated by `bench.py report` on {date.today()} -- do not hand-edit; "
             "numbers come from skill_scores.csv + belief_metrics.csv.", "",
             "## Skill scores", "",
             "skill = (basestock - llm) / (basestock - oracle_mean); "
             "headroom <= 0 -> unscoreable, excluded from means.", "",
             "| model | group | n | mean | median | neg |", "|---|---|---|---|---|---|"]
    for mdir in C.MODELS:
        mr = [r for r in rows if r["model"] == mdir]
        for g in list(C.GROUPS) + ["ALL"]:
            gr = [r["skill"] for r in mr if (g == "ALL" or r["group"] == g) and r["skill"] != ""]
            if gr:
                lines.append(f"| {mdir} | {g} | {len(gr)} | {st.mean(gr):+.2f} | "
                             f"{st.median(gr):+.2f} | {sum(1 for x in gr if x < 0)} |")
    excluded = sorted({r["seed"] for r in rows if r["skill"] == ""})
    thin = sorted({r["seed"] for r in rows if 0 < r["headroom"] < C.THIN_HEADROOM})
    lines += ["", f"Excluded (headroom <= 0): {excluded or 'none'}",
              f"Thin headroom (< {C.THIN_HEADROOM}): {thin or 'none'}"]

    bm_path = exp_dir / "belief_metrics.csv"
    if bm_path.is_file():
        bm = list(csv.DictReader(open(bm_path)))
        lines += ["", "## Belief metrics (grader)", "",
                  "| model | seeds | mean detection lag | stress episodes | never detected | KD rate |",
                  "|---|---|---|---|---|---|"]
        for mdir, subset in C.MODELS.items():
            # same seed subset as the skill table (deepseek = core-20 only)
            mr = [r for r in bm if r["model"] == mdir
                  and (subset is None or int(r["seed"]) in subset)]
            if not mr:
                continue
            lags = [float(r["mean_detection_lag"]) for r in mr if r["mean_detection_lag"] != ""]
            kd = [float(r["knowing_doing_rate"]) for r in mr if r["knowing_doing_rate"] != ""]
            lines.append(f"| {mdir} | {len(mr)} | {st.mean(lags):.2f} | "
                         f"{sum(int(r['n_episodes']) for r in mr)} | "
                         f"{sum(int(r['n_never_detected']) for r in mr)} | "
                         f"{st.mean(kd):.2f} |")

    (exp_dir / "report.md").write_text("\n".join(lines) + "\n")
    print(f"wrote {exp_dir / 'report.md'}")

    git = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=BACKEND,
                         capture_output=True, text=True).stdout.strip()
    manifest = {
        "experiment": args.exp,
        "generated": str(date.today()),
        "code": f"commit {git or 'unknown'}",
        "world": "RICH 6-factor, single product, masked (sup_mask_otif=true)",
        "prompt_arm": "faithful (rules only, no playbook)",
        # ladder-v1 ran July 2026 on the deepagents scaffold (injected
        # write_todos/file/execute/task tools + appended SDK prompt --
        # DEFECTS.md D15); deepagents was removed 2026-08-06, so every
        # later experiment runs the clean harness.
        "harness": ("deepagents 0.6.10 scaffold (see DEFECTS.md D15)"
                    if args.exp == "ladder-v1" else
                    "clean (plain langchain create_agent: world tools only, "
                    "prompt verbatim)"),
        "seeds": C.GROUPS,
        "core20": sorted(C.CORE20),
        "models": {m: ("all" if keep is None else "core20") for m, keep in C.MODELS.items()},
        "references": f"oracle = {C.ORACLE_REPS}-rep mean per seed (oracle_refs.csv); "
                      "basestock from sweep/results.csv",
        "metric": "skill = (basestock - llm) / (basestock - oracle)",
        "pipeline": "bench.py run|oracle|score|grade|report",
    }
    (exp_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"wrote {exp_dir / 'manifest.json'}")


def cmd_all(args):
    for fn in (cmd_run, cmd_oracle, cmd_score, cmd_grade, cmd_report):
        fn(args)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--exp", default=C.EXP)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("run", help="fill missing (model, seed) traces, sequential")
    p.add_argument("--models", nargs="*", help="model dir slugs (default: all in config)")
    p.add_argument("--seeds", nargs="*", type=int)
    p.set_defaults(fn=cmd_run)

    p = sub.add_parser("oracle", help="20-rep oracle refs (resumable, deterministic)")
    p.add_argument("--seeds", nargs="*", type=int)
    p.add_argument("--out", help="override output csv path")
    p.add_argument("--yes", action="store_true", help="allow computing many seeds")
    p.set_defaults(fn=cmd_oracle)

    p = sub.add_parser("score", help="skill scores -> skill_scores.csv")
    p.set_defaults(fn=cmd_score)

    p = sub.add_parser("grade", help="pass-through to runs/grade_beliefs.py")
    p.set_defaults(fn=cmd_grade)

    p = sub.add_parser("report", help="report.md + manifest.json")
    p.set_defaults(fn=cmd_report)

    p = sub.add_parser("status", help="live per-model completion + active episode week")
    p.set_defaults(fn=cmd_status)

    p = sub.add_parser("all", help="run -> oracle -> score -> grade -> report")
    p.add_argument("--models", nargs="*")
    p.add_argument("--seeds", nargs="*", type=int)
    p.add_argument("--out", default=None)
    p.add_argument("--yes", action="store_true")
    p.set_defaults(fn=cmd_all, rest=[])

    # parse_known_args so `bench.py grade --dry-run ...` forwards unknown flags
    args, extra = ap.parse_known_args()
    if extra and args.cmd not in ("grade", "all"):
        ap.error(f"unrecognized arguments: {' '.join(extra)}")
    args.rest = extra
    args.fn(args)


if __name__ == "__main__":
    main()
