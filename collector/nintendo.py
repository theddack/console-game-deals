"""닌텐도 한국 eShop 할인.

닌텐도 스토어 웹페이지(store.nintendo.co.kr)는 GitHub Actions 같은 클라우드 서버의 접속을 막는다.
그래서 두 단계로 나눈다.

1) 게임 목록 만들기 — 내 PC에서 가끔 (예: 한 달에 한 번)
   python -m collector.nintendo --catalog
   스토어 할인 목록 페이지에서 이름·상품번호(nsuid)·주소·표지 이미지 주소·발매일을 받고,
   스토어 필터(대상 본체·장르)별로 한 번씩 더 훑어 기종·장르를 붙여
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
PER_PAGE = 48
PRICE = "https://api.ec.nintendo.com/v1/price?country=KR&lang=ko&ids={ids}"
CATALOG = DATA / "ns_catalog.json"
MAX_PAGES = 80
BATCH = 50
PAUSE = 1.0


# ---------- 1) 게임 목록 (스토어 웹페이지, 내 PC에서) ----------

def _first(pattern: str, text: str) -> str | None:
    m = re.search(pattern, text, re.S)
    return m.group(1) if m else None


def _released(text: str | None) -> str | None:
    """'26.12.4' → '2026-12-04'"""
    m = re.fullmatch(r"\s*(\d{2,4})\.(\d{1,2})\.(\d{1,2})\s*", text or "")
    if not m:
        return None
    y = int(m.group(1))
    return f"{y + 2000 if y < 100 else y:04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"


def parse_list(page: str) -> list[dict]:
    """할인 목록 페이지 → [{nsuid, name, url, img, released, price, regular}]"""
    out = []
    for block in page.split('class="product-item-info"')[1:]:
        href = _first(r'class="product-item-link"\s+href="([^"]+)"', block)
        name = _first(r'class="product-item-link"[^>]*>\s*(.*?)\s*</a>', block)
        nsuid = _first(r"/(\d{14})(?:\D|$)", (href or "") + "/")
        if not (href and name and nsuid):
            continue
        final = _first(r'data-price-amount="(\d+)"\s+data-price-type="finalPrice"', block)
        old = _first(r'data-price-amount="(\d+)"\s+data-price-type="oldPrice"', block)
        out.append({
            "nsuid": nsuid, "name": html.unescape(re.sub(r"\s+", " ", name)).strip(), "url": href,
            "img": _first(r'class="product-image-photo"\s+src="([^"]+)"', block),
            "released": _released(_first(r'category-product-item-released">\s*<span>[^<]*</span>([^<]*)<', block)),
            "price": int(final) if final else None, "regular": int(old or final) if final else None,
        })
    return out


def parse_filters(page: str) -> dict:
    """목록 왼쪽 필터 → {"label_platform": {번호: 이름}, "game_category": {번호: 이름}}"""
    out = {"label_platform": {}, "game_category": {}}
    for m in re.finditer(r'href="[^"]*[?&](label_platform|game_category)=(\d+)[^"]*"[^>]*>(.*?)</a>', page, re.S):
        text = html.unescape(" ".join(re.sub(r"<[^>]+>", " ", m.group(3)).split()))
        text = re.sub(r"\s*\d[\d,]*\s*건\s*$", "", text).strip()
        if text:
            out[m.group(1)].setdefault(m.group(2), text)
    return out


def platform_label(name: str) -> str:
    """'Nintendo Switch 2' → 'Switch 2', 'Nintendo Switch' → 'Switch'"""
    return re.sub(r"^Nintendo\s+", "", name).strip()


def _crawl(extra: str = "", label: str = "") -> tuple[list[dict], str]:
    """할인 목록을 끝까지 (extra: '&label_platform=4679' 같은 필터). (상품들, 첫 페이지 원문)"""
    items, seen, first, pages, page = [], set(), "", MAX_PAGES, 0
    while page < pages:
        page += 1
        raw = fetch(LIST.format(page=page) + extra).decode("utf-8", "replace")
        if not first:
            first = raw
            # 전체 개수로 쪽수를 정한다. 필터를 건 목록은 순서가 흔들려 이미 본 게임만 있는 쪽이 중간에 나올 수 있다
            nums = [int(n.replace(",", "")) for n in re.findall(r'toolbar-number">([\d,]+)<', raw)]
            if nums:
                pages = min(MAX_PAGES, -(-max(nums) // PER_PAGE))
        got = [d for d in parse_list(raw) if d["nsuid"] not in seen]
        if not got and page == 1:
            break
        seen.update(d["nsuid"] for d in got)
        items += got
        print("\r" + f"{label or '전체'} {page}쪽 · {len(items)}개   ", end="", flush=True)
        time.sleep(PAUSE)
    print()
    return items, first


def build_catalog() -> dict:
    """할인 목록 전체 + 기종별 + 장르별로 한 번씩 훑어 목록을 채운다 (4~5분)."""
    catalog = load_json(CATALOG, {})
    today = now_kst().date().isoformat()
    items, first = _crawl()
    if not items:
        raise RuntimeError("할인 목록을 읽지 못했습니다 (스토어가 막았거나 페이지 구조가 바뀜)")
    added = 0
    for d in items:
        added += d["nsuid"] not in catalog
        old = catalog.get(d["nsuid"], {})
        catalog[d["nsuid"]] = {"name": d["name"], "url": d["url"], "img": d["img"],
                               "released": d["released"] or old.get("released"),
                               "platforms": [], "genres": [], "seen": today}
    filters = parse_filters(first)
    for key, field, fmt in (("label_platform", "platforms", platform_label), ("game_category", "genres", str)):
        for fid, fname in filters[key].items():
            name = fmt(fname)
            for d in _crawl(f"&{key}={fid}", name)[0]:
                c = catalog.get(d["nsuid"])
                if c is not None and name not in c[field]:
                    c[field].append(name)
    # 이번에 안 보인 게임은 예전 분류를 그대로 둔다 (할인이 끝났을 뿐)
    for c in catalog.values():
        c.pop("platform", None)
    print(f"닌텐도 게임 목록: 이번에 {len(items)}개 확인, 새로 {added}개, 전체 {len(catalog)}개 · "
          f"기종 {len(filters['label_platform'])}종 · 장르 {len(filters['game_category'])}종")
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
            "platforms": c.get("platforms") or [], "genres": c.get("genres") or [], "released": c.get("released"),
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
