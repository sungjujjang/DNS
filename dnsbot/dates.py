from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from discord import app_commands

KST = ZoneInfo("Asia/Seoul")


def now_kst() -> datetime:
    return datetime.now(KST)


WEEKDAY_KO = ["월", "화", "수", "목", "금", "토", "일"]
# 새벽자습은 월요일부터 목요일까지만 신청할 수 있어요.
WEEKDAY_CHOICES = [
    app_commands.Choice(name="월요일", value=0),
    app_commands.Choice(name="화요일", value=1),
    app_commands.Choice(name="수요일", value=2),
    app_commands.Choice(name="목요일", value=3),
]


def monday_of(today: date, week_offset: int) -> date:
    return today - timedelta(days=today.weekday()) + timedelta(days=7 * week_offset)


def resolve_week(
    today: date,
    week_mode: str,
    start_weekday: int,
    end_weekday: int,
) -> tuple[date, date]:
    """신청 기간(시작일, 종료일)을 계산해요.

    week_mode: "auto" | "this" | "next"
    - auto: 이번 주 범위 종료일(end_weekday)이 오늘보다 크거나 같으면 이번 주, 아니면 다음 주
    """
    offset = {"this": 0, "next": 1}.get(week_mode, -1)
    if offset < 0:
        base_this = monday_of(today, 0)
        end_this = base_this + timedelta(days=end_weekday)
        if today <= end_this:
            offset = 0
        else:
            offset = 1
    base = monday_of(today, offset)
    return base + timedelta(days=start_weekday), base + timedelta(days=end_weekday)


def parse_week_mode(raw: str) -> str:
    return raw if raw in ("auto", "this", "next") else "auto"


def iso(value: date) -> str:
    return value.isoformat()


def weekday_label(index: int) -> str:
    return WEEKDAY_KO[index]
