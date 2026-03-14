import os
from utils.sql_handler import SQLHandler

DB_PATH = "data/leveling.db"


class LevelingDB:
    def __init__(self):
        os.makedirs("data", exist_ok=True)
        self.sql = SQLHandler(DB_PATH)
        self._init_db()

    def _init_db(self):
        self.sql.execute("""
            CREATE TABLE IF NOT EXISTS leveling (
                guild_id TEXT NOT NULL,
                user_id  TEXT NOT NULL,
                level    INTEGER NOT NULL DEFAULT 1,
                xp       INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (guild_id, user_id)
            )
        """)

    # ------------------------------------------------------------------
    #  CRUD — all synchronous to match SQLHandler
    # ------------------------------------------------------------------

    async def get_user(self, guild_id, user_id):
        """Return {"level": int, "xp": int} or None if the user doesn't exist yet."""
        row = self.sql.fetchone(
            "SELECT level, xp FROM leveling WHERE guild_id=? AND user_id=?",
            (str(guild_id), str(user_id))
        )
        if not row:
            return None
        return {"level": row["level"], "xp": row["xp"]}

    async def create_user(self, guild_id, user_id):
        """Insert a brand-new user record at level 1, xp 0."""
        self.sql.execute(
            "INSERT OR IGNORE INTO leveling (guild_id, user_id, level, xp) VALUES (?, ?, 1, 0)",
            (str(guild_id), str(user_id))
        )

    async def set_user(self, guild_id, user_id, xp: int, level: int):
        """Upsert level and xp for a user."""
        self.sql.execute("""
            INSERT INTO leveling (guild_id, user_id, level, xp)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(guild_id, user_id) DO UPDATE SET
                level = excluded.level,
                xp    = excluded.xp
        """, (str(guild_id), str(user_id), level, xp))

    async def get_leaderboard(self, guild_id, limit: int = 10):
        rows = self.sql.fetchall(
            "SELECT user_id, level, xp FROM leveling WHERE guild_id=? ORDER BY level DESC, xp DESC LIMIT ?",
            (str(guild_id), limit)
        )
        return [{"user_id": r["user_id"], "level": r["level"], "xp": r["xp"]} for r in rows]