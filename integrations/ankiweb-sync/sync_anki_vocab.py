"""Reusable read-only AnkiWeb daily review summary adapter for Vault inbox."""

from __future__ import annotations

import argparse
from datetime import date, datetime, time, timedelta, timezone, tzinfo
import html
import json
import os
from pathlib import Path
import re
import sqlite3
import tempfile
from zoneinfo import ZoneInfo

DEFAULT_TZ = "Asia/Shanghai"
ROLLOVER_HOUR = 4
CORE_DEF_RE = re.compile(r'<div class="core-def">(.*?)</div>', re.DOTALL)
TAG_RE = re.compile(r"<[^>]+>")


def resolve_tz(tz_name: str) -> tzinfo:
    if tz_name in ("Asia/Shanghai", "UTC+8", "+08:00"):
        return timezone(timedelta(hours=8))
    return ZoneInfo(tz_name)


def strip_html(raw: str) -> str:
    text = html.unescape(TAG_RE.sub(" ", raw or ""))
    return " ".join(text.split())


def extract_word_and_def(flds: str) -> tuple[str, str]:
    """Read only field 0 (Word) and field 1 (Exam_Meaning); ignore field 2+ (Private_Hook)."""
    parts = (flds or "").split("\x1f")
    word = strip_html(parts[0]) if parts else ""
    meaning_raw = parts[1] if len(parts) > 1 else ""
    match = CORE_DEF_RE.search(meaning_raw)
    short_def = strip_html(match.group(1)) if match else strip_html(meaning_raw)[:60]
    return word, short_def


def study_day_bounds(target_day: date, tz: tzinfo) -> tuple[int, int]:
    start_dt = datetime.combine(target_day, time(ROLLOVER_HOUR, 0), tzinfo=tz)
    end_dt = start_dt + timedelta(days=1)
    return int(start_dt.timestamp() * 1000), int(end_dt.timestamp() * 1000)


def default_study_day(tz: tzinfo, now: datetime | None = None) -> date:
    current = (now or datetime.now(tz)).astimezone(tz)
    return (current - timedelta(hours=ROLLOVER_HOUR)).date()


def download_ankiweb_collection(dest_col: Path, hkey: str, endpoint: str | None = None) -> None:
    from anki.collection import Collection
    from anki.sync_pb2 import SyncAuth, SyncCollectionResponse

    col = Collection(str(dest_col))
    try:
        auth = SyncAuth(hkey=hkey, endpoint=endpoint) if endpoint else SyncAuth(hkey=hkey)
        resp = col.sync_collection(auth, sync_media=False)
        if resp.new_endpoint:
            auth = SyncAuth(hkey=hkey, endpoint=resp.new_endpoint)
            resp = col.sync_collection(auth, sync_media=False)
        if resp.required in (
            SyncCollectionResponse.FULL_SYNC,
            SyncCollectionResponse.FULL_DOWNLOAD,
            SyncCollectionResponse.FULL_UPLOAD,
        ):
            # Strictly upload=False: never push back to AnkiWeb from headless sync.
            col.full_upload_or_download(auth=auth, server_usn=None, upload=False)
    finally:
        col.close()


def summarize_collection(col_path: Path, target_day: date, tz: tzinfo) -> dict | None:
    start_ms, end_ms = study_day_bounds(target_day, tz)
    conn = sqlite3.connect(f"file:{col_path.as_posix()}?mode=ro", uri=True)
    try:
        row = conn.execute(
            """
            SELECT COUNT(*),
                   COUNT(DISTINCT cid),
                   COALESCE(SUM(time), 0),
                   SUM(CASE WHEN type = 0 THEN 1 ELSE 0 END),
                   SUM(CASE WHEN ease = 1 THEN 1 ELSE 0 END),
                   SUM(CASE WHEN ease = 2 THEN 1 ELSE 0 END),
                   SUM(CASE WHEN ease = 3 THEN 1 ELSE 0 END),
                   SUM(CASE WHEN ease = 4 THEN 1 ELSE 0 END)
            FROM revlog
            WHERE id >= ? AND id < ?
            """,
            (start_ms, end_ms),
        ).fetchone()
        total_reviews = int(row[0] or 0)
        if total_reviews == 0:
            return None

        distinct_cards = int(row[1] or 0)
        minutes = round(float(row[2] or 0) / 60000.0, 1)
        learn_clicks = int(row[3] or 0)
        again, hard, good, easy = (int(row[i] or 0) for i in range(4, 8))

        stubborn_rows = conn.execute(
            """
            SELECT n.flds,
                   SUM(CASE WHEN r.ease = 1 THEN 1 ELSE 0 END) AS again_today,
                   c.lapses
            FROM revlog r
            JOIN cards c ON c.id = r.cid
            JOIN notes n ON n.id = c.nid
            WHERE r.id >= ? AND r.id < ?
            GROUP BY c.id
            HAVING again_today > 0 OR c.lapses >= 3
            ORDER BY again_today DESC, c.lapses DESC, c.id ASC
            LIMIT 20
            """,
            (start_ms, end_ms),
        ).fetchall()

        flagged_rows = conn.execute(
            """
            SELECT n.flds
            FROM cards c
            JOIN notes n ON n.id = c.nid
            WHERE (c.flags & 7) = 1
            ORDER BY c.id DESC
            LIMIT 15
            """
        ).fetchall()
    finally:
        conn.close()

    stubborn_items = []
    for flds, again_today, lapses in stubborn_rows:
        word, short_def = extract_word_and_def(flds)
        if word:
            label = f"{word}（{short_def}）" if short_def else word
            stubborn_items.append(f"{label}[今日重来{again_today}/累计忘{lapses}]")

    flagged_words = []
    for (flds,) in flagged_rows:
        word, _ = extract_word_and_def(flds)
        if word and word not in flagged_words:
            flagged_words.append(word)

    lines = [
        f"Anki 词汇复习自动汇总（{target_day.isoformat()}）："
        f"共点击 {total_reviews} 次（覆盖 {distinct_cards} 张卡，新学点击 {learn_clicks} 次，用时约 {minutes} 分钟；"
        f"重来 {again} / 困难 {hard} / 良好 {good} / 简单 {easy}）。"
    ]
    if stubborn_items:
        lines.append("需在阅读语境重点复现的易忘词：" + "；".join(stubborn_items) + "。")
    if flagged_words:
        lines.append("当前标红旗待补助记词：" + ", ".join(flagged_words) + "。")

    return {"total_reviews": total_reviews, "summary": "\n".join(lines)}


def next_request_path(inbox_dir: Path, target_day: date, subject_label: str, total_reviews: int) -> Path | None:
    day_compact = target_day.strftime("%Y%m%d")
    slug = re.sub(r"[^A-Za-z0-9_-]+", "-", subject_label).strip("-") or "vocab"
    prefix = f"anki-{day_compact}-{slug}-vocab-"
    existing = sorted(inbox_dir.glob(f"{prefix}*.json"))
    marker = f"共点击 {total_reviews} 次"
    for path in existing:
        try:
            body = json.loads(path.read_text(encoding="utf-8"))
            if marker in body.get("payload", {}).get("summary", ""):
                return None
        except Exception:
            continue
    return inbox_dir / f"{prefix}{len(existing) + 1:03d}.json"


def sync_to_inbox(
    vault_root: Path,
    target_day: date,
    *,
    subject_label: str = "english",
    source_ref: str = "AnkiDroid / FSRS",
    tz_name: str = DEFAULT_TZ,
    col_path: Path | None = None,
    now: datetime | None = None,
) -> Path | None:
    tz = resolve_tz(tz_name)
    if col_path is not None:
        stats = summarize_collection(col_path, target_day, tz)
    else:
        hkey = os.environ.get("ANKI_SYNC_HKEY", "").strip()
        if not hkey:
            return None
        endpoint = os.environ.get("ANKI_SYNC_ENDPOINT", "").strip() or None
        with tempfile.TemporaryDirectory(prefix="anki-readonly-") as tmp:
            temp_col = Path(tmp) / "collection.anki2"
            download_ankiweb_collection(temp_col, hkey=hkey, endpoint=endpoint)
            stats = summarize_collection(temp_col, target_day, tz)

    if stats is None:
        return None

    inbox_dir = vault_root / "inbox"
    inbox_dir.mkdir(parents=True, exist_ok=True)
    req_path = next_request_path(inbox_dir, target_day, subject_label, stats["total_reviews"])
    if req_path is None:
        return None

    request_id = req_path.stem
    created_at = (now or datetime.now(tz)).astimezone(tz).isoformat(timespec="seconds")
    envelope = {
        "schema_version": "1.0",
        "request_id": request_id,
        "created_at": created_at,
        "operation": "save_study_record",
        "client": "ankiweb-sync",
        "payload": {
            "summary": stats["summary"],
            "subject_label": subject_label,
            "topic": "Anki 词汇复习同步",
            "source_ref": source_ref,
            "occurred_on": target_day.isoformat(),
        },
    }
    req_path.write_text(json.dumps(envelope, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return req_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vault-root", type=Path, default=Path.cwd())
    parser.add_argument("--date", type=str, default=None)
    parser.add_argument("--subject-label", type=str, default="english")
    parser.add_argument("--source-ref", type=str, default="AnkiDroid / FSRS")
    parser.add_argument("--tz", type=str, default=DEFAULT_TZ)
    parser.add_argument("--col-path", type=Path, default=None)
    parser.add_argument("--github-output", type=Path, default=None)
    args = parser.parse_args()

    tz = resolve_tz(args.tz)
    target_day = date.fromisoformat(args.date) if args.date else default_study_day(tz)
    written = sync_to_inbox(
        args.vault_root.resolve(),
        target_day=target_day,
        subject_label=args.subject_label,
        source_ref=args.source_ref,
        tz_name=args.tz,
        col_path=args.col_path,
    )
    if args.github_output:
        rel = written.relative_to(args.vault_root.resolve()).as_posix() if written else ""
        with args.github_output.open("a", encoding="utf-8") as fh:
            fh.write(f"inbox_path={rel}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
