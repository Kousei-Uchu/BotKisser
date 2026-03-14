import datetime
from utils.sql_handler import SQLHandler


class StickyDB:
    """DB wrapper for sticky messages using SQLHandler."""

    def __init__(self, db_path="data/sticky.db"):
        self.db = SQLHandler(db_path)
        self._init_table()

    def _init_table(self):
        self.db.execute("""
        CREATE TABLE IF NOT EXISTS sticky_messages (
            channel_id    TEXT PRIMARY KEY,
            message_id    TEXT,
            content       TEXT,
            last_activity TEXT
        )
        """)
        # SQLHandler.execute() already commits; no extra commit() needed

    # ------------------------
    # CRUD METHODS
    # ------------------------

    def get(self, channel_id):
        row = self.db.fetchone(
            "SELECT message_id, content, last_activity FROM sticky_messages WHERE channel_id=?",
            (str(channel_id),)
        )
        if row:
            last_activity = (
                datetime.datetime.fromisoformat(row["last_activity"])
                if row["last_activity"] else None
            )
            return {
                "message_id":    int(row["message_id"]),
                "content":       row["content"],
                "last_activity": last_activity,
            }
        return None

    def set(self, channel_id, message_id, content, last_activity=None):
        last_activity_str = (
            last_activity.isoformat()
            if last_activity
            else datetime.datetime.utcnow().isoformat()
        )
        self.db.execute("""
        INSERT INTO sticky_messages (channel_id, message_id, content, last_activity)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(channel_id)
        DO UPDATE SET
            message_id    = excluded.message_id,
            content       = excluded.content,
            last_activity = excluded.last_activity
        """, (str(channel_id), str(message_id), content, last_activity_str))

    def remove(self, channel_id):
        self.db.execute(
            "DELETE FROM sticky_messages WHERE channel_id=?",
            (str(channel_id),)
        )

    def update_activity(self, channel_id):
        self.db.execute(
            "UPDATE sticky_messages SET last_activity=? WHERE channel_id=?",
            (datetime.datetime.utcnow().isoformat(), str(channel_id))
        )

    def all(self):
        return self.db.fetchall(
            "SELECT channel_id, message_id, content, last_activity FROM sticky_messages"
        )