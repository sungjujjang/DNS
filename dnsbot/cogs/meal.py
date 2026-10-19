from __future__ import annotations

import logging
import re
from datetime import date
from typing import Any

import discord
from discord import app_commands
from discord.ext import commands

from dnsbot import embeds
from dnsbot.dates import now_kst

log = logging.getLogger(__name__)

TIME_RE = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")
DATE_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")


class Meal(commands.Cog):
    def __init__(self, bot: Any) -> None:
        self.bot = bot

    @staticmethod
    def _normalize_time(raw: str) -> str | None:
        match = TIME_RE.match((raw or "").strip())
        if not match:
            return None
        return f"{int(match.group(1)):02d}:{match.group(2)}"

    @staticmethod
    def _parse_date(raw: str | None) -> str:
        text = (raw or "").strip()
        if not text:
            return now_kst().date().isoformat()
        match = DATE_RE.match(text)
        if not match:
            raise ValueError
        parsed = date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        return parsed.isoformat()

    @app_commands.command(
        name="meal", description="오늘 또는 지정한 날짜의 급식을 확인합니다"
    )
    @app_commands.describe(target="조회할 날짜 (YYYY-MM-DD), 생략 시 오늘")
    async def meal(
        self, interaction: discord.Interaction, target: str | None = None
    ) -> None:
        try:
            day = self._parse_date(target)
        except ValueError:
            await interaction.response.send_message(
                embed=embeds.failure(
                    "날짜 형식이 올바르지 않아요", "`2026-10-19`처럼 입력해주세요."
                ),
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)
        entry = await self.bot.dms.meal_for(str(interaction.user.id), day)
        await interaction.followup.send(
            embed=embeds.meal_embed(entry, day), ephemeral=True
        )

    @app_commands.command(
        name="meal_alert_set",
        description="매일 정해진 시각에 급식 알림을 DM으로 받습니다",
    )
    @app_commands.describe(alert_time="알림 시각 (HH:MM, 예: 08:00)")
    async def alert_set(
        self, interaction: discord.Interaction, alert_time: str
    ) -> None:
        normalized = self._normalize_time(alert_time)
        if normalized is None:
            await interaction.response.send_message(
                embed=embeds.failure(
                    "시각 형식이 올바르지 않아요",
                    "`08:00`처럼 `HH:MM`으로 입력해주세요.",
                ),
                ephemeral=True,
            )
            return

        await self.bot.db.set_meal_alert(str(interaction.user.id), normalized, None)
        embed = embeds.success(
            "급식 알림을 켰어요",
            f"매일 {normalized}에 그날 급식을 DM으로 보내드려요.\n"
            "`/meal_alert_off`로 해제할 수 있어요.",
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="meal_alert_off", description="급식 알림을 끕니다")
    async def alert_off(self, interaction: discord.Interaction) -> None:
        removed = await self.bot.db.clear_meal_alert(str(interaction.user.id))
        if removed:
            embed = embeds.success("급식 알림을 껐어요.")
        else:
            embed = embeds.notice("알림이 설정되어 있지 않았어요.")
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: Any) -> None:
    await bot.add_cog(Meal(bot))
