"""할인 소식: PlayStation 블로그 한국어판 + 루리웹 콘솔 뉴스 (제목·링크·날짜만).

- PS 블로그: 세일·할인 말이 들어간 글
- 루리웹 콘솔 뉴스: 세일·할인 말과 PS·닌텐도 말이 함께 들어간 글 (스토어 세일 시작, 본체 가격 인하 같은 소식).
  닌텐도는 공식 RSS 가 없어서 닌텐도 세일 소식은 주로 여기서 잡힌다
루리웹 콘솔 뉴스 RSS 는 6시간 남짓 분량이라 핫딜과 함께 30분마다 받는다 (.github/workflows/hotdeals.yml).
결과는 data/news.json 에 쌓는다 (처음 본 지 KEEP_DAYS 일 안, 최대 MAX_ITEMS 건).
"""

import html
import re
import time
import xml.etree.ElementTree as ET
from datetime import timedelta
from email.utils import parsedate_to_datetime

from .common import DATA, KST, fetch, load_json, now_kst, save_json

OUT = DATA / "news.json"
KEEP_DAYS = 30
MAX_ITEMS = 40

SALE = re.compile(r"할인|세일|특가|프로모션|가격\s*인하|인하|무료\s*배포|days of play|black friday|블랙\s*프라이데이|"
                  r"플레이스테이션 플러스|ps plus|게임\s*카탈로그", re.I)
CONSOLE = re.compile(r"ps5|ps4|ps\s*vr|플스|플레이스테이션|playstation|ps\s*store|ps\s*plus|스위치|switch|닌텐도|nintendo|"
                     r"e숍|eshop|듀얼센스", re.I)

# (출처 이름, 주소, id 앞머리, 콘솔 말도 있어야 하나)
FEEDS = [
    ("PS 블로그", "https://blog.ko.playstation.com/feed/", "psblog", False),
    ("루리웹 콘솔 뉴스", "https://bbs.ruliweb.com/news/board/1001/rss", "rulinews", True),
]


def pick(title: str, need_console: bool) -> bool:
    return bool(SALE.search(title)) and (not need_console or bool(CONSOLE.search(title)))


def parse_feed(xml: bytes, source: str, prefix: str, need_console: bool) -> list[dict]:
    out = []
    for it in ET.fromstring(xml).iter("item"):
        title = html.unescape((it.findtext("title") or "").strip())
        link = (it.findtext("link") or "").strip()
        if not title or not link or not pick(title, need_console):
            continue
        try:
            posted = parsedate_to_datetime(it.findtext("pubDate")).astimezone(KST).isoformat(timespec="minutes")
        except Exception:
            posted = None
        out.append({"id": f"{prefix}:{link}", "source": source, "title": title, "url": link, "posted": posted})
    return out


def collect() -> dict:
    found, errors = [], []
    for source, url, prefix, need_console in FEEDS:
        try:
            items = parse_feed(fetch(url), source, prefix, need_console)
            print(f"소식 {source}: {len(items)}건")
            found += items
        except Exception as e:
            errors.append(source)
            print(f"::warning::소식 {source} 수집 실패: {e}")
        time.sleep(1)

    now = now_kst()
    stamp = now.isoformat(timespec="minutes")
    old = {d["id"]: d for d in load_json(OUT, {}).get("items", [])}
    for d in found:
        d["first_seen"] = old.get(d["id"], {}).get("first_seen") or stamp
        old[d["id"]] = d
    cutoff = (now - timedelta(days=KEEP_DAYS)).isoformat(timespec="minutes")
    items = sorted((d for d in old.values() if (d.get("first_seen") or stamp) >= cutoff),
                   key=lambda d: d.get("posted") or d.get("first_seen") or "", reverse=True)[:MAX_ITEMS]
    # 새 글이 없으면 파일을 그대로 둔다 (updated 만 바뀌어 30분마다 커밋되지 않게)
    prev = load_json(OUT, {})
    if [d["id"] for d in prev.get("items", [])] == [d["id"] for d in items] and prev.get("errors") == errors:
        return prev
    result = {"updated": stamp, "errors": errors, "items": items}
    save_json(OUT, result)
    return result


if __name__ == "__main__":
    collect()
