"""핫딜 게시판(루리웹 게임 핫딜 · 뽐뿌 · 아카라이브)에서 PS·닌텐도 관련 글만 모은다.

제목·가격·원문 링크만 가져오고 본문·이미지는 가져오지 않는다.
결과는 data/hotdeals.json 에 최근 KEEP_DAYS 일치만 남긴다 (처음 본 시각 first_seen 유지).
"""

import html
import re
import time
import xml.etree.ElementTree as ET
from datetime import timedelta
from email.utils import parsedate_to_datetime

from .common import DATA, fetch, load_config, load_json, now_kst, save_json, won

OUT = DATA / "hotdeals.json"
KEEP_DAYS = 7

RULIWEB = "https://bbs.ruliweb.com/market/board/1020/rss"
PPOMPPU = "https://www.ppomppu.co.kr/rss.php?id=ppomppu"
ARCA = "https://arca.live/b/hotdeal"

# 뜻이 여럿인 말(멀티탭 '스위치' 등). 게임 전용 게시판이 아니면 이 말만으로는 콘솔 글로 보지 않는다
AMBIGUOUS = {"스위치", "switch", "ns"}
NINTENDO_CONTEXT = re.compile(r"닌텐도|nintendo|스위치\s*(2|oled|라이트|lite)|switch\s*(2|oled|lite)|조이콘|프로콘", re.I)


def _kw_hit(title: str, kw: str) -> bool:
    kw = kw.lower()
    if re.fullmatch(r"[a-z0-9 ]+", kw):  # 영문 짧은 말은 단어 경계로 (ns 가 buds 에 걸리지 않게)
        return re.search(rf"(?<![a-z0-9]){re.escape(kw)}(?![a-z0-9])", title) is not None
    return kw in title


def classify(title: str, game_board: bool, cfg: dict | None = None) -> str | None:
    """콘솔 관련이면 'device'(기기·주변기기) 또는 'game', 아니면 None."""
    cfg = cfg or load_config()
    t = title.lower()
    hits = {k.lower() for k in cfg.get("console_keywords", []) if _kw_hit(t, k)}
    if not hits and game_board and any(_kw_hit(t, k) for k in cfg.get("game_title_keywords", [])):
        hits = {"title"}
    if not hits:
        return None
    if not game_board and hits <= AMBIGUOUS and not NINTENDO_CONTEXT.search(t):
        return None
    if any(_kw_hit(t, k) for k in cfg.get("device_keywords", [])):
        return "device"
    return "game"


def _rss(url: str, source: str, game_board: bool, cfg: dict) -> list[dict]:
    root = ET.fromstring(fetch(url))
    out = []
    for it in root.iter("item"):
        title = html.unescape((it.findtext("title") or "").strip())
        link = (it.findtext("link") or "").strip()
        if not title or not link:
            continue
        kind = classify(title, game_board, cfg)
        if not kind:
            continue
        posted = None
        try:
            posted = parsedate_to_datetime(it.findtext("pubDate")).astimezone(now_kst().tzinfo).isoformat(timespec="minutes")
        except Exception:
            pass
        no = re.search(r"(\d+)(?!.*\d)", link)
        out.append({
            "id": f"{source}:{no.group(1) if no else link}",
            "source": source, "title": title, "url": link,
            "price": won(title), "kind": kind, "posted": posted,
        })
    return out


_ARCA_ROW = re.compile(
    r'<span class="deal-store">(?P<store>[^<]*)</span>\s*(?:&nbsp;\s*)?'
    r'(?:<a class="badge" href="[^"]*category=(?P<cat>[a-z]+)">[^<]*</a>\s*)?</span>\s*'
    r'<a class="title hybrid-title" href="(?P<href>/b/hotdeal/(?P<no>\d+))[^"]*">(?P<title>.*?)<span class="info">.*?'
    r'<span class="deal-price">(?P<price>[^<]*)',
    re.S)


def parse_arca(page: str, cfg: dict) -> list[dict]:
    out = []
    for m in _ARCA_ROW.finditer(page):
        title = html.unescape(re.sub(r"<[^>]+>", "", m["title"])).strip()
        title = re.sub(r"\s+", " ", title)
        store = html.unescape(m["store"]).strip()
        kind = classify(title, m["cat"] == "sw", cfg)
        if not kind:
            continue
        out.append({
            "id": f"아카라이브:{m['no']}", "source": "아카라이브",
            "title": f"[{store}] {title}" if store else title,
            "url": "https://arca.live" + m["href"],
            "price": won(m["price"]) or won(title), "kind": kind, "posted": None,
        })
    return out


def collect() -> dict:
    cfg = load_config()
    found, errors = [], []
    for name, job in [
        ("루리웹", lambda: _rss(RULIWEB, "루리웹", True, cfg)),
        ("뽐뿌", lambda: _rss(PPOMPPU, "뽐뿌", False, cfg)),
        ("아카라이브", lambda: parse_arca(fetch(ARCA).decode("utf-8", "replace"), cfg)),
    ]:
        try:
            items = job()
            print(f"핫딜 {name}: {len(items)}건")
            found += items
        except Exception as e:
            errors.append(name)
            print(f"::warning::핫딜 {name} 수집 실패: {e}")
        time.sleep(1)

    now = now_kst()
    old = {d["id"]: d for d in load_json(OUT, {}).get("items", [])}
    stamp = now.isoformat(timespec="minutes")
    for d in found:
        prev = old.get(d["id"])
        d["first_seen"] = prev["first_seen"] if prev else stamp
        old[d["id"]] = d
    cutoff = (now - timedelta(days=KEEP_DAYS)).isoformat(timespec="minutes")
    items = sorted((d for d in old.values() if d["first_seen"] >= cutoff),
                   key=lambda d: d.get("posted") or d["first_seen"], reverse=True)
    result = {"updated": stamp, "errors": errors, "items": items}
    save_json(OUT, result)
    return result


if __name__ == "__main__":
    collect()
