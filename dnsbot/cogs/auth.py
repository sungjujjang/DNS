from __future__ import annotations

import logging
from typing import Any

import discord
from discord import app_commands
from discord.ext import commands

from dnsbot import embeds
from dnsbot.dms.errors import DmsError, friendly

log = logging.getLogger(__name__)


class LoginModal(discord.ui.Modal, title="DMS 로그인"):
    account_id = discord.ui.TextInput(
        label="아이디",
        placeholder="DMS 로그인 아이디",
        max_length=50,
        required=True,
    )
    password = discord.ui.TextInput(
        label="비밀번호",
        placeholder="DMS 비밀번호",
        style=discord.TextStyle.short,
        min_length=1,
        max_length=100,
        required=True,
    )

    def __init__(self, bot: Any) -> None:
        super().__init__(timeout=300)
        self.bot = bot

    async def on_submit(self, interaction: discord.Interaction) -> None:
        account_id = str(self.account_id).strip()
        password = str(self.password)
        await interaction.response.defer(ephemeral=True)

        try:
            profile = await self.bot.dms.login_and_save(
                str(interaction.user.id), account_id, password
            )
        except DmsError as exc:
            embed = embeds.failure("로그인에 실패했어요", friendly(exc))
            await interaction.followup.send(embed=embed, ephemeral=True)
            return
        except Exception:
            log.exception("로그인 중 예기치 않은 오류 (user=%s)", interaction.user.id)
            embed = embeds.failure("로그인에 실패했어요", "잠시 후 다시 시도해주세요.")
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        name = profile.get("name") or account_id
        gcn = profile.get("gcn") or ""
        embed = embeds.success(
            "로그인 완료",
            f"{name} ({gcn}학번) 님으로 로그인했어요.\n"
            "아이디와 비밀번호는 암호화해 저장되며, 세션이 만료되면 자동으로 다시 로그인해요.",
        )
        image = profile.get("profile_image_url")
        if isinstance(image, str) and image.startswith("http"):
            embed.set_thumbnail(url=image)
        await interaction.followup.send(embed=embed, ephemeral=True)

    async def on_error(
        self, interaction: discord.Interaction, error: Exception
    ) -> None:  # pragma: no cover
        log.exception("로그인 모달 오류", exc_info=error)
        if interaction.response.is_done():
            await interaction.followup.send(
                embed=embeds.failure("처리하지 못했어요", "잠시 후 다시 시도해주세요."),
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                embed=embeds.failure("처리하지 못했어요", "잠시 후 다시 시도해주세요."),
                ephemeral=True,
            )


class Auth(commands.Cog):
    def __init__(self, bot: Any) -> None:
        self.bot = bot

    @app_commands.command(name="login", description="DMS 계정으로 로그인합니다")
    async def login(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(LoginModal(self.bot))

    @app_commands.command(
        name="logout", description="저장된 계정 정보와 세션을 삭제합니다"
    )
    async def logout(self, interaction: discord.Interaction) -> None:
        removed = await self.bot.db.get_user(str(interaction.user.id))
        if removed is None:
            embed = embeds.notice("로그인되지 않았어요", "이미 로그인 상태가 아니에요.")
        else:
            await self.bot.db.delete_user(str(interaction.user.id))
            embed = embeds.success(
                "로그아웃했어요", "저장된 계정 정보와 세션을 모두 삭제했어요."
            )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(
        name="profile", description="내 정보(상벌점, 학번, 프로필)를 확인합니다"
    )
    async def profile(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        profile = await self.bot.dms.get_profile(str(interaction.user.id))
        await interaction.followup.send(
            embed=embeds.profile_embed(profile), ephemeral=True
        )

    @app_commands.command(name="help", description="DNS 봇 사용법을 보여줍니다")
    async def help_command(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message(
            embed=embeds.help_embed(), ephemeral=True
        )


async def setup(bot: Any) -> None:
    await bot.add_cog(Auth(bot))
