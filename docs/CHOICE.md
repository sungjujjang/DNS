# 기술 결정 (CHOICE.md)

구현하면서 기술적으로 결정한 내용을 기록해요.

## 스택과 구조

| 항목 | 결정 | 이유 |
| --- | --- | --- |
| 프레임워크 | `discord.py` 2.7.1 | PLAN 요구사항. 슬래시 커맨드/모달/뷰/자동완성 모두 내장 |
| 패키지 이름 | `dnsbot` | `dns`는 표준/외부 패키지와 흔히 충돌해서 회피 |
| 실행 방법 | `python -m dnsbot` | 진입점이 하나(`dnsbot/__main__.py`)라 배포가 단순함 |
| DB | SQLite + `aiosqlite` | 단일 파일, WAL 모드. 봇은 한 대라 동시성은 충분 |
| HTTP | `httpx.AsyncClient` | 타임아웃/비동기가 깔끔해서 |
| 개인정보 암호화 | `cryptography.Fernet` | DB 파일이 유출돼도 아이디/비밀번호가 평문으로 안 남음 |
| 설정 | `.env` + `python-dotenv` | `dnsbot/config.py` 한 곳에서만 읽음 |

## 슬래시 커맨드 네이밍

- 명령어/옵션 **이름은 영문 ASCII**, 설명만 한국어.
  - Discord는 명령어 이름에 한글을 허용하지만 옵션·선택지 이름의 다국어 처리가
    까다롭고 등록 실패 리스크가 있어 영문으로 통일했어요.
- 커맨드 프리픽스는 `commands.when_mentioned`로 두고, 실제로는 전부 슬래시로만 써요(PLAN 규칙).

## DMS API 대응

- 요청 바디는 **snake_case**로 보냅니다. (`account_id`, `teacher_id`, `start_date` …)
  - 로그인에 camelCase를 쓰면 `401 SECURITY-401-1`이 나요.
- 응답도 `access_token`, `start_date` 등 snake_case라 그대로 파싱해요.
- 토큰 만료 시각은 JWT 헤더/페이로드의 `exp`로 계산해요. `*_expired_at` 문자열은 보조 수단.
  - access 약 1시간, refresh 약 2주.
  - API가 `PUT /auth/reissue` + `refresh-token` 헤더로 **refresh를 회전시키지 않아**(같은 RT 재사용 가능)
    RT는 저장해두고 쓰다가, RT도 죽으면 저장된 아이디/비밀번호로 자동 재로그인해요.
- 이중 방어로 한 번 더 붙어요: 요청이 `401`이 나면 강제 refresh 후 **1회 재시도**.
- 요청마다 사용자별 `asyncio.Lock`을 걸어 동시 refresh가 경쟁하지 않게 했어요.
- `/meals/{YYYY-MM-DD}` 은 요청한 날짜가 아니라 **그 달 전체 급식**을 돌려줘요.
  그래서 `meals()`는 목록을 그대로 주고, `meal_for()`가 `date`가 같은 항목만 골라요.
  항목마다 마지막 원소는 Kcal 문자열이라 급식 항목은 문자열로 필터링하지 않고 그대로 보여줘요.

## 새벽자습 신청

- 양식(saeja_templates)에는 **요일(월~목)**만 저장하고, 실제 `start_date`/`end_date`는
  신청할 때 "이번 주 / 다음 주 / 자동" 기준으로 계산해요. (`dnsbot/dates.py`)
  - `auto`: 시작 요일이 오늘 이상이면 이번 주, 이미 지났으면 다음 주.
  - 자동화는 기본이 **다음 주**예요.
- 선생님은 **드롭다운(Select)**으로 고르게 했어요. API에 선생님이 31명이라 Discord
  Select 25개 제한을 넘어서, 페이지 버튼(◀/▶)으로 25명씩 나눠 보여줘요.
- 활동 유형(5개)도 같은 폼의 Select로 골라요.
- 저장 폼은 `discord.ui.View`(180초 타임아웃)이고, 본인만 저장/취소할 수 있어요.
- 이미 `409 DAYBREAK-409-1`(이미 신청 중)이 나면 `/saeja_status` 안내로 유도해요.

## 권한/보안

- 사용자 1:1 매핑(`users.discord_id` PK), 로그인은 모달, 세션은 자동 갱신.
  개인정보 동의는 사용자가 받은 상태라 별도 동의 절차는 두지 않았어요.
- **화이트리스트 게이트**는 `CommandTree.interaction_check`에 뒀어요.
  커맨드보다 먼저 불리고, 차단하면 사용자에게 임베드로 알려준 뒤 False를 반환해요.
  - 자동완성 상호작용에는 메시지를 쓸 수 없어 **빈 선택지만** 돌려줘요.
- **관리자 전용 커맨드**는 `Cog.interaction_check`에 뒀어요. False면 discord.py가
  `CheckFailure`를 던지고, 전역 `tree.on_error`가 관리자 안내 임베드를 보내는 구조라
  권한 검사 로직이 한 곳에만 있어요.
- 마스터 관리자(`DNS_MASTER_ADMIN_ID`)만 `/admin_remove`를 쓸 수 있어요.
- 오류는 `DmsError`/`AuthRequired`/`CheckFailure`/기타 4가지로만 나눠서
  사용자 문구(`dnsbot/dms/errors.py`)로 치환해요.

## 시간

- 서버 시각 기준이 아니라 **`Asia/Seoul`(zoneinfo)** 로만 계산해요.
  급식 알림(`alert_time <= now`)과 자동화 실행 시각이 KST 기준이어야 해요.
- 자동화는 `last_run_key = YYYY-MM-DD`로 하루에 한 번만 돌게 해요.
  (`run_time`이 이미 지난 요일에 설정하면 오늘은 건너뛰게 초기값을 넣어둬요.)
- 루프는 20초/30초 주기로 돌리고, 재시작했을 때 놓친 실행은 그 시각 이후에 붙잡아요.

## 명시적 선택지

- 급식/양식 조회는 전부 **ephemeral**로 답해요(개인 정보라 공개 채널에 안 남김).
- 자동 신청 결과와 급식 알림은 **DM**으로 보내요(PLAN 요구사항).
- 글로벌 커맨드 동기화는 반영까지 최대 1시간이 걸려서, `DNS_GUILD_ID`가 있으면
  길드 커맨드만 동기화해 즉시 반영돼요(개발용).
