import unittest

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


if __name__ == "__main__":
    unittest.main()
