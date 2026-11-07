"""Classify WeRead failures without confusing HTTP and service error codes.

These labels are operational hints, not claims about undocumented quota limits.
"""


def classify_weread_error(code, source="business") -> str:
    """Return a stable failure category given the code's originating layer."""
    if code in ("timeout", "network_error"):
        return "network_error"
    if source == "http":
        try:
            status = int(code)
        except (TypeError, ValueError):
            return "http_error"
        if status == 401:
            return "auth_required"
        if status == 403:
            return "forbidden"
        if status == 429:
            return "rate_limited"
        if status == 499:
            # Nonstandard status; don't equate client-closed/blocked with 429.
            return "http_499"
        if status in (408, 504):
            return "network_error"
        if 500 <= status < 600:
            return "upstream_error"
        return "http_error"
    try:
        business_code = int(code)
    except (TypeError, ValueError):
        return "other_error"
    if business_code in (-2012, -2010):
        # WeRead's login/session signal; only a successful renewal can confirm it.
        return "auth_required"
    if business_code == -2041:
        return "endpoint_rejected"
    if business_code == -2014:
        return "access_restricted"
    return "other_error"


def cooldown_seconds(category: str, failures: int) -> int:
    """A 4h auth backoff gives the scheduled renewal another opportunity."""
    base = {
        "auth_required": 4 * 3600,
        "endpoint_rejected": 12 * 3600,
        "rate_limited": 12 * 3600,
        "http_499": 12 * 3600,
        "access_restricted": 12 * 3600,
        "forbidden": 24 * 3600,
        "network_error": 2 * 3600,
        "upstream_error": 2 * 3600,
    }.get(category, 4 * 3600)
    return min(base * (2 ** min(max(failures - 1, 0), 3)), 48 * 3600)
