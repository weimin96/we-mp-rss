import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import yaml

from core.weread_session_renewal import (
    parse_cookie, renew_cookie, renew_saved_account,
)


class WeReadSessionRenewalTests(unittest.TestCase):
    def test_deduplicates_and_rotates_existing_session(self):
        response = Mock(status_code=200)
        response.json.return_value = {"succ": 1}
        response.cookies = [
            SimpleNamespace(name="wr_skey", value="new-skey"),
            SimpleNamespace(name="wr_rt", value="new-long-session"),
            SimpleNamespace(name="wr_vid", value="7"),
        ]
        request = Mock(return_value=response)
        new_cookie = renew_cookie(
            "wr_vid=7; wr_skey=stale; wr_rt=long-session; wr_skey=stale-duplicate",
            request=request,
        )
        fields = parse_cookie(new_cookie)
        self.assertEqual(fields["wr_skey"], "new-skey")
        self.assertEqual(fields["wr_rt"], "new-long-session")
        self.assertEqual(new_cookie.count("wr_skey="), 1)
        self.assertEqual(request.call_args.kwargs["json"]["ql"], False)

    def test_rejected_response_does_not_write_any_credentials(self):
        response = Mock(status_code=200)
        response.json.return_value = {"succ": 0}
        response.cookies = []
        with self.assertRaisesRegex(RuntimeError, "renew_rejected"):
            renew_cookie("wr_vid=7; wr_rt=valid; wr_skey=stale", request=Mock(return_value=response))

    def test_atomic_save_preserves_wechat_token_and_account_list(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "wx.lic"
            path.write_text(yaml.safe_dump({
                "token_data": {"token": "wechat-mp-token"},
                "weread_data": {"accounts": [
                    {"cookie": "wr_vid=7; wr_rt=old; wr_skey=old", "vid": "7"},
                    {"cookie": "wr_vid=8; wr_rt=backup; wr_skey=backup", "vid": "8"},
                ]},
            }), encoding="utf-8")
            path.chmod(0o600)
            result = renew_saved_account(path, renew=lambda old: old.replace("wr_rt=old", "wr_rt=new"))
            doc = yaml.safe_load(path.read_text(encoding="utf-8"))
            self.assertEqual(doc["token_data"]["token"], "wechat-mp-token")
            self.assertIn("wr_rt=new", doc["weread_data"]["accounts"][0]["cookie"])
            self.assertIn("wr_rt=backup", doc["weread_data"]["accounts"][1]["cookie"])
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertTrue(result["renewed"])


if __name__ == "__main__":
    unittest.main()
