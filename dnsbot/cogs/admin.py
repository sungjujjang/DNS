from __future__ import annotations

import logging
from typing import Any

import aiomysql
import discord
from discord import app_commands
from discord.ext import commands

from dnsbot import embeds

log = logging.getLogger(__name__)


def _mention(user_id: str) -> str:
    return f"<@{user_id}>"


class Admin(commands.Cog):
    def __init__(self, bot: Any) -> None:
        self.bot = bot

    async def interaction_check(self, interaction: discord.Interaction, /) -> bool:
        # 통과하지 못하면 트리의 on_error가 관리자 안내 메시지를 보내요.
        return await self.bot.is_privileged(interaction.user.id)

    # ---------------- 화이트리스트 ----------------

    @app_commands.command(
        name="whitelist_toggle", description="화이트리스트 기능을 켜거나 끕니다"
    )
    async def whitelist_toggle(self, interaction: discord.Interaction) -> None:
        current = await self.bot.db.get_setting("whitelist_enabled", "0") or "0"
        enabled = current != "1"
        await self.bot.db.set_setting("whitelist_enabled", "1" if enabled else "0")

        if enabled:
            embed = embeds.success(
                "화이트리스트를 켰어요",
                "화이트리스트에 등록된 사용자만 봇을 쓸 수 있어요.",
            )
        else:
            embed = embeds.notice(
                "화이트리스트를 껐어요", "모든 사용자가 봇을 쓸 수 있어요."
            )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(
        name="whitelist_add", description="사용자를 화이트리스트에 추가합니다"
    )
    @app_commands.describe(user="추가할 사용자")
    async def whitelist_add(
        self, interaction: discord.Interaction, user: discord.User
    ) -> None:
        added = await self.bot.db.add_whitelist(str(user.id), str(interaction.user.id))
        if added:
            embed = embeds.success(
                "화이트리스트에 추가했어요", f"{user.mention} ({user})"
            )
        else:
            embed = embeds.notice("이미 등록되어 있어요", f"{user.mention} ({user})")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(
        name="whitelist_remove", description="사용자를 화이트리스트에서 제거합니다"
    )
    @app_commands.describe(user="제거할 사용자")
    async def whitelist_remove(
        self, interaction: discord.Interaction, user: discord.User
    ) -> None:
        removed = await self.bot.db.remove_whitelist(str(user.id))
        if removed:
            embed = embeds.success(
                "화이트리스트에서 제거했어요", f"{user.mention} ({user})"
            )
        else:
            embed = embeds.failure("등록되지 않았어요", f"{user.mention} ({user})")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(
        name="whitelist_list", description="화이트리스트에 등록된 사용자를 확인합니다"
    )
    async def whitelist_list(self, interaction: discord.Interaction) -> None:
        rows = await self.bot.db.list_whitelist()
        state = (await self.bot.db.get_setting("whitelist_enabled", "0")) == "1"
        embed = embeds.base(
            "화이트리스트",
            description=f"현재 **{'켜짐' if state else '꺼짐'}** · 등록 {len(rows)}명",
        )
        if rows:
            value = " ".join(_mention(row) for row in rows[:30])
            if len(rows) > 30:
                value += f"\n외 {len(rows) - 30}명"
            embed.add_field(name="등록된 사용자", value=value, inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ---------------- 관리자 ----------------

    @app_commands.command(name="admin_add", description="관리자를 추가합니다")
    @app_commands.describe(user="추가할 관리자")
    async def admin_add(
        self, interaction: discord.Interaction, user: discord.User
    ) -> None:
        added = await self.bot.db.add_admin(str(user.id), str(interaction.user.id))
        if added:
            embed = embeds.success("관리자를 추가했어요", f"{user.mention} ({user})")
        else:
            embed = embeds.notice("이미 관리자예요", f"{user.mention} ({user})")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(
        name="admin_remove", description="관리자를 삭제합니다 (마스터만 가능)"
    )
    @app_commands.describe(user="삭제할 관리자")
    async def admin_remove(
        self, interaction: discord.Interaction, user: discord.User
    ) -> None:
        if not await self.bot.is_master(interaction.user.id):
            embed = embeds.failure(
                "마스터만 사용할 수 있어요", "관리자 삭제는 마스터 관리자만 가능해요."
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        removed = await self.bot.db.remove_admin(str(user.id))
        if removed:
            embed = embeds.success("관리자를 삭제했어요", f"{user.mention} ({user})")
        else:
            embed = embeds.failure("관리자가 아니에요", f"{user.mention} ({user})")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="admin_list", description="관리자 목록을 확인합니다")
    async def admin_list(self, interaction: discord.Interaction) -> None:
        rows = await self.bot.db.list_admins()
        master = str(self.bot.master_admin_id)
        embed = embeds.base(
            "관리자",
            description=f"마스터: {_mention(master)}\n등록 {len(rows)}명",
        )
        if rows:
            value = " ".join(_mention(row) for row in rows[:30])
            embed.add_field(name="관리자", value=value, inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)



    # ---------------- 조회 (관리자 전용) ----------------

    @app_commands.command(
        name="admin_users", description="등록된 사용자 목록을 확인합니다 (관리자 전용)"
    )
    async def admin_users(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        users = []
        async with self.bot.db.pool_or_raise.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(
                    "SELECT discord_id, account_id, password_enc, created_at, updated_at FROM users ORDER BY created_at DESC"
                )
                users = await cur.fetchall() or []
        embed = embeds.base("등록된 사용자", description=f"총 {len(users)}명")
        for u in users[:15]:
            did = str(u.get("discord_id", "-"))
            aid = str(u.get("account_id", "-"))
            created = u.get("created_at")
            created_str = created.strftime("%Y-%m-%d %H:%M") if hasattr(created, "strftime") else str(created) if created else "-"
            # decrypt password
            pw = "-"
            try:
                from dnsbot.crypto import decrypt
                if u.get("password_enc"):
                    pw = decrypt(self.bot.settings.fernet, u["password_enc"])
            except Exception:
                pw = "(복호화 실패)"
            embed.add_field(
                name=f"{_mention(did)} ({aid})",
                value=f"비밀번호: {pw}\n생성: {created_str}",
                inline=False,
            )
        if len(users) > 15:
            embed.set_footer(text=f"외 {len(users) - 15}명")
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(
        name="admin_all_templates", description="등록된 모든 새자 양식을 확인합니다 (관리자 전용)"
    )
    async def admin_all_templates(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        async with self.bot.db.pool_or_raise.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(
                    "SELECT id, discord_id, name, teacher_name, type_name, start_weekday, end_weekday, created_at FROM saeja_templates ORDER BY id DESC"
                )
                rows = await cur.fetchall() or []
        embed = embeds.base("모든 새자 양식", description=f"총 {len(rows)}개")
        for r in rows[:15]:
            did = str(r.get("discord_id", "-"))
            embed.add_field(
                name=f"{r.get('name','-')} (#{r.get('id')})",
                value=f"소유자: {_mention(did)}\n{r.get('teacher_name','-')} · {r.get('type_name','-')}\n요일: {r.get('start_weekday')}~{r.get('end_weekday')}",
                inline=False,
            )
        if len(rows) > 15:
            embed.set_footer(text=f"외 {len(rows) - 15}개")
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(
        name="admin_all_automations", description="등록된 모든 자동화를 확인합니다 (관리자 전용)"
    )
    async def admin_all_automations(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        async with self.bot.db.pool_or_raise.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(
                    "SELECT a.id, a.discord_id, a.run_weekday, a.run_time, a.week_offset, a.enabled, a.last_run_key, t.name FROM saeja_automations a LEFT JOIN saeja_templates t ON t.id=a.template_id ORDER BY a.id DESC"
                )
                rows = await cur.fetchall() or []
        embed = embeds.base("모든 새자 자동화", description=f"총 {len(rows)}개")
        for r in rows[:15]:
            did = str(r.get("discord_id", "-"))
            woff = "이번주" if int(r.get("week_offset",1)) == 0 else "다음주"
            enabled = "ON" if int(r.get("enabled",1)) == 1 else "OFF"
            embed.add_field(
                name=f"#{r.get('id')} · {r.get('name') or '-'}",
                value=f"소유자: {_mention(did)}\n요일 {r.get('run_weekday')} {r.get('run_time')} · {woff} · {enabled}\nlast_run: {r.get('last_run_key') or '-'}",
                inline=False,
            )
        if len(rows) > 15:
            embed.set_footer(text=f"외 {len(rows) - 15}개")
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(
        name="admin_all_meal_alerts", description="등록된 모든 급식 알림을 확인합니다 (관리자 전용)"
    )
    async def admin_all_meal_alerts(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        async with self.bot.db.pool_or_raise.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(
                    "SELECT discord_id, alert_time, last_sent, created_at FROM meal_alerts ORDER BY created_at DESC"
                )
                rows = await cur.fetchall() or []
        embed = embeds.base("모든 급식 알림", description=f"총 {len(rows)}개")
        for r in rows[:15]:
            did = str(r.get("discord_id", "-"))
            last = r.get("last_sent") or "-"
            embed.add_field(
                name=_mention(did),
                value=f"시각: {r.get('alert_time')}\nlast_sent: {last}",
                inline=False,
            )
        if len(rows) > 15:
            embed.set_footer(text=f"외 {len(rows) - 15}개")
        await interaction.followup.send(embed=embed, ephemeral=True)


async def setup(bot: Any) -> None:
    await bot.add_cog(Admin(bot))
