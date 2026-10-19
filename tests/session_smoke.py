"""실제 DMS API로 로그인·토큰 갱신·자동 재로그인 흐름을 검증하는 테스트.

실행: DMS_TEST_ACCOUNT=... DMS_TEST_PASSWORD=... .venv/bin/python tests/session_smoke.py
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault("DISCORD_TOKEN", "session-smoke-token")
os.environ.setdefault("DNS_DB_HOST", "127.0.0.1")
os.environ.setdefault("DNS_DB_PORT", "3307")
os.environ.setdefault("DNS_DB_USER", "root")
os.environ.setdefault("DNS_DB_NAME", "dns")
os.environ.setdefault("DNS_CRYPTO_KEY", "xCqjyIwDo9s95yFeSApex7t-K_2pOcoqxNLLs14f7-k=")

from dnsbot.config import load_settings
from dnsbot.db import Database
from dnsbot.dms.client import DmsClient
from dnsbot.dms.errors import AuthRequired, DmsError

UID = "session-smoke-user"
ACCOUNT = (os.environ.get("DMS_TEST_ACCOUNT") or "").strip()
PASSWORD = (os.environ.get("DMS_TEST_PASSWORD") or "").strip()


async def main() -> None:
    if not ACCOUNT or not PASSWORD:
        raise SystemExit("DMS_TEST_ACCOUNT / DMS_TEST_PASSWORD 환경변수를 설정해주세요.")

    settings = load_settings()
    db = Database(settings.database)
    await db.connect()
    dms = DmsClient(db, settings.api_base, settings.fernet)
    await dms.start()

    try:
        profile = await dms.login_and_save(UID, ACCOUNT, PASSWORD)
        print("1. 로그인 성공:", profile.get("name"))

        user = await db.get_user(UID)
        await db.update_tokens(
            UID,
            {
                "access_token": "expired-access-token",
                "access_token_exp": time.time() - 10,
                "refresh_token": user["refresh_token"],
                "refresh_token_exp": time.time() + 60 * 60 * 24,
            },
        )
        refreshed = await dms.get_profile(UID)
        new_user = await db.get_user(UID)
        assert new_user["access_token"] != "expired-access-token", "refresh로 토큰이 바뀌지 않았어요"
        assert new_user["refresh_token"] == user["refresh_token"], "refresh 토큰이 회전됐어요"
        print("2. refresh 재발급 성공:", refreshed.get("name"), "| access 갱신됨")

        await db.update_tokens(
            UID,
            {
                "access_token": "expired-access-token",
                "access_token_exp": time.time() - 10,
                "refresh_token": "not-a-real-refresh-token",
                "refresh_token_exp": time.time() + 60 * 60 * 24,
            },
        )
        relogin = await dms.get_profile(UID)
        relogin_row = await db.get_user(UID)
        assert relogin_row["refresh_token"] != "not-a-real-refresh-token", "재로그인으로 토큰이 갱신되지 않았어요"
        print("3. 자동 재로그인 성공:", relogin.get("name"))

        try:
            await dms.get_profile("unknown-user")
        except AuthRequired as exc:
            print("4. 미로그인 감지:", exc.message)
        else:  # pragma: no cover
            raise AssertionError("미로그인 사용자가 통과했어요")

        try:
            await dms.request(UID, "GET", "/daybreaks/does-not-exist")
        except DmsError as exc:
            print("5. 오류 매핑:", exc.status, exc.code, "|", exc.message)
        else:  # pragma: no cover
            raise AssertionError("404가 오지 않았어요")
    finally:
        await dms.close()
        await db.close()

    print("SESSION SMOKE OK")


if __name__ == "__main__":
    asyncio.run(main())
