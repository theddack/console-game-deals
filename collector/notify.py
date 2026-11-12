"""텔레그램 브리핑. 수집이 끝날 때마다 '아직 안 보낸 것'만 모아 한 통 보낸다. 보낼 것이 없으면 보내지 않는다.

담는 것 (config.json 기준)
- 기기 핫딜: 핫딜 게시판의 PS·닌텐도 기기·주변기기 글 (device_price_limits 가 있으면 그 가격 이하만)
- 게임 핫딜: 핫딜 게시판의 콘솔 게임 글
- 위시리스트: wishlist 의 게임이 할인 중 (가격이 더 내려가면 다시)
- 새 최저가: 수집 기록보다 싸진 게임
- 큰 할인: 할인율 min_discount 이상 새로 시작한 게임 (상위 big_discount_notify_max 개, 나머지는 개수만)
- PS 블로그 세일 소식

보낸 기록: data/sent.json (게임은 보낸 가격, 할인이 끝나면 지워서 다음 할인 때 다시 알린다)
환경변수: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID. 없거나 DRY_RUN=1 이면 보내지 않고 출력만.
"""

import html
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta

from .common import DATA, load_config, load_json, now_kst, save_json

SENT = DATA / "sent.json"
SITE = "https://theddack.github.io/console-game-deals/"
TEXT_MAX = 3800
HOTDEAL_MAX = 15
LIST_MAX = 10
GAME_TYPES = {"", "게임", "에디션", "번들"}  # 큰 할인 알림은 본편 위주 (추가 콘텐츠·재화 제외)
WEEK = "월화수목금토일"
STORE = {"nintendo": "닌텐도", "playstation": "PS"}


def _e(s) -> str:
    return html.escape(str(s), quote=False)


def _won(n) -> str:
    return f"{n:,}원" if isinstance(n, int) else "가격 미상"


def _a(text: str, url: str) -> str:
    return f'<a href="{html.escape(url)}">{_e(text)}</a>'


def _ends(d: dict) -> str:
    if not d.get("ends"):
        return ""
    try:
        end = datetime.fromisoformat(d["ends"].replace("Z", "+00:00")).astimezone(now_kst().tzinfo)
        return f" ~{end.month}/{end.day}"
    except ValueError:
        return ""


def _game_line(d: dict, extra: str = "") -> str:
    store = STORE.get(d["store"], d["store"])
    plus = " (PS Plus)" if d.get("plus") else ""
    return (f"• [{store}] {_a(d['name'], d['url'])} {_won(d['price'])} "
            f"(-{d['discount']}%){plus}{_ends(d)}{extra}")


def _over_limit(d: dict, limits: dict) -> bool:
    t = d["title"].lower()
    for kw, limit in limits.items():
        if kw.lower() in t and limit and d.get("price") and d["price"] > limit:
            return True
    return False


def build(state: dict, cfg: dict, now: datetime) -> tuple[list[str], dict]:
    """(보낼 묶음들, 새 기록). 묶음은 제목과 줄들."""
    sent_hd = dict(state.get("hotdeals", {}))
    sent_games = dict(state.get("games", {}))
    sent_news = dict(state.get("news", {}))
    today = now.date().isoformat()
    sections = []

    # 핫딜
    hd = load_json(DATA / "hotdeals.json", {}).get("items", [])
    recent = (now - timedelta(days=2)).isoformat(timespec="minutes")
    limits = cfg.get("device_price_limits", {}) or {}
    dev, game = [], []
    for d in hd:
        if d["id"] in sent_hd or d["first_seen"] < recent:
            continue
        sent_hd[d["id"]] = today
        if d["kind"] == "device" and _over_limit(d, limits):
            continue
        (dev if d["kind"] == "device" else game).append(d)
    for title, items in (("🕹 기기 핫딜", dev), ("💿 게임 핫딜", game)):
        if items:
            lines = [f"• [{_e(d['source'])}] {_a(d['title'], d['url'])}" for d in items[:HOTDEAL_MAX]]
            if len(items) > HOTDEAL_MAX:
                lines.append(f"  외 {len(items) - HOTDEAL_MAX}건")
            sections.append(f"<b>{title}</b>\n" + "\n".join(lines))

    # 게임 할인
    games = load_json(DATA / "games.json", {})
    failed = set(games.get("errors", []))
    on_sale = {}
    for key in ("nintendo", "playstation"):
        for d in games.get(key, []):
            on_sale[d["id"]] = d

    def fresh(d):  # 아직 안 보냈거나, 보낸 뒤 더 싸졌으면
        return d["id"] not in sent_games or d["price"] < sent_games[d["id"]]

    wish = [d for d in on_sale.values() if d.get("wish") and fresh(d)]
    lows = [d for d in on_sale.values() if d.get("new_low") and not d.get("wish") and fresh(d)]
    min_disc = int(cfg.get("min_discount", 60))
    min_regular = int(cfg.get("big_discount_min_regular", 20000))
    big = [d for d in on_sale.values()
           if d["discount"] >= min_disc and d["regular"] >= min_regular and d.get("type", "") in GAME_TYPES
           and not d.get("plus") and not d.get("wish") and not d.get("new_low") and d["id"] not in sent_games]
    # 1,000원짜리 소품이 위를 덮지 않게, 아끼는 금액이 큰 순 (정가 높은 대작이 먼저)
    big.sort(key=lambda d: -(d["regular"] - d["price"]))
    big_max = int(cfg.get("big_discount_notify_max", LIST_MAX))

    if wish:
        sections.append("<b>🎯 위시리스트 할인</b>\n" + "\n".join(_game_line(d) for d in wish[:LIST_MAX]))
    if lows:
        lows.sort(key=lambda d: (d["price"] - d["prev_low"]))
        lines = [_game_line(d, f" ← 이전 최저 {_won(d['prev_low'])}") for d in lows[:LIST_MAX]]
        if len(lows) > LIST_MAX:
            lines.append(f"  외 {len(lows) - LIST_MAX}개")
        sections.append("<b>📉 새 최저가</b>\n" + "\n".join(lines))
    if big:
        lines = [_game_line(d) for d in big[:big_max]]
        if len(big) > big_max:
            lines.append(f"  외 {len(big) - big_max}개 (페이지에서 보기)")
        sections.append(f"<b>🔥 새로 {min_disc}% 이상 할인</b>\n" + "\n".join(lines))
    for d in wish + lows + big:
        sent_games[d["id"]] = d["price"]

    # 할인이 끝난 게임은 기록에서 지운다 (다음 할인 때 다시 알림). 수집이 실패한 스토어는 건드리지 않는다
    prefix_ok = tuple(p for p, label in (("ns:", "닌텐도"), ("ps:", "PlayStation")) if label not in failed)
    sent_games = {k: v for k, v in sent_games.items() if k in on_sale or not k.startswith(prefix_ok or ("-",))}

    # PS 블로그
    news = [d for d in load_json(DATA / "news.json", {}).get("items", []) if d["id"] not in sent_news]
    if news:
        sections.append("<b>📰 할인 소식</b>\n" + "\n".join(f"• [{_e(d['source'])}] {_a(d['title'], d['url'])}" for d in news[:5]))
    for d in news:
        sent_news[d["id"]] = today

    keep = (now - timedelta(days=30)).date().isoformat()
    new_state = {
        "saved_at": now.isoformat(timespec="minutes"),
        "hotdeals": {k: v for k, v in sent_hd.items() if v >= keep},
        "news": {k: v for k, v in sent_news.items() if v >= keep},
        "games": sent_games,
    }
    if not sections:
        return [], new_state
    part = "오전" if now.hour < 15 else "저녁"
    head = f"🎮 <b>콘솔 할인 브리핑</b> · {now.month}/{now.day}({WEEK[now.weekday()]}) {part}"
    if failed:
        head += f"\n⚠️ 이번 수집 실패: {', '.join(sorted(failed))}"
    foot = f'\n\n{_a("전체 목록 보기", SITE)}'
    return _split(head, sections, foot), new_state


def _split(head: str, sections: list[str], foot: str) -> list[str]:
    msgs, cur = [], head
    for s in sections:
        if len(cur) + len(s) + 2 > TEXT_MAX:
            msgs.append(cur)
            cur = s
        else:
            cur += "\n\n" + s
    msgs.append(cur + foot)
    return msgs


def send(text: str, token: str, chat: str) -> None:
    body = urllib.parse.urlencode({"chat_id": chat, "text": text, "parse_mode": "HTML",
                                   "disable_web_page_preview": "true"}).encode()
    req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage", data=body)
    with urllib.request.urlopen(req, timeout=30) as r:
        res = json.loads(r.read())
    if not res.get("ok"):
        raise RuntimeError(res.get("description"))


def run() -> int:
    dry = "--dry-run" in sys.argv or os.environ.get("DRY_RUN") == "1"
    token, chat = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if not (token and chat):
        print("텔레그램 설정(TELEGRAM_BOT_TOKEN·TELEGRAM_CHAT_ID)이 없어 보내지 않고 출력만 합니다")
        dry = True
    msgs, new_state = build(load_json(SENT, {}), load_config(), now_kst())
    if not msgs:
        print("보낼 것 없음")
    for m in msgs:
        if dry:
            print(m, "\n" + "-" * 40)
        else:
            send(m, token, chat)
    if msgs:
        print(f"{'(미발송) ' if dry else ''}메시지 {len(msgs)}통")
    if not dry or not (token and chat):
        # 설정이 없을 때도 기록은 남긴다: 나중에 봇을 연결했을 때 지난 것이 한꺼번에 쏟아지지 않게
        save_json(SENT, new_state)
    return 0


if __name__ == "__main__":
    sys.exit(run())
