"""The port module's data table: visible BAND -> the MEAN berth-wait days.
berth_wait is a NOISY draw around this. Scalar knobs (transition probs, noise sd,
demurrage rate) live on the global WorldConfig.

Band collapse (mirrors disruption "crash"): congested & customs_hold ONSET share
`slow`; next week they separate (congestion persists vs the hold clears)."""

PORT_WAIT = {
    "clear":     1,   # normal berthing
    "building":  4,   # queue forming
    "slow":     14,   # congested & customs_hold ONSET — shared (the ambiguity)
    "congested": 16,  # sustained anchorage backlog
}
