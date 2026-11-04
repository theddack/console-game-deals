"""PlayStation 블로그 한국어판에서 세일·할인 소식만 (제목·링크·날짜)."""

import html
import re
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

from .common import KST, fetch

FEED = "https://blog.ko.playstation.com/feed/"
SALE = re.compile(r"할인|세일|특가|프로모션|days of play|black friday|블랙 ?프라이데이|플레이스테이션 플러스|ps plus", re.I)


def collect() -> list[dict]:
    root = ET.fromstring(fetch(FEED))
    out = []
    for it in root.iter("item"):
        title = html.unescape((it.findtext("title") or "").strip())
        if not SALE.search(title):
            continue
        try:
            posted = parsedate_to_datetime(it.findtext("pubDate")).astimezone(KST).isoformat(timespec="minutes")
        except Exception:
            posted = None
        link = (it.findtext("link") or "").strip()
        out.append({"id": f"psblog:{link}", "source": "PS 블로그", "title": title, "url": link, "posted": posted})
    print(f"PS 블로그 세일 소식: {len(out)}건")
    return out[:15]
