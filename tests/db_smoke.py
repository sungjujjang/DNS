"""MySQL DB 동작 검증 (실제 DB 필요)."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault("DISCORD_TOKEN", "smoke-test-token")
os.environ.setdefault("DNS_DB_HOST", "127.0.0.1")
os.environ.setdefault("DNS_DB_PORT", "3307")
os.environ.setdefault("DNS_DB_USER", "root")
os.environ.setdefault("DNS_DB_NAME", "dns")
os.environ.setdefault("DNS_CRYPTO_KEY", "xCqjyIwDo9s95yFeSApex7t-K_2pOcoqxNLLs14f7-k=")

from dnsbot.config import load_settings
from dnsbot.crypto import encrypt
from dnsbot.db import WHITELIST_ENABLED_KEY, Database


async def exercise_db(db: Database, fernet) -> None:
    import pymysql.err

    uid = "111111111111111111"
    other = "222222222222222222"

    await db.upsert_login(
        uid,
        "test-account",
        encrypt(fernet, "password-1234"),
        {"access_token": "a1", "access_token_exp": 1.0, "refresh_token": "r1", "refresh_token_exp": 2.0},
    )
    assert (await db.get_user(uid))["account_id"] == "test-account"
    await db.update_tokens(
        uid,
        {"access_token": "a2", "access_token_exp": 3.0, "refresh_token": "r2", "refresh_token_exp": 4.0},
    )
    user = await db.get_user(uid)
    assert user["access_token"] == "a2" and user["refresh_token"] == "r2"

    template = {
        "discord_id": uid,
        "name": "주중 새자",
        "teacher_id": "fe3d5440-03f8-11f0-b6f0-bb1322270714",
        "teacher_name": "강현선",
        "type_id": "81c698c0-ee5c-46c7-a3b5-ae4a456d3093",
        "type_name": "개인 프로젝트",
        "reason": "프로젝트 마감",
        "start_weekday": 0,
        "end_weekday": 3,
    }
    template_id = await db.add_template(template)
    assert await db.get_template_by_name(uid, "주중 새자") is not None
    try:
        await db.add_template(template)
    except pymysql.err.IntegrityError:
        pass
    else:  # pragma: no cover
        raise AssertionError("같은 이름 양식이 중복 저장됐어요")

    automation_id = await db.add_automation(
        {
            "discord_id": uid,
            "template_id": template_id,
            "run_weekday": 3,
            "run_time": "06:30",
            "week_offset": 1,
            "last_run_key": None,
        }
    )
    assert len(await db.list_automations(uid)) == 1
    assert len(await db.list_automations(other)) == 0
    assert len(await db.due_automations(3, "06:30", "2026-01-01")) == 1
    assert len(await db.due_automations(3, "06:29", "2026-01-01")) == 0
    assert len(await db.due_automations(2, "09:00", "2026-01-01")) == 0
    await db.mark_automation_run(automation_id, "2026-01-01")
    assert len(await db.due_automations(3, "06:30", "2026-01-01")) == 0
    assert len(await db.due_automations(3, "06:30", "2026-01-02")) == 1

    await db.set_meal_alert(uid, "08:00", None)
    assert [r["discord_id"] for r in await db.meal_alerts_due("07:59", "2026-01-01")] == []
    assert [r["discord_id"] for r in await db.meal_alerts_due("08:00", "2026-01-01")] == [uid]
    await db.mark_meal_alert_sent(uid, "2026-01-01")
    assert await db.meal_alerts_due("08:00", "2026-01-01") == []
    assert [r["discord_id"] for r in await db.meal_alerts_due("08:00", "2026-01-02")] == [uid]
    await db.clear_meal_alert(uid) == 1
    assert await db.get_meal_alert(uid) is None

    assert await db.add_whitelist(uid, other) is True
    assert await db.add_whitelist(uid, other) is False
    assert await db.is_whitelisted(uid) is True
    assert await db.is_whitelisted(other) is False
    await db.set_setting(WHITELIST_ENABLED_KEY, "1")
    assert await db.get_setting(WHITELIST_ENABLED_KEY, "0") == "1"
    assert await db.remove_whitelist(uid) is True
    assert await db.remove_whitelist(uid) is False

    assert await db.add_admin(other, uid) is True
    assert await db.is_admin(other) is True
    assert await db.remove_admin(other) is True

    await db.set_meal_alert(uid, "08:00", None)
    assert await db.delete_template(uid, template_id) == 1
    assert await db.list_templates(uid) == []
    assert await db.list_automations(uid) == []
    await db.delete_user(uid)
    assert await db.get_user(uid) is None
    assert await db.get_meal_alert(uid) is None
    print("DB 쿼리 검증 완료")


async def main() -> None:
    settings = load_settings()
    db = Database(settings.database)
    await db.connect()
    try:
        await exercise_db(db, settings.fernet)
    finally:
        await db.close()
    print("DB SMOKE OK")


if __name__ == "__main__":
    asyncio.run(main())
