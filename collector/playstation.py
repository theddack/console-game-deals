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


def _page(offset: int) -> dict:
    var = {"id": ALL_DEALS, "pageArgs": {"size": PAGE, "offset": offset}, "sortBy": None, "filterBy": [], "facetOptions": []}
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


def parse_product(p: dict) -> dict | None:
    pr = p.get("price") or {}
    price, regular = won(pr.get("discountedPrice")), won(pr.get("basePrice"))
    if pr.get("isFree"):
        price = 0
    if price is None or not regular or price >= regular:
        return None
    disc = re.search(r"(\d+)\s*%", pr.get("discountText") or "")
    cls = p.get("storeDisplayClassification") or ""
    return {
        "id": f"ps:{p['id']}", "store": "playstation", "name": clean_name(p.get("name", "")),
        "url": PRODUCT.format(id=p["id"]), "price": price, "regular": regular,
        "discount": int(disc.group(1)) if disc else round((regular - price) * 100 / regular),
        "platforms": p.get("platforms") or [], "type": KIND.get(cls, cls),
        "plus": bool(pr.get("isTiedToSubscription")),  # PS Plus 가입자만 받는 할인
    }


def collect() -> list[dict]:
    items, offset = [], 0
    for _ in range(MAX_PAGES):
        grid = _page(offset)
        items += [d for d in map(parse_product, grid.get("products") or []) if d]
        info = grid.get("pageInfo") or {}
        if info.get("isLast") or not grid.get("products"):
            break
        offset += PAGE
        time.sleep(PAUSE)
    seen, out = set(), []
    for d in items:
        if d["id"] not in seen:
            seen.add(d["id"])
            out.append(d)
    print(f"PlayStation 할인: {len(out)}개")
    return out


if __name__ == "__main__":
    for d in collect()[:5]:
        print(d)
