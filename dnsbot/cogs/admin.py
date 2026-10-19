from __future__ import annotations

import logging
from typing import Any

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


async def setup(bot: Any) -> None:
    await bot.add_cog(Admin(bot))
