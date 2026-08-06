"""Learned-dynamics oracle: fit every factor's transition table from PASSIVE
observation tapes only (no hidden-state peeking), via Baum-Welch EM with the
sensor model held known.

Scope (v1, "system identification" split):
  - LEARNED: all transition probabilities, on the same state graph the exact
    filters use (known topology: which arcs exist, not their weights).
  - KNOWN: emission likelihoods (the sensor model) and the surrogate cost
    mechanics in oracle_policy.py. States therefore stay identified with
    their regime labels -- no label-switching problem.

Training data: passive replay tapes from seeds TRAIN_BASE..TRAIN_BASE+N-1,
disjoint from every benchmark/calibration seed range. Observations in this
world are action-independent, so passive tapes are the same observation
process the oracle faces at benchmark time (minus the ordering-week
realized_fill channel, which the passive tape never emits).

Run:
    uv run python fit_oracle.py --fit 200                # writes learned_trans.json
    uv run python fit_oracle.py --compare learned_trans.json
Then:
    uv run python oracle_policy.py --seed 7 --params learned_trans.json
"""

import argparse
import json
import math

from filters import FACTORS
from src.world.config import WorldConfig
from src.world.engine import World
from src.world.registry import RICH

TRAIN_BASE = 5000  # ponytail: far above benchmark (ladder) and calib (100+) seeds
EPS = 1e-3         # Laplace smoothing per arc, keeps topology alive


def passive_tape(seed: int, cfg: WorldConfig) -> list:
    w = World(cfg, registry=RICH)
    w.reset(seed)
    while not w.done:
        w.step({})
    return [rec["obs"] for rec in w.trace]


def uniform_init_trans(true_trans: dict) -> dict:
    """Same arcs as the true table, uniform weights -- the 'known topology,
    unknown probabilities' starting point. Single-arc rows are deterministic
    by structure and carry nothing to learn."""
    return {s: [(s2, 1.0 / len(row)) for s2, _ in row]
            for s, row in true_trans.items()}


def forward_backward(states, trans, lik_fn, obs_seq):
    """Scaled forward-backward. Returns (loglik, xi) where xi[(i, j)] is the
    expected number of i->j transitions over this sequence."""
    T = len(obs_seq)
    n = len(states)
    b = [{s: lik_fn(s, o) for s in states} for o in obs_seq]

    # forward (uniform initial belief, matching ForwardFilter's init), with
    # the same predict-then-correct convention the filter uses: the week-0
    # obs corrects the uniform prior pushed through one predict step? No --
    # ForwardFilter.step() does predict() then correct(), and replay feeds it
    # every trace record including week 0. Mirror that exactly: alpha_0 is
    # uniform pushed through one transition, then corrected on obs[0].
    prior = {s: 1.0 / n for s in states}
    alpha, scales = [], []
    cur = prior
    loglik = 0.0
    for t in range(T):
        pred = {s: 0.0 for s in states}
        for s, p in cur.items():
            if p == 0.0:
                continue
            for s2, tp in trans[s]:
                pred[s2] += p * tp
        un = {s: pred[s] * b[t][s] for s in states}
        z = sum(un.values())
        if z <= 0:  # impossible obs under current params (hard-gate factors)
            return float("-inf"), {}
        cur = {s: v / z for s, v in un.items()}
        alpha.append(cur)
        scales.append(z)
        loglik += math.log(z)

    # backward with the same scales
    beta = [None] * T
    beta[T - 1] = {s: 1.0 for s in states}
    for t in range(T - 2, -1, -1):
        row = {s: 0.0 for s in states}
        for s in states:
            acc = 0.0
            for s2, tp in trans[s]:
                acc += tp * b[t + 1][s2] * beta[t + 1][s2]
            row[s] = acc / scales[t + 1]
        beta[t] = row

    # expected transition counts between consecutive corrected steps
    xi = {}
    for t in range(T - 1):
        for s in states:
            a = alpha[t][s]
            if a == 0.0:
                continue
            for s2, tp in trans[s]:
                v = a * tp * b[t + 1][s2] * beta[t + 1][s2] / scales[t + 1]
                if v > 0.0:
                    xi[(s, s2)] = xi.get((s, s2), 0.0) + v
    return loglik, xi


def fit_factor(name: str, cfg: WorldConfig, tapes: list,
               max_iter: int = 100, tol: float = 1e-4):
    build, _ = FACTORS[name]
    true_filt = build(cfg)
    states, lik_fn = true_filt.states, true_filt.likelihood_fn
    trans = uniform_init_trans(true_filt.trans)

    prev_ll = float("-inf")
    for it in range(max_iter):
        total_ll, counts = 0.0, {}
        for tape in tapes:
            ll, xi = forward_backward(states, trans, lik_fn, tape)
            total_ll += ll
            for k, v in xi.items():
                counts[k] = counts.get(k, 0.0) + v
        new = {}
        for s, row in trans.items():
            if len(row) == 1:
                new[s] = [(row[0][0], 1.0)]
                continue
            cs = [(s2, counts.get((s, s2), 0.0) + EPS) for s2, _ in row]
            z = sum(c for _, c in cs)
            new[s] = [(s2, c / z) for s2, c in cs]
        trans = new
        if abs(total_ll - prev_ll) < tol * max(1.0, abs(prev_ll)):
            prev_ll = total_ll
            break
        prev_ll = total_ll
    return trans, prev_ll, it + 1


def fit(n_train: int, out: str):
    cfg = WorldConfig(sup_mask_otif=True)  # same config family as the benchmark
    tapes = [passive_tape(TRAIN_BASE + i, cfg) for i in range(n_train)]
    result = {"meta": {"n_train": n_train, "train_base": TRAIN_BASE, "eps": EPS}}
    for name in FACTORS:
        trans, ll, iters = fit_factor(name, cfg, tapes)
        result[name] = {repr(s): [[repr(s2), p] for s2, p in row]
                        for s, row in trans.items()}
        print(f"{name:>10}: loglik={ll:.1f} after {iters} EM iters")
    with open(out, "w") as f:
        json.dump(result, f, indent=1)
    print(f"wrote {out}")


def load_learned_trans(path: str, cfg: WorldConfig) -> dict:
    """{factor: trans-dict keyed by the REAL state objects} -- for overriding
    a built ForwardFilter's .trans (used by oracle_policy --params)."""
    with open(path) as f:
        data = json.load(f)
    out = {}
    for name in FACTORS:
        build, _ = FACTORS[name]
        filt = build(cfg)
        by_repr = {repr(s): s for s in filt.states}
        out[name] = {by_repr[sk]: [(by_repr[nk], p) for nk, p in row]
                     for sk, row in data[name].items()}
    return out


def compare(path: str):
    cfg = WorldConfig(sup_mask_otif=True)
    learned = load_learned_trans(path, cfg)
    print(f"{'factor':>10} {'arcs':>5} {'mean|err|':>10} {'max|err|':>9}  worst arc")
    for name in FACTORS:
        build, _ = FACTORS[name]
        true_trans = build(cfg).trans
        errs, worst = [], ("", 0.0)
        for s, row in true_trans.items():
            if len(row) == 1:
                continue
            lrow = dict(learned[name][s])
            for s2, tp in row:
                e = abs(lrow[s2] - tp)
                errs.append(e)
                if e > worst[1]:
                    worst = (f"{s}->{s2} true={tp:.3f} learned={lrow[s2]:.3f}", e)
        print(f"{name:>10} {len(errs):>5} {sum(errs)/len(errs):>10.4f} "
              f"{max(errs):>9.4f}  {worst[0]}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fit", type=int, default=None, metavar="N_TRAIN")
    ap.add_argument("--out", default="learned_trans.json")
    ap.add_argument("--compare", default=None, metavar="JSON")
    args = ap.parse_args()
    if args.fit:
        fit(args.fit, args.out)
    if args.compare:
        compare(args.compare)


if __name__ == "__main__":
    main()
