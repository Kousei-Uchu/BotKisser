"""
migrate_json_to_sql.py
----------------------
One-shot migration script: reads all legacy JSON data files and writes
them into the SQLite databases used by the new codebase.

Run ONCE from the bot root directory:
    python migrate_json_to_sql.py

Safe to re-run — uses INSERT OR IGNORE / INSERT OR REPLACE so duplicates
are silently skipped.

Files read:
  data/leveling.json      → data/leveling.db  (leveling table)
  data/moderation.json    → data/bot.db        (modlogs, warnings, notes,
                                                timed_actions, persisted_roles,
                                                locked_channels)
  data/sticky.json        → data/sticky.db     (sticky_messages)
  data/analytics.json     → data/analytics.db  (users, status_changes,
                                                channel_activity, user_hours,
                                                server_hours, games)

Files NOT migrated (no longer used / superseded):
  data/ticket.json        — ticket state is ephemeral; open tickets will
                            be re-created naturally.
  data/fireboard.json     — only stores repost message IDs; stale after
                            repost messages were deleted.

Usage:
    cd /path/to/bot
    python migrate_json_to_sql.py
"""

import json
import os
import sqlite3
import sys
from pathlib import Path

# ── helpers ──────────────────────────────────────────────────────────────── #

def open_db(path: str) -> sqlite3.Connection:
    os.makedirs("data", exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def load_json(path: str) -> dict | list | None:
    p = Path(path)
    if not p.exists():
        print(f"  [skip] {path} not found")
        return None
    with open(p) as f:
        return json.load(f)


# ── 1. Leveling ───────────────────────────────────────────────────────────── #

def migrate_leveling():
    print("\n[leveling] Reading data/leveling.json …")
    data = load_json("data/leveling.json")
    if data is None:
        return

    conn = open_db("data/leveling.db")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS leveling (
            guild_id TEXT NOT NULL,
            user_id  TEXT NOT NULL,
            level    INTEGER NOT NULL DEFAULT 1,
            xp       INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (guild_id, user_id)
        )
    """)
    conn.commit()

    inserted = 0
    for guild_id, members in data.items():
        for user_id, info in members.items():
            level = info.get("level", 1)
            xp    = info.get("xp", 0)
            conn.execute(
                """
                INSERT OR IGNORE INTO leveling (guild_id, user_id, level, xp)
                VALUES (?, ?, ?, ?)
                """,
                (str(guild_id), str(user_id), level, xp)
            )
            inserted += 1

    conn.commit()
    conn.close()
    print(f"  [ok] {inserted} leveling records inserted into data/leveling.db")


# ── 2. Moderation ────────────────────────────────────────────────────────── #

def migrate_moderation():
    print("\n[moderation] Reading data/moderation.json …")
    data = load_json("data/moderation.json")
    if data is None:
        return

    conn = open_db("data/bot.db")

    # ── create tables (mirrors moderation_db.py) ── #
    conn.executescript("""
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
        );

        CREATE TABLE IF NOT EXISTS warnings (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id     TEXT    NOT NULL,
            user_id      TEXT    NOT NULL,
            reason       TEXT    NOT NULL,
            moderator_id INTEGER NOT NULL,
            timestamp    TEXT    NOT NULL
        );

        CREATE TABLE IF NOT EXISTS notes (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id     TEXT    NOT NULL,
            user_id      TEXT    NOT NULL,
            note         TEXT    NOT NULL,
            moderator_id INTEGER NOT NULL,
            timestamp    TEXT    NOT NULL
        );

        CREATE TABLE IF NOT EXISTS timed_actions (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id   INTEGER NOT NULL,
            type       TEXT    NOT NULL,
            user_id    INTEGER,
            role_id    INTEGER,
            channel_id INTEGER,
            end_ts     REAL    NOT NULL
        );

        CREATE TABLE IF NOT EXISTS persisted_roles (
            guild_id TEXT    NOT NULL,
            user_id  TEXT    NOT NULL,
            role_id  INTEGER NOT NULL,
            PRIMARY KEY (guild_id, user_id, role_id)
        );

        CREATE TABLE IF NOT EXISTS locked_channels (
            guild_id   TEXT    NOT NULL,
            channel_id INTEGER NOT NULL,
            PRIMARY KEY (guild_id, channel_id)
        );
    """)
    conn.commit()

    total = {"modlogs": 0, "warnings": 0, "notes": 0,
             "timed": 0, "persisted": 0, "locked": 0}

    # ── mod logs ── #
    for guild_id, cases in data.get("modlogs", {}).items():
        for case in cases:
            conn.execute(
                """
                INSERT OR IGNORE INTO modlogs
                    (case_id, guild_id, action, user_id, moderator_id,
                     reason, duration, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    case["case_id"],
                    str(guild_id),
                    case.get("action", "Unknown"),
                    case.get("user_id"),
                    case.get("moderator_id", 0),
                    case.get("reason"),
                    case.get("duration"),
                    case.get("timestamp", "1970-01-01T00:00:00"),
                )
            )
            total["modlogs"] += 1

    # ── warnings ── #
    for guild_id, users in data.get("warnings", {}).items():
        for user_id, warns in users.items():
            for w in warns:
                conn.execute(
                    """
                    INSERT INTO warnings
                        (guild_id, user_id, reason, moderator_id, timestamp)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        str(guild_id),
                        str(user_id),
                        w.get("reason", ""),
                        w.get("mod", 0),
                        w.get("time", "1970-01-01T00:00:00"),
                    )
                )
                total["warnings"] += 1

    # ── notes ── #
    for guild_id, users in data.get("notes", {}).items():
        for user_id, notes in users.items():
            for n in notes:
                conn.execute(
                    """
                    INSERT INTO notes
                        (guild_id, user_id, note, moderator_id, timestamp)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        str(guild_id),
                        str(user_id),
                        n.get("note", n.get("text", "")),
                        n.get("mod", n.get("moderator_id", 0)),
                        n.get("time", n.get("timestamp", "1970-01-01T00:00:00")),
                    )
                )
                total["notes"] += 1

    # ── timed actions ── #
    for entry in data.get("timed", []):
        conn.execute(
            """
            INSERT INTO timed_actions
                (guild_id, type, user_id, role_id, channel_id, end_ts)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                entry.get("guild_id", 0),
                entry.get("type", entry.get("action", "unknown")),
                entry.get("user_id"),
                entry.get("role_id"),
                entry.get("channel_id"),
                entry.get("end_ts", entry.get("expires", 0)),
            )
        )
        total["timed"] += 1

    # ── persisted roles ── #
    for guild_id, users in data.get("persisted_roles", {}).items():
        for user_id, roles in users.items():
            for role_id in roles:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO persisted_roles
                        (guild_id, user_id, role_id)
                    VALUES (?, ?, ?)
                    """,
                    (str(guild_id), str(user_id), role_id)
                )
                total["persisted"] += 1

    # ── locked channels ── #
    for entry in data.get("locked_channels", []):
        guild_id = entry.get("guild_id")
        ch_id = entry.get("channel_id")
        if guild_id is not None and ch_id is not None:
            conn.execute(
                """
                INSERT OR IGNORE INTO locked_channels (guild_id, channel_id)
                VALUES (?, ?)
                """,
                (str(guild_id), ch_id)
            )
            total["locked"] += 1

    conn.commit()
    conn.close()
    for key, count in total.items():
        print(f"  [ok] {count:4d} {key} rows inserted into data/bot.db")


# ── 3. Sticky messages ────────────────────────────────────────────────────── #

def migrate_sticky():
    print("\n[sticky] Reading data/sticky.json …")
    data = load_json("data/sticky.json")
    if data is None:
        return

    conn = open_db("data/sticky.db")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sticky_messages (
            channel_id    TEXT PRIMARY KEY,
            message_id    TEXT,
            content       TEXT,
            last_activity TEXT
        )
    """)
    conn.commit()

    inserted = 0
    for channel_id, info in data.items():
        conn.execute(
            """
            INSERT OR REPLACE INTO sticky_messages
                (channel_id, message_id, content, last_activity)
            VALUES (?, ?, ?, ?)
            """,
            (
                str(channel_id),
                str(info.get("message_id", "")),
                info.get("content", ""),
                None,
            )
        )
        inserted += 1

    conn.commit()
    conn.close()
    print(f"  [ok] {inserted} sticky messages inserted into data/sticky.db")


# ── 4. Analytics ──────────────────────────────────────────────────────────── #

def migrate_analytics():
    print("\n[analytics] Reading data/analytics.json …")
    data = load_json("data/analytics.json")
    if data is None:
        print("  [warn] No analytics.json found, skipping migration.")
        return

    conn = open_db("data/analytics.db")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            guild_id      TEXT,
            user_id       TEXT,
            message_count INTEGER DEFAULT 0,
            last_active   TEXT,
            online_time   REAL DEFAULT 0,
            last_seen     TEXT,
            PRIMARY KEY (guild_id, user_id)
        );

        CREATE TABLE IF NOT EXISTS channel_activity (
            guild_id   TEXT,
            user_id    TEXT,
            channel_id TEXT,
            count      INTEGER DEFAULT 0,
            PRIMARY KEY (guild_id, user_id, channel_id)
        );

        CREATE TABLE IF NOT EXISTS user_hours (
            guild_id TEXT,
            user_id  TEXT,
            hour     INTEGER,
            count    INTEGER DEFAULT 0,
            PRIMARY KEY (guild_id, user_id, hour)
        );

        CREATE TABLE IF NOT EXISTS server_hours (
            guild_id TEXT,
            hour     INTEGER,
            count    INTEGER DEFAULT 0,
            PRIMARY KEY (guild_id, hour)
        );

        CREATE TABLE IF NOT EXISTS status_changes (
            guild_id    TEXT,
            user_id     TEXT,
            timestamp   TEXT,
            from_status TEXT,
            to_status   TEXT
        );

        CREATE TABLE IF NOT EXISTS games (
            guild_id TEXT,
            user_id  TEXT,
            game     TEXT,
            count    INTEGER DEFAULT 0,
            PRIMARY KEY (guild_id, user_id, game)
        );
    """)
    conn.commit()

    users_inserted = 0
    channel_inserted = 0
    hours_inserted = 0
    status_inserted = 0
    games_inserted = 0

    for guild_id, guild_data in data.items():
        users = guild_data.get("users", {})
        for user_id, info in users.items():
            msg_count   = info.get("message_count", 0)
            last_active = info.get("last_active")
            online_time = info.get("online_time", 0)
            last_seen   = info.get("last_seen")

            # insert main user row
            conn.execute(
                """
                INSERT OR REPLACE INTO users
                    (guild_id, user_id, message_count, last_active, online_time, last_seen)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (str(guild_id), str(user_id), msg_count, last_active, online_time, last_seen)
            )
            users_inserted += 1

            # insert channel activity
            activity = info.get("activity", {})
            for ch_id, count in activity.get("channels", {}).items():
                conn.execute(
                    """
                    INSERT OR REPLACE INTO channel_activity
                        (guild_id, user_id, channel_id, count)
                    VALUES (?, ?, ?, ?)
                    """,
                    (str(guild_id), str(user_id), str(ch_id), count)
                )
                channel_inserted += 1

            # insert user hours
            for hour_str, count in activity.get("active_hours", {}).items():
                try:
                    hour = int(hour_str)
                except ValueError:
                    continue

                conn.execute(
                    """
                    INSERT OR REPLACE INTO user_hours
                        (guild_id, user_id, hour, count)
                    VALUES (?, ?, ?, ?)
                    """,
                    (str(guild_id), str(user_id), hour, count)
                )
                hours_inserted += 1

                # aggregate into server_hours
                existing = conn.execute(
                    "SELECT count FROM server_hours WHERE guild_id=? AND hour=?",
                    (str(guild_id), hour)
                ).fetchone()
                if existing:
                    conn.execute(
                        "UPDATE server_hours SET count = count + ? WHERE guild_id=? AND hour=?",
                        (count, str(guild_id), hour)
                    )
                else:
                    conn.execute(
                        "INSERT INTO server_hours (guild_id, hour, count) VALUES (?, ?, ?)",
                        (str(guild_id), hour, count)
                    )

            # insert status changes
            for sc in info.get("status_changes", []):
                conn.execute(
                    """
                    INSERT INTO status_changes
                        (guild_id, user_id, timestamp, from_status, to_status)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        str(guild_id),
                        str(user_id),
                        sc.get("timestamp"),
                        sc.get("from"),
                        sc.get("to"),
                    )
                )
                status_inserted += 1

            # insert games
            for game, count in info.get("games", {}).items():
                conn.execute(
                    """
                    INSERT OR REPLACE INTO games
                        (guild_id, user_id, game, count)
                    VALUES (?, ?, ?, ?)
                    """,
                    (str(guild_id), str(user_id), game, count)
                )
                games_inserted += 1

    conn.commit()
    conn.close()

    print(f"  [ok] {users_inserted:5d} user rows inserted into data/analytics.db")
    print(f"  [ok] {channel_inserted:5d} channel_activity rows")
    print(f"  [ok] {hours_inserted:5d} user_hours rows")
    print(f"  [ok] {status_inserted:5d} status_change rows")
    print(f"  [ok] {games_inserted:5d} game rows")


# ── entry point ───────────────────────────────────────────────────────────── #

if __name__ == "__main__":
    print("=" * 60)
    print("  JSON → SQLite migration")
    print("  Run from the bot root directory.")
    print("=" * 60)

    migrate_leveling()
    migrate_moderation()
    migrate_sticky()
    migrate_analytics()

    print("\n" + "=" * 60)
    print("  Migration complete.")
    print("  You can now delete the JSON files if everything looks good.")
    print("  Suggested cleanup:")
    print("    rm data/leveling.json data/moderation.json")
    print("    rm data/sticky.json data/analytics.json")
    print("    rm data/ticket.json data/tickets.json data/fireboard.json")
    print("=" * 60)