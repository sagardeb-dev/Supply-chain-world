"""The quality module's data tables. Unlike the other factors, the OBSERVABLE
is a noisy DISCRETE sample (an AQL band), not a noisy read of a mean -- so the
belief never collapses to a singleton. Scalar knobs (transition probs, rework
cost) live on the global WorldConfig.

QUALITY_DEFECT -- the true defective FRACTION per regime (drives the cost effect).
QUALITY_BAND_PROBS -- P(accept, marginal, reject) of the incoming-inspection AQL
sample per regime (the noisy observation). A `marginal` is shared by late
in_control (unlucky sample) and early drifting -- the inherent ambiguity, so no
deterministic band-collapse is needed."""

QUALITY_DEFECT = {
    "in_control":     0.001,   # ~Cpk 1.33, ~ accept
    "drifting":       0.02,    # straddles AQL 1.0/2.5
    "out_of_control": 0.06,    # special cause, high defect
}

# P(accept, marginal, reject) -- order matters (cumulative sampling).
QUALITY_BAND_PROBS = {
    "in_control":     (0.90, 0.09, 0.01),
    "drifting":       (0.30, 0.50, 0.20),
    "out_of_control": (0.05, 0.25, 0.70),
}

AQL_BANDS = ("accept", "marginal", "reject")
