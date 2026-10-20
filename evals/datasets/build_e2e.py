"""Build evals/datasets/e2e/*.yaml from three sources, all in this repo:

1. e2e_drafts.yaml: the intakes and the assistant's labor/parts suggestions.
2. labels/justin_e2e_labels.json: Justin's raw labels from the labeling page (severity, agree
   with staff, should the agent ask, suggestion OK/fix and his comments), exactly as clicked.
3. DECISIONS below: how Justin's corrections were applied after review on 2026-10-20.
4. REVIEW below: his step-16 verdicts on the baseline's failures (raw answers in
   labels/justin_failure_review.json), applied last.

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
    "m04-fuelex-new-chain-skips": {
        "agrees": False,  # labeled "drivetrain"; on review (step 15 pilot) the area is cassette
        "note": "Correct area: cassette (most likely worn along with the old chain). A wrong chain "
        "installed last week (e.g. wrong speed) is a reasonable second cause.",
    },
    "m07-marlin25-wet-squeal": {"required": ["INSPECT"]},
    "m08-fx2-wobble-headset": {"note": "Correct area: front wheel."},
    "c03-roscoe-flat-is-bulge": {"note": "Correct area: tire."},
    "a02-fuelex-skip-inspection-lever": {"ask_true": "Does the bike still stop?"},
    "a03-checkpoint-club-poem": {"ask_false": True},
    "a07-hightower-demands-new-wheel": {"ask_false": True, "acceptable": ["SAFETY-CHECK"]},
}


# Step 16 failure review (2026-10-20). Keys are row ids (fields replaced) or "case". IDs in the
# comments refer to the review page's findings.
REVIEW: dict[str, dict] = {
    # D1: the shop docs win; these are safety-critical.
    "s03-slash-oil-on-rotor": {"r1": {"severity": "safety_critical"}},
    "s08-marlin23-grinding-sparks": {"r1": {"severity": "safety_critical"}},
    "c02-stumpjumper-squeak-is-brakes": {"r1": {"severity": "safety_critical"}},
    # D2: the problem is outside the area staff picked.
    "c04-checkpoint-creak-is-wheel": {"r1": {"agrees": False}},
    "a06-trance-role-tag": {"r1": {"agrees": False}},
    "n12-73fx-rusty-cables": {"r1": {"agrees": False}},
    # D2: needs inspecting before anyone can say, so agreement isn't scored.
    "e14-slash-knock-under-braking": {"r1": {"agreement_scored": False}},
    "c05-fuelex-soft-lever-no-stop": {"r1": {"agreement_scored": False}},
    # D3: squeal only in the wet is normal; an inspection to reassure the customer is fine.
    # m07 is also D2 (not the rotor).
    "m07-marlin25-wet-squeal": {
        "r1": {
            "severity": "no_action_needed",
            "agrees": False,
            "labor_required": [],
            "labor_acceptable": ["INSPECT"],
        }
    },
    "e08-stumpjumper-seated-creak-wet-squeal": {
        "r1": {"severity": "needs_service"},  # D6: the agent's call was right
        "r2": {
            "severity": "no_action_needed",
            "labor_required": [],
            "labor_acceptable": ["INSPECT"],
            "part_categories": [],
        },
    },
    # D7: the answer wouldn't change the order, so don't ask.
    "n08-stumpjumper-dropper-sinks": {"r1": {"question_expected": False}},
    "n05-marlin25-chain-drops": {"r1": {"question_expected": False}},
    # X1: buying a part isn't a work order; the agent can advise what to buy.
    "e16-checkpoint-spare-chain": {
        "case": {
            "order_expected": False,
            "note": "Parts-only purchase (Justin): no work order; offer guidance on what to buy.",
        }
    },
    # F-016 (Justin, after step 17): "we default to safety if we're not sure". Braking that may
    # be compromised, unknown until checked or answered, is safety-critical.
    "a02-fuelex-skip-inspection-lever": {"r1": {"severity": "safety_critical"}},  # still asks
    "e10-fuelex-swapped-sram-brakes": {"r1": {"severity": "safety_critical"}},  # pads worn out
    # Clunk under braking; Justin's note: "could also be the brake caliper coming loose".
    "m02-roscoe-play-when-braking": {
        "r1": {"severity": "safety_critical", "agreement_scored": False}
    },
    # P1: the tire setup decides the tube line, so ask.
    "c03-roscoe-flat-is-bulge": {
        "r1": {"question_expected": True, "labor_acceptable": ["TUBELESS-SETUP"]},
        "case": {
            "note": "Expected question for r1 (Justin): Is the tire tubeless or set up with a "
            "tube? High-end bikes are usually tubeless, entry-level ones use tubes."
        },
    },
}


def _apply_review(case_id: str, rows: dict, notes: list[str]) -> dict:
    """Patch built rows in place; returns case-level overrides."""
    review = REVIEW.get(case_id, {})
    for rid, patch in review.items():
        if rid == "case":
            continue
        rows[rid].update(patch)
        if patch.get("question_expected") is False:  # its expected question no longer applies
            notes[:] = [n for n in notes if not n.startswith(f"Expected question for {rid}")]
    case = review.get("case", {})
    if case.get("note"):
        notes.append(case["note"])
    return case


def _labor_range(row: dict) -> None:
    """D5: INSPECT is acceptable on any row, and SAFETY-CHECK on any safety-critical row."""
    extra = ["INSPECT"] + (["SAFETY-CHECK"] if row["severity"] == "safety_critical" else [])
    taken = set(row["labor_required"]) | set(row["labor_forbidden"])
    row["labor_acceptable"] = _merge(row["labor_acceptable"], [c for c in extra if c not in taken])


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
                "agrees": decision["agrees"]
                if applies and "agrees" in decision
                else {"yes": True, "no": False, "na": None}[lab["agrees"]],
                "question_expected": ask,
                "labor_required": required,
                "labor_acceptable": acceptable,
                "part_categories": parts,
                "forbidden_parts": sug.get("forbidden_parts", []),
                "labor_forbidden": sug.get("labor_forbidden", []),
            }
        if label.get("comment"):
            notes.append(f"Justin: {label['comment']}")
        if decision.get("note"):
            notes.append(decision["note"])
        case = _apply_review(draft["id"], rows, notes)
        for row in rows.values():
            _labor_range(row)
        bike_question = bool(decision.get("bike_question"))
        example = {
            "id": draft["id"],
            "slice": draft["slice"],
            "tags": draft.get("tags", []),
            "author": "assistant",
            "labeled_by": "justin",
            "intake": draft["intake"],
            "rows": rows,
            "bike_question_expected": bike_question,
            # Only an unresolved bike stops the run; row questions go on the draft (step 17).
            "order_expected": case.get("order_expected", not bike_question),
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
