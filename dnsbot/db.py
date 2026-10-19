from __future__ import annotations

import asyncio
from typing import Any

import aiomysql
import pymysql.err

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  discord_id VARCHAR(32) NOT NULL PRIMARY KEY,
  account_id VARCHAR(100) NOT NULL,
  password_enc TEXT NOT NULL,
  access_token TEXT NULL,
  access_token_exp DOUBLE NULL,
  refresh_token TEXT NULL,
  refresh_token_exp DOUBLE NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS saeja_templates (
  id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  discord_id VARCHAR(32) NOT NULL,
  name VARCHAR(50) NOT NULL,
  teacher_id VARCHAR(50) NOT NULL,
  teacher_name VARCHAR(50) NOT NULL,
  type_id VARCHAR(50) NOT NULL,
  type_name VARCHAR(50) NOT NULL,
  reason VARCHAR(200) NOT NULL,
  start_weekday TINYINT NOT NULL,
  end_weekday TINYINT NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uniq_template (discord_id, name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS saeja_automations (
  id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  discord_id VARCHAR(32) NOT NULL,
  template_id BIGINT UNSIGNED NOT NULL,
  run_weekday TINYINT NOT NULL,
  run_time CHAR(5) NOT NULL,
  week_offset TINYINT NOT NULL DEFAULT 1,
  enabled TINYINT NOT NULL DEFAULT 1,
  last_run_key VARCHAR(10) NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  KEY idx_auto_due (enabled, run_weekday, run_time),
  CONSTRAINT fk_auto_template FOREIGN KEY (template_id) REFERENCES saeja_templates (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS meal_alerts (
  discord_id VARCHAR(32) NOT NULL PRIMARY KEY,
  alert_time CHAR(5) NOT NULL,
  last_sent DATE NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS whitelist (
  discord_id VARCHAR(32) NOT NULL PRIMARY KEY,
  added_by VARCHAR(32) NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS admins (
  discord_id VARCHAR(32) NOT NULL PRIMARY KEY,
  added_by VARCHAR(32) NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS settings (
  `key` VARCHAR(64) NOT NULL PRIMARY KEY,
  `value` TEXT NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
"""

WHITELIST_ENABLED_KEY = "whitelist_enabled"


def _dict(row: dict[str, Any] | tuple | None) -> dict[str, Any] | None:
    if row is None:
        return None
    if isinstance(row, dict):
        return row
    return dict(row)


class Database:
    def __init__(self, db_settings) -> None:
        self.db_settings = db_settings
        self.pool: aiomysql.Pool | None = None
        self._lock = asyncio.Lock()

    @property
    def pool_or_raise(self) -> aiomysql.Pool:
        if self.pool is None:
            raise RuntimeError("Database.connect()를 먼저 호출해야 해요.")
        return self.pool

    async def connect(self) -> None:
        cfg = self.db_settings
        self.pool = await aiomysql.create_pool(
            host=cfg.host,
            port=cfg.port,
            user=cfg.user,
            password=cfg.password,
            db=cfg.name,
            autocommit=True,
            charset="utf8mb4",
            minsize=1,
            maxsize=10,
        )
        async with self.pool_or_raise.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute("SET NAMES utf8mb4")
                await cur.execute("SET time_zone = '+09:00'")
                await cur.execute(SCHEMA)

    async def close(self) -> None:
        if self.pool is not None:
            self.pool.close()
            await self.pool.wait_closed()
            self.pool = None

    async def _exec(self, sql: str, params: tuple = ()) -> None:
        async with self.pool_or_raise.acquire() as conn, conn.cursor() as cur:
            await cur.execute(sql, params)

    async def _fetchone(self, sql: str, params: tuple = ()) -> dict[str, Any] | None:
        async with self.pool_or_raise.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(sql, params)
                row = await cur.fetchone()
        return _dict(row)

    async def _fetchall(self, sql: str, params: tuple = ()) -> list[dict[str, Any]]:
        async with self.pool_or_raise.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(sql, params)
                rows = await cur.fetchall()
        return [_dict(r) or {} for r in rows]  # type: ignore

    async def get_user(self, discord_id: str) -> dict[str, Any] | None:
        return await self._fetchone(
            "SELECT * FROM users WHERE discord_id = %s", (discord_id,)
        )

    async def upsert_login(
        self,
        discord_id: str,
        account_id: str,
        password_enc: str,
        tokens: dict[str, Any],
    ) -> None:
        sql = """
        INSERT INTO users (discord_id, account_id, password_enc, access_token,
                           access_token_exp, refresh_token, refresh_token_exp)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
          account_id = VALUES(account_id),
          password_enc = VALUES(password_enc),
          access_token = VALUES(access_token),
          access_token_exp = VALUES(access_token_exp),
          refresh_token = VALUES(refresh_token),
          refresh_token_exp = VALUES(refresh_token_exp),
          updated_at = CURRENT_TIMESTAMP
        """
        await self._exec(
            sql,
            (
                discord_id,
                account_id,
                password_enc,
                tokens.get("access_token"),
                tokens.get("access_token_exp"),
                tokens.get("refresh_token"),
                tokens.get("refresh_token_exp"),
            ),
        )

    async def update_tokens(self, discord_id: str, tokens: dict[str, Any]) -> None:
        await self._exec(
            """
            UPDATE users SET
              access_token = %s,
              access_token_exp = %s,
              refresh_token = %s,
              refresh_token_exp = %s,
              updated_at = CURRENT_TIMESTAMP
            WHERE discord_id = %s
            """,
            (
                tokens.get("access_token"),
                tokens.get("access_token_exp"),
                tokens.get("refresh_token"),
                tokens.get("refresh_token_exp"),
                discord_id,
            ),
        )

    async def delete_user(self, discord_id: str) -> None:
        async with self.pool_or_raise.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("DELETE FROM users WHERE discord_id = %s", (discord_id,))
                await cur.execute("DELETE FROM meal_alerts WHERE discord_id = %s", (discord_id,))
                await cur.execute("DELETE FROM saeja_automations WHERE discord_id = %s", (discord_id,))
                await cur.execute("DELETE FROM saeja_templates WHERE discord_id = %s", (discord_id,))

    async def add_template(self, data: dict[str, Any]) -> int:
        async with self.pool_or_raise.acquire() as conn, conn.cursor() as cur:
            await cur.execute(
                """
                    INSERT INTO saeja_templates
                      (discord_id, name, teacher_id, teacher_name, type_id, type_name,
                       reason, start_weekday, end_weekday)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                (
                    data["discord_id"],
                    data["name"],
                    data["teacher_id"],
                    data["teacher_name"],
                    data["type_id"],
                    data["type_name"],
                    data["reason"],
                    data["start_weekday"],
                    data["end_weekday"],
                ),
            )
            return cur.lastrowid or 0

    async def list_templates(self, discord_id: str) -> list[dict[str, Any]]:
        return await self._fetchall(
            "SELECT * FROM saeja_templates WHERE discord_id = %s ORDER BY id",
            (discord_id,),
        )

    async def get_template(self, discord_id: str, template_id: int) -> dict[str, Any] | None:
        return await self._fetchone(
            "SELECT * FROM saeja_templates WHERE discord_id = %s AND id = %s",
            (discord_id, template_id),
        )

    async def get_template_by_name(self, discord_id: str, name: str) -> dict[str, Any] | None:
        return await self._fetchone(
            "SELECT * FROM saeja_templates WHERE discord_id = %s AND name = %s",
            (discord_id, name),
        )

    async def delete_template(self, discord_id: str, template_id: int) -> int:
        async with self.pool_or_raise.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "DELETE FROM saeja_templates WHERE discord_id = %s AND id = %s",
                    (discord_id, template_id),
                )
                count = cur.rowcount
                await cur.execute(
                    "DELETE FROM saeja_automations WHERE discord_id = %s AND template_id = %s",
                    (discord_id, template_id),
                )
                return count

    async def add_automation(self, data: dict[str, Any]) -> int:
        async with self.pool_or_raise.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    INSERT INTO saeja_automations
                      (discord_id, template_id, run_weekday, run_time, week_offset, enabled, last_run_key)
                    VALUES (%s, %s, %s, %s, %s, 1, %s)
                    """,
                    (
                        data["discord_id"],
                        data["template_id"],
                        data["run_weekday"],
                        data["run_time"],
                        data.get("week_offset", 1),
                        data.get("last_run_key"),
                    ),
                )
                return cur.lastrowid or 0

    async def list_automations(self, discord_id: str) -> list[dict[str, Any]]:
        return await self._fetchall(
            """
            SELECT a.*, t.name AS template_name, t.teacher_name, t.type_name
            FROM saeja_automations a
            JOIN saeja_templates t ON t.id = a.template_id
            WHERE a.discord_id = %s
            ORDER BY a.id
            """,
            (discord_id,),
        )

    async def delete_automation(self, discord_id: str, automation_id: int) -> int:
        async with self.pool_or_raise.acquire() as conn, conn.cursor() as cur:
            await cur.execute(
                "DELETE FROM saeja_automations WHERE discord_id = %s AND id = %s",
                (discord_id, automation_id),
            )
            return cur.rowcount

    async def due_automations(self, weekday: int, time_now: str, run_key: str) -> list[dict[str, Any]]:
        return await self._fetchall(
            """
            SELECT a.*, t.name AS template_name, t.teacher_id, t.teacher_name,
                   t.type_id, t.type_name, t.reason, t.start_weekday, t.end_weekday,
                   t.discord_id AS owner_id
            FROM saeja_automations a
            JOIN saeja_templates t ON t.id = a.template_id
            WHERE a.enabled = 1
              AND a.run_weekday = %s
              AND a.run_time <= %s
              AND (a.last_run_key IS NULL OR a.last_run_key <> %s)
            """,
            (weekday, time_now, run_key),
        )

    async def mark_automation_run(self, automation_id: int, run_key: str) -> None:
        await self._exec(
            "UPDATE saeja_automations SET last_run_key = %s WHERE id = %s",
            (run_key, automation_id),
        )

    async def get_meal_alert(self, discord_id: str) -> dict[str, Any] | None:
        return await self._fetchone("SELECT * FROM meal_alerts WHERE discord_id = %s", (discord_id,))

    async def set_meal_alert(self, discord_id: str, alert_time: str, last_sent: str | None) -> None:
        await self._exec(
            """
            INSERT INTO meal_alerts (discord_id, alert_time, last_sent)
            VALUES (%s, %s, %s)
            ON DUPLICATE KEY UPDATE
              alert_time = VALUES(alert_time),
              last_sent = VALUES(last_sent)
            """,
            (discord_id, alert_time, last_sent),
        )

    async def clear_meal_alert(self, discord_id: str) -> int:
        async with self.pool_or_raise.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("DELETE FROM meal_alerts WHERE discord_id = %s", (discord_id,))
                return cur.rowcount

    async def meal_alerts_due(self, time_now: str, today: str) -> list[dict[str, Any]]:
        return await self._fetchall(
            """
            SELECT * FROM meal_alerts
            WHERE alert_time <= %s
              AND (last_sent IS NULL OR last_sent <> %s)
            """,
            (time_now, today),
        )

    async def mark_meal_alert_sent(self, discord_id: str, today: str) -> None:
        await self._exec(
            "UPDATE meal_alerts SET last_sent = %s WHERE discord_id = %s",
            (today, discord_id),
        )

    async def is_whitelisted(self, discord_id: str) -> bool:
        row = await self._fetchone("SELECT 1 FROM whitelist WHERE discord_id = %s", (discord_id,))
        return row is not None

    async def add_whitelist(self, discord_id: str, added_by: str) -> bool:
        if await self.is_whitelisted(discord_id):
            return False
        try:
            await self._exec("INSERT INTO whitelist (discord_id, added_by) VALUES (%s, %s)", (discord_id, added_by))
        except pymysql.err.IntegrityError:
            return False
        return True

    async def remove_whitelist(self, discord_id: str) -> bool:
        async with self.pool_or_raise.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("DELETE FROM whitelist WHERE discord_id = %s", (discord_id,))
                return cur.rowcount > 0

    async def list_whitelist(self) -> list[str]:
        rows = await self._fetchall("SELECT discord_id FROM whitelist ORDER BY created_at, discord_id")
        return [r["discord_id"] for r in rows]

    async def is_admin(self, discord_id: str) -> bool:
        row = await self._fetchone("SELECT 1 FROM admins WHERE discord_id = %s", (discord_id,))
        return row is not None

    async def add_admin(self, discord_id: str, added_by: str) -> bool:
        if await self.is_admin(discord_id):
            return False
        try:
            await self._exec("INSERT INTO admins (discord_id, added_by) VALUES (%s, %s)", (discord_id, added_by))
        except pymysql.err.IntegrityError:
            return False
        return True

    async def remove_admin(self, discord_id: str) -> bool:
        async with self.pool_or_raise.acquire() as conn, conn.cursor() as cur:
            await cur.execute("DELETE FROM admins WHERE discord_id = %s", (discord_id,))
            return cur.rowcount > 0

    async def list_admins(self) -> list[str]:
        rows = await self._fetchall("SELECT discord_id FROM admins ORDER BY created_at, discord_id")
        return [r["discord_id"] for r in rows]

    async def get_setting(self, key: str, default: str | None = None) -> str | None:
        row = await self._fetchone("SELECT `value` FROM settings WHERE `key` = %s", (key,))
        return row["value"] if row else default

    async def set_setting(self, key: str, value: str) -> None:
        await self._exec(
            """
            INSERT INTO settings (`key`, `value`) VALUES (%s, %s)
            ON DUPLICATE KEY UPDATE `value` = VALUES(`value`)
            """,
            (key, value),
        )
