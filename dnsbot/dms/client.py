from __future__ import annotations

import asyncio
import base64
import json
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from dnsbot.crypto import decrypt, encrypt
from dnsbot.db import Database
from dnsbot.dms.errors import AuthRequired, DmsError, NetworkError

KST = ZoneInfo("Asia/Seoul")

REFRESH_MARGIN = 60.0
TEACHER_CACHE_TTL = 600.0
TYPE_CACHE_TTL = 600.0


def jwt_exp(token: str | None) -> float | None:
    if not token:
        return None
    parts = token.split(".")
    if len(parts) != 3:
        return None
    payload = parts[1]
    payload += "=" * (-len(payload) % 4)
    try:
        data = json.loads(base64.urlsafe_b64decode(payload.encode()))
    except (ValueError, UnicodeDecodeError):
        return None
    exp = data.get("exp")
    try:
        return float(exp)
    except (TypeError, ValueError):
        return None


def _expires_at(token: str | None, iso: str | None) -> float | None:
    exp = jwt_exp(token)
    if exp:
        return exp
    if iso:
        try:
            parsed = datetime.fromisoformat(iso)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=KST)
        return parsed.timestamp()
    return None


@dataclass
class TokenBundle:
    access_token: str | None = None
    access_token_exp: float | None = None
    refresh_token: str | None = None
    refresh_token_exp: float | None = None
    features: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_response(cls, data: dict[str, Any]) -> TokenBundle:
        access = data.get("access_token")
        refresh = data.get("refresh_token")
        return cls(
            access_token=access,
            access_token_exp=_expires_at(access, data.get("access_token_expired_at")),
            refresh_token=refresh,
            refresh_token_exp=_expires_at(
                refresh, data.get("refresh_token_expired_at")
            ),
            features=data.get("features") or {},
        )

    def as_row(self) -> dict[str, Any]:
        return {
            "access_token": self.access_token,
            "access_token_exp": self.access_token_exp,
            "refresh_token": self.refresh_token,
            "refresh_token_exp": self.refresh_token_exp,
        }

    @property
    def is_valid(self) -> bool:
        if not self.access_token:
            return False
        if self.access_token_exp is None:
            return True
        return time.time() < self.access_token_exp - REFRESH_MARGIN


class DmsClient:
    """DMS REST API 클라이언트. 토큰 갱신은 여기서 모두 처리해요."""

    def __init__(self, db: Database, api_base: str, fernet: Any) -> None:
        self.db = db
        self.api_base = api_base.rstrip("/")
        self.fernet = fernet
        self._http: httpx.AsyncClient | None = None
        self._locks: dict[str, asyncio.Lock] = {}
        self._teachers: tuple[float, list[dict[str, Any]]] | None = None
        self._types: tuple[float, list[dict[str, Any]]] | None = None

    async def start(self) -> None:
        self._http = httpx.AsyncClient(
            base_url=self.api_base,
            timeout=httpx.Timeout(15.0, connect=10.0),
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )

    async def close(self) -> None:
        if self._http is not None:
            await self._http.aclose()
            self._http = None

    @property
    def http(self) -> httpx.AsyncClient:
        if self._http is None:
            raise RuntimeError("DmsClient.start()를 먼저 호출해야 해요.")
        return self._http

    def _lock_for(self, discord_id: str) -> asyncio.Lock:
        lock = self._locks.get(discord_id)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[discord_id] = lock
        return lock

    # ---------------- 하위 수준 요청 ----------------

    @staticmethod
    def _parse_error(resp: httpx.Response) -> DmsError:
        payload: Any = None
        try:
            payload = resp.json()
        except ValueError:
            payload = None

        status = resp.status_code
        message = f"요청에 실패했어요 ({status})."
        code: str | None = None
        field_error: dict[str, Any] | None = None

        if isinstance(payload, dict):
            status = int(payload.get("status") or status)
            message = str(payload.get("message") or message)
            code = payload.get("code")
            raw_field = payload.get("field_error")
            if isinstance(raw_field, dict):
                field_error = raw_field

        if resp.status_code == 401:
            return DmsError(
                status, message or "로그인 세션이 만료됐어요.", code, field_error
            )
        return DmsError(status, message, code, field_error)

    async def _send(
        self,
        method: str,
        path: str,
        *,
        json_body: Any = None,
        token: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        merged = dict(headers or {})
        if token:
            merged["Authorization"] = f"Bearer {token}"
        try:
            return await self.http.request(
                method, path, json=json_body, headers=merged or None
            )
        except httpx.HTTPError as exc:
            raise NetworkError() from exc

    async def authenticate(self, account_id: str, password: str) -> TokenBundle:
        resp = await self._send(
            "POST",
            "/auth/tokens",
            json_body={
                "account_id": account_id,
                "password": password,
                "device_token": None,
            },
        )
        if resp.status_code >= 400:
            raise self._parse_error(resp)
        return TokenBundle.from_response(resp.json())

    async def _reissue(self, refresh_token: str) -> TokenBundle:
        resp = await self._send(
            "PUT", "/auth/reissue", headers={"refresh-token": refresh_token}
        )
        if resp.status_code >= 400:
            raise self._parse_error(resp)
        return TokenBundle.from_response(resp.json())

    async def _relogin(self, user: dict[str, Any]) -> TokenBundle:
        password = decrypt(self.fernet, user["password_enc"])
        bundle = await self.authenticate(user["account_id"], password)
        await self.db.upsert_login(
            user["discord_id"],
            user["account_id"],
            user["password_enc"],
            bundle.as_row(),
        )
        return bundle

    # ---------------- 세션 관리 ----------------

    async def tokens_for(self, discord_id: str) -> TokenBundle:
        user = await self.db.get_user(discord_id)
        if user is None:
            raise AuthRequired()

        bundle = TokenBundle(
            access_token=user.get("access_token"),
            access_token_exp=user.get("access_token_exp"),
            refresh_token=user.get("refresh_token"),
            refresh_token_exp=user.get("refresh_token_exp"),
        )
        if bundle.is_valid:
            return bundle
        return await self._refresh(discord_id, user, bundle)

    async def _refresh(
        self,
        discord_id: str,
        user: dict[str, Any] | None,
        current: TokenBundle,
        *,
        force: bool = False,
    ) -> TokenBundle:
        async with self._lock_for(discord_id):
            user = user or await self.db.get_user(discord_id)
            if user is None:
                raise AuthRequired()

            fresh = TokenBundle(
                access_token=user.get("access_token"),
                access_token_exp=user.get("access_token_exp"),
                refresh_token=user.get("refresh_token"),
                refresh_token_exp=user.get("refresh_token_exp"),
            )
            if not force and fresh.is_valid:
                return fresh

            refresh_token = user.get("refresh_token")
            refresh_exp = user.get("refresh_token_exp")
            refresh_expired = refresh_exp is not None and time.time() >= refresh_exp

            if refresh_token and not refresh_expired:
                try:
                    bundle = await self._reissue(refresh_token)
                except DmsError as exc:
                    if exc.status in (0, 401, 404) and exc.status != 0:
                        pass
                    elif exc.status == 0:
                        raise
                    else:
                        raise AuthRequired(
                            "세션을 재발급하지 못했어요. 다시 로그인해주세요."
                        )
                else:
                    await self.db.update_tokens(discord_id, bundle.as_row())
                    return bundle

            return await self._relogin(user)

    async def request(
        self,
        discord_id: str,
        method: str,
        path: str,
        *,
        json_body: Any = None,
    ) -> Any:
        bundle = await self.tokens_for(discord_id)
        resp = await self._send(
            method, path, json_body=json_body, token=bundle.access_token
        )

        if resp.status_code == 401:
            # 토큰이 방금 만족됐다면 한 번 강제 갱신 후 재시도해요.
            # 그래도 401이면 서버가 알려준 오류 코드를 그대로 내보내요.
            bundle = await self._refresh(discord_id, None, bundle, force=True)
            resp = await self._send(
                method, path, json_body=json_body, token=bundle.access_token
            )

        if resp.status_code >= 400:
            raise self._parse_error(resp)
        if resp.status_code == 204 or not resp.content:
            return None
        try:
            return resp.json()
        except ValueError:
            return resp.text

    async def login_and_save(
        self, discord_id: str, account_id: str, password: str
    ) -> dict[str, Any]:
        """자격 증명을 검증하고 프로필까지 확인한 뒤 저장해요."""
        bundle = await self.authenticate(account_id, password)
        password_enc = encrypt(self.fernet, password)
        await self.db.upsert_login(
            discord_id, account_id, password_enc, bundle.as_row()
        )

        try:
            profile = await self.get_profile(discord_id)
        except DmsError as exc:
            if isinstance(exc, AuthRequired):
                raise
            profile = None
        if not isinstance(profile, dict):
            raise DmsError(500, "프로필을 불러오지 못했어요.")
        return profile

    # ---------------- 엔드포인트 ----------------

    async def get_profile(self, discord_id: str) -> dict[str, Any]:
        return await self.request(discord_id, "GET", "/students/profile")

    async def teachers(self, discord_id: str) -> list[dict[str, Any]]:
        now = time.monotonic()
        if self._teachers and now - self._teachers[0] < TEACHER_CACHE_TTL:
            return self._teachers[1]
        data = await self.request(discord_id, "GET", "/teachers/general")
        teachers = list((data or {}).get("teachers") or [])
        self._teachers = (now, teachers)
        return teachers

    async def study_types(self, discord_id: str) -> list[dict[str, Any]]:
        now = time.monotonic()
        if self._types and now - self._types[0] < TYPE_CACHE_TTL:
            return self._types[1]
        data = await self.request(discord_id, "GET", "/daybreaks/study-type")
        types = list((data or {}).get("types") or [])
        self._types = (now, types)
        return types

    async def my_application(self, discord_id: str) -> dict[str, Any] | None:
        try:
            return await self.request(
                discord_id, "GET", "/daybreaks/study-application/my"
            )
        except DmsError as exc:
            if exc.status == 404:
                return None
            raise

    async def submit_application(
        self, discord_id: str, payload: dict[str, Any]
    ) -> None:
        await self.request(
            discord_id, "POST", "/daybreaks/study-application", json_body=payload
        )

    async def meals(self, discord_id: str, target: str) -> list[dict[str, Any]]:
        data = await self.request(discord_id, "GET", f"/meals/{target}")
        meals = (data or {}).get("meals")
        if not isinstance(meals, list):
            return []
        return meals

    async def meal_for(self, discord_id: str, target: str) -> dict[str, Any] | None:
        entries = [
            item
            for item in await self.meals(discord_id, target)
            if isinstance(item, dict)
        ]
        for entry in entries:
            if str(entry.get("date")) == target:
                return entry
        return None
