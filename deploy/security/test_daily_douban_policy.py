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
        self.assertEqual(classify_error(-2012), "auth_required")
        self.assertEqual(classify_error(-2010), "auth_required")
        self.assertEqual(classify_error(-2041), "endpoint_rejected")
        self.assertEqual(classify_error(-2014), "access_restricted")
        self.assertEqual(classify_error(499, source="http"), "http_499")
        self.assertEqual(classify_error(429, source="http"), "rate_limited")
        self.assertEqual(classify_error(401, source="http"), "auth_required")
        self.assertEqual(classify_error(403, source="http"), "forbidden")
        self.assertEqual(classify_error(503, source="http"), "upstream_error")
        self.assertEqual(classify_error(503, source="business"), "other_error")

    def test_cooldown_increases_but_is_bounded(self):
        self.assertEqual(cooldown_seconds("auth_required", 1), 4 * 3600)
        self.assertEqual(cooldown_seconds("auth_required", 2), 8 * 3600)
        self.assertEqual(cooldown_seconds("auth_required", 3), 16 * 3600)
        self.assertEqual(cooldown_seconds("auth_required", 8), 32 * 3600)
        self.assertEqual(cooldown_seconds("rate_limited", 8), 48 * 3600)

    def test_network_failure_backoff_shorter(self):
        self.assertEqual(cooldown_seconds("network_error", 1), 2 * 3600)

    def test_only_new_rotated_credentials_unlock_auth_failure(self):
        failed = {
            "last_error_category": "auth_required",
            "last_run_at": 1000,
            "blocked_until": 50000,
            "consecutive_failures": 2,
        }
        self.assertFalse(poller.resume_after_renewal(failed, {
            "last_result": "success", "last_success_at": 900, "last_rotated": True,
        }))
        self.assertFalse(poller.resume_after_renewal(failed, {
            "last_result": "success", "last_success_at": 2000, "last_rotated": False,
        }))
        self.assertTrue(poller.resume_after_renewal(failed, {
            "last_result": "success", "last_success_at": 2000, "last_rotated": True,
        }))
        self.assertEqual(failed["blocked_until"], 0)
        self.assertEqual(failed["last_auth_retry_renewed_at"], 2000)
        self.assertFalse(poller.resume_after_renewal(failed, {
            "last_result": "success", "last_success_at": 2000, "last_rotated": True,
        }))
        blocked_for_rate_limit = {
            "last_error_category": "rate_limited",
            "last_run_at": 1000,
            "blocked_until": 50000,
        }
        self.assertFalse(poller.resume_after_renewal(blocked_for_rate_limit, {
            "last_result": "success", "last_success_at": 2000, "last_rotated": True,
        }))
        self.assertEqual(blocked_for_rate_limit["blocked_until"], 50000)

    def test_poll_persists_http_and_business_codes_independently(self):
        from unittest.mock import Mock
        from core.wx.model.weread_mp import WereadMPAPIError, MpsWereadMP

        with tempfile.TemporaryDirectory() as directory:
            state_file = Path(directory) / "poll.json"
            renewal_file = Path(directory) / "renew.json"
            collector = Mock(spec=MpsWereadMP)
            collector.get_Articles.side_effect = WereadMPAPIError(
                -2012, "session expired", source="business",
                endpoint="/web/mp/content", http_status=200,
            )
            collector.weread_request_stats.return_value = {
                "total": 1, "by_endpoint": {"/web/mp/content": 1},
            }
            with patch.object(poller, "STATE_FILE", state_file), \
                    patch.object(poller, "RENEWAL_STATUS_FILE", renewal_file), \
                    patch.object(poller.time, "time", return_value=1000), \
                    patch("core.wx.model.weread_mp.MpsWereadMP", return_value=collector), \
                    contextlib.redirect_stdout(io.StringIO()), \
                    contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(poller.main(), 1)
            state = json.loads(state_file.read_text(encoding="utf-8"))
            self.assertEqual(state["last_error_source"], "business")
            self.assertEqual(state["last_error_code"], "-2012")
            self.assertEqual(state["last_business_code"], "-2012")
            self.assertEqual(state["last_http_status"], 200)
            self.assertEqual(state["last_error_endpoint"], "/web/mp/content")
            self.assertEqual(state["requests_total"], 1)

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
