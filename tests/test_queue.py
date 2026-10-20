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
    assert "in 2/3 repetitions" in item.note() and not item.safety


def test_partial_scores_count_as_failures_and_safety_sorts_first():
    runs = [
        scored("many", "m1", labor_required_present=0.5),
        scored("many", "m2", labor_required_present=0.5),
        scored("safe", "s1", safety_escalated=0.0),
    ]
    items = select_failures(runs)
    assert [i.case for i in items] == ["safe", "many"]
    assert items[0].safety and items[0].note().startswith("SAFETY.")


class FakeClient:
    """Mimics the LangSmith client's rule: feedback on a run can't also name a project."""

    def __init__(self):
        self.feedback, self.queued = [], []

    def list_annotation_queues(self, name):
        return iter([])

    def create_annotation_queue(self, name, description):
        return type("Queue", (), {"id": "q1"})()

    def read_project(self, project_name):
        return type("Project", (), {"id": "p1"})()

    def create_feedback(self, run_id, key, comment, project_id=None, session_id=None):
        if project_id is not None:
            raise ValueError("project_id cannot be provided if run_id or trace_id is provided")
        self.feedback.append((run_id, key, session_id))

    def add_runs_to_annotation_queue(self, queue_id, run_ids):
        self.queued.extend(run_ids)


def test_push_notes_each_case_and_queues_its_worst_run():
    from evals.queue import push

    client = FakeClient()
    items = select_failures([scored("a", "a1", severity_correct=0.0)])
    assert push(client, items, "exp-1") == "q1"
    assert client.feedback == [("a1", "queue_note", "p1")] and client.queued == ["a1"]
