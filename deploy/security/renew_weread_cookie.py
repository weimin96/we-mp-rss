"""One bounded WeRead cookie renewal. Never print Cookie or token values."""

import json
import os
import tempfile
import time
from pathlib import Path

from core.weread_session_renewal import renew_saved_account


LIC_PATH = Path("data/wx.lic")
STATUS_PATH = Path("data/weread_renewal_status.json")
COOLDOWN_AFTER_FAILURE_SECONDS = 6 * 3600


def main() -> int:
    now = int(time.time())
    state = json.loads(STATUS_PATH.read_text()) if STATUS_PATH.exists() else {}
    if now < int(state.get("retry_after", 0)):
        print("WeRead renewal: cooldown active; no request")
        return 0
    state["attempts"] = int(state.get("attempts", 0)) + 1
    state["last_attempt_at"] = now
    try:
        result = renew_saved_account(LIC_PATH)
    except Exception as exc:
        state["failures"] = int(state.get("failures", 0)) + 1
        state["last_result"] = "failed"
        # Only store an exception *class*, not a server response that could
        # contain a session cookie or other sensitive material.
        state["last_error_type"] = type(exc).__name__
        state["retry_after"] = now + COOLDOWN_AFTER_FAILURE_SECONDS
        _store_status(state)
        print(f"WeRead renewal: failed ({type(exc).__name__}); retry after 6h")
        return 1
    state["successes"] = int(state.get("successes", 0)) + 1
    state["last_success_at"] = now
    state["last_result"] = "success"
    state["last_error_type"] = None
    state["retry_after"] = 0
    state["last_rotated"] = result["rotated"]
    _store_status(state)
    print("WeRead renewal: success; credentials persisted")
    return 0


def _store_status(state: dict) -> None:
    STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    fd, path = tempfile.mkstemp(prefix=".wr-renew-", dir=STATUS_PATH.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            json.dump(state, file, ensure_ascii=False, sort_keys=True)
        os.replace(path, STATUS_PATH)
    finally:
        if os.path.exists(path):
            os.unlink(path)


if __name__ == "__main__":
    raise SystemExit(main())
