"""Sync the YAML datasets to LangSmith: `make upload-datasets`.

Example ids in LangSmith are derived from the YAML ids (uuid5), so re-uploading updates
examples instead of duplicating them, and removed examples are deleted. Only examples labeled
by Justin are uploaded. Each upload is tagged with the git commit, so an experiment can name
the exact dataset version it ran against.
"""

from __future__ import annotations

import sys
import uuid
from datetime import UTC, datetime

from counterwrench.config import load_config
from counterwrench.tracing import git_version
from evals.datasets.schema import load_e2e, load_retrieval

E2E_DATASET = "counterwrench-e2e"
RETRIEVAL_DATASET = "counterwrench-retrieval"
_NAMESPACE = uuid.UUID("8f2d6c1e-5b0a-4c7e-9a3d-2e6f1b4c8a90")


def example_uuid(dataset: str, example_id: str) -> uuid.UUID:
    return uuid.uuid5(_NAMESPACE, f"{dataset}/{example_id}")


def e2e_record(ex) -> dict:
    return {
        "inputs": {"intake": ex.intake.model_dump(mode="json", exclude_none=True)},
        "outputs": {
            "rows": {k: v.model_dump(mode="json") for k, v in ex.rows.items()},
            "escalation_required": ex.escalation_required,
            "bike_question_expected": ex.bike_question_expected,
            "order_expected": ex.order_expected,
            "judge_notes": ex.judge_notes,
        },
        "metadata": {"slice": ex.slice, "tags": ex.tags, "author": ex.author},
    }


def retrieval_record(ex) -> dict:
    return {
        "inputs": {"query": ex.query, "bike_id": ex.bike_id},
        "outputs": {"expected_chunks": ex.expected_chunks},
        "metadata": {"author": ex.author, "notes": ex.notes},
    }


def sync_dataset(client, name: str, description: str, records: dict[str, dict]) -> dict:
    if client.has_dataset(dataset_name=name):
        dataset = client.read_dataset(dataset_name=name)
    else:
        dataset = client.create_dataset(name, description=description)
    wanted = {example_uuid(name, key): record for key, record in records.items()}
    existing = {ex.id: ex for ex in client.list_examples(dataset_id=dataset.id)}
    new = [{"id": i, **r} for i, r in wanted.items() if i not in existing]
    if new:
        client.create_examples(dataset_id=dataset.id, examples=new)
    updated = 0
    for i, r in wanted.items():
        ex = existing.get(i)
        if ex and (ex.inputs, ex.outputs, ex.metadata or {}) != (
            r["inputs"],
            r["outputs"],
            {**(ex.metadata or {}), **r["metadata"]},
        ):
            client.update_example(i, inputs=r["inputs"], outputs=r["outputs"],
                                  metadata=r["metadata"])  # fmt: skip
            updated += 1
    removed = [i for i in existing if i not in wanted]
    for i in removed:
        client.delete_example(i)
    git = git_version()
    tag = f"git-{git['git_commit']}" + ("-dirty" if git["git_dirty"] else "")
    client.update_dataset_tag(dataset_id=dataset.id, as_of=datetime.now(UTC), tag=tag)
    return {"dataset": dataset, "added": len(new), "updated": updated,
            "removed": len(removed), "tag": tag}  # fmt: skip


def main() -> int:
    load_config()  # loads .env and configures LangSmith
    from langsmith import Client

    e2e = load_e2e()
    retrieval = load_retrieval()
    labeled_e2e = {ex.id: e2e_record(ex) for ex in e2e if ex.labeled_by == "justin"}
    labeled_ret = {ex.id: retrieval_record(ex) for ex in retrieval if ex.labeled_by == "justin"}
    skipped = (len(e2e) - len(labeled_e2e)) + (len(retrieval) - len(labeled_ret))

    client = Client()
    for name, desc, records in [
        (E2E_DATASET, "CounterWrench end-to-end intakes with expected outcomes.", labeled_e2e),
        (RETRIEVAL_DATASET, "Queries with the knowledge chunks that should answer them.",
         labeled_ret),
    ]:  # fmt: skip
        result = sync_dataset(client, name, desc, records)
        print(
            f"{name:<24} {len(records)} examples: {result['added']} added, {result['updated']} "
            f"updated, {result['removed']} removed; tagged {result['tag']}"
        )
        print(f"{'':24} {result['dataset'].url}")
    if skipped:
        print(f"Skipped {skipped} unlabeled example(s): set labeled_by: justin once reviewed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
