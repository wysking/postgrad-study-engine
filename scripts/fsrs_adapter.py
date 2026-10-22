"""Optional py-fsrs 6.3.2 adapter; explicit ratings, no invented ease grades.

The caller supplies rating observations linked to existing qualified events.
Nothing here writes evidence or replaces the cross-subject scheduler.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from importlib.metadata import version

from scripts.contracts import ContractError, parse_datetime
from scripts.learning_models import digest, observed_by, unassisted_observation
from scripts.reducer import load_units


def fsrs_report(events: list[dict], units, ratings: dict, cutoff: datetime,
                learner_id: str, *, optimize: bool = False) -> dict:
    if (not isinstance(ratings, dict) or set(ratings) != {"schema_version", "learner_id", "ratings"}
            or ratings["schema_version"] != "1.0" or ratings["learner_id"] != learner_id
            or not isinstance(ratings["ratings"], list)):
        raise ContractError("FSRS ratings need a matching versioned learner identity")
    registry, mapping = load_units(units), {}
    for entry in ratings["ratings"]:
        if (not isinstance(entry, dict) or set(entry) != {"event_id", "rating", "source"}
                or not isinstance(entry["event_id"], str) or entry["event_id"] in mapping
                or type(entry["rating"]) is not int or entry["rating"] not in {1, 2, 3, 4}
                or entry["source"] != "observed"):
            raise ContractError("explicit FSRS ratings require unique event_id, observed source and integer rating 1..4")
        mapping[entry["event_id"]] = entry["rating"]
    if set(mapping) - {e["event_id"] for e in events}:
        raise ContractError("rating references an unknown event")
    reviewed = []
    for e in observed_by(events, cutoff):
        if e["event_id"] not in mapping:
            continue
        if e["event_type"] != "attempt" or len(e["unit_ids"]) != 1:
            raise ContractError("FSRS rating must reference one atomic recall attempt")
        spec = registry.get(e["unit_ids"][0], {})
        targets = set(spec.get("evidence_targets", []))
        if (e["activity"] not in {"recall", "review"} or not unassisted_observation(e)
                or "recall" not in targets or targets & {"independent", "transfer", "timed"}
                or spec.get("subject") != e["subject"]):
            raise ContractError("FSRS rating references an unqualified or non-recall observation")
        if (mapping[e["event_id"]] == 1) != (e["attempt"]["result"] == "incorrect"):
            raise ContractError("FSRS rating conflicts with the observed recall result")
        reviewed.append(e)
    # Require every intervening assessed exposure on each rated unit to have an
    # explicit rating too; omitted exposure cannot silently become a long gap.
    rated_units = {e["unit_ids"][0] for e in reviewed}
    for e in observed_by(events, cutoff):
        if e["event_type"] == "attempt" and rated_units.intersection(e["unit_ids"]) and e["event_id"] not in mapping:
            raise ContractError("incomplete FSRS history for a rated unit; missing exposure/rating")
    try:
        from fsrs import Card, Rating, Scheduler
    except ImportError:
        raise ContractError("optional FSRS adapter requires fsrs==6.3.2; the standard-library baseline remains available") from None
    if version("fsrs") != "6.3.2":
        raise ContractError("this adapter is validated against fsrs==6.3.2; review other versions before use")

    def replay(scheduler):
        cards, logs, predictions = {}, [], []
        for e in reviewed:
            uid = e["unit_ids"][0]
            at = parse_datetime(e["timestamp"]).astimezone(timezone.utc)
            if uid not in cards:
                cards[uid] = Card(card_id=int(hashlib.sha256(uid.encode()).hexdigest()[:15], 16), due=at)
            card = cards[uid]
            if card.last_review is not None and (at - card.last_review).total_seconds() >= 86400:
                predictions.append({"event_id": e["event_id"], "unit_id": uid,
                                    "predicted_recall": scheduler.get_card_retrievability(card, current_datetime=at),
                                    "recalled": int(mapping[e["event_id"]] != 1)})
            cards[uid], log = scheduler.review_card(card, Rating(mapping[e["event_id"]]), review_datetime=at)
            logs.append(log)
        return cards, logs, predictions

    scheduler = Scheduler(enable_fuzzing=False)
    cards, logs, predictions = replay(scheduler)
    if optimize and logs:
        try:
            from fsrs import Optimizer
            parameters = Optimizer(logs).compute_optimal_parameters()
            scheduler = Scheduler(parameters=parameters, enable_fuzzing=False)
            cards, logs, predictions = replay(scheduler)
        except ImportError:
            raise ContractError("FSRS fitting requires the optional fsrs[optimizer]==6.3.2 dependencies") from None
    model_input = {"events": reviewed, "ratings": {e["event_id"]: mapping[e["event_id"]] for e in reviewed}}
    return {"schema_version": "1.0", "learner_id": learner_id, "adapter_version": "py-fsrs-6.3.2-adapter-0.1",
            "training_cutoff": cutoff.isoformat(), "source_hash": digest(model_input),
            "status": "fitted_uncalibrated" if optimize and logs else "library_default_parameters",
            "score_scope": "in_sample_not_validation" if optimize else "prequential_fixed_parameters",
            "parameters": list(scheduler.parameters), "sample_count": len(predictions), "predictions": predictions,
            "brier": sum((p["predicted_recall"] - p["recalled"]) ** 2 for p in predictions) / len(predictions) if predictions else None,
            "cards": {uid: {"predicted_recall": scheduler.get_card_retrievability(c, current_datetime=cutoff.astimezone(timezone.utc)),
                            "suggested_due_at": c.due.isoformat()} for uid, c in sorted(cards.items())},
            "limitations": ["Not automatically applied to the global scheduler.",
                            "Explicit observed ratings are required; correctness is not converted to Good/Easy.",
                            "Fitted training scores are not held-out calibration or evidence of learning effects."]}
