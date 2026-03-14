import json
from utils.sql_handler import SQLHandler


class FireboardDB:

    def __init__(self):
        self.db = SQLHandler()
        self.create_tables()

    def create_tables(self):

        self.db.execute("""
        CREATE TABLE IF NOT EXISTS fireboard_messages (
            message_id INTEGER PRIMARY KEY,
            repost_id INTEGER,
            channel_id INTEGER,
            reaction_type TEXT,
            attachments TEXT
        )
        """)

        self.db.execute("""
        CREATE TABLE IF NOT EXISTS fireboard_stats (
            message_id INTEGER,
            user_id INTEGER
        )
        """)

    def get_message(self, message_id):

        row = self.db.fetchone(
            "SELECT * FROM fireboard_messages WHERE message_id=?",
            (message_id,)
        )

        if not row:
            return None

        return {
            "message_id": row["message_id"],
            "repost_id": row["repost_id"],
            "channel_id": row["channel_id"],
            "reaction_type": row["reaction_type"],
            "attachments": json.loads(row["attachments"]) if row["attachments"] else []
        }

    def get_original_from_repost(self, repost_id):

        row = self.db.fetchone(
            "SELECT message_id FROM fireboard_messages WHERE repost_id=?",
            (repost_id,)
        )

        return row["message_id"] if row else None

    def save_message(self, message_id, repost_id, channel_id, reaction_type, attachments):

        self.db.execute("""
        INSERT OR REPLACE INTO fireboard_messages
        (message_id, repost_id, channel_id, reaction_type, attachments)
        VALUES (?, ?, ?, ?, ?)
        """, (
            message_id,
            repost_id,
            channel_id,
            reaction_type,
            json.dumps(attachments)
        ))

    def add_stat(self, message_id, user_id):

        self.db.execute(
            "INSERT INTO fireboard_stats (message_id, user_id) VALUES (?, ?)",
            (message_id, user_id)
        )

    def get_leaderboard(self):

        return self.db.fetchall("""
        SELECT user_id, COUNT(*) AS fires
        FROM fireboard_stats
        GROUP BY user_id
        ORDER BY fires DESC
        LIMIT 10
        """)