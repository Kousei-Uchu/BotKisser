import asyncio
import datetime

from utils.sql_handler import SQLHandler


class AnalyticsDB:

    FLUSH_INTERVAL = 5

    def __init__(self):
        self.db = SQLHandler("data/analytics.db")

        self.message_buffer = []
        self.status_buffer  = []
        self.game_buffer    = []

        self._init_tables()
        self._init_indexes()

        asyncio.create_task(self._flush_worker())

    # ------------------------
    # TABLES
    # ------------------------

    def _init_tables(self):
        self.db.execute("""
        CREATE TABLE IF NOT EXISTS users (
            guild_id      TEXT,
            user_id       TEXT,
            message_count INTEGER DEFAULT 0,
            last_active   TEXT,
            online_time   REAL DEFAULT 0,
            last_seen     TEXT,
            PRIMARY KEY (guild_id, user_id)
        )
        """)

        self.db.execute("""
        CREATE TABLE IF NOT EXISTS channel_activity (
            guild_id   TEXT,
            user_id    TEXT,
            channel_id TEXT,
            count      INTEGER DEFAULT 0,
            PRIMARY KEY (guild_id, user_id, channel_id)
        )
        """)

        self.db.execute("""
        CREATE TABLE IF NOT EXISTS user_hours (
            guild_id TEXT,
            user_id  TEXT,
            hour     INTEGER,
            count    INTEGER DEFAULT 0,
            PRIMARY KEY (guild_id, user_id, hour)
        )
        """)

        self.db.execute("""
        CREATE TABLE IF NOT EXISTS server_hours (
            guild_id TEXT,
            hour     INTEGER,
            count    INTEGER DEFAULT 0,
            PRIMARY KEY (guild_id, hour)
        )
        """)

        self.db.execute("""
        CREATE TABLE IF NOT EXISTS status_changes (
            guild_id    TEXT,
            user_id     TEXT,
            timestamp   TEXT,
            from_status TEXT,
            to_status   TEXT
        )
        """)

        self.db.execute("""
        CREATE TABLE IF NOT EXISTS games (
            guild_id TEXT,
            user_id  TEXT,
            game     TEXT,
            count    INTEGER DEFAULT 0,
            PRIMARY KEY (guild_id, user_id, game)
        )
        """)
        # SQLHandler.execute() already commits; no extra commit() needed

    # ------------------------
    # INDEXES
    # ------------------------

    def _init_indexes(self):
        self.db.execute("CREATE INDEX IF NOT EXISTS idx_users_messages    ON users(message_count)")
        self.db.execute("CREATE INDEX IF NOT EXISTS idx_users_last_active ON users(last_active)")
        self.db.execute("CREATE INDEX IF NOT EXISTS idx_channel_activity  ON channel_activity(channel_id)")
        self.db.execute("CREATE INDEX IF NOT EXISTS idx_games             ON games(game)")

    # ------------------------
    # QUEUE METHODS
    # ------------------------

    async def log_message(self, guild_id, user_id, channel_id):
        now = datetime.datetime.utcnow()
        self.message_buffer.append({
            "guild":     guild_id,
            "user":      user_id,
            "channel":   channel_id,
            "hour":      now.hour,
            "timestamp": now.isoformat()
        })

    async def log_status_change(self, guild_id, user_id, before, after):
        self.status_buffer.append({
            "guild":     guild_id,
            "user":      user_id,
            "before":    before,
            "after":     after,
            "timestamp": datetime.datetime.utcnow().isoformat()
        })

    async def log_game(self, guild_id, user_id, game):
        self.game_buffer.append({
            "guild": guild_id,
            "user":  user_id,
            "game":  game
        })

    # ------------------------
    # FLUSH WORKER
    # ------------------------

    async def _flush_worker(self):
        while True:
            await asyncio.sleep(self.FLUSH_INTERVAL)
            await self.flush()

    async def flush(self):
        if not self.message_buffer and not self.status_buffer and not self.game_buffer:
            return

        # Drain buffers atomically so new events can keep arriving
        messages = self.message_buffer[:]
        statuses = self.status_buffer[:]
        games    = self.game_buffer[:]
        self.message_buffer.clear()
        self.status_buffer.clear()
        self.game_buffer.clear()

        for event in messages:
            guild     = event["guild"]
            user      = event["user"]
            channel   = event["channel"]
            hour      = event["hour"]
            timestamp = event["timestamp"]

            self.db.execute("""
            INSERT INTO users (guild_id, user_id, message_count, last_active)
            VALUES (?, ?, 1, ?)
            ON CONFLICT(guild_id, user_id)
            DO UPDATE SET
                message_count = message_count + 1,
                last_active   = excluded.last_active
            """, (guild, user, timestamp))

            self.db.execute("""
            INSERT INTO channel_activity (guild_id, user_id, channel_id, count)
            VALUES (?, ?, ?, 1)
            ON CONFLICT(guild_id, user_id, channel_id)
            DO UPDATE SET count = count + 1
            """, (guild, user, channel))

            self.db.execute("""
            INSERT INTO user_hours (guild_id, user_id, hour, count)
            VALUES (?, ?, ?, 1)
            ON CONFLICT(guild_id, user_id, hour)
            DO UPDATE SET count = count + 1
            """, (guild, user, hour))

            self.db.execute("""
            INSERT INTO server_hours (guild_id, hour, count)
            VALUES (?, ?, 1)
            ON CONFLICT(guild_id, hour)
            DO UPDATE SET count = count + 1
            """, (guild, hour))

        for event in statuses:
            self.db.execute("""
            INSERT INTO status_changes (guild_id, user_id, timestamp, from_status, to_status)
            VALUES (?, ?, ?, ?, ?)
            """, (event["guild"], event["user"], event["timestamp"], event["before"], event["after"]))

        for event in games:
            self.db.execute("""
            INSERT INTO games (guild_id, user_id, game, count)
            VALUES (?, ?, ?, 1)
            ON CONFLICT(guild_id, user_id, game)
            DO UPDATE SET count = count + 1
            """, (event["guild"], event["user"], event["game"]))

        # SQLHandler commits on each execute(); nothing extra needed here

    # ------------------------
    # QUERY METHODS
    # ------------------------

    def get_user(self, guild_id, user_id):
        return self.db.fetchone(
            "SELECT * FROM users WHERE guild_id=? AND user_id=?",
            (guild_id, user_id)
        )

    def get_top_users(self, guild_id, limit=10):
        return self.db.fetchall("""
        SELECT user_id, message_count
        FROM users
        WHERE guild_id=?
        ORDER BY message_count DESC
        LIMIT ?
        """, (guild_id, limit))

    def get_top_channels(self, guild_id, limit=10):
        return self.db.fetchall("""
        SELECT channel_id, SUM(count) as total
        FROM channel_activity
        WHERE guild_id=?
        GROUP BY channel_id
        ORDER BY total DESC
        LIMIT ?
        """, (guild_id, limit))

    def get_user_games(self, guild_id, user_id):
        return self.db.fetchall("""
        SELECT game, count
        FROM games
        WHERE guild_id=? AND user_id=?
        ORDER BY count DESC
        LIMIT 5
        """, (guild_id, user_id))

    def get_busiest_hour(self, guild_id):
        return self.db.fetchone("""
        SELECT hour, count
        FROM server_hours
        WHERE guild_id=?
        ORDER BY count DESC
        LIMIT 1
        """, (guild_id,))