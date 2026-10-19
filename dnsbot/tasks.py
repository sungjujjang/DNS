from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

import discord

from dnsbot import embeds
from dnsbot.dates import now_kst, resolve_week
from dnsbot.dms.errors import DmsError, friendly

if TYPE_CHECKING:
    from dnsbot.bot import DNSBot

log = logging.getLogger(__name__)

AUTOMATION_INTERVAL = 20.0
MEAL_INTERVAL = 30.0


async def _send_dm(
    bot: DNSBot,
    user_id: str,
    *,
    embed: discord.Embed | None = None,
    content: str | None = None,
) -> None:
    try:
        user = await bot.fetch_user(int(user_id))
    except (discord.NotFound, discord.HTTPException, ValueError):
        log.warning("DM 사용자를 찾지 못했어요 (user=%s)", user_id)
        return
    try:
        await user.send(content=content, embed=embed)
    except discord.Forbidden:
        log.info("DM이 차단되어 전송하지 못했어요 (user=%s)", user_id)
    except discord.HTTPException:  # pragma: no cover
        log.warning("DM 전송 실패 (user=%s)", user_id)


def automation_dates(row: dict[str, Any]) -> tuple[str, str]:
    """양식의 요일 규칙과 대상 주 설정으로 신청 기간을 계산해요.

    주간 모드 동작:
    - week_offset == 0 또는 week_mode 명시가 'this' 성격이면 'this' 주
    - 기본값은 week_offset == 1 → 'next' 주 (기존 자동화 기본값 유지)
    """
    today = now_kst().date()
    woff = int(row.get("week_offset", 1))
    week_mode = "this" if woff == 0 else "next"
    start, end = resolve_week(
        today,
        week_mode,
        int(row.get("start_weekday", 0)),
        int(row.get("end_weekday", 3)),
    )
    return start.isoformat(), end.isoformat()


async def run_automation(bot: DNSBot, row: dict[str, Any]) -> None:
    discord_id = str(row.get("owner_id") or row.get("discord_id"))
    start_date, end_date = automation_dates(row)
    try:
        await bot.dms.submit_application(
            discord_id,
            {
                "teacher_id": row["teacher_id"],
                "type_id": row["type_id"],
                "reason": row["reason"],
                "start_date": start_date,
                "end_date": end_date,
            },
        )
    except DmsError as exc:
        embed = embeds.failure(
            f"자동 신청 실패 · {row.get('template_name') or ''}", friendly(exc)
        )
        embed.add_field(name="기간", value=f"{start_date} ~ {end_date}", inline=False)
        await _send_dm(bot, discord_id, embed=embed)
        log.info("자동 신청 실패 (user=%s, code=%s)", discord_id, exc.code)
        return
    except Exception:  # pragma: no cover
        log.exception("자동 신청 중 예기치 않은 오류 (user=%s)", discord_id)
        return

    embed = embeds.success(
        f"새벽자습 자동 신청 완료 · {row.get('template_name') or ''}"
    )
    embed.add_field(
        name="선생님", value=str(row.get("teacher_name") or "-"), inline=True
    )
    embed.add_field(name="유형", value=str(row.get("type_name") or "-"), inline=True)
    embed.add_field(name="기간", value=f"{start_date} ~ {end_date}", inline=False)
    await _send_dm(bot, discord_id, embed=embed)
    log.info("자동 신청 완료 (user=%s, automation=%s)", discord_id, row.get("id"))


async def tick_automation(bot: DNSBot) -> None:
    now = now_kst()
    run_key = now.date().isoformat()
    rows = await bot.db.due_automations(now.weekday(), now.strftime("%H:%M"), run_key)
    for row in rows:
        await bot.db.mark_automation_run(int(row["id"]), run_key)
        await run_automation(bot, row)


async def tick_meal_alerts(bot: DNSBot) -> None:
    now = now_kst()
    today = now.date().isoformat()
    rows = await bot.db.meal_alerts_due(now.strftime("%H:%M"), today)
    for row in rows:
        discord_id = str(row["discord_id"])
        await bot.db.mark_meal_alert_sent(discord_id, today)
        try:
            entry = await bot.dms.meal_for(discord_id, today)
        except DmsError as exc:
            log.info("급식 알림 조회 실패 (user=%s, code=%s)", discord_id, exc.code)
            continue
        embed = embeds.meal_embed(entry, today, title=f"오늘의 급식 · {today}")
        await _send_dm(bot, discord_id, embed=embed)


async def saeja_automation_loop(bot: DNSBot) -> None:
    await bot.wait_until_ready()
    log.info("새자 자동화 루프 시작")
    while not bot.is_closed():
        try:
            await tick_automation(bot)
        except asyncio.CancelledError:  # pragma: no cover
            raise
        except Exception:
            log.exception("새자 자동화 루프 오류")
        await asyncio.sleep(AUTOMATION_INTERVAL)


async def meal_alert_loop(bot: DNSBot) -> None:
    await bot.wait_until_ready()
    log.info("급식 알림 루프 시작")
    while not bot.is_closed():
        try:
            await tick_meal_alerts(bot)
        except asyncio.CancelledError:  # pragma: no cover
            raise
        except Exception:
            log.exception("급식 알림 루프 오류")
        await asyncio.sleep(MEAL_INTERVAL)
