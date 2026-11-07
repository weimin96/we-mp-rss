"""Renew WeRead web cookies using their saved long-lived wr_rt session.

Only the WeRead session is renewed. The WeChat MP authorization token and
WeRSS admin JWT are separate credentials and are deliberately not touched.
"""

import os
import tempfile
from pathlib import Path

import requests
import yaml


RENEW_URL = "https://weread.qq.com/web/login/renewal"
RENEW_BODY = {"rq": "%2Fweb%2Fbook%2Fread", "ql": False}
COOKIE_NAMES = {"wr_vid", "wr_skey", "wr_rt", "wr_ql", "wr_pf", "wr_gid", "wr_fp"}


def parse_cookie(cookie: str) -> dict:
    """Normalize duplicate keys, letting the latest occurrence win."""
    result = {}
    for part in (cookie or "").split(";"):
        key, separator, value = part.strip().partition("=")
        if separator and key and value:
            result[key] = value
    return result


def cookie_string(cookie_map: dict) -> str:
    return "; ".join(f"{key}={value}" for key, value in cookie_map.items())


def renew_cookie(cookie: str, *, timeout=(5, 12), request=requests.post) -> str:
    """Return refreshed cookie only after successful renewal and rotation.

    No auth secrets or upstream response bodies are logged on failures.
    """
    original = parse_cookie(cookie)
    if not original.get("wr_rt") or not original.get("wr_vid"):
        raise ValueError("missing_long_session")

    response = request(
        RENEW_URL,
        json=RENEW_BODY,
        headers={
            "Cookie": cookie_string(original),
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json, text/plain, */*",
            "Origin": "https://weread.qq.com",
            "Referer": "https://weread.qq.com/",
        },
        timeout=timeout,
    )
    if response.status_code != 200:
        raise RuntimeError(f"renew_http_{response.status_code}")
    try:
        payload = response.json()
    except ValueError as exc:
        raise RuntimeError("renew_invalid_json") from exc
    if not isinstance(payload, dict) or payload.get("succ") != 1:
        raise RuntimeError("renew_rejected")

    updates = {
        item.name: item.value
        for item in response.cookies
        if item.name in COOKIE_NAMES and item.value
    }
    # A success response with no updated auth cookie doesn't establish renewal.
    if not updates.get("wr_skey") or not updates.get("wr_rt"):
        raise RuntimeError("renew_missing_auth_cookie")
    combined = {**original, **updates}
    if not combined.get("wr_vid"):
        raise RuntimeError("renew_missing_vid")
    return cookie_string(combined)


def save_yaml_atomic(path: Path, data: dict) -> None:
    """Preserve permissions and replace atomically; never expose credentials."""
    mode = (path.stat().st_mode & 0o777) if path.exists() else 0o600
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".wr-lic-")
    try:
        os.fchmod(fd, mode & 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            yaml.safe_dump(data, handle, allow_unicode=True, sort_keys=False)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def renew_saved_account(path: Path, index: int = 0, *, renew=renew_cookie) -> dict:
    """Renew a saved WeRead account while keeping other wx.lic sections intact."""
    document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    data = document.get("weread_data") or {}
    accounts = data.get("accounts") or []
    selected = accounts[index] if accounts else data
    old_cookie = selected.get("cookie") or ""
    new_cookie = renew(old_cookie)
    changed = new_cookie != old_cookie
    selected["cookie"] = new_cookie
    selected["vid"] = parse_cookie(new_cookie).get("wr_vid", selected.get("vid", ""))
    if accounts and index == 0:
        # Keep legacy fields consistent with the account array.
        data["cookie"] = new_cookie
        data["vid"] = selected["vid"]
    document["weread_data"] = data
    save_yaml_atomic(path, document)
    return {"account_index": index, "renewed": True, "rotated": changed}
