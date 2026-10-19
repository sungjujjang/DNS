from __future__ import annotations

import os
import sys
from dataclasses import dataclass

from cryptography.fernet import Fernet
from dotenv import load_dotenv

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_PATH = os.path.join(ROOT, ".env")

log = __import__("logging").getLogger(__name__)


def _get_int(name: str, default: int | None = None) -> int | None:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw.strip())
    except ValueError:
        return default


def _genkey() -> str:
    return Fernet.generate_key().decode()


def generate_crypto_key() -> str:
    key = _genkey()
    print(key, end="")
    return key


@dataclass(frozen=True)
class DbSettings:
    host: str
    port: int
    user: str
    password: str | None
    name: str

    @property
    def dict(self) -> dict:
        return {
            "host": self.host,
            "port": self.port,
            "user": self.user,
            "password": self.password if self.password else None,
            "db": self.name,
        }


@dataclass(frozen=True)
class Settings:
    discord_token: str
    guild_id: int | None
    master_admin_id: int
    database: DbSettings
    crypto_key: bytes
    api_base: str
    log_level: str

    @property
    def fernet(self) -> Fernet:
        return Fernet(self.crypto_key)


def load_settings() -> Settings:
    # Load .env only if it exists (optional for local dev)
    if os.path.exists(ENV_PATH):
        load_dotenv(ENV_PATH)

    # Pre-check for keygen
    if len(sys.argv) > 1 and sys.argv[1] in ("--genkey", "-g"):
        generate_crypto_key()
        sys.exit(0)

    token = (os.environ.get("DISCORD_TOKEN") or "").strip()
    if not token:
        raise SystemExit("DISCORD_TOKEN 환경변수를 설정해주세요.")

    crypto_raw = (os.environ.get("DNS_CRYPTO_KEY") or "").strip()
    if not crypto_raw:
        raise SystemExit(
            "DNS_CRYPTO_KEY 환경변수가 없습니다.\n"
            "다음 명령으로 생성한 값을 DNS_CRYPTO_KEY에 설정해주세요:\n"
            "python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
        )
    try:
        crypto_key = crypto_raw.encode("utf-8")
        Fernet(crypto_key)  # validate
    except Exception as e:
        raise SystemExit(f"DNS_CRYPTO_KEY 형식이 잘못됐습니다: {e}")

    db = DbSettings(
        host=(os.environ.get("DNS_DB_HOST") or "127.0.0.1").strip(),
        port=_get_int("DNS_DB_PORT", 3306) or 3306,
        user=(os.environ.get("DNS_DB_USER") or "").strip(),
        password=(os.environ.get("DNS_DB_PASSWORD") or "").strip() or None,
        name=(os.environ.get("DNS_DB_NAME") or "").strip(),
    )
    if not db.user or not db.name:
        raise SystemExit("DNS_DB_USER, DNS_DB_NAME 환경변수를 설정해주세요.")

    guild_raw = (os.environ.get("DNS_GUILD_ID") or "").strip()
    master = (os.environ.get("DNS_MASTER_ADMIN_ID") or "1337070890323673182").strip()

    return Settings(
        discord_token=token,
        guild_id=int(guild_raw) if guild_raw.isdigit() else None,
        master_admin_id=int(master),
        database=db,
        crypto_key=crypto_key,
        api_base=(os.environ.get("DNS_API_BASE") or "https://api-dms.dsmhs.kr").rstrip("/"),
        log_level=(os.environ.get("DNS_LOG_LEVEL") or "INFO").upper(),
    )
