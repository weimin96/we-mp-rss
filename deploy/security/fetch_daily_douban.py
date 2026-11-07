"""Low-request WeRead poll with persistent cooldown and safe HTTP counters.

Executed as stdin in the existing WeRSS container by a locked systemd timer.
Only endpoint paths and aggregate request counts are persisted; never cookies.
"""

import contextlib
import datetime
import json
import os
import sys
import tempfile
import time
from pathlib import Path

from core.weread_error_policy import classify_weread_error, cooldown_seconds


FEED_ID = "MP_WXS_2391391020"
STATE_FILE = Path("data/daily_douban_poll_state.json")
RENEWAL_STATUS_FILE = Path("data/weread_renewal_status.json")
LIST_PROBE_SECONDS = 24 * 3600


def classify_error(code, source="business") -> str:
    """Compatibility wrapper for the canonical WeRead error policy."""
    return classify_weread_error(code, source=source)


def resume_after_renewal(state: dict, renewal: dict) -> bool:
    """Allow one auth retry after a *new*, successful cookie rotation.

    Do not clear unrelated rate-limit or endpoint-rejection cooldowns.
    """
    if state.get("last_error_category") not in ("auth_required", "auth_or_restricted"):
        return False
    renewed_at = int(renewal.get("last_success_at", 0))
    if (renewal.get("last_result") != "success"
            or not renewal.get("last_rotated")
            or renewed_at <= int(state.get("last_run_at", 0))
            or renewed_at <= int(state.get("last_auth_retry_renewed_at", 0))):
        return False
    state["blocked_until"] = 0
    state["consecutive_failures"] = 0
    state["last_auth_retry_renewed_at"] = renewed_at
    return True


def load_state() -> dict:
    if not STATE_FILE.exists():
        return {}
    return json.loads(STATE_FILE.read_text(encoding="utf-8"))


def save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".daily_douban_", dir=STATE_FILE.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, sort_keys=True)
            f.write("\n")
        os.replace(name, STATE_FILE)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def local_time(timestamp: int) -> str:
    return datetime.datetime.fromtimestamp(timestamp).isoformat(timespec="seconds")


def main() -> int:
    now = int(time.time())
    state = load_state()
    if RENEWAL_STATUS_FILE.exists():
        renewal = json.loads(RENEWAL_STATUS_FILE.read_text(encoding="utf-8"))
        if resume_after_renewal(state, renewal):
            save_state(state)
            print("WeRSS poll: new renewed session detected; auth cooldown lifted")
    blocked_until = int(state.get("blocked_until", 0))
    if now < blocked_until:
        # Distinguish a timer tick intentionally skipped under cooldown from
        # an actual collection attempt (state['runs']).
        state["skipped_runs"] = int(state.get("skipped_runs", 0)) + 1
        state["last_skipped_at"] = now
        save_state(state)
        print(f"WeRSS poll: cooldown active until {local_time(blocked_until)}; requests=0")
        return 0

    # List probing is deliberately rare; `latest` avoids a repeatedly rejected
    # endpoint while `auto` restores backfill if it becomes available later.
    last_probe = int(state.get("last_list_probe_at", now))
    list_mode = "auto" if now - last_probe >= LIST_PROBE_SECONDS else "latest"
    collector = None
    added = repaired = 0
    error = None
    with open(os.devnull, "w") as sink:
        try:
            # Avoid storing full article HTML / auth data in the system journal.
            with contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
                from core.wx.model.weread_mp import MpsWereadMP
                from jobs.article import UpdateArticle

                collector = MpsWereadMP()
                collector.get_Articles(
                    faker_id="MjM5MTM5MTAyMA==",
                    Mps_id=FEED_ID,
                    Mps_title="每日豆瓣",
                    CallBack=UpdateArticle,
                    MaxPage=1,
                    list_mode=list_mode,
                )
                added = collector.all_count()
                if added == 0:
                    repaired = collector.repair_one_missing_fulltext(FEED_ID)
        except Exception as exc:
            error = exc

    stats = collector.weread_request_stats() if collector is not None else {"total": 0, "by_endpoint": {}}
    state["runs"] = int(state.get("runs", 0)) + 1
    state["requests_total"] = int(state.get("requests_total", 0)) + stats["total"]
    by_endpoint = state.setdefault("requests_by_endpoint", {})
    for endpoint, count in stats["by_endpoint"].items():
        by_endpoint[endpoint] = int(by_endpoint.get(endpoint, 0)) + count
    state["last_run_at"] = now
    state["last_run_requests"] = stats["by_endpoint"]
    if list_mode == "auto" or "last_list_probe_at" not in state:
        state["last_list_probe_at"] = now

    if error is None:
        state["consecutive_failures"] = 0
        state["blocked_until"] = 0
        state["last_success_at"] = now
        state["last_error_code"] = None
        state["last_error_category"] = None
        state["last_error_source"] = None
        state["last_error_endpoint"] = None
        state["last_http_status"] = None
        state["last_business_code"] = None
        save_state(state)
        print(f"WeRSS poll: ok mode={list_mode} added={added} repaired={repaired} "
              f"requests={stats['total']} by_endpoint={stats['by_endpoint']}")
        return 0

    code = getattr(error, "code", type(error).__name__)
    source = getattr(error, "source", "internal")
    category = classify_error(code, source=source)
    failures = int(state.get("consecutive_failures", 0)) + 1
    next_retry = now + cooldown_seconds(category, failures)
    state["consecutive_failures"] = failures
    state["blocked_until"] = next_retry
    state["last_error_code"] = str(code)
    state["last_error_category"] = category
    state["last_error_source"] = source
    state["last_http_status"] = getattr(error, "http_status", None)
    state["last_business_code"] = str(code) if source == "business" else None
    # Endpoint path only, never URL query strings or credentials.
    state["last_error_endpoint"] = getattr(error, "endpoint", None)
    save_state(state)
    print(f"WeRSS poll: failed category={category} source={source} code={code} "
          f"http={state['last_http_status']} "
          f"endpoint={state['last_error_endpoint']} mode={list_mode} "
          f"requests={stats['total']} by_endpoint={stats['by_endpoint']} "
          f"next_retry_after={local_time(next_retry)}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
