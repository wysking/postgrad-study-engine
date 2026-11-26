"""Tests for the reusable AnkiWeb read-only inbox sync integration."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import importlib.util
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from scripts import contracts, process_inbox

MODULE_PATH = Path(__file__).resolve().parents[1] / "integrations" / "ankiweb-sync" / "sync_anki_vocab.py"
SPEC = importlib.util.spec_from_file_location("ankiweb_sync_adapter", MODULE_PATH)
assert SPEC and SPEC.loader
ankiweb_sync = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ankiweb_sync)


class AnkiWebSyncIntegrationTests(unittest.TestCase):
    def test_sync_extracts_stubborn_words_ignores_private_hook_and_validates(self):
        tz = timezone(timedelta(hours=8))
        with tempfile.TemporaryDirectory(prefix="core-anki-sync-") as tmp:
            root = Path(tmp)
            for sub in ("inbox", "outbox", "config"):
                (root / sub).mkdir()
            (root / "config" / "scheduler.json").write_text(
                json.dumps({"schema_version": "1.0", "weights": {}, "phase": "foundation"}),
                encoding="utf-8",
            )
            db_path = root / "sample.anki2"
            conn = sqlite3.connect(db_path)
            conn.executescript(
                """
                CREATE TABLE notes (id INTEGER PRIMARY KEY, flds TEXT);
                CREATE TABLE cards (id INTEGER PRIMARY KEY, nid INTEGER, lapses INTEGER, flags INTEGER);
                CREATE TABLE revlog (id INTEGER PRIMARY KEY, cid INTEGER, ease INTEGER, time INTEGER, type INTEGER);
                """
            )
            conn.execute(
                "INSERT INTO notes VALUES (1, ?), (2, ?)",
                (
                    'cognitive\x1f<div class="core-def">认知的</div>\x1fPRIVATE_UNSHARED_MNEMONIC',
                    'comprehension\x1f<div class="core-def">理解</div>\x1fSECOND_PRIVATE_HOOK',
                ),
            )
            conn.execute("INSERT INTO cards VALUES (11, 1, 3, 1), (12, 2, 0, 0)")
            ts = int(datetime(2026, 11, 25, 20, 0, tzinfo=tz).timestamp() * 1000)
            conn.execute(
                "INSERT INTO revlog VALUES (?, 11, 1, 9000, 0), (?, 12, 4, 6000, 2)",
                (ts, ts + 2000),
            )
            conn.commit()
            conn.close()

            req_path = ankiweb_sync.sync_to_inbox(root, date(2026, 11, 25), col_path=db_path)
            self.assertIsNotNone(req_path)
            raw = req_path.read_text(encoding="utf-8")
            self.assertNotIn("PRIVATE_UNSHARED_MNEMONIC", raw)
            self.assertNotIn("SECOND_PRIVATE_HOOK", raw)
            self.assertIn("cognitive（认知的）", raw)

            # Second run with identical review count is a no-op
            self.assertIsNone(ankiweb_sync.sync_to_inbox(root, date(2026, 11, 25), col_path=db_path))

            envelope = json.loads(raw)
            contracts.validate_mobile_request(envelope)
            contracts.validate_study_record_payload(envelope["payload"])
            receipt = process_inbox.process_file(root, req_path)
            self.assertEqual(receipt["status"], "succeeded", receipt)

    def test_delayed_cron_after_rollover_still_backfills_previous_study_day(self):
        tz = timezone(timedelta(hours=8))
        delayed_now = datetime(2026, 11, 26, 8, 47, tzinfo=tz)
        days = ankiweb_sync.default_study_days(tz, now=delayed_now, lookback_days=2)
        self.assertEqual(days, [date(2026, 11, 25), date(2026, 11, 26)])

        with tempfile.TemporaryDirectory(prefix="core-anki-delay-") as tmp:
            root = Path(tmp)
            (root / "inbox").mkdir()
            db_path = root / "sample.anki2"
            conn = sqlite3.connect(db_path)
            conn.executescript(
                """
                CREATE TABLE notes (id INTEGER PRIMARY KEY, flds TEXT);
                CREATE TABLE cards (id INTEGER PRIMARY KEY, nid INTEGER, lapses INTEGER, flags INTEGER);
                CREATE TABLE revlog (id INTEGER PRIMARY KEY, cid INTEGER, ease INTEGER, time INTEGER, type INTEGER);
                """
            )
            conn.execute(
                "INSERT INTO notes VALUES (1, ?)",
                ('cognitive\x1f<div class="core-def">认知的</div>\x1fPRIVATE_HOOK',),
            )
            conn.execute("INSERT INTO cards VALUES (11, 1, 1, 0)")
            ts_prev = int(datetime(2026, 11, 25, 21, 30, tzinfo=tz).timestamp() * 1000)
            conn.execute("INSERT INTO revlog VALUES (?, 11, 3, 5000, 0)", (ts_prev,))
            conn.commit()
            conn.close()

            written = ankiweb_sync.sync_days_to_inbox(root, days, col_path=db_path, now=delayed_now)
            self.assertEqual([p.name for p in written], ["anki-20261125-english-vocab-001.json"])
            self.assertEqual(ankiweb_sync.sync_days_to_inbox(root, days, col_path=db_path, now=delayed_now), [])


if __name__ == "__main__":
    unittest.main()
