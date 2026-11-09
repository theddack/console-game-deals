"""게임 할인 수집: 닌텐도 · PlayStation · PS 블로그 소식 (핫딜은 collector/hotdeals.py 가 30분마다 따로).

파일
- data/hotdeals.json  핫딜 최근 7일 (hotdeals 작업이 커밋)
- data/news.json      PS 블로그 세일 소식 (커밋)
- data/lowest.json    게임별 수집 기준 최저가 기록 (커밋, 한 줄에 한 게임)
- data/games.json     지금 할인 중인 게임 전체 (매번 새로 만드는 큰 파일이라 커밋하지 않고 페이지에만 올린다)

한 곳이 실패해도 나머지는 계속한다. 실패한 곳은 각 파일의 errors 에 남고 화면·로그에 표시된다.
"""

import re
import sys
from datetime import date

from . import hotdeals, news, nintendo, playstation
from .common import DATA, load_config, load_json, now_kst, save_json

LOWEST = DATA / "lowest.json"
GAMES = DATA / "games.json"
NEWS = DATA / "news.json"
AT_LOW_MIN_DAYS = 30   # 기록이 이 일수 이상 쌓였을 때만 '최저가와 같음'을 표시 (짧으면 의미 없음)
FORGET_DAYS = 365      # 이만큼 안 보인 게임은 최저가 기록에서 지운다


def _norm(s: str) -> str:
    return re.sub(r"[\s:：\-–—'’!?.,()\[\]™®]", "", s.lower())


def mark(items: list[dict], hist: dict, today: date, wishlist: list[str]) -> None:
    """최저가·위시리스트 표시를 붙이고 기록을 갱신한다. hist[id] = [최저가, 그날, 처음 본 날, 마지막 본 날]."""
    t = today.isoformat()
    wants = [_norm(w) for w in wishlist if w.strip()]
    for d in items:
        prev = hist.get(d["id"])
        if prev is None:
            hist[d["id"]] = [d["price"], t, t, t]
        else:
            low, low_day, first, _ = prev
            tracked = (today - date.fromisoformat(first)).days
            d["tracked_days"] = tracked
            if d["price"] < low:
                d["new_low"] = True
                d["prev_low"] = low
                hist[d["id"]] = [d["price"], t, first, t]
            else:
                if d["price"] == low and tracked >= AT_LOW_MIN_DAYS:
                    d["at_low"] = True
                hist[d["id"]] = [low, low_day, first, t]
        name = _norm(d["name"])
        if any(w in name for w in wants):
            d["wish"] = True


def run() -> int:
    cfg = load_config()
    now = now_kst()
    stamp = now.isoformat(timespec="minutes")
    failed = []

    # 핫딜은 따로 30분마다 받는다 (.github/workflows/hotdeals.yml). 여기서도 받으면 두 작업이 같은 파일을
    # 고쳐 커밋이 부딪힌다. 로컬에서 한꺼번에 보려면 --with-hotdeals
    if "--with-hotdeals" in sys.argv:
        try:
            hotdeals.collect()
        except Exception as e:
            print(f"::warning::핫딜 수집 실패: {e}")

    try:
        save_json(NEWS, {"updated": stamp, "items": news.collect()})
    except Exception as e:
        failed.append("PS 블로그")
        print(f"::warning::PS 블로그 수집 실패: {e}")

    hist = load_json(LOWEST, {})
    games = {"updated": stamp, "errors": [], "nintendo": [], "playstation": []}
    for key, label, mod in [("nintendo", "닌텐도", nintendo), ("playstation", "PlayStation", playstation)]:
        try:
            items = mod.collect()
            mark(items, hist, now.date(), cfg.get("wishlist", []))
            items.sort(key=lambda d: (-d["discount"], d["price"]))
            games[key] = items
        except Exception as e:
            games["errors"].append(label)
            failed.append(label)
            print(f"::warning::{label} 수집 실패: {e}")

    today = now.date()
    hist = {k: v for k, v in hist.items() if (today - date.fromisoformat(v[3])).days <= FORGET_DAYS}
    save_json(LOWEST, hist, one_per_line=True)
    save_json(GAMES, games, compact=True)
    # 비상용 예약이 '최근에 수집했는지' 보는 표시 (.github/workflows/collect.yml 의 gate)
    (DATA / "collected_at.txt").write_text(stamp + chr(10), encoding="utf-8")

    if failed:
        print(f"::warning::실패한 곳: {', '.join(failed)}")
    # 모든 곳이 실패했을 때만 실패로 끝낸다 (일부 실패는 경고로 두고 배포는 계속)
    return 1 if len(failed) >= 3 else 0  # PS 블로그 · 닌텐도 · PlayStation 이 모두 실패


if __name__ == "__main__":
    sys.exit(run())
