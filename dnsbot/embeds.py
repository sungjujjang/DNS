from __future__ import annotations

from datetime import datetime
from typing import Any

import discord

NAVY = 0x243B55
GREEN = 0x2E9E6B
RED = 0xD64545
AMBER = 0xE0A100
GREY = 0x6B7280

WEEKDAY_KO = ["월", "화", "수", "목", "금", "토", "일"]

APPLICATION_STATUS = {
    "PENDING": ("신청 대기 중", AMBER),
    "FIRST_APPROVED": ("1차 승인", AMBER),
    "SECOND_APPROVED": ("승인 완료", GREEN),
    "APPROVED": ("승인 완료", GREEN),
    "FIRST_REJECTED": ("1차 반려", RED),
    "SECOND_REJECTED": ("반려", RED),
    "REJECTED": ("반려", RED),
    "EXPIRED": ("기간 만료", GREY),
    "CANCELED": ("취소됨", GREY),
    "CANCELLED": ("취소됨", GREY),
}


def base(
    title: str,
    *,
    description: str | None = None,
    color: int = NAVY,
) -> discord.Embed:
    embed = discord.Embed(title=title, description=description, color=color)
    embed.set_footer(text="DNS · 대덕소프트웨어마이스터고등학교")
    embed.timestamp = discord.utils.utcnow()
    return embed


def success(title: str, description: str | None = None) -> discord.Embed:
    return base(title, description=description, color=GREEN)


def failure(title: str, description: str | None = None) -> discord.Embed:
    return base(title, description=description, color=RED)


def notice(title: str, description: str | None = None) -> discord.Embed:
    return base(title, description=description, color=AMBER)


def format_range(start: str | None, end: str | None) -> str:
    if not start and not end:
        return "기간 정보 없음"
    if start and end:
        return f"{start} ~ {end}" if start != end else start
    return start or end or "기간 정보 없음"


def profile_embed(profile: dict[str, Any]) -> discord.Embed:
    name = profile.get("name") or "이름 없음"
    gcn = profile.get("gcn") or ""
    embed = base(f"{name} · {gcn}학번")
    embed.add_field(name="학교", value=profile.get("school_name") or "-", inline=True)
    embed.add_field(name="학번", value=f"{gcn}학번" if gcn else "-", inline=True)
    embed.add_field(
        name="성별",
        value={"MALE": "남", "FEMALE": "여"}.get(profile.get("sex"), "-"),
        inline=True,
    )
    embed.add_field(name="가점", value=str(profile.get("bonus_point", 0)), inline=True)
    embed.add_field(name="감점", value=str(profile.get("minus_point", 0)), inline=True)
    embed.add_field(
        name="총점",
        value=str(
            int(profile.get("bonus_point", 0)) - int(profile.get("minus_point", 0))
        ),
        inline=True,
    )
    embed.add_field(name="한 줄", value=profile.get("phrase") or "-", inline=False)

    image = profile.get("profile_image_url")
    if image and isinstance(image, str) and image.startswith("http"):
        embed.set_thumbnail(url=image)
    return embed


def application_embed(
    status: dict[str, Any] | None, *, fallback_title: str = "내 새벽자습"
) -> discord.Embed:
    if not status:
        embed = base(
            fallback_title, description="신청 중인 새벽자습이 없어요.", color=GREY
        )
        return embed

    raw = str(status.get("status") or "")
    label, color = APPLICATION_STATUS.get(raw, (raw or "알 수 없음", GREY))
    embed = base(fallback_title, color=color)
    embed.add_field(name="상태", value=label, inline=True)
    embed.add_field(
        name="기간",
        value=format_range(status.get("start_date"), status.get("end_date")),
        inline=True,
    )
    embed.set_footer(
        text=f"원본 코드: {raw or '-'} · DNS · 대덕소프트웨어마이스터고등학교"
    )
    return embed


MEAL_SECTIONS = (("breakfast", "아침"), ("lunch", "점심"), ("dinner", "저녁"))


def _menu(items: Any) -> str:
    if not isinstance(items, list) or not items:
        return "급식이 없습니다."
    lines = [str(item) for item in items]
    if len(lines) == 1 and lines[0] == "급식이 없습니다.":
        return "급식이 없습니다."
    return "\n".join(lines)


def meal_embed(
    entry: dict[str, Any] | None, target: str, *, title: str | None = None
) -> discord.Embed:
    try:
        parsed = datetime.strptime(target, "%Y-%m-%d")
        day_label = f"{parsed.year}년 {parsed.month}월 {parsed.day}일 ({WEEKDAY_KO[parsed.weekday()]})"
    except ValueError:
        day_label = target

    if entry is None:
        return base(
            f"{day_label} 급식",
            description="해당 날짜의 급식 정보가 없어요.",
            color=GREY,
        )

    embed = base(title or f"{day_label} 급식")
    for key, label in MEAL_SECTIONS:
        embed.add_field(name=label, value=_menu(entry.get(key)) or "-", inline=False)
    return embed


def template_embed(template: dict[str, Any]) -> discord.Embed:
    embed = base(f"양식 · {template.get('name')}")
    embed.add_field(
        name="선생님", value=template.get("teacher_name") or "-", inline=True
    )
    embed.add_field(name="유형", value=template.get("type_name") or "-", inline=True)
    embed.add_field(
        name="기간",
        value=f"매주 {WEEKDAY_KO[int(template.get('start_weekday', 0))]}요일 ~ "
        f"{WEEKDAY_KO[int(template.get('end_weekday', 3))]}요일",
        inline=False,
    )
    embed.add_field(name="사유", value=template.get("reason") or "-", inline=False)
    return embed


def automation_embed(item: dict[str, Any]) -> discord.Embed:
    embed = base(f"자동화 #{item.get('id')}")
    embed.add_field(name="양식", value=item.get("template_name") or "-", inline=True)
    embed.add_field(
        name="실행",
        value=f"{WEEKDAY_KO[int(item.get('run_weekday', 0))]}요일 {item.get('run_time')}",
        inline=True,
    )
    embed.add_field(
        name="대상 주",
        value="이번 주" if int(item.get("week_offset", 1)) == 0 else "다음 주",
        inline=True,
    )
    embed.add_field(
        name="선생님 · 유형",
        value=f"{item.get('teacher_name') or '-'} / {item.get('type_name') or '-'}",
        inline=False,
    )
    return embed


def help_embed() -> discord.Embed:
    embed = base(
        "DNS 사용법",
        description="디스코드에서 DMS의 주요 기능을 바로 쓸 수 있는 봇이에요.",
    )
    embed.add_field(
        name="계정",
        value="`/login` 로그인 · `/logout` 로그아웃 · `/profile` 내정보",
        inline=False,
    )
    embed.add_field(
        name="새벽자습",
        value=(
            "`/saeja_template_save` 양식 저장 · `/saeja_template_list` 양식 목록\n"
            "`/saeja_apply` 신청 · `/saeja_status` 상태 확인\n"
            "`/saeja_auto_set` 자동 신청 · `/saeja_auto_list` · `/saeja_auto_delete`"
        ),
        inline=False,
    )
    embed.add_field(
        name="급식",
        value="`/meal` 급식 조회 · `/meal_alert_set` 매일 알림 · `/meal_alert_off` 알림 해제",
        inline=False,
    )
    embed.add_field(
        name="관리자",
        value=(
            "`/whitelist_toggle` 화이트리스트 켜기/끄기 · "
            "`/whitelist_add` · `/whitelist_remove` · `/whitelist_list`\n"
            "`/admin_add` 관리자 추가 · `/admin_remove` 관리자 삭제 · `/admin_list`"
        ),
        inline=False,
    )
    return embed
