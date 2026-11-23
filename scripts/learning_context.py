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


def _render_memory_svg(memory_models: dict, units: dict, esc) -> str:
    """Render a zero-JS, pure inline SVG forgetting-curve chart from real fitted models."""
    fitted = []
    colors = ("#C83E2B", "#1F6FEB", "#2E7D32", "#8250DF")
    for uid, m in memory_models.items():
        curve = m.get("curve_if_recalled_now")
        if m.get("status") != "fitted_uncalibrated" or not curve:
            continue
        title = units.get(uid, {}).get("title") or uid
        hl = m.get("half_life_days")
        fitted.append((uid, title, hl, m.get("sample_count", 0), curve))
    if not fitted:
        return "<div class='empty'>尚无足够延迟复习样本拟合遗忘曲线 / Add delayed reviews to fit recall curves.</div>"

    w, h = 500, 210
    pad_l, pad_r, pad_t, pad_b = 42, 18, 16, 30
    pw, ph = w - pad_l - pad_r, h - pad_t - pad_b
    max_day = max(max(pt["days"] for pt in item[4]) for item in fitted) or 14

    def sx(day: float) -> float:
        return pad_l + (day / max_day) * pw

    def sy(prob: float) -> float:
        return pad_t + (1.0 - max(0.0, min(1.0, prob))) * ph

    grid = []
    for pct in (0, 25, 50, 75, 100):
        y = sy(pct / 100.0)
        dash = " stroke-dasharray='3,3'" if pct not in (0, 100) else ""
        grid.append(f"<line x1='{pad_l}' y1='{y:.1f}' x2='{w - pad_r}' y2='{y:.1f}' stroke='#E5E7EB' stroke-width='1'{dash}/>")
        grid.append(f"<text x='{pad_l - 8}' y='{y + 4:.1f}' text-anchor='end' font-size='10' fill='#6B7280'>{pct}%</text>")
    for d in (0, 1, 3, 7, 14):
        if d <= max_day:
            x = sx(d)
            grid.append(f"<text x='{x:.1f}' y='{h - 8}' text-anchor='middle' font-size='10' fill='#6B7280'>D+{d}</text>")

    paths = []
    legend = []
    curve_rows = []
    for idx, (_uid, title, hl, n_samples, curve) in enumerate(fitted[:4]):
        color = colors[idx % len(colors)]
        pts = [(0.0, 1.0)] + [(float(pt["days"]), float(pt["predicted_recall"])) for pt in curve]
        d_str = " ".join(f"{'M' if i == 0 else 'L'}{sx(dx):.1f},{sy(py):.1f}" for i, (dx, py) in enumerate(pts))
        paths.append(f"<path d='{d_str}' fill='none' stroke='{color}' stroke-width='2.6' stroke-linecap='round' stroke-linejoin='round'/>")
        for dx, py in pts[1:]:
            paths.append(f"<circle cx='{sx(dx):.1f}' cy='{sy(py):.1f}' r='3.5' fill='white' stroke='{color}' stroke-width='2'/>")
        hl_txt = f"t½ ≈ {hl:.1f}天" if isinstance(hl, (int, float)) else ""
        legend.append(
            f"<div class='leg-item'><span class='dot' style='background:{color}'></span>"
            f"<strong>{esc(title)}</strong><span class='muted'> {esc(hl_txt)} · n={esc(n_samples)}</span></div>"
        )
        day_map = {int(pt["days"]): int(round(float(pt["predicted_recall"]) * 100)) for pt in curve}
        interval = memory_models[_uid].get("model_interval_90_days")
        ci_txt = f"{interval[0]:.1f}–{interval[1]:.1f}天" if isinstance(interval, list) and len(interval) == 2 else "—"
        curve_rows.append(
            "<tr>"
            f"<td><span class='dot' style='background:{color};margin-right:6px'></span><strong>{esc(title)}</strong></td>"
            f"<td>{esc(f'{hl:.1f}天' if isinstance(hl, (int, float)) else '—')} <span class='muted'>({esc(ci_txt)})</span></td>"
            f"<td>{esc(day_map.get(1, '—'))}%</td>"
            f"<td>{esc(day_map.get(3, '—'))}%</td>"
            f"<td>{esc(day_map.get(7, '—'))}%</td>"
            f"<td>{esc(day_map.get(14, '—'))}%</td>"
            "</tr>"
        )

    svg = (f"<svg viewBox='0 0 {w} {h}' width='100%' role='img' aria-label='Fitted forgetting curves'>"
           + "".join(grid) + "".join(paths) + "</svg>")
    detail_tbl = (
        "<table class='mini-tbl'><thead><tr>"
        "<th>知识点</th><th>半衰期 (90%区间)</th><th>D+1</th><th>D+3</th><th>D+7</th><th>D+14</th>"
        "</tr></thead><tbody>" + "".join(curve_rows) + "</tbody></table>"
    )
    return svg + "<div class='legend'>" + "".join(legend) + "</div>" + detail_tbl


def render_dashboard(context: dict) -> str:
    """No scripts, remote requests or embedded raw evidence; escape all text."""
    esc = lambda value: html.escape(str(value), quote=True)
    units = context["state"]["units"]
    target_labels = {
        "comprehension": "理解",
        "recall": "回忆",
        "independent": "独立求解",
        "transfer": "变式迁移",
        "delayed": "延迟复测",
        "timed": "限时演练",
    }
    task_type_labels = {
        "correction": ("错因复核", "pill-red"),
        "review": ("延迟巩固", "pill-amber"),
        "diagnostic": ("诊断核查", "pill-blue"),
        "targeted_variant": ("变式迁移", "pill-blue"),
    }

    practiced_units = [u for u in units.values() if u["mastery_overall"] is not None]
    unpracticed_units = [u for u in units.values() if u["mastery_overall"] is None]
    practiced_units.sort(key=lambda u: (-u["attempts"]["total"], u["unit_id"]))
    unpracticed_units.sort(key=lambda u: u["unit_id"])

    fitted_count = sum(1 for m in context["models"]["memory"].values() if m.get("status") == "fitted_uncalibrated")
    due_work = context["due_work"]
    probes = context["diagnostics"]["selected"]
    mode_badge = "14-Day Demo / 示例轨迹" if context["learner"]["mode"] == "demo" else "Private Vault / 私人档案"

    # Due work cards
    due_items = []
    for task in due_work:
        u_title = units.get(task["unit_id"], {}).get("title") or task["unit_id"]
        t_label, t_cls = task_type_labels.get(task.get("task_type"), ("待复习", "pill-gray"))
        mins = task.get("estimated_minutes")
        min_badge = f"<span class='meta'>{esc(mins)} min</span>" if mins else ""
        due_items.append(
            "<div class='item'>"
            f"<div class='item-top'><span class='pill {t_cls}'>{esc(t_label)}</span>"
            f"<span class='item-title'>{esc(u_title)}</span>{min_badge}</div>"
            f"<div class='item-sub'>{esc(task['reason'])}</div>"
            "</div>"
        )
    due_html = "".join(due_items) or "<div class='empty'>今日暂无到期复习任务 / No due items today.</div>"

    # Diagnostic probes cards
    probe_items = []
    for p in probes:
        u_title = units.get(p["unit_id"], {}).get("title") or p["unit_id"]
        tags = "".join(f"<span class='chip'>{esc(d)}</span>" for d in p.get("distinguishes", []))
        probe_items.append(
            "<div class='item'>"
            f"<div class='item-top'><span class='pill pill-dark'>闭卷探针</span>"
            f"<span class='item-title'>{esc(u_title)}</span>"
            f"<span class='meta'>{esc(p.get('estimated_minutes', 3))} min</span></div>"
            f"<div class='probe-q'>{esc(p['prompt'])}</div>"
            f"<div class='chips'>{tags}</div>"
            "</div>"
        )
    probe_html = "".join(probe_items) or "<div class='empty'>暂无待核查探针 / No targeted probes queued.</div>"

    # Unit mastery table rows (practiced units with bars first, then unpracticed)
    rows = []
    for u in practiced_units:
        pct = int(round(float(u["mastery_overall"]) * 100))
        att = u["attempts"]
        obs = "".join(f"<span class='chip chip-ok'>{esc(target_labels.get(t, t))}</span>"
                      for t in u["evidence_coverage"]["observed_targets"])
        rows.append(
            "<tr>"
            f"<td><strong>{esc(u['title'])}</strong><div class='sub-id'>{esc(u['subject'])}</div></td>"
            f"<td><div class='bar-wrap'><div class='bar-track'><div class='bar-fill' style='width:{pct}%'></div></div>"
            f"<span class='bar-num'>{pct}%</span></div></td>"
            f"<td><span class='stat-num'>{esc(att['correct'])}/{esc(att['total'])}</span> <span class='muted'>正确</span></td>"
            f"<td><div class='chips'>{obs or '<span class=\"muted\">—</span>'}</div></td>"
            "</tr>"
        )
    for u in unpracticed_units:
        missing = "".join(f"<span class='chip'>{esc(target_labels.get(t, t))}</span>"
                          for t in u["evidence_coverage"]["missing_targets"][:3])
        rows.append(
            "<tr class='row-dim'>"
            f"<td>{esc(u['title'])}<div class='sub-id'>{esc(u['subject'])}</div></td>"
            "<td><span class='pill pill-gray'>待首次演练 · Unknown / 未知</span></td>"
            "<td class='muted'>0 次</td>"
            f"<td><div class='chips'>{missing}</div></td>"
            "</tr>"
        )

    memory_svg = _render_memory_svg(context["models"]["memory"], units, esc)
    as_of_short = str(context["as_of"])[:10]

    return (
        "<!doctype html><html lang='zh-CN'><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<meta http-equiv='Content-Security-Policy' content=\"default-src 'none'; style-src 'unsafe-inline'\">"
        "<title>Postgrad Study Engine · Learning Dashboard</title><style>"
        "*{box-sizing:border-box}"
        "body{font:14px/1.55 -apple-system,BlinkMacSystemFont,'Segoe UI','PingFang SC','Microsoft YaHei',sans-serif;"
        "background:#F5F6F8;color:#18181B;margin:0;padding:24px}"
        ".wrap{max-width:1120px;margin:0 auto}"
        ".header{display:flex;justify-content:space-between;align-items:flex-end;margin-bottom:18px;padding-bottom:14px;border-bottom:1px solid #E4E4E7}"
        ".brand{font-size:22px;font-weight:700;letter-spacing:-.02em;color:#111827}"
        ".brand span{color:#C83E2B}"
        ".subtitle{font-size:12.5px;color:#6B7280;margin-top:2px}"
        ".badge-top{background:#1C1C1E;color:#F9FAFB;padding:5px 11px;border-radius:999px;font-size:12px;font-weight:500}"
        ".kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-bottom:18px}"
        ".kpi{background:#FFF;border:1px solid #E4E4E7;border-radius:12px;padding:14px 16px}"
        ".kpi-label{font-size:12px;color:#6B7280}"
        ".kpi-val{font-size:26px;font-weight:700;color:#111827;margin:4px 0 2px}"
        ".kpi-val.accent{color:#C83E2B}"
        ".kpi-note{font-size:11.5px;color:#71717A}"
        ".grid2{display:grid;grid-template-columns:1.05fr .95fr;gap:16px;margin-bottom:16px}"
        ".card{background:#FFF;border:1px solid #E4E4E7;border-radius:12px;padding:16px 18px}"
        ".card-title{font-size:15px;font-weight:700;color:#111827;margin:0 0 12px;display:flex;justify-content:space-between;align-items:center}"
        ".card-title small{font-size:11.5px;font-weight:400;color:#6B7280}"
        ".legend{display:flex;flex-wrap:wrap;gap:12px;margin-top:8px;font-size:12px}"
        ".leg-item{display:flex;align-items:center;gap:6px}"
        ".dot{width:9px;height:9px;border-radius:50%;display:inline-block}"
        ".item{padding:10px 12px;border:1px solid #F0F0F2;background:#FAFAFB;border-radius:9px;margin-bottom:9px}"
        ".item:last-child{margin-bottom:0}"
        ".item-top{display:flex;align-items:center;gap:8px;flex-wrap:wrap}"
        ".item-title{font-weight:600;color:#111827;font-size:13.5px}"
        ".item-sub{font-size:12px;color:#6B7280;margin-top:4px}"
        ".probe-q{font-size:13px;color:#1F2937;margin:6px 0;font-weight:500}"
        ".meta{margin-left:auto;font-size:11.5px;color:#6B7280;background:#FFF;border:1px solid #E4E4E7;padding:1px 7px;border-radius:999px}"
        ".pill{display:inline-block;padding:2px 8px;border-radius:999px;font-size:11.5px;font-weight:600}"
        ".pill-red{background:#FEE2E2;color:#B91C1C}"
        ".pill-amber{background:#FEF3C7;color:#B45309}"
        ".pill-blue{background:#DBEAFE;color:#1D4ED8}"
        ".pill-dark{background:#1C1C1E;color:#F9FAFB}"
        ".pill-gray{background:#F4F4F5;color:#52525B;font-weight:500}"
        ".chips{display:flex;flex-wrap:wrap;gap:5px}"
        ".chip{font-size:11px;padding:2px 7px;border-radius:6px;background:#F4F4F5;color:#52525B}"
        ".chip-ok{background:#ECFDF5;color:#047857}"
        "table{width:100%;border-collapse:collapse;font-size:13px}"
        "th{text-align:left;font-size:12px;color:#6B7280;font-weight:600;padding:7px 10px;border-bottom:1px solid #E4E4E7}"
        "td{padding:7px 10px;border-bottom:1px solid #F4F4F5;vertical-align:middle}"
        ".mini-tbl{margin-top:14px;font-size:12px;border-top:1px solid #F0F0F2}"
        ".mini-tbl th{font-size:11px;padding:7px 6px}"
        ".mini-tbl td{padding:7px 6px}"
        "tr:last-child td{border-bottom:none}"
        ".row-dim td{color:#52525B}"
        ".sub-id{font-size:11px;color:#9CA3AF;text-transform:uppercase;letter-spacing:.04em}"
        ".bar-wrap{display:flex;align-items:center;gap:8px}"
        ".bar-track{width:110px;height:7px;background:#E5E7EB;border-radius:999px;overflow:hidden}"
        ".bar-fill{height:100%;background:linear-gradient(90deg,#C83E2B,#E05A47);border-radius:999px}"
        ".bar-num{font-weight:700;font-size:12.5px;color:#111827}"
        ".stat-num{font-weight:600;color:#111827}"
        ".muted{color:#71717A;font-size:12px}"
        ".empty{color:#71717A;font-size:13px;padding:12px 0}"
        ".footer{margin-top:12px;font-size:11.5px;color:#71717A;display:flex;justify-content:space-between}"
        "</style><div class='wrap'>"
        "<div class='header'><div>"
        "<div class='brand'>Postgrad Study Engine <span>·</span> 学习记忆仪表盘</div>"
        f"<div class='subtitle'>Long-term Memory · Half-Life / FSRS Recall · Targeted Probes &nbsp;|&nbsp; As of {esc(as_of_short)}</div>"
        f"</div><div class='badge-top'>{esc(mode_badge)}</div></div>"
        "<div class='kpis'>"
        f"<div class='kpi'><div class='kpi-label'>累计学习事件 · Events</div><div class='kpi-val'>{esc(context['state']['event_count'])}</div><div class='kpi-note'>Append-only 可追溯账本</div></div>"
        f"<div class='kpi'><div class='kpi-label'>今日到期复习 · Due Today</div><div class='kpi-val accent'>{esc(len(due_work))}</div><div class='kpi-note'>错因复核与延迟巩固队列</div></div>"
        f"<div class='kpi'><div class='kpi-label'>遗忘曲线拟合 · Memory Fit</div><div class='kpi-val'>{esc(fitted_count)}</div><div class='kpi-note'>半衰期 / FSRS 个人记忆模型</div></div>"
        f"<div class='kpi'><div class='kpi-label'>课程知识点 · Units</div><div class='kpi-val'>{esc(len(units))}</div><div class='kpi-note'>已演练 {esc(len(practiced_units))} · 待首次覆盖 {esc(len(unpracticed_units))}</div></div>"
        "</div>"
        "<div class='grid2'>"
        "<div class='card'><div class='card-title'>个人遗忘曲线拟合 · Fitted Forgetting Curves<small>D+1 / D+3 / D+7 / D+14 留存率预测</small></div>"
        + memory_svg +
        "</div>"
        "<div class='card'><div class='card-title'>AI 私教闭卷探针 · Targeted Probes<small>精准定位卡点</small></div>"
        + probe_html +
        "<div class='card-title' style='margin-top:14px'>今日优先复习队列 · Due Work</div>"
        + due_html +
        "</div></div>"
        "<div class='card'><div class='card-title'>知识点掌握与覆盖总览 · Knowledge Units<small>严格区分独立求解与提示完成</small></div>"
        "<table><thead><tr><th>知识点 / Unit</th><th>掌握度估计 / Mastery</th><th>作答记录 / Attempts</th><th>已覆盖 / 待补齐维度</th></tr></thead><tbody>"
        + "".join(rows) +
        "</tbody></table></div>"
        "<div class='footer'><span>Postgrad Study Engine · Zero-Dependency Local Report</span>"
        "<span>Heuristic estimates &amp; uncalibrated recall curves for study guidance</span></div>"
        "</div></html>"
    )
