"""
moderation_db.py
----------------
SQL interface layer for the Moderation cog.
All database reads/writes go through this class, which wraps SQLHandler.
"""

import datetime
from utils.sql_handler import SQLHandler


class ModerationDB:
    def __init__(self, sql: SQLHandler):
        self.sql = sql
        self._init_tables()

    # ------------------------------------------------------------------ #
    #  Schema                                                              #
    # ------------------------------------------------------------------ #

    def _init_tables(self):
        """Create all required tables if they do not already exist."""

        self.sql.execute("""
            CREATE TABLE IF NOT EXISTS modlogs (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                case_id       INTEGER NOT NULL,
                guild_id      TEXT    NOT NULL,
                action        TEXT    NOT NULL,
                user_id       INTEGER,
                moderator_id  INTEGER NOT NULL,
                reason        TEXT,
                duration      TEXT,
                timestamp     TEXT    NOT NULL
            )
        """)

        self.sql.execute("""
            CREATE TABLE IF NOT EXISTS warnings (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id     TEXT    NOT NULL,
                user_id      TEXT    NOT NULL,
                reason       TEXT    NOT NULL,
                moderator_id INTEGER NOT NULL,
                timestamp    TEXT    NOT NULL
            )
        """)

        self.sql.execute("""
            CREATE TABLE IF NOT EXISTS notes (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id     TEXT    NOT NULL,
                user_id      TEXT    NOT NULL,
                note         TEXT    NOT NULL,
                moderator_id INTEGER NOT NULL,
                timestamp    TEXT    NOT NULL
            )
        """)

        self.sql.execute("""
            CREATE TABLE IF NOT EXISTS timed_actions (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id   INTEGER NOT NULL,
                type       TEXT    NOT NULL,
                user_id    INTEGER,
                role_id    INTEGER,
                channel_id INTEGER,
                end_ts     REAL    NOT NULL
            )
        """)

        self.sql.execute("""
            CREATE TABLE IF NOT EXISTS persisted_roles (
                guild_id TEXT    NOT NULL,
                user_id  TEXT    NOT NULL,
                role_id  INTEGER NOT NULL,
                PRIMARY KEY (guild_id, user_id, role_id)
            )
        """)

        self.sql.execute("""
            CREATE TABLE IF NOT EXISTS locked_channels (
                guild_id   TEXT    NOT NULL,
                channel_id INTEGER NOT NULL,
                PRIMARY KEY (guild_id, channel_id)
            )
        """)

    # ------------------------------------------------------------------ #
    #  Mod Logs                                                            #
    # ------------------------------------------------------------------ #

    def next_case_id(self, guild_id: str) -> int:
        row = self.sql.fetchone(
            "SELECT COALESCE(MAX(case_id), 0) + 1 FROM modlogs WHERE guild_id = ?",
            (guild_id,)
        )
        return row[0]

    def add_modlog(self, guild_id: str, action: str, user_id, moderator_id: int,
                   reason: str = None, duration: str = None) -> int:
        case_id = self.next_case_id(guild_id)
        timestamp = datetime.datetime.utcnow().isoformat()
        self.sql.execute(
            """INSERT INTO modlogs
               (case_id, guild_id, action, user_id, moderator_id, reason, duration, timestamp)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (case_id, guild_id, action, user_id, moderator_id, reason, duration, timestamp)
        )
        return case_id

    def get_modlogs_for_user(self, guild_id: str, user_id: int, page: int = 1):
        offset = (page - 1) * 5
        return self.sql.fetchall(
            "SELECT * FROM modlogs WHERE guild_id = ? AND user_id = ? ORDER BY case_id LIMIT 5 OFFSET ?",
            (guild_id, user_id, offset)
        )

    def get_case(self, guild_id: str, case_id: int):
        return self.sql.fetchone(
            "SELECT * FROM modlogs WHERE guild_id = ? AND case_id = ?",
            (guild_id, case_id)
        )

    def update_case_reason(self, guild_id: str, case_id: int, reason: str) -> bool:
        row = self.get_case(guild_id, case_id)
        if not row:
            return False
        self.sql.execute(
            "UPDATE modlogs SET reason = ? WHERE guild_id = ? AND case_id = ?",
            (reason, guild_id, case_id)
        )
        return True

    def update_case_duration(self, guild_id: str, case_id: int, duration: str) -> bool:
        row = self.get_case(guild_id, case_id)
        if not row or row["duration"] is None:
            return False
        self.sql.execute(
            "UPDATE modlogs SET duration = ? WHERE guild_id = ? AND case_id = ?",
            (duration, guild_id, case_id)
        )
        return True

    def get_modstats(self, guild_id: str, moderator_id: int):
        """Return a list of (action, count) tuples for a moderator."""
        return self.sql.fetchall(
            """SELECT action, COUNT(*) as cnt
               FROM modlogs
               WHERE guild_id = ? AND moderator_id = ?
               GROUP BY action
               ORDER BY action""",
            (guild_id, moderator_id)
        )

    # ------------------------------------------------------------------ #
    #  Warnings                                                            #
    # ------------------------------------------------------------------ #

    def add_warning(self, guild_id: str, user_id: str, reason: str, moderator_id: int):
        self.sql.execute(
            """INSERT INTO warnings (guild_id, user_id, reason, moderator_id, timestamp)
               VALUES (?, ?, ?, ?, ?)""",
            (guild_id, user_id, reason, moderator_id, datetime.datetime.utcnow().isoformat())
        )

    def get_warnings(self, guild_id: str, user_id: str):
        return self.sql.fetchall(
            "SELECT * FROM warnings WHERE guild_id = ? AND user_id = ? ORDER BY id",
            (guild_id, user_id)
        )

    def delete_warning(self, guild_id: str, user_id: str, index: int) -> bool:
        """Delete warning by 1-based index. Returns True on success."""
        rows = self.get_warnings(guild_id, user_id)
        if index < 1 or index > len(rows):
            return False
        target_id = rows[index - 1]["id"]
        self.sql.execute("DELETE FROM warnings WHERE id = ?", (target_id,))
        return True

    # ------------------------------------------------------------------ #
    #  Notes                                                               #
    # ------------------------------------------------------------------ #

    def add_note(self, guild_id: str, user_id: str, note: str, moderator_id: int):
        self.sql.execute(
            """INSERT INTO notes (guild_id, user_id, note, moderator_id, timestamp)
               VALUES (?, ?, ?, ?, ?)""",
            (guild_id, user_id, note, moderator_id, datetime.datetime.utcnow().isoformat())
        )

    def get_notes(self, guild_id: str, user_id: str):
        return self.sql.fetchall(
            "SELECT * FROM notes WHERE guild_id = ? AND user_id = ? ORDER BY id",
            (guild_id, user_id)
        )

    def edit_note(self, guild_id: str, user_id: str, index: int, text: str) -> bool:
        rows = self.get_notes(guild_id, user_id)
        if index < 1 or index > len(rows):
            return False
        target_id = rows[index - 1]["id"]
        self.sql.execute("UPDATE notes SET note = ? WHERE id = ?", (text, target_id))
        return True

    def delete_note(self, guild_id: str, user_id: str, index: int) -> bool:
        rows = self.get_notes(guild_id, user_id)
        if index < 1 or index > len(rows):
            return False
        target_id = rows[index - 1]["id"]
        self.sql.execute("DELETE FROM notes WHERE id = ?", (target_id,))
        return True

    def clear_notes(self, guild_id: str, user_id: str):
        self.sql.execute(
            "DELETE FROM notes WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id)
        )

    # ------------------------------------------------------------------ #
    #  Timed Actions                                                       #
    # ------------------------------------------------------------------ #

    def add_timed_action(self, guild_id: int, action_type: str, end_ts: float,
                         user_id: int = None, role_id: int = None, channel_id: int = None):
        self.sql.execute(
            """INSERT INTO timed_actions (guild_id, type, user_id, role_id, channel_id, end_ts)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (guild_id, action_type, user_id, role_id, channel_id, end_ts)
        )

    def get_expired_actions(self, now_ts: float):
        return self.sql.fetchall(
            "SELECT * FROM timed_actions WHERE end_ts <= ?",
            (now_ts,)
        )

    def delete_timed_action(self, action_id: int):
        self.sql.execute("DELETE FROM timed_actions WHERE id = ?", (action_id,))

    def update_timed_action_end(self, guild_id: int, action_type: str, user_id: int, new_end: float):
        """Update end timestamp for a specific user's timed action."""
        self.sql.execute(
            """UPDATE timed_actions SET end_ts = ?
               WHERE guild_id = ? AND type = ? AND user_id = ?""",
            (new_end, guild_id, action_type, user_id)
        )

    # ------------------------------------------------------------------ #
    #  Persisted Roles                                                     #
    # ------------------------------------------------------------------ #

    def add_persisted_role(self, guild_id: str, user_id: str, role_id: int):
        self.sql.execute(
            """INSERT OR IGNORE INTO persisted_roles (guild_id, user_id, role_id)
               VALUES (?, ?, ?)""",
            (guild_id, user_id, role_id)
        )

    def remove_persisted_role(self, guild_id: str, user_id: str, role_id: int):
        self.sql.execute(
            "DELETE FROM persisted_roles WHERE guild_id = ? AND user_id = ? AND role_id = ?",
            (guild_id, user_id, role_id)
        )

    def get_persisted_roles(self, guild_id: str, user_id: str):
        rows = self.sql.fetchall(
            "SELECT role_id FROM persisted_roles WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id)
        )
        return [r["role_id"] for r in rows]

    # ------------------------------------------------------------------ #
    #  Locked Channels                                                     #
    # ------------------------------------------------------------------ #

    def lock_channel(self, guild_id: str, channel_id: int):
        self.sql.execute(
            "INSERT OR IGNORE INTO locked_channels (guild_id, channel_id) VALUES (?, ?)",
            (guild_id, channel_id)
        )

    def unlock_channel(self, guild_id: str, channel_id: int):
        self.sql.execute(
            "DELETE FROM locked_channels WHERE guild_id = ? AND channel_id = ?",
            (guild_id, channel_id)
        )

    def is_channel_locked(self, guild_id: str, channel_id: int) -> bool:
        row = self.sql.fetchone(
            "SELECT 1 FROM locked_channels WHERE guild_id = ? AND channel_id = ?",
            (guild_id, channel_id)
        )
        return row is not None

    def get_locked_channels(self, guild_id: str):
        rows = self.sql.fetchall(
            "SELECT channel_id FROM locked_channels WHERE guild_id = ?",
            (guild_id,)
        )
        return [r["channel_id"] for r in rows]

    def clear_locked_channels(self, guild_id: str):
        self.sql.execute(
            "DELETE FROM locked_channels WHERE guild_id = ?",
            (guild_id,)
        )