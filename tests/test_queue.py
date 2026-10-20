"""Review queue selection: one item per failing case, the worst repetition, safety first."""

from evals.queue import ScoredRun, select_failures


def scored(case, run_id, **scores):
    return ScoredRun(example_id=case, case=case, run_id=run_id, scores=scores)


def test_one_item_per_failing_case_with_the_worst_repetition():
    runs = [
        scored("a", "a1", severity_correct=1.0, labor_no_extras=0.0),
        scored("a", "a2", severity_correct=0.0, labor_no_extras=0.0),
        scored("a", "a3", severity_correct=1.0, labor_no_extras=1.0),
        scored("b", "b1", severity_correct=1.0, labor_no_extras=None),  # None isn't a failure
    ]
    [item] = select_failures(runs)
    assert (item.case, item.run_id, item.failed_runs, item.total_runs) == ("a", "a2", 2, 3)
    assert item.failing == ["labor_no_extras", "severity_correct"]
    assert "Failed 2/3" in item.note() and not item.safety


def test_partial_scores_count_as_failures_and_safety_sorts_first():
    runs = [
        scored("many", "m1", labor_required_present=0.5),
        scored("many", "m2", labor_required_present=0.5),
        scored("safe", "s1", safety_escalated=0.0),
    ]
    items = select_failures(runs)
    assert [i.case for i in items] == ["safe", "many"]
    assert items[0].safety and items[0].note().startswith("SAFETY.")
