"""여러 수집기가 함께 쓰는 것: 요청, 시간, JSON 읽기·쓰기, 가격 글자 → 숫자."""

import json
import re
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
KST = timezone(timedelta(hours=9))
UA = "Mozilla/5.0 (compatible; console-game-deals/0.1; +https://github.com/theddack/console-game-deals)"
CONFIG = ROOT / "config.json"


def now_kst() -> datetime:
    return datetime.now(KST)


def fetch(url: str, headers: dict | None = None, timeout: int = 30, retries: int = 2) -> bytes:
    h = {"User-Agent": UA, "Accept-Language": "ko-KR,ko;q=0.9"}
    h.update(headers or {})
    last = None
    for i in range(retries + 1):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=timeout) as r:
                return r.read()
        except Exception as e:  # 네트워크·5xx 잠깐 실패는 몇 번 다시
            last = e
            time.sleep(2 * (i + 1))
    raise last


def load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return default


def save_json(path: Path, obj, one_per_line: bool = False, compact: bool = False) -> None:
    """one_per_line: 딕셔너리를 한 줄에 한 항목으로 써서 git 변경분이 작게 남게 한다.
    compact: 공백 없이 (페이지가 내려받는 큰 파일)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if compact:
        text = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    elif one_per_line and isinstance(obj, dict):
        lines = [f"{json.dumps(k, ensure_ascii=False)}: {json.dumps(v, ensure_ascii=False)}" for k, v in sorted(obj.items())]
        text = "{\n" + ",\n".join(lines) + "\n}\n" if lines else "{}\n"
    else:
        text = json.dumps(obj, ensure_ascii=False, indent=1) + "\n"
    path.write_text(text, encoding="utf-8")


def load_config() -> dict:
    return load_json(CONFIG, {})


_WON = re.compile(r"(\d{1,3}(?:,\d{3})+|\d{3,})\s*원")
_SLASH = re.compile(r"/\s*₩?\s*(\d{1,3}(?:,\d{3})+)(?!\s*\$)")


def won(text: str | None) -> int | None:
    """'34,350원', '₩34,350', '/ 64,800' 같은 글자에서 원화 금액. 없으면 None."""
    if not text:
        return None
    m = _WON.search(text) or _SLASH.search(text)
    if not m:
        m = re.search(r"₩\s*(\d{1,3}(?:,\d{3})+|\d+)", text)
    if not m:
        return None
    n = int(m.group(1).replace(",", ""))
    return n if n >= 100 else None
