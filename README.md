# DNS · DMS 디스코드 봇

대덕소프트웨어마이스터고등학교 DMS의 주요 기능(로그인/내정보, 새벽자습 신청·자동화, 급식 조회·알림,
화이트리스트/관리자 관리)을 디스코드 슬래시 커맨드로 쓸 수 있는 봇이에요.

- 언어/라이브러리: Python 3 · [discord.py](https://discordpy.readthedocs.io/) 2.7
- DB: SQLite (`aiosqlite`) · 설정: `.env` · 개인정보: Fernet 암호화 저장

설계와 API 검증 기록은 [docs/PLAN.md](docs/PLAN.md), [docs/API.md](docs/API.md),
[docs/CHOICE.md](docs/CHOICE.md) 를 참고해주세요.

## 설치

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
```

`.env` 값:

| 키 | 설명 |
| --- | --- |
| `DISCORD_TOKEN` | **필수.** Discord Developer Portal > Bot 토큰 |
| `DNS_GUILD_ID` | (권장) 테스트 서버 ID. 설정하면 커맨드가 즉시 반영돼요 |
| `DNS_MASTER_ADMIN_ID` | 마스터 관리자 Discord ID (기본값 내장) |
| `DNS_DB_PATH` | SQLite 경로 (기본 `data/dns.db`) |
| `DNS_CRYPTO_KEY` | 개인정보 암호화 키. 비워두면 실행 시 자동 생성돼요 |
| `DNS_API_BASE` | DMS API 주소 (기본 `https://api-dms.dsmhs.kr`) |
| `DNS_LOG_LEVEL` | `DEBUG` / `INFO` / `WARNING` / `ERROR` |

Discord Developer Portal에서 **Bot** 을 만들고, `bot` 인텐트는 기본(`Intents.default()`)이면 충분해요.
슬래시 커맨드를 쓰려면 `DNS_GUILD_ID`에 테스트 서버 ID를 넣는 편이 빨라요.

## 실행

```bash
.venv/bin/python -m dnsbot
```

첫 로그에 `길드 커맨드 22개 동기화` 같은 줄이 나오면 정상이에요.

## Docker

```bash
docker build -t dns-bot .
docker run -d --name dns-bot --restart unless-stopped \
  -e DISCORD_TOKEN=<봇 토큰> \
  -e DNS_CRYPTO_KEY=<.env의 키> \
  -e DNS_GUILD_ID=<테스트 서버 ID> \
  -v dns-data:/data \
  dns-bot
```

- DB(암호화된 세션 포함)는 `/data/dns.db` 볼륨에 저장돼요. 볼륨을 지우면 `/login`부터 다시 해야 해요.
- `DNS_CRYPTO_KEY`는 꼭 넘겨주세요. 없으면 컨테이너 안에서 새 키가 만들어져서 재시작 후 저장된 세션을 못 읽어요.
- 이미지에 `tzdata`가 들어있어 `Asia/Seoul` 기준으로 동작해요.
- 그 밖의 설정(`DNS_MASTER_ADMIN_ID`, `DNS_API_BASE`, `DNS_LOG_LEVEL`)도 `-e`로 넘기면 돼요.

## 명령어

### 계정
| 명령어 | 설명 |
| --- | --- |
| `/login` | 모달로 아이디/비밀번호 입력 → 세션 저장 |
| `/logout` | 저장된 계정과 세션 삭제 |
| `/profile` | 상벌점, 학번, 프로필 사진 등 내 정보 |
| `/help` | 사용법 요약 |

### 새벽자습
| 명령어 | 설명 |
| --- | --- |
| `/saeja_template_save` | 양식 저장 (선생님·유형은 드롭다운, 요일은 월~목) |
| `/saeja_template_list` | 저장한 양식 목록 |
| `/saeja_template_delete` | 양식 삭제 (자동완성 지원) |
| `/saeja_apply` | 양식으로 신청 (이번/다음/자동 주 선택) |
| `/saeja_status` | 내 신청 상태 |
| `/saeja_auto_set` | 요일·시각 지정 자동 신청 (결과는 DM) |
| `/saeja_auto_list` | 자동 신청 목록 |
| `/saeja_auto_delete` | 자동 신청 삭제 |

### 급식
| 명령어 | 설명 |
| --- | --- |
| `/meal` | 오늘(또는 지정 날짜) 급식 — 아침·점심·저녁 |
| `/meal_alert_set` | 매일 지정 시각에 급식 DM |
| `/meal_alert_off` | 급식 알림 해제 |

### 관리자
| 명령어 | 설명 |
| --- | --- |
| `/whitelist_toggle` | 화이트리스트 켜기/끄기 |
| `/whitelist_add` · `/whitelist_remove` · `/whitelist_list` | 화이트리스트 관리 |
| `/admin_add` · `/admin_remove` · `/admin_list` | 관리자 관리 (삭제는 마스터만) |

## 프로젝트 구조

```
dnsbot/
├── __main__.py        # 실행 진입점
├── config.py          # .env 로딩, 암호화 키 관리
├── db.py              # SQLite 스키마와 쿼리
├── crypto.py          # Fernet 암호화
├── dates.py           # KST 기준 주/요일 계산
├── embeds.py          # 임베드 출력 형식
├── bot.py             # 봇 본체, 권한 게이트, 오류 처리
├── tasks.py           # 급식 알림 루프, 새자 자동화 루프
├── dms/
│   ├── client.py      # DMS API 클라이언트 (토큰 갱신 포함)
│   └── errors.py      # API 오류 → 사용자 안내 문구
└── cogs/
    ├── auth.py        # /login /logout /profile /help
    ├── saeja.py       # 양식·신청·자동화
    ├── meal.py        # 급식·알림
    └── admin.py       # 화이트리스트·관리자
```

## 확인 방법

```bash
# 문법 검사
.venv/bin/python -m compileall -q dnsbot

# 커맨드 등록/날짜 계산/임베드/DB 스모크 테스트 (네트워크 없이)
.venv/bin/python tests/smoke.py

# 실제 API로 로그인·토큰 갱신 흐름 검증 (실계정 필요, 네트워크 필요)
DMS_TEST_ACCOUNT=<아이디> DMS_TEST_PASSWORD=<비밀번호> .venv/bin/python tests/session_smoke.py

# 정적 검사 (선택)
.venv/bin/pip install ruff
.venv/bin/ruff check dnsbot tests
```
