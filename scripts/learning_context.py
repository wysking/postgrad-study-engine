"""Read-only context, auditable diagnostic ranking and a local HTML report."""

from __future__ import annotations

import html
import json
from datetime import datetime
from pathlib import Path

from scripts.contracts import ContractError, load_json, load_jsonl, parse_datetime
from scripts.learning_models import fit_models, observed_by
from scripts.reducer import load_units, rebuild_state
from scripts.scheduler import build_schedule


def validate_learner_identity(learner: dict) -> dict:
    if (not isinstance(learner, dict) or set(learner) != {"schema_version", "learner_id", "mode"}
            or learner["schema_version"] != "1.0" or learner["mode"] not in {"personal", "demo"}
            or not isinstance(learner["learner_id"], str) or not learner["learner_id"].strip()):
        raise ContractError("Vault needs a versioned learner.json identity; no identity is inferred")
    return learner


def validate_course(course: dict) -> dict:
    allowed = {"schema_version", "course_id", "title", "fictional", "units", "probes"}
    if (not isinstance(course, dict) or set(course) != allowed or course["schema_version"] != "1.0"
            or not isinstance(course["fictional"], bool)):
        raise ContractError("course requires the documented versioned course-package fields")
    for field in ("course_id", "title"):
        if not isinstance(course[field], str) or not course[field].strip():
            raise ContractError(f"course.{field} must be nonempty")
    if any(c not in "abcdefghijklmnopqrstuvwxyz0123456789-" for c in course["course_id"]):
        raise ContractError("course_id must be lowercase letters, digits or hyphens")
    units = load_units(course["units"])
    if not units or not isinstance(course["probes"], list):
        raise ContractError("course needs units and a probes array")
    visiting, visited = set(), set()

    def visit(uid):
        if uid in visiting:
            raise ContractError("course prerequisites contain a cycle")
        if uid in visited:
            return
        visiting.add(uid)
        for parent in units[uid].get("prerequisites", []):
            if parent not in units:
                raise ContractError("course must include its prerequisite units")
            visit(parent)
        visiting.remove(uid)
        visited.add(uid)

    for uid in units:
        visit(uid)
    probe_ids = set()
    for probe in course["probes"]:
        if not isinstance(probe, dict) or set(probe) != {"probe_id", "unit_id", "prompt", "answer", "distinguishes", "estimated_minutes"}:
            raise ContractError("probe fields do not match course-package contract")
        if probe["unit_id"] not in units or probe["probe_id"] in probe_ids:
            raise ContractError("probe has unknown unit or duplicate ID")
        for field in ("probe_id", "prompt", "answer"):
            if not isinstance(probe[field], str) or not probe[field].strip():
                raise ContractError(f"probe.{field} must be nonempty")
        if (isinstance(probe["estimated_minutes"], bool) or not isinstance(probe["estimated_minutes"], int)
                or probe["estimated_minutes"] < 1):
            raise ContractError("probe duration must be a positive integer estimate")
        if (not isinstance(probe["distinguishes"], list) or len(probe["distinguishes"]) < 2
                or any(not isinstance(x, str) or not x.strip() for x in probe["distinguishes"])):
            raise ContractError("probe must name at least two candidate explanations")
        probe_ids.add(probe["probe_id"])
    return course


def active(spec: dict, config: dict, as_of: datetime) -> bool:
    at = config.get("subject_activation", {}).get(spec["subject"])
    return (spec.get("status", "active") == "active"
            and spec["subject"] in config.get("phase_subjects", [])
            and (at is None or parse_datetime(at) <= as_of))


def select_diagnostics(registry: dict, state: dict, models: dict, courses: list[dict],
                       config: dict, as_of: datetime, minutes: int | None = None) -> dict:
    if minutes is not None and (isinstance(minutes, bool) or not isinstance(minutes, int) or minutes < 1):
        raise ContractError("minutes must be a positive integer")
    probes, course_ids = [], set()
    for course in courses:
        validate_course(course)
        if course["course_id"] in course_ids:
            raise ContractError("duplicate installed course identity")
        course_ids.add(course["course_id"])
        probes.extend({**probe, "course_id": course["course_id"]} for probe in course["probes"])
    candidates, exclusions = {}, []
    # A pending future check cannot become a completed delayed check today.
    immediate = {t["unit_id"] for t in state["review_queue"] if parse_datetime(t["due_at"]) <= as_of
                 and t["task_type"] in {"correction", "diagnostic", "targeted_variant"}}
    deferred = {t["unit_id"] for t in state["review_queue"]
                if parse_datetime(t["due_at"]) > as_of} - immediate
    for target, spec in sorted(registry.items()):
        if not active(spec, config, as_of):
            exclusions.append({"unit_id": target, "reason": "inactive_subject_or_unit"})
            continue
        affected = list(dict.fromkeys([target, *spec.get("prerequisites", [])]))
        for uid in affected:
            if uid not in registry or not active(registry[uid], config, as_of):
                exclusions.append({"unit_id": uid, "target_unit_id": target, "reason": "missing_or_inactive_prerequisite"})
                continue
            if uid in deferred:
                exclusions.append({"unit_id": uid, "reason": "existing_confirmation_not_due"})
                continue
            risk = models["skill_risks"].get(uid, {})
            unit = state["units"].get(uid, {})
            memory_rows = [s for s in models["sample_audit"]["included"] if s["unit_id"] == uid]
            memory_failed = bool(memory_rows and not memory_rows[-1]["recalled"]
                                 and models["memory"].get(uid, {}).get("anchor") is None)
            failures = risk.get("incorrect", 0) + int(memory_failed)
            unknown = unit.get("mastery_overall") is None
            if not failures and not unknown:
                continue
            kind = "observed_failure_needs_check" if failures else "evidence_insufficient_needs_check"
            count = risk.get("sample_count", 0)
            for probe in probes:
                if probe["unit_id"] != uid:
                    continue
                if minutes is not None and probe["estimated_minutes"] > minutes:
                    exclusions.append({"probe_id": probe["probe_id"], "reason": "over_budget"})
                    continue
                components = {"observed_failure": 2.0 if failures else 0.0,
                              "evidence_gap": 1.0 if unknown else 0.0,
                              "exploration": 1.0 / (1 + count),
                              "duration_penalty": -probe["estimated_minutes"] / 60}
                key = probe["course_id"] + ":" + probe["probe_id"]
                item = {"probe_id": key, "unit_id": uid, "subject": registry[uid]["subject"],
                        "course_id": probe["course_id"], "source_probe_id": probe["probe_id"],
                        "target_unit_ids": [target], "status": "hypothesis_not_confirmed",
                        "reason": kind, "prompt": probe["prompt"], "distinguishes": probe["distinguishes"],
                        "estimated_minutes": probe["estimated_minutes"], "score_components": components,
                        "score": sum(components.values()), "source_event_ids": list(risk.get("source_event_ids", []))
                        + ([memory_rows[-1]["event_id"]] if memory_failed else [])}
                if key in candidates:
                    candidates[key]["target_unit_ids"].append(target)
                else:
                    candidates[key] = item
    ranked = sorted(candidates.values(), key=lambda x: (-x["score"], x["probe_id"]))
    selected, remaining = [], minutes
    for candidate in ranked:
        if len(selected) == 2:
            break
        if remaining is None or candidate["estimated_minutes"] <= remaining:
            selected.append(candidate)
            if remaining is not None:
                remaining -= candidate["estimated_minutes"]
    return {"method": "transparent_heuristic_not_expected_information_gain", "candidates": ranked,
            "selected": selected, "excluded": exclusions, "formal_schedule": False}


def context_for_vault(root: Path, as_of: datetime, minutes: int | None = None) -> dict:
    learner = validate_learner_identity(load_json(root / "learner.json"))
    config = load_json(root / "config/personal/scheduler.json")
    units_path = root / "state/knowledge_units.json"
    units = load_json(units_path) if units_path.exists() else {"schema_version": "1.0", "units": []}
    registry = load_units(units)
    events = load_jsonl(root / "events/learning_events.jsonl")
    included = observed_by(events, as_of)
    state = rebuild_state(included, registry)
    # Old Core snapshots omit coverage until a unit receives its first attempt.
    # Fill the empty contextual view without modifying the formal reducer/output.
    for unit in state["units"].values():
        unit.setdefault("mastery_overall", None)
        unit.setdefault("evidence_coverage", {"observed_targets": [], "supported_targets": [],
                         "missing_targets": list(unit["evidence_targets"]), "unverified_targets": [],
                         "independent_questions": 0, "sufficient_for_overall": False})
    models = fit_models(included, units, as_of, learner["learner_id"])
    courses = []
    for path in sorted((root / "config/courses").glob("*.json")):
        course = validate_course(load_json(path))
        if course["fictional"] and learner["mode"] != "demo":
            raise ContractError("fictional courses cannot be used in a personal Vault")
        for spec in course["units"]:
            if registry.get(spec["unit_id"]) != spec:
                raise ContractError("installed course and registered units differ; review the course update")
        courses.append(course)
    diagnostics = select_diagnostics(registry, state, models, courses, config, as_of, minutes)
    due = [t for t in state["review_queue"] if parse_datetime(t["due_at"]) <= as_of
           and t["unit_id"] in registry and active(registry[t["unit_id"]], config, as_of)]
    schedule = None
    if minutes is not None:
        # Original scheduling rules remain authoritative. No model scores enter them.
        schedule = build_schedule(state, {"schema_version": "1.0", "available_minutes": minutes,
                                         "as_of": as_of.isoformat()}, config)
    return {"schema_version": "1.0", "as_of": as_of.isoformat(), "learner": learner,
            "state": state, "models": models, "due_work": due, "diagnostics": diagnostics,
            "schedule": schedule, "evidence_gaps": [
                {"unit_id": uid, "title": u["title"],
                 "missing": u["evidence_coverage"]["missing_targets"],
                 "unverified": u["evidence_coverage"]["unverified_targets"]}
                for uid, u in state["units"].items() if active(u, config, as_of)
                and not u["evidence_coverage"]["sufficient_for_overall"]],
            "error_hypotheses": [{"diagnosis_id": key, "status": d["status"],
                                   "unit_ids": d["unit_ids"], "error_tags": d.get("error_tags", []),
                                   "source_event_ids": d.get("evidence_refs", []),
                                   "tag_probability": None, "reason": "error-opportunity_denominators_unavailable"}
                                  for key, d in state["diagnoses"].items() if d["status"] != "rejected"]}


def render_today(context: dict) -> str:
    lines = ["Study brief / 今日学习建议", f"As of: {context['as_of']}",
             "DEMO / 虚构演示" if context["learner"]["mode"] == "demo" else "Private learner / 私人学习档案",
             f"Due work / 到期任务: {len(context['due_work'])}"]
    for task in context["due_work"]:
        lines.append(f"- {task['unit_id']}: {task['reason']}")
    lines.append(f"Evidence gaps / 证据缺口: {len(context['evidence_gaps'])}")
    for gap in context["evidence_gaps"]:
        lines.append(f"- {gap['title']}: missing={','.join(gap['missing']) or 'none'}, unverified={','.join(gap['unverified']) or 'none'}")
    lines.append("Probe suggestions / 探针建议（待验证假设）:")
    for p in context["diagnostics"]["selected"]:
        lines.append(f"- [{p['probe_id']}] {p['prompt']} ({p['reason']})")
    if not context["diagnostics"]["selected"]:
        lines.append("- No eligible authored probe; no question or diagnosis is invented.")
    lines.append("Memory / 记忆模型: " + ", ".join(f"{uid}: {m['status']} (n={m['sample_count']})"
                                                  for uid, m in context["models"]["memory"].items()))
    lines.append("No time budget: suggestions only / 未提供时间预算，仅为建议" if context["schedule"] is None
                 else f"Rule-based plan / 原规则计划: {context['schedule']['scheduled_minutes']} minutes")
    lines.append("Unknown is not low mastery. Predictions are uncalibrated; no score-gain claim.")
    return "\n".join(lines) + "\n"


def render_dashboard(context: dict) -> str:
    """No scripts, remote requests or embedded raw evidence; escape all text."""
    esc = lambda value: html.escape(str(value), quote=True)
    rows = []
    for u in context["state"]["units"].values():
        coverage = u["evidence_coverage"]
        label = "Unknown / 未知" if u["mastery_overall"] is None else "Heuristic evidence / 启发式证据"
        rows.append("<tr>" + "".join(f"<td>{esc(x)}</td>" for x in
                    (u["title"], label, u["attempts"]["total"], ", ".join(coverage["missing_targets"]),
                     ", ".join(coverage["unverified_targets"]))) + "</tr>")
    body = render_today(context)
    return ("<!doctype html><html lang='zh-CN'><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width,initial-scale=1'>"
            "<meta http-equiv='Content-Security-Policy' content=\"default-src 'none'; style-src 'unsafe-inline'\">"
            "<title>Evidence-based study brief</title><style>"
            "body{font:16px/1.6 system-ui,sans-serif;background:#f3f5f7;color:#142b3e;max-width:1100px;margin:3rem auto;padding:1rem}"
            "h1{font-size:2rem}table{border-collapse:collapse;background:white;width:100%}td,th{text-align:left;padding:.8rem;border-bottom:1px solid #dae1e7}"
            "pre{white-space:pre-wrap;background:white;padding:1.5rem;border-radius:12px}small{color:#506779}</style>"
            "<h1>Learning evidence / 学习证据</h1><small>"
            + esc(context["as_of"]) + " · Local report; review before sharing / 本地报告，分享前请检查</small>"
            "<table><thead><tr><th>Unit / 知识点</th><th>Status / 状态</th><th>Attempts / 作答</th>"
            "<th>Missing / 缺少</th><th>Unverified / 待核验</th></tr></thead><tbody>"
            + "".join(rows) + "</tbody></table><h2>Next checks / 下一步核查</h2><pre>"
            + esc(body) + "</pre></html>")
