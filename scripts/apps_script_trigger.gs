// Google Apps Script (script.google.com) 에 붙여 넣을 코드. 이 파일은 사본이다.
// GitHub Actions 예약이 6시간쯤 늦게 돌아서(2026-11-05~09), 게임 할인 수집을 여기서 시각에 맞춰 건다.
// 수집 작업(collect.yml) 안에서 텔레그램 브리핑까지 이어서 보낸다.
//
// 설정 (한 번)
// 1. script.google.com → 새 프로젝트 → 이 코드를 붙여 넣기
// 2. 프로젝트 설정(톱니바퀴) → 시간대를 '(GMT+09:00) 서울'로
// 3. 프로젝트 설정 → 스크립트 속성 → GITHUB_TOKEN 추가
//    값: GitHub fine-grained 토큰 (저장소 theddack/console-game-deals 만, 권한 Actions: Read and write)
//    항공권(icn-air-deals)용 토큰이 있으면 그 토큰의 저장소 목록에 console-game-deals 를 더해서 써도 된다
// 4. 위 함수 목록에서 setupTriggers 를 골라 한 번 실행 (구글 권한 허용)
// 실패하면 구글이 실패 알림 메일을 보낸다 (토큰 만료 등). 다시 실행해도 트리거가 겹치지 않는다
var REPO = 'theddack/console-game-deals';
var WORKFLOW = 'collect.yml';
var HOURS = [9, 19]; // KST, 각 시각 10분 전후(±15분)

function dispatchCollect() {
  var token = PropertiesService.getScriptProperties().getProperty('GITHUB_TOKEN');
  if (!token) throw new Error('스크립트 속성 GITHUB_TOKEN이 없습니다');
  var res = UrlFetchApp.fetch(
    'https://api.github.com/repos/' + REPO + '/actions/workflows/' + WORKFLOW + '/dispatches',
    {
      method: 'post',
      contentType: 'application/json',
      headers: {
        Authorization: 'Bearer ' + token,
        Accept: 'application/vnd.github+json'
      },
      payload: JSON.stringify({ ref: 'main' }),
      muteHttpExceptions: true
    }
  );
  // 성공은 204. 실패하면 오류를 던져서 구글이 실패 알림 메일을 보내게 한다
  if (res.getResponseCode() !== 204) {
    throw new Error('실행 요청 실패 ' + res.getResponseCode() + ': ' + res.getContentText());
  }
}

function setupTriggers() {
  var triggers = ScriptApp.getProjectTriggers();
  for (var i = 0; i < triggers.length; i++) {
    if (triggers[i].getHandlerFunction() === 'dispatchCollect') {
      ScriptApp.deleteTrigger(triggers[i]);
    }
  }
  for (var j = 0; j < HOURS.length; j++) {
    ScriptApp.newTrigger('dispatchCollect')
      .timeBased().atHour(HOURS[j]).nearMinute(10).everyDays(1)
      .inTimezone('Asia/Seoul')
      .create();
  }
}
