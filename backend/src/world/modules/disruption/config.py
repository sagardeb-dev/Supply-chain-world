"""The disruption module's data tables. The tunable scalar knobs
(onset_prob, watch_*, *_persist_prob, cape_local_prob) live on the global
WorldConfig dataclass so the oracle reads them unchanged; the lookup tables
that are this module's alone live here."""

# Noiseless weekly transit counts (suez, bab, cape), keyed by visible regime.
# "crash" is shared by false_alarm AND the first week of either disruption
# type — the deliberate ambiguity. One week later the regimes separate.
REGIME_COUNTS = {
    "calm":     (70, 70, 60),
    "watch":    (63, 63, 60),   # caution dip ~10%
    "crash":    (28, 25, 66),   # news breaks: transits crash, small cape uptick
    "blockage": (0, 0, 72),     # short type, age>=1: canal physically shut
    "crisis":   (14, 10, 96),   # long type, age>=1: -75/-90% transits, cape +60%
    "recovery": (56, 56, 69),   # backlog clearing
}
CAPE_LOCAL_EXTRA = 21           # iid local Cape-port congestion, cape channel only
