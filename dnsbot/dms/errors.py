from __future__ import annotations

from typing import Any


class DmsError(Exception):
    """DMS API가 비정상 응답을 반환했을 때 발생해요."""

    def __init__(
        self,
        status: int,
        message: str,
        code: str | None = None,
        field_error: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.message = message
        self.code = code
        self.field_error = field_error or {}

    @property
    def detail(self) -> str:
        if not self.field_error:
            return self.message
        extra = ", ".join(f"{key}: {value}" for key, value in self.field_error.items())
        return f"{self.message} ({extra})" if self.message else extra

    def __str__(self) -> str:  # pragma: no cover - 디버그용
        return f"[{self.status} {self.code or '-'}] {self.detail}"


class AuthRequired(DmsError):
    """세션을 복구하지 못해 다시 로그인이 필요할 때 발생해요."""

    def __init__(
        self, message: str = "로그인이 필요해요. `/login`으로 다시 로그인해주세요."
    ) -> None:
        super().__init__(401, message, code="DNS-AUTH")


class NetworkError(DmsError):
    def __init__(
        self, message: str = "DMS 서버에 연결하지 못했어요. 잠시 후 다시 시도해주세요."
    ) -> None:
        super().__init__(0, message, code="DNS-NETWORK")


_MESSAGES = {
    "USER-404-1": "등록되지 않은 아이디예요.",
    "AUTH-422-1": "비밀번호가 틀렸어요.",
    "AUTH-404-1": "로그인 세션을 찾을 수 없어요. 다시 로그인해주세요.",
    "SECURITY-401-1": "로그인 세션이 만료됐어요.",
    "DAYBREAK-409-1": "이미 신청 중인 새벽자습이 있어요.",
    "DAYBREAK-400-1": "신청 기간이나 내용이 올바르지 않아요.",
}

CODES = {"DAYBREAK-409-1"}

HINTS = {
    "DAYBREAK-409-1": "이미 신청 중이에요. `/saeja_status`로 현재 상태를 확인해보세요.",
}


def friendly(error: DmsError) -> str:
    """사람이 읽기 좋은 안내 문구로 바꿔요."""
    if isinstance(error, AuthRequired):
        return error.message
    hint = HINTS.get(error.code or "")
    if hint:
        return hint
    if error.code in _MESSAGES:
        return _MESSAGES[error.code]
    if error.status == 401:
        return "로그인 세션이 만료됐어요. `/login`으로 다시 로그인해주세요."
    if error.status == 404:
        return "요청한 내용을 찾을 수 없어요."
    if error.status == 400:
        return f"입력값이 올바르지 않아요. {error.detail}"
    if error.status == 0:
        return error.message
    return error.detail
