"""One bounded WeRead incremental poll for the Daily Douban feed.

Read as stdin by the host's systemd timer. No tokens or credentials in source.
"""

import contextlib
import datetime
import os
import sys


def main() -> int:
    try:
        # WX/sql logging includes full article HTML; don't write that to journald.
        with open(os.devnull, "w") as sink, contextlib.redirect_stdout(sink):
            from core.wx.model.weread_mp import MpsWereadMP
            from jobs.article import UpdateArticle

            collector = MpsWereadMP()
            collector.get_Articles(
                faker_id="MjM5MTM5MTAyMA==",
                Mps_id="MP_WXS_2391391020",
                Mps_title="每日豆瓣",
                CallBack=UpdateArticle,
                MaxPage=1,
            )
            added = collector.all_count()
        print(f"WeRSS incremental: added={added} at {datetime.datetime.now().isoformat(timespec='seconds')}")
        return 0
    except Exception as exc:
        print(f"WeRSS incremental failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
