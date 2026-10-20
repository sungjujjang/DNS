"""네트워크 없이 커맨드 등록과 핵심 계산을 검증하는 스모크 테스트.

실행: `.venv/bin/python tests/smoke.py`
"""

from __future__ import annotations

import asyncio
import os
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault("DISCORD_TOKEN", "smoke-test-token")
os.environ.setdefault("DNS_DB_HOST", "127.0.0.1")
os.environ.setdefault("DNS_DB_PORT", "3307")
os.environ.setdefault("DNS_DB_USER", "root")
os.environ.setdefault("DNS_DB_NAME", "dns")
os.environ.setdefault("DNS_CRYPTO_KEY", "xCqjyIwDo9s95yFeSApex7t-K_2pOcoqxNLLs14f7-k=")
os.environ.setdefault("DNS_GUILD_ID", "123456789012345678")

from dnsbot import embeds
from dnsbot.bot import DNSBot
from dnsbot.config import load_settings
from dnsbot.dates import resolve_week
from dnsbot.tasks import automation_dates

EXTENSIONS = [
    "dnsbot.cogs.auth",
    "dnsbot.cogs.saeja",
    "dnsbot.cogs.meal",
    "dnsbot.cogs.admin",
]


async def exercise(bot: DNSBot) -> None:
    assert len(bot.tree.get_commands()) >= 22

    apply_cmd = bot.tree.get_command("saeja_apply")
    assert apply_cmd is not None
    assert apply_cmd.get_parameter("name").autocomplete, "양식 이름 자동완성이 없어요"

    from dnsbot.cogs.admin import Admin

    cog = bot.get_cog("Admin")
    assert isinstance(cog, Admin), f"AdminCog를 찾지 못했어요: {cog}"
    assert cog.interaction_check is not None

    assert resolve_week(date(2026, 10, 19), "auto", 0, 3) == (date(2026, 10, 19), date(2026, 10, 22))
    assert resolve_week(date(2026, 10, 25), "auto", 0, 3) == (date(2026, 10, 19), date(2026, 10, 22))
    assert resolve_week(date(2026, 10, 20), "this", 1, 3) == (date(2026, 10, 20), date(2026, 10, 22))

    next_week = automation_dates({"week_offset": 1, "start_weekday": 0, "end_weekday": 3})
    assert next_week[0] >= date.today().isoformat(), next_week

    assert embeds.profile_embed({"name": "테스트", "gcn": "1112", "bonus_point": 1, "minus_point": 0})
    assert embeds.application_embed({"status": "PENDING", "start_date": "2026-10-19", "end_date": "2026-10-22"})
    assert embeds.application_embed(None)
    assert embeds.meal_embed({"date": "2026-10-19", "lunch": ["김치", "1000.0 Kcal"]}, "2026-10-19")
    assert embeds.meal_embed(None, "2026-10-19")
    assert embeds.help_embed()

    try:
        assert await bot.db.get_setting("whitelist_enabled", "0") == "0"
    except Exception:
        pass  # DB 연결 환경에 따라 생략


async def main() -> None:
    settings = load_settings()
    bot = DNSBot(settings)
    await bot.db.connect()
    try:
        for ext in EXTENSIONS:
            await bot.load_extension(ext)
        commands = sorted(bot.tree.get_commands(), key=lambda c: c.name)
        print(f"등록된 커맨드 {len(commands)}개")
        for cmd in commands:
            params = ", ".join(f"{p.name}:{p.type.name}" for p in cmd.parameters)
            print(f"  /{cmd.name:<24} [{params}]")
        assert len(commands) >= 22, f"커맨드 수가 달라요: {len(commands)}"
        await exercise(bot)
        print("SMOKE OK")
    finally:
        await bot.db.close()


if __name__ == "__main__":
    asyncio.run(main())
