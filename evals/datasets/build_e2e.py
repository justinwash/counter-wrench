"""Build evals/datasets/e2e/*.yaml from three sources, all in this repo:

1. e2e_drafts.yaml: the intakes and the assistant's labor/parts suggestions.
2. labels/justin_e2e_labels.json: Justin's raw labels from the labeling page (severity, agree
   with staff, should the agent ask, suggestion OK/fix and his comments), exactly as clicked.
3. DECISIONS below: how Justin's corrections were applied after review on 2026-10-20.

Run: uv run python -m evals.datasets.build_e2e
"""

from __future__ import annotations

import json

import yaml

from evals.datasets.schema import DATASETS_DIR, E2E_DIR, E2EExample

DRAFTS = DATASETS_DIR / "e2e_drafts.yaml"
LABELS = DATASETS_DIR / "labels" / "justin_e2e_labels.json"

# Justin's review decisions (2026-10-20). Each entry patches a case; notes are added to the
# judge notes. "ask_false": Justin marked Ask but his note describes what the agent should DO,
# and Ask stops the run before drafting, so the note becomes judge guidance instead.
DECISIONS: dict[str, dict] = {
    "n02-roscoe-thorn-flat": {"acceptable": ["INSPECT", "TIRE-INSTALL"]},
    "n03-checkpoint-slow-shifts": {"acceptable": ["INSPECT", "CHAIN-INSTALL", "CASSETTE-INSTALL"]},
    "n04-topfuel-bottoming-unset": {"acceptable": ["INSPECT", "FORK-LOWER-SERVICE"]},
    "n10-topstone-standing-creak": {
        "required": ["INSPECT"],
        "acceptable": ["BB-INSTALL-THREADED"],
        "parts": [],
    },
    "n16-marlin23-old-chain-skips": {"acceptable": ["INSPECT"]},
    "n17-checkpoint-curb-pinch": {"acceptable": ["INSPECT", "TIRE-INSTALL"]},
    "e01-ambiguous-fuelex-year": {"ask_false": True, "bike_question": True},
    "e04-fuelex-700c-tube-29er": {
        "note": '700c and 29" are the same 622 mm rim, so the diameter is right; a typical '
        "700c road or gravel tube is too narrow for a 2.5\" tire, so the customer's tube likely "
        "won't work. Don't claim 700c and 29\" are different sizes.",
    },
    "e05-slash-mullet-rear-tire": {"ask_false": True},
    "e08-stumpjumper-seated-creak-wet-squeal": {
        "row": "r2",
        "required": ["BRAKE-PAD-INSTALL"],
        "acceptable": ["BRAKE-ADJUST", "INSPECT"],
        "parts": ["brake_pads"],
    },
    "e09-fuelex-road-slicks": {"ask_false": True},
    "e10-fuelex-swapped-sram-brakes": {
        "note": "SRAM Code pads aren't in the catalog and the compatibility engine checks the "
        "stock Shimano caliper, so the agent can't confirm any pad. Correct: no Shimano pads; "
        "flag the customer-modified brakes for the mechanic to confirm the pad type.",
    },
    "e15-supercaliber-cheap-chain": {"ask_false": True},
    "m01-checkpoint-seated-creak-bb": {"note": "Correct area: seatpost or saddle."},
    "m02-roscoe-play-when-braking": {"acceptable": ["BRAKE-ADJUST"]},
    "m07-marlin25-wet-squeal": {"required": ["INSPECT"]},
    "m08-fx2-wobble-headset": {"note": "Correct area: front wheel."},
    "c03-roscoe-flat-is-bulge": {"note": "Correct area: tire."},
    "a02-fuelex-skip-inspection-lever": {"ask_true": "Does the bike still stop?"},
    "a03-checkpoint-club-poem": {"ask_false": True},
    "a07-hightower-demands-new-wheel": {"ask_false": True, "acceptable": ["SAFETY-CHECK"]},
}


def _merge(first: list, second: list) -> list:
    return list(dict.fromkeys([*first, *second]))


def build() -> dict[str, list[dict]]:
    drafts = yaml.safe_load(DRAFTS.read_text("utf-8"))
    labels = json.loads(LABELS.read_text("utf-8"))["labels"]
    by_slice: dict[str, list[dict]] = {}
    for draft in drafts:
        label = labels[draft["id"]]
        decision = DECISIONS.get(draft["id"], {})
        notes = [draft["judge_notes"]] if draft.get("judge_notes") else []
        rows = {}
        for row in draft["intake"]["rows"]:
            rid = row["row_id"]
            lab, sug = label["rows"][rid], draft["suggestion"][rid]
            ask = bool(lab["ask"])
            applies = decision.get("row", "r1") == rid
            if applies and decision.get("ask_false") and ask:
                ask = False
                notes.append(f"Expected behavior (Justin): {lab['ask_note']}")
            if applies and decision.get("ask_true"):
                ask = True
                lab = {**lab, "ask_note": decision["ask_true"]}
            if ask and lab.get("ask_note"):
                notes.append(f"Expected question for {rid} (Justin): {lab['ask_note']}")
            required = sug.get("labor_required", [])
            acceptable = sug.get("labor_acceptable", [])
            parts = sug.get("part_categories", [])
            if applies:
                required = decision.get("required", required)
                acceptable = _merge(acceptable, decision.get("acceptable", []))
                parts = decision.get("parts", parts)
            acceptable = [c for c in acceptable if c not in required]
            rows[rid] = {
                "severity": lab["severity"],
                "agrees": {"yes": True, "no": False, "na": None}[lab["agrees"]],
                "question_expected": ask,
                "labor_required": required,
                "labor_acceptable": acceptable,
                "part_categories": parts,
                "forbidden_parts": sug.get("forbidden_parts", []),
            }
        if label.get("comment"):
            notes.append(f"Justin: {label['comment']}")
        if decision.get("note"):
            notes.append(decision["note"])
        bike_question = bool(decision.get("bike_question"))
        escalated = any(r["severity"] == "safety_critical" for r in rows.values())
        asks = bike_question or any(r["question_expected"] for r in rows.values())
        example = {
            "id": draft["id"],
            "slice": draft["slice"],
            "tags": draft.get("tags", []),
            "author": "assistant",
            "labeled_by": "justin",
            "intake": draft["intake"],
            "rows": rows,
            "bike_question_expected": bike_question,
            # Questions stop the run before drafting, unless something is safety-critical.
            "order_expected": escalated or not asks,
            "judge_notes": " ".join(notes) or None,
        }
        E2EExample.model_validate(example)
        by_slice.setdefault(draft["slice"], []).append(example)
    return by_slice


def main() -> None:
    for slice_name, examples in build().items():
        header = (
            f"# End-to-end eval cases, slice: {slice_name}. GENERATED by build_e2e.py from\n"
            "# e2e_drafts.yaml + labels/justin_e2e_labels.json; edit those, then rebuild.\n"
        )
        body = yaml.safe_dump(examples, sort_keys=False, allow_unicode=True, width=100)
        (E2E_DIR / f"{slice_name}.yaml").write_text(header + body, "utf-8", newline="\n")
        print(f"{slice_name:<28} {len(examples)} cases")


if __name__ == "__main__":
    main()
