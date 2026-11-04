"""닌텐도 한국 스토어(eShop) 할인 중인 게임.

1) store.nintendo.co.kr/digital/sale 목록에서 이름·상품번호(nsuid)·할인가·정가
2) 닌텐도 가격 조회(api.ec.nintendo.com)로 할인 종료일을 덧붙인다 (실패해도 목록은 쓴다)
"""

import html
import json
import re
import time

from .common import fetch

LIST = "https://store.nintendo.co.kr/digital/sale?product_list_limit=48&p={page}"
PRICE = "https://api.ec.nintendo.com/v1/price?country=KR&lang=ko&ids={ids}"
MAX_PAGES = 80
PAUSE = 1.0

_ITEM = re.compile(
    r'<a class="product-item-link"\s+href="(?P<href>[^"]+)">\s*(?P<name>.*?)\s*</a>.*?'
    r'data-price-amount="(?P<final>\d+)"\s+data-price-type="finalPrice"'
    r'(?:(?:(?!product-item-link).)*?data-price-amount="(?P<old>\d+)"\s+data-price-type="oldPrice")?',
    re.S)


def parse_list(page: str) -> list[dict]:
    out = []
    for m in _ITEM.finditer(page):
        href = m["href"]
        nsuid = re.search(r"/(\d{14})(?:\D|$)", href + "/")
        price, regular = int(m["final"]), int(m["old"] or m["final"])
        if regular <= price:
            continue
        key = nsuid.group(1) if nsuid else href.rstrip("/").rsplit("/", 1)[-1]
        out.append({
            "id": f"ns:{key}", "store": "nintendo", "nsuid": nsuid.group(1) if nsuid else None,
            "name": html.unescape(re.sub(r"\s+", " ", m["name"])).strip(), "url": href,
            "price": price, "regular": regular,
            "discount": round((regular - price) * 100 / regular),
        })
    return out


def _add_end_dates(items: list[dict]) -> None:
    ids = [d["nsuid"] for d in items if d.get("nsuid")]
    by_id = {d["nsuid"]: d for d in items if d.get("nsuid")}
    for i in range(0, len(ids), 50):
        try:
            data = json.loads(fetch(PRICE.format(ids=",".join(ids[i:i + 50]))))
        except Exception as e:
            print(f"::warning::닌텐도 종료일 조회 실패 ({i}~): {e}")
            continue
        for p in data.get("prices", []):
            end = (p.get("discount_price") or {}).get("end_datetime")
            d = by_id.get(str(p.get("title_id")))
            if d and end:
                d["ends"] = end
        time.sleep(PAUSE)


def collect() -> list[dict]:
    items, seen = [], set()
    for page in range(1, MAX_PAGES + 1):
        got = parse_list(fetch(LIST.format(page=page)).decode("utf-8", "replace"))
        new = [d for d in got if d["id"] not in seen]
        if not new:  # 마지막 페이지를 넘기면 마지막 페이지가 다시 나온다
            break
        seen.update(d["id"] for d in new)
        items += new
        time.sleep(PAUSE)
    _add_end_dates(items)
    print(f"닌텐도 할인: {len(items)}개")
    return items


if __name__ == "__main__":
    for d in collect()[:5]:
        print(d)
