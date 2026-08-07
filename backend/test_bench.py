"""Tests for the bench.py pipeline helpers -- no LLM calls, no world sims."""
import bench
import bench_config as C

# snippet copied verbatim from a real trace (pins the play_agent emit format)
REAL_TAIL = ("WORLD ADVANCED -> week 26  week cost $143  cum $5386  ** EPISODE DONE **\n"
             "  SITUATION  ...")


def test_skill_formula():
    r = bench.score_row("m", 157, basestock=1000.0, oracle_mean=800.0, oracle_se=5.0, cost=900.0)
    assert r["headroom"] == 200.0
    assert r["skill"] == 0.5
    assert list(r.keys()) == ["model", "seed", "group", "basestock", "oracle_mean",
                              "oracle_se", "llm_cost", "headroom", "skill"]


def test_skill_zero_headroom_excluded():
    # the "seed-11 rule" (ladder-v1): negative headroom -> unscoreable. Seed 11
    # was swapped out 2026-08-06; the rule itself is seed-agnostic.
    r = bench.score_row("m", 157, basestock=800.0, oracle_mean=900.0, oracle_se=5.0, cost=850.0)
    assert r["skill"] == ""


def test_llm_cost_takes_last_match():
    text = ("... cum $100  ** EPISODE DONE **\n garbage retry \n" + REAL_TAIL)
    assert bench.llm_cost(text) == 5386.0


def test_llm_cost_real_format():
    assert bench.llm_cost(REAL_TAIL) == 5386.0


def test_trace_valid_predicate(tmp_path):
    f = tmp_path / "t.chat.txt"
    assert not bench.trace_valid(f)  # missing file
    f.write_text("WORLD ADVANCED\n" * 26)
    assert not bench.trace_valid(f)  # no DONE marker
    f.write_text("WORLD ADVANCED\n" * 25 + REAL_TAIL)
    assert bench.trace_valid(f)  # 25 + 1 in the tail = 26, plus DONE
    f.write_text("WORLD ADVANCED\n" * 10 + "EPISODE DONE")
    assert not bench.trace_valid(f)  # too few weeks


def test_config_consistency():
    seeds = [s for g in C.GROUPS.values() for s in g]
    assert len(seeds) == len(set(seeds)), "seed duplicated across groups"
    # CORE20 is a ladder-v1 historical constant; the 2026-08-06 swap removed
    # seeds 24/36 from GROUPS, so it is no longer a subset of the live set.
    assert len(C.CORE20) == 20
    assert C.all_seeds() == sorted(seeds)
    assert C.group_of(157) == "ISOLATED"
    assert C.openrouter_name("anthropic-claude-sonnet-5") == "anthropic/claude-sonnet-5"
    assert C.openrouter_name("deepseek-deepseek-v4-pro") == "deepseek/deepseek-v4-pro"


def test_oracle_refs_resume(tmp_path):
    f = tmp_path / "oracle_refs.csv"
    f.write_text("seed,mean,se,n,min,max\n157,3880.0,16.4,20,3679.8,3931.7\n"
                 "25,4825.8,42.7,5,4576.1,5569.5\n")
    refs = bench.read_oracle_refs(f)
    assert 157 in refs          # n=20 -> done
    assert 25 not in refs       # n=5 < ORACLE_REPS -> needs recompute
    assert bench.read_oracle_refs(tmp_path / "absent.csv") == {}
