from __future__ import annotations

import logging
import re
from typing import Any

import discord
from discord import app_commands
from discord.ext import commands

from dnsbot import embeds
from dnsbot.dates import WEEKDAY_CHOICES, WEEKDAY_KO, now_kst, resolve_week

log = logging.getLogger(__name__)

PAGE_SIZE = 25
TIME_RE = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")

WEEK_CHOICES = [
    app_commands.Choice(name="자동 (가장 가까운 주)", value="auto"),
    app_commands.Choice(name="이번 주", value="this"),
    app_commands.Choice(name="다음 주", value="next"),
]

OFFSET_CHOICES = [
    app_commands.Choice(name="이번 주", value="this"),
    app_commands.Choice(name="다음 주", value="next"),
]


# ---------------------------------------------------------------- 양식 입력 폼


class TeacherSelect(discord.ui.Select):
    def __init__(self, form: TemplateFormView) -> None:
        self.form = form
        start = form.page * PAGE_SIZE
        chunk = form.teachers[start : start + PAGE_SIZE]
        options = [
            discord.SelectOption(
                label=str(t.get("name") or "이름 없음"), value=str(t.get("id"))
            )
            for t in chunk
        ]
        page_label = f"{form.page + 1}/{form.page_count}페이지"
        super().__init__(
            placeholder=f"선생님을 선택해주세요 ({page_label})",
            options=options,
            row=0,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        self.form.teacher_id = self.values[0]
        for option in self.options:
            if option.value == self.values[0]:
                self.form.teacher_name = option.label
                break
        await self.form.refresh(interaction)


class TypeSelect(discord.ui.Select):
    def __init__(self, form: TemplateFormView) -> None:
        self.form = form
        options = [
            discord.SelectOption(
                label=str(t.get("name") or "이름 없음"), value=str(t.get("id"))
            )
            for t in form.types
        ]
        super().__init__(
            placeholder="활동 유형을 선택해주세요",
            options=options,
            row=1,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        self.form.type_id = self.values[0]
        for option in self.options:
            if option.value == self.values[0]:
                self.form.type_name = option.label
                break
        await self.form.refresh(interaction)


class PrevPage(discord.ui.Button):
    def __init__(self, form: TemplateFormView) -> None:
        super().__init__(
            label="이전",
            emoji="◀",
            style=discord.ButtonStyle.secondary,
            row=2,
            disabled=form.page <= 0,
        )
        self.form = form

    async def callback(self, interaction: discord.Interaction) -> None:
        self.form.page = max(0, self.form.page - 1)
        self.form.teacher_id = None
        self.form.teacher_name = None
        await self.form.refresh(interaction)


class NextPage(discord.ui.Button):
    def __init__(self, form: TemplateFormView) -> None:
        super().__init__(
            label="다음",
            emoji="▶",
            style=discord.ButtonStyle.secondary,
            row=2,
            disabled=form.page >= form.page_count - 1,
        )
        self.form = form

    async def callback(self, interaction: discord.Interaction) -> None:
        self.form.page = min(self.form.page_count - 1, self.form.page + 1)
        self.form.teacher_id = None
        self.form.teacher_name = None
        await self.form.refresh(interaction)


class SaveButton(discord.ui.Button):
    def __init__(self, form: TemplateFormView) -> None:
        super().__init__(
            label="저장",
            style=discord.ButtonStyle.success,
            row=2,
            disabled=not (form.teacher_id and form.type_id),
        )
        self.form = form

    async def callback(self, interaction: discord.Interaction) -> None:
        await self.form.save(interaction)


class CancelButton(discord.ui.Button):
    def __init__(self, form: TemplateFormView) -> None:
        super().__init__(label="취소", style=discord.ButtonStyle.danger, row=2)
        self.form = form

    async def callback(self, interaction: discord.Interaction) -> None:
        await self.form.cancel(interaction)


class TemplateFormView(discord.ui.View):
    """선생님/유형을 드롭다운으로 고르고 저장하는 양식 입력 폼이에요."""

    def __init__(
        self,
        bot: Any,
        *,
        owner_id: int,
        draft: dict[str, Any],
        teachers: list[dict[str, Any]],
        types: list[dict[str, Any]],
    ) -> None:
        super().__init__(timeout=180.0)
        self.bot = bot
        self.owner_id = owner_id
        self.draft = draft
        self.teachers = teachers
        self.types = types
        self.page = 0
        self.page_count = max(1, (len(teachers) + PAGE_SIZE - 1) // PAGE_SIZE)
        self.teacher_id: str | None = None
        self.teacher_name: str | None = None
        self.type_id: str | None = None
        self.type_name: str | None = None
        self.message: discord.Message | None = None
        self._render()

    def _render(self) -> None:
        self.clear_items()
        if not self.teachers:
            return
        self.add_item(TeacherSelect(self))
        if self.types:
            self.add_item(TypeSelect(self))
        if self.page_count > 1:
            self.add_item(PrevPage(self))
            self.add_item(NextPage(self))
        self.add_item(SaveButton(self))
        self.add_item(CancelButton(self))

    def owned_by(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.owner_id

    async def refresh(self, interaction: discord.Interaction) -> None:
        self._render()
        await interaction.response.edit_message(view=self)

    async def save(self, interaction: discord.Interaction) -> None:
        if not self.owned_by(interaction):
            await interaction.response.send_message(
                embed=embeds.failure("본인의 폼만 사용할 수 있어요."), ephemeral=True
            )
            return
        if not self.teacher_id or not self.type_id:
            await interaction.response.send_message(
                embed=embeds.failure("선생님과 활동 유형을 모두 선택해주세요."),
                ephemeral=True,
            )
            return

        discord_id = str(interaction.user.id)
        name = self.draft["name"]
        existing = await self.bot.db.get_template_by_name(discord_id, name)
        if existing is not None:
            embed = embeds.failure(
                "이미 같은 이름의 양식이 있어요",
                f"**{name}** 양식은 이미 저장되어 있어요.",
            )
            await interaction.response.edit_message(embed=embed, view=None)
            self.stop()
            return

        payload = {
            "discord_id": discord_id,
            "name": name,
            "teacher_id": self.teacher_id,
            "teacher_name": self.teacher_name or "-",
            "type_id": self.type_id,
            "type_name": self.type_name or "-",
            "reason": self.draft["reason"],
            "start_weekday": self.draft["start_weekday"],
            "end_weekday": self.draft["end_weekday"],
        }
        template_id = await self.bot.db.add_template(payload)
        row = await self.bot.db.get_template(discord_id, template_id)

        embed = embeds.template_embed(row or payload)
        embed.title = f"양식 저장완료 · {name}"
        embed.colour = embeds.GREEN
        await interaction.response.edit_message(embed=embed, view=None)
        self.stop()

    async def cancel(self, interaction: discord.Interaction) -> None:
        if not self.owned_by(interaction):
            await interaction.response.send_message(
                embed=embeds.failure("본인의 폼만 사용할 수 있어요."), ephemeral=True
            )
            return
        embed = embeds.notice("입력을 취소했어요", "양식은 저장되지 않았어요.")
        await interaction.response.edit_message(embed=embed, view=None)
        self.stop()

    async def on_timeout(self) -> None:
        for item in self.children:
            item.disabled = True
        if self.message is None:
            return
        try:
            await self.message.edit(view=self)
        except discord.HTTPException:  # pragma: no cover
            pass


# ---------------------------------------------------------------- 커맨드


class Saeja(commands.Cog):
    def __init__(self, bot: Any) -> None:
        self.bot = bot

    # ---------------- 자동완성 ----------------

    async def template_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        try:
            rows = await self.bot.db.list_templates(str(interaction.user.id))
        except Exception:  # noqa: BLE001 - 자동완성은 절대 예외를 던지면 안 돼요
            return []
        needle = (current or "").strip().lower()
        hits = [r for r in rows if needle in str(r["name"]).lower()]
        return [
            app_commands.Choice(name=str(r["name"]), value=str(r["name"]))
            for r in hits[:25]
        ]

    # ---------------- 양식 ----------------

    @app_commands.command(
        name="saeja_template_save", description="새벽자습 신청 양식을 저장합니다"
    )
    @app_commands.describe(
        name="양식 이름 (같은 이름은 저장할 수 없어요)",
        start_weekday="시작 요일",
        end_weekday="종료 요일",
        reason="신청 사유",
    )
    @app_commands.choices(start_weekday=WEEKDAY_CHOICES, end_weekday=WEEKDAY_CHOICES)
    async def template_save(
        self,
        interaction: discord.Interaction,
        name: str,
        start_weekday: int,
        end_weekday: int,
        reason: str,
    ) -> None:
        name = name.strip()
        reason = reason.strip()

        if not name or len(name) > 32:
            await interaction.response.send_message(
                embed=embeds.failure("양식 이름은 1자 이상 32자 이하여야 해요."),
                ephemeral=True,
            )
            return
        if not reason or len(reason) > 300:
            await interaction.response.send_message(
                embed=embeds.failure("신청 사유는 1자 이상 300자 이하여야 해요."),
                ephemeral=True,
            )
            return
        if start_weekday > end_weekday:
            await interaction.response.send_message(
                embed=embeds.failure(
                    "요일 순서가 맞지 않아요",
                    f"시작은 {WEEKDAY_KO[start_weekday]}요일, 종료는 {WEEKDAY_KO[end_weekday]}요일이에요.",
                ),
                ephemeral=True,
            )
            return

        discord_id = str(interaction.user.id)
        if await self.bot.db.get_template_by_name(discord_id, name):
            await interaction.response.send_message(
                embed=embeds.failure(
                    "이미 같은 이름의 양식이 있어요",
                    f"**{name}** 양식은 이미 저장되어 있어요.",
                ),
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)
        teachers = await self.bot.dms.teachers(discord_id)
        types = await self.bot.dms.study_types(discord_id)

        if not teachers:
            await interaction.followup.send(
                embed=embeds.failure("선생님 목록을 불러오지 못했어요."), ephemeral=True
            )
            return
        if not types:
            await interaction.followup.send(
                embed=embeds.failure("활동 유형 목록을 불러오지 못했어요."),
                ephemeral=True,
            )
            return

        view = TemplateFormView(
            self.bot,
            owner_id=interaction.user.id,
            draft={
                "name": name,
                "reason": reason,
                "start_weekday": start_weekday,
                "end_weekday": end_weekday,
            },
            teachers=teachers,
            types=types,
        )
        embed = embeds.base(
            f"양식 작성 · {name}",
            description=(
                f"**{WEEKDAY_KO[start_weekday]}요일 ~ {WEEKDAY_KO[end_weekday]}요일**\n"
                f"사유: {reason}\n\n"
                "선생님과 활동 유형을 드롭다운으로 고른 뒤 **저장** 버튼을 눌러주세요."
            ),
        )
        message = await interaction.followup.send(
            embed=embed, view=view, ephemeral=True, wait=True
        )
        view.message = message

    @app_commands.command(
        name="saeja_template_list", description="저장한 새벽자습 신청 양식을 확인합니다"
    )
    async def template_list(self, interaction: discord.Interaction) -> None:
        rows = await self.bot.db.list_templates(str(interaction.user.id))
        if not rows:
            await interaction.response.send_message(
                embed=embeds.notice(
                    "저장된 양식이 없어요",
                    "`/saeja_template_save`로 새 양식을 만들어주세요.",
                ),
                ephemeral=True,
            )
            return

        embed = embeds.base(f"저장된 양식 {len(rows)}개")
        for row in rows[:10]:
            value = (
                f"{row['teacher_name']} · {row['type_name']} · "
                f"{WEEKDAY_KO[int(row['start_weekday'])]}~{WEEKDAY_KO[int(row['end_weekday'])]}요일\n"
                f"{str(row['reason'])[:80]}"
            )
            embed.add_field(name=str(row["name"]), value=value, inline=False)
        if len(rows) > 10:
            embed.set_footer(text=f"외 {len(rows) - 10}개 · DNS")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(
        name="saeja_template_delete", description="저장한 양식을 삭제합니다"
    )
    @app_commands.describe(name="삭제할 양식 이름")
    @app_commands.autocomplete(name=template_autocomplete)
    async def template_delete(
        self, interaction: discord.Interaction, name: str
    ) -> None:
        discord_id = str(interaction.user.id)
        row = await self.bot.db.get_template_by_name(discord_id, name)
        if row is None:
            await interaction.response.send_message(
                embed=embeds.failure(
                    "찾을 수 없는 양식이에요", f"**{name}** 양식이 없어요."
                ),
                ephemeral=True,
            )
            return
        await self.bot.db.delete_template(discord_id, int(row["id"]))
        await interaction.response.send_message(
            embed=embeds.success(
                "양식을 삭제했어요",
                f"**{name}** 양식과 연동된 자동화도 함께 삭제했어요.",
            ),
            ephemeral=True,
        )

    # ---------------- 신청 ----------------

    @app_commands.command(
        name="saeja_apply", description="저장한 양식으로 새벽자습을 신청합니다"
    )
    @app_commands.describe(name="사용할 양식 이름", week="신청할 주")
    @app_commands.choices(week=WEEK_CHOICES)
    @app_commands.autocomplete(name=template_autocomplete)
    async def apply(
        self,
        interaction: discord.Interaction,
        name: str,
        week: str = "auto",
    ) -> None:
        discord_id = str(interaction.user.id)
        row = await self.bot.db.get_template_by_name(discord_id, name)
        if row is None:
            await interaction.response.send_message(
                embed=embeds.failure(
                    "찾을 수 없는 양식이에요", f"**{name}** 양식이 없어요."
                ),
                ephemeral=True,
            )
            return

        today = now_kst().date()
        start, end = resolve_week(
            today, week, int(row["start_weekday"]), int(row["end_weekday"])
        )

        await interaction.response.defer(ephemeral=True)
        payload = {
            "teacher_id": row["teacher_id"],
            "type_id": row["type_id"],
            "reason": row["reason"],
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
        }
        await self.bot.dms.submit_application(discord_id, payload)
        status = await self.bot.dms.my_application(discord_id)

        embed = embeds.success("새벽자습을 신청했어요")
        embed.add_field(name="양식", value=str(row["name"]), inline=True)
        embed.add_field(name="선생님", value=str(row["teacher_name"]), inline=True)
        embed.add_field(name="유형", value=str(row["type_name"]), inline=True)
        embed.add_field(
            name="기간", value=f"{start.isoformat()} ~ {end.isoformat()}", inline=False
        )
        if status:
            raw = str(status.get("status") or "")
            label, color = embeds.APPLICATION_STATUS.get(
                raw, (raw or "확인 중", embeds.GREY)
            )
            embed.add_field(name="현재 상태", value=label, inline=False)
            embed.colour = color
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(
        name="saeja_status", description="내 새벽자습 신청 상태를 확인합니다"
    )
    async def status(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        status = await self.bot.dms.my_application(str(interaction.user.id))
        await interaction.followup.send(
            embed=embeds.application_embed(status), ephemeral=True
        )

    # ---------------- 자동화 ----------------

    @app_commands.command(
        name="saeja_auto_set",
        description="정해진 요일과 시각에 새벽자습을 자동으로 신청합니다",
    )
    @app_commands.describe(
        name="사용할 양식 이름",
        run_weekday="자동 신청을 실행할 요일",
        run_time="실행 시각 (HH:MM, 예: 06:30)",
        week="매주 신청할 주",
    )
    @app_commands.choices(run_weekday=WEEKDAY_CHOICES, week=OFFSET_CHOICES)
    @app_commands.autocomplete(name=template_autocomplete)
    async def auto_set(
        self,
        interaction: discord.Interaction,
        name: str,
        run_weekday: int,
        run_time: str,
        week: str = "next",
    ) -> None:
        discord_id = str(interaction.user.id)
        run_time = run_time.strip()
        match = TIME_RE.match(run_time)
        if not match:
            await interaction.response.send_message(
                embed=embeds.failure(
                    "시각 형식이 올바르지 않아요",
                    "`06:30`처럼 `HH:MM`으로 입력해주세요.",
                ),
                ephemeral=True,
            )
            return
        run_time = f"{int(match.group(1)):02d}:{match.group(2)}"

        row = await self.bot.db.get_template_by_name(discord_id, name)
        if row is None:
            await interaction.response.send_message(
                embed=embeds.failure(
                    "찾을 수 없는 양식이에요", f"**{name}** 양식이 없어요."
                ),
                ephemeral=True,
            )
            return

        existing = [
            a
            for a in await self.bot.db.list_automations(discord_id)
            if int(a["template_id"]) == int(row["id"])
        ]
        if existing:
            await interaction.response.send_message(
                embed=embeds.failure(
                    "이미 자동화가 설정되어 있어요",
                    f"**{name}** 양식은 `#{existing[0]['id']}` 자동화가 이미 있어요.\n"
                    "`/saeja_auto_list`로 확인하거나 `/saeja_auto_delete`로 삭제해주세요.",
                ),
                ephemeral=True,
            )
            return

        now = now_kst()
        today = now.date()
        last_run_key = None
        if run_weekday == today.weekday() and run_time <= now.strftime("%H:%M"):
            last_run_key = today.isoformat()

        automation_id = await self.bot.db.add_automation(
            {
                "discord_id": discord_id,
                "template_id": int(row["id"]),
                "run_weekday": run_weekday,
                "run_time": run_time,
                "week_offset": 0 if week == "this" else 1,
                "last_run_key": last_run_key,
            }
        )
        rows = await self.bot.db.list_automations(discord_id)
        item = next((a for a in rows if int(a["id"]) == automation_id), None)

        embed = embeds.success(
            "자동 신청을 설정했어요",
            f"매주 {WEEKDAY_KO[run_weekday]}요일 {run_time}에 "
            f"{'이번' if week == 'this' else '다음'} 주 신청을 자동으로 진행해요.\n"
            "결과는 DM으로 보내드려요.",
        )
        if item:
            embed.add_field(
                name="설정",
                value=f"양식 {item['template_name']} · #{item['id']}",
                inline=False,
            )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(
        name="saeja_auto_list", description="설정한 자동 신청 목록을 확인합니다"
    )
    async def auto_list(self, interaction: discord.Interaction) -> None:
        rows = await self.bot.db.list_automations(str(interaction.user.id))
        if not rows:
            await interaction.response.send_message(
                embed=embeds.notice(
                    "설정된 자동 신청이 없어요", "`/saeja_auto_set`으로 설정해주세요."
                ),
                ephemeral=True,
            )
            return
        embed = embeds.base(f"자동 신청 {len(rows)}개")
        for item in rows[:10]:
            value = (
                f"{item.get('template_name') or '-'} · {item.get('teacher_name') or '-'}\n"
                f"매주 {WEEKDAY_KO[int(item.get('run_weekday', 0))]}요일 {item.get('run_time')} · "
                f"{'이번 주' if int(item.get('week_offset', 1)) == 0 else '다음 주'}"
            )
            embed.add_field(name=f"#{item['id']}", value=value, inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(
        name="saeja_auto_delete", description="자동 신청 설정을 삭제합니다"
    )
    @app_commands.describe(automation_id="삭제할 설정 번호 (/saeja_auto_list에서 확인)")
    async def auto_delete(
        self, interaction: discord.Interaction, automation_id: int
    ) -> None:
        deleted = await self.bot.db.delete_automation(
            str(interaction.user.id), automation_id
        )
        if deleted:
            embed = embeds.success(
                "자동 신청을 삭제했어요", f"#{automation_id} 설정을 삭제했어요."
            )
        else:
            embed = embeds.failure(
                "찾을 수 없는 설정이에요", f"#{automation_id} 설정이 없어요."
            )
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: Any) -> None:
    await bot.add_cog(Saeja(bot))
