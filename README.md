# 콘솔 할인 모아보기

PS5·닌텐도 스위치 기기 핫딜과 한국 스토어 게임 할인을 하루 두 번 모아서, 텔레그램으로 요약을 받고 페이지로 봅니다.

- 페이지: https://theddack.github.io/console-game-deals/
- 게임 할인 수집 + 텔레그램 브리핑: KST 09·19시 (Google Apps Script 가 실행을 건다, 아래 '수집 시각' 참고)
- 핫딜: 30분마다 (`.github/workflows/hotdeals.yml`, 페이지는 저장소 파일을 바로 읽음)

## 소스

| 구분 | 소스 | 가져오는 것 |
|---|---|---|
| 핫딜 | 루리웹 핫딜 RSS, 뽐뿌 RSS (아카라이브는 꺼 둠: Actions 접속 차단 + 콘솔 글이 드묾) | PS·닌텐도 관련 글의 제목·가격·원문 링크 (본문·이미지 없음) |
| 게임 | 닌텐도 게임 목록(`data/ns_catalog.json`) + 닌텐도 가격 조회 | 이름·표지·할인가·정가·종료일·기종(스위치/스위치2)·장르·발매일 |
| 게임 | PlayStation Store 한국 '모든 할인' | 이름·표지·할인가·정가·기종(PS4/PS5)·장르·VR·PS Plus 회원 할인·인기 순위·출시일 순서·방금 출시/출시 예정 |
| 소식 | PlayStation 블로그 한국어판 피드 | 세일·할인 관련 글 제목·링크 |

PlayStation Store와 닌텐도 가격 조회는 공식 공개 API가 아니어서 스토어가 바뀌면 깨질 수 있습니다. 한 곳이 실패해도 나머지는 계속 수집하고, 페이지 위쪽과 텔레그램에 실패한 곳을 표시합니다.

## 수집 시각 — Google Apps Script

GitHub Actions 예약은 6시간쯤 늦게 돌았습니다 (09:23 예약이 15:46에). 그래서 항공권 프로젝트처럼
Google Apps Script 가 KST 09·19시 10분 전후에 수집을 겁니다. 설정 방법은 `scripts/apps_script_trigger.gs` 맨 위에 있습니다.

Actions 예약(KST 10:40 · 20:40)은 비상용으로 남겨 둡니다. 최근 8시간 안에 수집했으면 아무것도 하지 않고,
Apps Script 가 멈췄을 때만 대신 수집합니다. 핫딜은 RSS 에 최근 글만 담기므로(뽐뿌는 1시간 남짓) 30분마다 따로 받습니다.

## 페이지에서 고르기

- 기종: PS5 / PS4, Switch 2 / Switch
- 장르: 각 스토어 분류 그대로 (PS 35종, 닌텐도 19종)
- 발매 시기: 닌텐도는 발매일로 최근 1년 · 1~3년 · 3년 넘음 · 발매 예정. PS 는 할인 목록에 발매일이 오지 않아 스토어 표시인 방금 출시(30일) · 출시 예정만
- 정렬: 아끼는 금액 · 인기(PS, 최근 30일 판매 상위 600) · 할인율 · 가격 · 출시일 최신/오래된 · 마감 임박(닌텐도)
- PS Plus 회원만 받는 할인은 회원가로 넣고 'PS Plus 전용'으로 표시합니다 ('PS Plus 전용 빼기'로 숨김)

## 닌텐도 게임 목록 새로 채우기 (가끔, 내 PC에서)

닌텐도 스토어 웹페이지는 GitHub Actions 같은 클라우드 서버 접속을 막습니다. 그래서 게임 목록(이름·상품번호·표지 주소)은
내 PC에서 만들어 두고, Actions 는 그 목록의 가격만 닌텐도 가격 조회로 확인합니다. 목록에 없는 게임의 새 할인은 놓치므로
한 달에 한 번쯤 새로 채웁니다 (4~5분, 기존 목록에 더해짐). 스토어 필터(대상 본체·장르)별로 한 번씩 더 훑어 기종·장르를 붙이고,
목록에 있는 발매일도 저장합니다.

```bash
python -m collector.nintendo --catalog
git add data/ns_catalog.json && git commit -m "닌텐도 게임 목록 갱신" && git push
```

표지 이미지는 저장소에 복사하지 않고 스토어 이미지 주소를 그대로 겁니다. 핫딜 글의 이미지는 가져오지 않습니다.

## 알림 기준 바꾸기 — `config.json`

- `wishlist`: 기다리는 게임 이름. 띄어쓰기·기호는 무시하고 이름 일부만 맞으면 됩니다. 예: `["티어스 오브 더 킹덤", "스텔라 블레이드"]`
- `min_discount`: '큰 할인' 알림 기준 할인율 (기본 60)
- `big_discount_min_regular`: '큰 할인' 알림은 정가가 이 금액 이상인 게임만 (기본 20000)
- `big_discount_notify_max`: '큰 할인'을 한 번에 몇 개까지 보여 줄지 (기본 10)
- `device_price_limits`: 기기 핫딜 가격 상한. 예: `{"스위치2": 450000}` → 제목에 '스위치2'가 있으면 45만원 이하일 때만 알림
- `disabled_hotdeal_sources`: 수집하지 않을 핫딜 게시판 (기본 `["아카라이브"]`)
- `console_keywords` · `device_keywords` · `game_title_keywords`: 핫딜 글을 고르는 말

## 텔레그램 연결

1. 텔레그램 @BotFather 에서 새 봇을 만들고 토큰을 받습니다.
2. 받을 대화방(개인 대화·그룹·채널)에 봇을 넣고 chat id 를 확인합니다.
3. 저장소 Settings → Secrets and variables → Actions 에 `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` 를 넣습니다.

설정이 없으면 알림은 보내지 않고 Actions 로그에만 찍습니다.

## 파일

- `collector/` 수집(`main.py`)·알림(`notify.py`)
- `data/hotdeals.json` 핫딜 최근 7일, `data/news.json` PS 블로그 소식, `data/lowest.json` 게임별 최저가 기록, `data/sent.json` 보낸 기록
- `data/games.json` 지금 할인 중인 게임 전체 — 매번 새로 만들어 페이지에만 올리고 저장소에는 커밋하지 않음
- `site/` 페이지

최저가는 이 저장소가 수집을 시작한 2026-11-04 이후의 기록입니다.

## 로컬 실행

```bash
python -m unittest discover -s tests
python -m collector.main
python -m collector.notify --dry-run
```
