"""닌텐도 한국 eShop 할인.

닌텐도 스토어 웹페이지(store.nintendo.co.kr)는 GitHub Actions 같은 클라우드 서버의 접속을 막는다.
그래서 두 단계로 나눈다.

1) 게임 목록 만들기 — 내 PC에서 가끔 (예: 한 달에 한 번)
   python -m collector.nintendo --catalog
   스토어 할인 목록 페이지에서 이름·상품번호(nsuid)·주소·표지 이미지 주소·기종을 받아
   data/ns_catalog.json 에 더한다 (지우지 않고 쌓는다).

2) 가격 조회 — Actions 에서 수집할 때마다
   목록의 상품번호로 닌텐도 가격 조회(api.ec.nintendo.com, 본체 eShop 이 쓰는 가격 조회)를 불러
   지금 할인 중인 것만 남긴다. 정가·할인가·할인 종료일이 함께 온다.

한계: 목록에 없는 게임이 새로 할인하면 놓친다. 목록을 가끔 새로 채운다.
"""

import html
import json
import re
import sys
import time

from .common import DATA, fetch, load_json, now_kst, save_json

LIST = "https://store.nintendo.co.kr/digital/sale?product_list_limit=48&p={page}"
PRICE = "https://api.ec.nintendo.com/v1/price?country=KR&lang=ko&ids={ids}"
CATALOG = DATA / "ns_catalog.json"
MAX_PAGES = 80
BATCH = 50
PAUSE = 1.0


# ---------- 1) 게임 목록 (스토어 웹페이지, 내 PC에서) ----------

def _first(pattern: str, text: str) -> str | None:
    m = re.search(pattern, text, re.S)
    return m.group(1) if m else None


def parse_list(page: str) -> list[dict]:
    """할인 목록 페이지 → [{nsuid, name, url, img, platform, price, regular}]"""
    out = []
    for block in page.split('class="product-item-info"')[1:]:
        href = _first(r'class="product-item-link"\s+href="([^"]+)"', block)
        name = _first(r'class="product-item-link"[^>]*>\s*(.*?)\s*</a>', block)
        nsuid = _first(r"/(\d{14})(?:\D|$)", (href or "") + "/")
        if not (href and name and nsuid):
            continue
        final = _first(r'data-price-amount="(\d+)"\s+data-price-type="finalPrice"', block)
        old = _first(r'data-price-amount="(\d+)"\s+data-price-type="oldPrice"', block)
        platform = _first(r'class="label_platform">\s*([^<]*?)\s*</p>', block) or ""
        out.append({
            "nsuid": nsuid, "name": html.unescape(re.sub(r"\s+", " ", name)).strip(), "url": href,
            "img": _first(r'class="product-image-photo"\s+src="([^"]+)"', block),
            "platform": html.unescape(platform),
            "price": int(final) if final else None, "regular": int(old or final) if final else None,
        })
    return out


def build_catalog() -> dict:
    catalog = load_json(CATALOG, {})
    seen, added = set(), 0
    today = now_kst().date().isoformat()
    for page in range(1, MAX_PAGES + 1):
        raw = fetch(LIST.format(page=page)).decode("utf-8", "replace")
        got = [d for d in parse_list(raw) if d["nsuid"] not in seen]
        if page == 1 and not got:
            raise RuntimeError("할인 목록을 읽지 못했습니다 (스토어가 막았거나 페이지 구조가 바뀜)")
        if not got:  # 마지막 페이지를 넘기면 마지막 페이지가 다시 나온다
            break
        for d in got:
            seen.add(d["nsuid"])
            added += d["nsuid"] not in catalog
            catalog[d["nsuid"]] = {"name": d["name"], "url": d["url"], "img": d["img"],
                                   "platform": d["platform"], "seen": today}
        print(f"\r목록 {page}쪽 · {len(seen)}개", end="", flush=True)
        time.sleep(PAUSE)
    print(f"\n닌텐도 게임 목록: 이번에 {len(seen)}개 확인, 새로 {added}개, 전체 {len(catalog)}개")
    save_json(CATALOG, catalog, one_per_line=True)
    return catalog


# ---------- 2) 가격 조회 (Actions 에서) ----------

def parse_prices(data: dict) -> dict:
    """가격 조회 응답 → {nsuid: {price, regular, ends}} (할인 중인 것만)"""
    out = {}
    for p in data.get("prices", []):
        disc, reg = p.get("discount_price"), p.get("regular_price")
        if not (disc and reg):
            continue
        try:
            price, regular = int(float(disc["raw_value"])), int(float(reg["raw_value"]))
        except (KeyError, ValueError):
            continue
        if price < regular:
            out[str(p.get("title_id"))] = {"price": price, "regular": regular, "ends": disc.get("end_datetime")}
    return out


def collect() -> list[dict]:
    catalog = load_json(CATALOG, {})
    if not catalog:
        raise RuntimeError("닌텐도 게임 목록(data/ns_catalog.json)이 비어 있습니다")
    ids, sale, failed = list(catalog), {}, 0
    for i in range(0, len(ids), BATCH):
        try:
            sale.update(parse_prices(json.loads(fetch(PRICE.format(ids=",".join(ids[i:i + BATCH]))))))
        except Exception as e:
            failed += 1
            print(f"::warning::닌텐도 가격 조회 실패 ({i}~): {e}")
        time.sleep(PAUSE)
    batches = (len(ids) + BATCH - 1) // BATCH
    if failed == batches:
        raise RuntimeError("닌텐도 가격 조회가 모두 실패했습니다")
    items = []
    for nsuid, p in sale.items():
        c = catalog[nsuid]
        items.append({
            "id": f"ns:{nsuid}", "store": "nintendo", "name": c["name"], "url": c["url"], "img": c.get("img"),
            "platforms": [c["platform"]] if c.get("platform") else [],
            "price": p["price"], "regular": p["regular"],
            "discount": round((p["regular"] - p["price"]) * 100 / p["regular"]), "ends": p["ends"],
        })
    print(f"닌텐도 할인: 목록 {len(ids)}개 중 {len(items)}개 할인 중")
    return items


if __name__ == "__main__":
    if "--catalog" in sys.argv:
        build_catalog()
    else:
        for d in collect()[:5]:
            print(d)
