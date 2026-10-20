from __future__ import annotations

import asyncio
import logging
from typing import Any

import discord
from discord import app_commands
from discord.ext import commands

from dnsbot import embeds
from dnsbot.config import Settings
from dnsbot.db import WHITELIST_ENABLED_KEY, Database
from dnsbot.dms import AuthRequired, DmsClient, DmsError
from dnsbot.dms.errors import friendly

log = logging.getLogger(__name__)

CogList = (
    "dnsbot.cogs.auth",
    "dnsbot.cogs.saeja",
    "dnsbot.cogs.meal",
    "dnsbot.cogs.admin",
)


class DNSCommandTree(app_commands.CommandTree):
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        bot = self.client
        if not isinstance(bot, DNSBot):  # pragma: no cover
            return True
        return await bot.allow_interaction(interaction)

    async def on_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        bot = self.client
        if isinstance(bot, DNSBot) and await bot.handle_app_error(interaction, error):
            return
        await super().on_error(interaction, error)


class DNSBot(commands.Bot):
    def __init__(self, settings: Settings) -> None:
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(
            command_prefix="!",
            help_command=None,
            description="DMS 디스코드 봇 DNS",
            intents=intents,
            tree_cls=DNSCommandTree,
        )
        self.settings = settings
        self.db = Database(settings.database)
        self.dms = DmsClient(self.db, settings.api_base, settings.fernet)
        self.master_admin_id = settings.master_admin_id
        self._background_tasks: list[asyncio.Task[Any]] = []

    # ---------------- 권한 ----------------

    async def is_master(self, user_id: int) -> bool:
        return user_id == self.master_admin_id

    async def is_privileged(self, user_id: int) -> bool:
        uid = str(user_id)
        if user_id == self.master_admin_id:
            return True
        return await self.db.is_admin(uid)

    async def allow_interaction(self, interaction: discord.Interaction) -> bool:
        if await self.is_privileged(interaction.user.id):
            return True

        enabled = await self.db.get_setting(WHITELIST_ENABLED_KEY, "0")
        if enabled != "1":
            return True

        if await self.db.is_whitelisted(str(interaction.user.id)):
            return True

        if interaction.type is discord.InteractionType.autocomplete:
            # 자동완성에는 메시지를 쓸 수 없으니 빈 목록만 돌려줘요.
            await interaction.response.autocomplete([])
        else:
            embed = embeds.failure(
                "사용 권한이 없어요",
                "화이트리스트에 등록된 사용자만 봇을 사용할 수 있어요.\n"
                "사용 권한이 필요하면 관리자에게 요청해주세요.",
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
        return False

    # ---------------- 오류 처리 ----------------

    async def handle_app_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> bool:
        root: Exception = error
        if (
            isinstance(error, app_commands.CommandInvokeError)
            and error.original is not None
        ):
            root = error.original

        embed: discord.Embed
        if isinstance(root, AuthRequired):
            embed = embeds.notice("로그인이 필요해요", root.message)
        elif isinstance(root, DmsError):
            embed = embeds.failure("요청에 실패했어요", friendly(root))
        elif isinstance(error, app_commands.CheckFailure):
            embed = embeds.failure(
                "권한이 부족해요", "이 명령어는 관리자만 사용할 수 있어요."
            )
        else:
            log.error(
                "슬래시 커맨드 오류 (command=%s)",
                getattr(getattr(interaction, "command", None), "name", "-"),
                exc_info=root,
            )
            embed = embeds.failure("처리하지 못했어요", "잠시 후 다시 시도해주세요.")

        try:
            if interaction.response.is_done():
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                await interaction.response.send_message(embed=embed, ephemeral=True)
        except discord.HTTPException:  # pragma: no cover
            log.warning("오류 응답 전송 실패 (interaction=%s)", interaction.id)
        return True

    # ---------------- 수명주기 ----------------

    async def setup_hook(self) -> None:
        await self.db.connect()
        await self.dms.start()

        for extension in CogList:
            await self.load_extension(extension)
        try:
            await self.add_cog(PrefixBridge(self))
        except Exception:
            pass

        if self.settings.guild_id:
            guild = discord.Object(id=self.settings.guild_id)
            self.tree.copy_global_to(guild=guild)
            synced = await self.tree.sync(guild=guild)
            log.info(
                "길드 커맨드 %d개 동기화 (guild=%s)",
                len(synced),
                self.settings.guild_id,
            )
        else:
            synced = await self.tree.sync()
            log.info("글로벌 커맨드 %d개 동기화", len(synced))

        from dnsbot import tasks

        self._background_tasks = [
            asyncio.create_task(
                tasks.saeja_automation_loop(self), name="saeja-automation"
            ),
            asyncio.create_task(tasks.meal_alert_loop(self), name="meal-alert"),
        ]

    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot:
            return
        await self.process_commands(message)
    
    async def close(self) -> None:
        for task in self._background_tasks:
            task.cancel()
        await self.dms.close()
        await self.db.close()
        await super().close()


def create_bot(settings: Settings) -> DNSBot:
    return DNSBot(settings)


class PrefixBridge(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def _reply_slash(self, ctx, name):
        await ctx.reply(f'슬래시 명령어를 사용해주세요: `/{name}`', mention_author=False)

    @commands.command(name='help')
    async def c_help(self, ctx): await self._reply_slash(ctx, 'help')
    @commands.command(name='login')
    async def c_login(self, ctx): await self._reply_slash(ctx, 'login')
    @commands.command(name='로그인')
    async def c_login2(self, ctx): await self._reply_slash(ctx, 'login')
    @commands.command(name='logout')
    async def c_logout(self, ctx): await self._reply_slash(ctx, 'logout')
    @commands.command(name='profile')
    async def c_profile(self, ctx): await self._reply_slash(ctx, 'profile')
    @commands.command(name='내정보')
    async def c_profile2(self, ctx): await self._reply_slash(ctx, 'profile')
    @commands.command(name='meal')
    async def c_meal(self, ctx): await self._reply_slash(ctx, 'meal')
    @commands.command(name='급식')
    async def c_meal2(self, ctx): await self._reply_slash(ctx, 'meal')
    @commands.command(name='새자')
    async def c_saeja(self, ctx): await self._reply_slash(ctx, '새자 신청')
