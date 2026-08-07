"""Single source of truth for the benchmark's seeds, groups, and models.

Replaces the copies that used to be hardcoded across score_all.py,
oracle_refs_30.py, launch_*.sh, and manifest.json (which is now generated
by `bench.py report`). Edit here, nowhere else.
"""

EXP = "ladder-v2"

# Seed tiers by stress profile of the true tape (see runs/TRACKER.md).
# 2026-08-06 seed swap (runs/seed-redesign-2026-08-06/): OUT 11 (unscoreable,
# headroom -218), 24 (onset wk24, 1 stressed wk), 36/160 (thin), 164 (thin);
# IN 415, 345 (ISOLATED), 333, 300 (PERSISTENT), 122 (COMPOUND) -- all with
# 20-rep headroom >= 1238 (candidate_refs.csv). Labels from analysis/
# classify_seeds.py rules. ladder-v1 used the pre-swap set.
GROUPS = {
    "ISOLATED": [157, 25, 112, 60, 86, 91, 178, 189, 345, 415],
    "PERSISTENT": [1, 172, 170, 95, 29, 58, 108, 198, 135, 194, 119, 169, 145, 53, 74, 300, 333],
    "COMPOUND": [21, 143, 99, 44, 94, 154, 85, 72, 82, 90, 9, 148, 168, 163, 0, 14, 187, 100, 33, 12, 75, 39, 122],
}

# The original 20-seed core (pre 50-seed expansion); cheaper models run only these.
CORE20 = {157, 25, 112, 60, 24, 86, 1, 172, 170, 95, 29, 58, 108, 21, 143, 99, 44, 94, 154, 85}

# model directory slug -> seed subset to score (None = all seeds in GROUPS)
MODELS = {
    # SLM row (user-directed 2026-08-06): the "qwen 3.8 27b" ask maps to
    # qwen/qwen3.6-27b -- no 27b exists in the 3.8 line on OpenRouter.
    "qwen-qwen3.6-27b": None,
    # debug tier (2026-08-07): fast SLM for pipeline shakeouts, own exp dirs,
    # NOT a paper row. 4-6 min/episode, AUDIT CLEAN on seed300 smoke.
    "qwen-qwen3.6-35b-a3b": None,
    "anthropic-claude-sonnet-5": None,
    "openai-gpt-5.4": None,
    "deepseek-deepseek-v4-pro": None,
    "x-ai-grok-4.5": None,
    "google-gemini-3.1-pro-preview": None,
}

# dir slugs whose provider prefix itself contains a '-' (first-dash rule breaks)
_OPENROUTER_OVERRIDES = {"x-ai-grok-4.5": "x-ai/grok-4.5"}

N_WEEKS = 26
THIN_HEADROOM = 700   # basestock-oracle gap below this -> skill score flagged noisy
ORACLE_REPS = 20
ORACLE_K_BASE = 191   # oracle ref = mean of run_oracle(seed, k) for k in range(191, 191+ORACLE_REPS)

_GROUP_OF = {s: g for g, seeds in GROUPS.items() for s in seeds}


def group_of(seed: int) -> str:
    return _GROUP_OF[seed]


def all_seeds() -> list[int]:
    return sorted(_GROUP_OF)


def openrouter_name(model_dir: str) -> str:
    """Directory slug back to OpenRouter id: first '-' is the provider '/'."""
    return _OPENROUTER_OVERRIDES.get(model_dir) or model_dir.replace("-", "/", 1)
