import unittest
import contextlib
import io
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from deploy.security import fetch_daily_douban as poller
from deploy.security.fetch_daily_douban import classify_error, cooldown_seconds


class DailyDoubanPollPolicyTests(unittest.TestCase):
    def test_ambiguous_login_error_is_not_claimed_as_quota(self):
        self.assertEqual(classify_error(-2012), "auth_or_restricted")
        self.assertEqual(classify_error(-2041), "request_restricted")
        self.assertEqual(classify_error(499), "request_restricted")

    def test_cooldown_increases_but_is_bounded(self):
        self.assertEqual(cooldown_seconds("auth_or_restricted", 1), 12 * 3600)
        self.assertEqual(cooldown_seconds("auth_or_restricted", 2), 24 * 3600)
        self.assertEqual(cooldown_seconds("auth_or_restricted", 3), 48 * 3600)
        self.assertEqual(cooldown_seconds("auth_or_restricted", 8), 48 * 3600)

    def test_network_failure_backoff_shorter(self):
        self.assertEqual(cooldown_seconds("network_error", 1), 2 * 3600)

    def test_cooldown_records_skipped_timer_ticks_without_http(self):
        with tempfile.TemporaryDirectory() as temp:
            state_file = Path(temp) / "state.json"
            state_file.write_text(json.dumps({
                "blocked_until": 4000,
                "runs": 2,
                "requests_total": 7,
            }), encoding="utf-8")
            with patch.object(poller, "STATE_FILE", state_file), \
                    patch.object(poller.time, "time", return_value=1000), \
                    contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(poller.main(), 0)
                self.assertEqual(poller.main(), 0)
            state = json.loads(state_file.read_text(encoding="utf-8"))
            self.assertEqual(state["runs"], 2)
            self.assertEqual(state["requests_total"], 7)
            self.assertEqual(state["skipped_runs"], 2)
            self.assertEqual(state["last_skipped_at"], 1000)
            self.assertIn("requests=0", output.getvalue())


if __name__ == "__main__":
    unittest.main()
