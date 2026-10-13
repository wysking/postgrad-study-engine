"""Exercise real processes on fictional Vaults; never rely on lock-file existence."""

from __future__ import annotations

import json
import queue
import shutil
import subprocess
import sys
import threading
import unittest
from pathlib import Path

from scripts import process_inbox
from scripts.contracts import ContractError
from tests import test_mobile_requests as mobile


ROOT = Path(__file__).resolve().parents[1]
PAUSED_PUBLISHER = """
import json, sys
from pathlib import Path
from scripts import process_inbox
publish = process_inbox._publish_outputs
def paused(*args):
    print('ready', flush=True)
    sys.stdin.readline()
    publish(*args)
process_inbox._publish_outputs = paused
response = process_inbox.process_file(Path(sys.argv[1]), Path(sys.argv[2]))
print(json.dumps(response))
"""
LOCK_HOLDER = """
import sys
from pathlib import Path
from scripts.process_inbox import _vault_writer
with _vault_writer(Path(sys.argv[1])):
    print('ready', flush=True)
    sys.stdin.readline()
"""


class InboxSerializationTests(unittest.TestCase):
    def make_vault(self):
        root = mobile.MobileRequestTests().make_vault()
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        return root

    def request_path(self, root, suffix):
        request = mobile.request(f"fictional-request-{suffix}", "record_attempt",
                                 {"event": mobile.event(f"fictional-event-{suffix}")})
        return mobile.MobileRequestTests().write_request(root, request)

    def child(self, source, *arguments):
        child = subprocess.Popen([sys.executable, "-c", source, *map(str, arguments)],
                                 cwd=ROOT, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE, text=True)
        self.addCleanup(self.stop_child, child)
        lines = queue.Queue()
        threading.Thread(target=lambda: lines.put(child.stdout.readline()), daemon=True).start()
        self.assertEqual(lines.get(timeout=10).strip(), "ready")
        return child

    @staticmethod
    def stop_child(child):
        if child.poll() is None:
            child.kill()
        child.communicate(timeout=10)

    def test_parallel_publication_cannot_erase_another_successful_attempt(self):
        root = self.make_vault()
        first_path = self.request_path(root, "first")
        second_path = self.request_path(root, "second")
        child = self.child(PAUSED_PUBLISHER, root, first_path)
        try:
            with self.assertRaisesRegex(ContractError, "writer"):
                process_inbox.process_file(root, second_path)
            self.assertFalse((root / "outbox" / "fictional-request-second.json").exists())
        finally:
            output, errors = child.communicate("continue\n", timeout=10)
        self.assertEqual(child.returncode, 0, errors)
        self.assertEqual(json.loads(output)["status"], "succeeded")
        second = process_inbox.process_file(root, second_path)
        self.assertEqual(second["status"], "succeeded")
        self.assertEqual(process_inbox.process_file(root, second_path), second)
        ledger = [json.loads(line) for line in (root / "events" / "learning_events.jsonl").read_text().splitlines()]
        self.assertEqual({event["event_id"] for event in ledger}, {"fictional-event-first", "fictional-event-second"})
        self.assertEqual(len(ledger), 2)

    def test_cli_contention_is_retryable_without_a_failed_receipt(self):
        root = self.make_vault()
        path = self.request_path(root, "cli")
        command = [sys.executable, "-m", "scripts.process_inbox", "--vault-root", str(root), "--request", str(path)]
        with process_inbox._vault_writer(root):
            blocked = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=10)
        self.assertEqual(blocked.returncode, 2, blocked.stderr)
        self.assertFalse(list((root / "outbox").glob("*.json")))
        retried = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=10)
        self.assertEqual(retried.returncode, 0, retried.stderr)
        self.assertEqual(json.loads(retried.stdout)["responses"][0]["status"], "succeeded")

    def test_killed_writer_does_not_leave_a_stale_exclusive_lock(self):
        root = self.make_vault()
        child = self.child(LOCK_HOLDER, root)
        child.kill()
        child.communicate(timeout=10)
        response = process_inbox.process_file(root, self.request_path(root, "after-crash"))
        self.assertEqual(response["status"], "succeeded")

    def test_failed_operation_releases_the_writer_for_another_request(self):
        root = self.make_vault()
        bad = mobile.request("fictional-invalid", "record_attempt", {"event": {}})
        path = mobile.MobileRequestTests().write_request(root, bad)
        self.assertEqual(process_inbox.process_file(root, path)["status"], "failed")
        self.assertEqual(process_inbox.process_file(root, self.request_path(root, "valid"))["status"], "succeeded")

    def test_separate_vaults_can_process_at_the_same_time(self):
        first, second = self.make_vault(), self.make_vault()
        child = self.child(PAUSED_PUBLISHER, first, self.request_path(first, "separate-first"))
        response = process_inbox.process_file(second, self.request_path(second, "separate-second"))
        self.assertEqual(response["status"], "succeeded")
        _, errors = child.communicate("continue\n", timeout=10)
        self.assertEqual(child.returncode, 0, errors)


if __name__ == "__main__":
    unittest.main()
