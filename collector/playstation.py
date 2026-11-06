"""PlayStation Store 한국 '모든 할인' 목록.

스토어 웹이 쓰는 조회(categoryGridRetrieve)를 그대로 부른다. 공식 공개 API가 아니어서
스토어가 바뀌면 깨질 수 있다 — 실패하면 main 이 이전 결과 없이 경고만 남기고 계속한다.
"""

import json
import re
import time
import urllib.parse

from .common import fetch, won

API = "https://web.np.playstation.com/api/graphql/v1/op"
ALL_DEALS = "3f772501-f6f8-49b7-abac-874a88ca4897"
HASH = "4ce7d410a4db2c8b635a48c1dcec375906ff63b19dadd87e073f8fd0c0481d35"
PAGE = 300
MAX_PAGES = 40
PAUSE = 1.0
PRODUCT = "https://store.playstation.com/ko-kr/product/{id}"
KIND = {"FULL_GAME": "게임", "PREMIUM_EDITION": "에디션", "GAME_BUNDLE": "번들", "ADD_ON_PACK": "추가 콘텐츠",
        "LEVEL": "추가 콘텐츠", "VIRTUAL_CURRENCY": "게임 내 재화", "BUNDLE": "번들"}


REL_DESC = {"name": "productReleaseDate", "isAscending": False}   # 출시일 최신순
SALES = {"name": "sales30", "isAscending": False}                 # 최근 30일 판매 많은 순
POP_TOP = 600          # 인기 순위는 위에서 이만큼만 매긴다 (나머지는 순위 없음)
RELEASE_TAG = {"last_thirty_days": "new", "next_thirty_days": "upcoming", "future_release_date": "upcoming"}


def _page(offset: int, sort: dict | None = None, filters: list | tuple = ()) -> dict:
    var = {"id": ALL_DEALS, "pageArgs": {"size": PAGE, "offset": offset}, "sortBy": sort,
           "filterBy": list(filters), "facetOptions": []}
    ext = {"persistedQuery": {"version": 1, "sha256Hash": HASH}}
    url = (f"{API}?operationName=categoryGridRetrieve&variables={urllib.parse.quote(json.dumps(var))}"
           f"&extensions={urllib.parse.quote(json.dumps(ext))}")
    data = json.loads(fetch(url, headers={"x-psn-store-locale-override": "ko-KR", "content-type": "application/json"}))
    grid = (data.get("data") or {}).get("categoryGridRetrieve")
    if not grid:
        raise RuntimeError(f"응답 형식이 바뀜: {str(data)[:200]}")
    return grid


_LANGS = re.compile(r"\s*\((?:[^()]|\([^()]*\))*(?:한국어|영어|일본어|중국어)(?:[^()]|\([^()]*\))*\)\s*$")


def clean_name(name: str) -> str:
    """'사이버펑크 2077 (한국어, 영어)' → '사이버펑크 2077'. 이름 끝 지원 언어 목록만 뗀다."""
    return _LANGS.sub("", name.strip()) or name.strip()


IMG_ROLES = ["MASTER", "GAMEHUB_COVER_ART", "EDITION_KEY_ART", "PORTRAIT_BANNER", "FOUR_BY_THREE_BANNER"]


def pick_image(media: list | None) -> str | None:
    """표지로 쓸 이미지 주소 (작은 크기로). 이미지는 저장하지 않고 주소만 건다."""
    imgs = [m for m in media or [] if m.get("type") == "IMAGE" and m.get("url")]
    for role in IMG_ROLES:
        for m in imgs:
            if m.get("role") == role:
                return m["url"] + "?w=160"
    return imgs[0]["url"] + "?w=160" if imgs else None


def parse_product(p: dict) -> dict | None:
    pr = p.get("price") or {}
    price, regular = won(pr.get("discountedPrice")), won(pr.get("basePrice"))
    if pr.get("isFree"):
        price = 0
    plus = bool(pr.get("isTiedToSubscription"))
    disc = re.search(r"(\d+)\s*%", pr.get("discountText") or "")
    upsell = re.search(r"(\d+)\s*%\s*할인", pr.get("upsellText") or "")
    if price is not None and regular and price >= regular and upsell:
        # 일반가는 그대로이고 PS Plus 회원만 할인 ('10% 할인'). 회원가를 계산해 넣는다
        disc = upsell
        price = round(regular * (100 - int(upsell.group(1))) / 100)
        plus = True
    if price is None or not regular or price >= regular:
        return None
    cls = p.get("storeDisplayClassification") or ""
    return {
        "id": f"ps:{p['id']}", "store": "playstation", "name": clean_name(p.get("name", "")),
        "url": PRODUCT.format(id=p["id"]), "img": pick_image(p.get("media")), "price": price, "regular": regular,
        "discount": int(disc.group(1)) if disc else round((regular - price) * 100 / regular),
        "platforms": p.get("platforms") or [], "type": KIND.get(cls, cls),
        "plus": plus,  # PS Plus 가입자만 받는 할인
    }


def _all(sort: dict | None = None, filters: list | tuple = (), limit: int | None = None) -> tuple[list, dict]:
    """조건에 맞는 상품 전부 (원본 그대로)와 첫 응답 (분류 목록이 들어 있음)."""
    products, first, offset = [], None, 0
    for _ in range(MAX_PAGES):
        grid = _page(offset, sort, filters)
        first = first or grid
        products += grid.get("products") or []
        if (grid.get("pageInfo") or {}).get("isLast") or not grid.get("products") or (limit and len(products) >= limit):
            break
        offset += PAGE
        time.sleep(PAUSE)
    return products[:limit] if limit else products, first


def _tag(by_id: dict, label: str, filters: list, apply) -> None:
    """filters 에 맞는 상품마다 apply(item) — 실패해도 본 목록은 그대로 둔다."""
    try:
        time.sleep(PAUSE)
        for p in _all(filters=filters)[0]:
            d = by_id.get(f"ps:{p.get('id')}")
            if d:
                apply(d)
    except Exception as e:
        print(f"::warning::PlayStation 분류 '{label}' 조회 실패: {e}")


def collect() -> list[dict]:
    # 1) 출시일 최신순으로 전부 — 순서가 곧 '출시일 순위'(rel, 0이 가장 최근)
    raw, first = _all(sort=REL_DESC)
    out, by_id = [], {}
    for p in raw:
        d = parse_product(p)
        if d and d["id"] not in by_id:
            d["rel"] = len(out)
            by_id[d["id"]] = d
            out.append(d)

    # 2) 인기 순위 (최근 30일 판매)
    try:
        time.sleep(PAUSE)
        rank = 0
        for p in _all(sort=SALES, limit=POP_TOP)[0]:
            d = by_id.get(f"ps:{p.get('id')}")
            if d and "pop" not in d:
                rank += 1
                d["pop"] = rank
    except Exception as e:
        print(f"::warning::PlayStation 인기 순위 조회 실패: {e}")

    # 3) 스토어 분류: 장르 · 방금 출시/출시 예정 · VR
    facets = {f.get("name"): f.get("values") or [] for f in (first or {}).get("facetOptions") or []}
    for v in facets.get("productGenres", []):
        if v.get("count"):
            name = v.get("displayName") or v["key"]
            _tag(by_id, name, [f"productGenres:{v['key']}"], lambda d, n=name: d.setdefault("genres", []).append(n))
    for v in facets.get("productReleaseDate", []):
        tag = RELEASE_TAG.get(v.get("key"))
        if tag and v.get("count"):
            _tag(by_id, v["key"], [f"productReleaseDate:{v['key']}"], lambda d, t=tag: d.__setitem__("fresh", t))
    for v in facets.get("productVrCompatibility", []):
        if v.get("count"):
            name = {"PSVR2": "PS VR2", "PSVR": "PS VR"}.get(v["key"], v["key"])
            _tag(by_id, name, [f"productVrCompatibility:{v['key']}"], lambda d, n=name: d.setdefault("vr", []).append(n))

    print(f"PlayStation 할인: {len(out)}개 (장르 {sum(1 for d in out if d.get('genres'))}개 · "
          f"인기 순위 {sum(1 for d in out if d.get('pop'))}개 · 방금 출시 {sum(1 for d in out if d.get('fresh') == 'new')}개)")
    return out


if __name__ == "__main__":
    for d in collect()[:5]:
        print(d)
