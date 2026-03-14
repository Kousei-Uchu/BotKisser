import datetime
from utils.sql_handler import SQLHandler


class TicketDB:
    def __init__(self, db_path="data/tickets.db"):
        self.db = SQLHandler(db_path)
        self._init_tables()

    def _init_tables(self):
        self.db.execute("""
        CREATE TABLE IF NOT EXISTS tickets (
            ticket_id  INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id   INTEGER NOT NULL,
            channel_id INTEGER NOT NULL,
            owner_id   INTEGER NOT NULL,
            created_at TEXT    NOT NULL,
            closed_at  TEXT
        )
        """)

        self.db.execute("""
        CREATE TABLE IF NOT EXISTS ticket_members (
            ticket_id INTEGER NOT NULL,
            user_id   INTEGER NOT NULL,
            PRIMARY KEY (ticket_id, user_id),
            FOREIGN KEY (ticket_id) REFERENCES tickets(ticket_id) ON DELETE CASCADE
        )
        """)
        # SQLHandler.execute() already commits; no extra commit() needed

    # ------------------------
    # Ticket CRUD
    # ------------------------

    def create_ticket(self, guild_id: int, channel_id: int, owner_id: int) -> int:
        created_at = datetime.datetime.utcnow().isoformat()
        self.db.execute(
            "INSERT INTO tickets (guild_id, channel_id, owner_id, created_at) VALUES (?, ?, ?, ?)",
            (guild_id, channel_id, owner_id, created_at)
        )
        # Retrieve the auto-generated ticket_id without a custom method
        row = self.db.fetchone(
            "SELECT ticket_id FROM tickets WHERE guild_id=? AND channel_id=? AND owner_id=? ORDER BY ticket_id DESC LIMIT 1",
            (guild_id, channel_id, owner_id)
        )
        ticket_id = row["ticket_id"]
        # Owner is always a member of their own ticket
        self.add_member(ticket_id, owner_id)
        return ticket_id

    def close_ticket(self, ticket_id: int):
        closed_at = datetime.datetime.utcnow().isoformat()
        self.db.execute(
            "UPDATE tickets SET closed_at=? WHERE ticket_id=?",
            (closed_at, ticket_id)
        )

    def get_ticket_by_channel(self, channel_id: int):
        return self.db.fetchone(
            "SELECT * FROM tickets WHERE channel_id=? AND closed_at IS NULL",
            (channel_id,)
        )

    def get_user_open_ticket(self, guild_id: int, owner_id: int):
        return self.db.fetchone(
            "SELECT * FROM tickets WHERE guild_id=? AND owner_id=? AND closed_at IS NULL",
            (guild_id, owner_id)
        )

    def get_all_open_tickets(self):
        return self.db.fetchall(
            "SELECT * FROM tickets WHERE closed_at IS NULL"
        )

    # ------------------------
    # Members
    # ------------------------

    def add_member(self, ticket_id: int, user_id: int):
        self.db.execute(
            "INSERT OR IGNORE INTO ticket_members (ticket_id, user_id) VALUES (?, ?)",
            (ticket_id, user_id)
        )

    def remove_member(self, ticket_id: int, user_id: int):
        self.db.execute(
            "DELETE FROM ticket_members WHERE ticket_id=? AND user_id=?",
            (ticket_id, user_id)
        )

    def get_ticket_members(self, ticket_id: int):
        rows = self.db.fetchall(
            "SELECT user_id FROM ticket_members WHERE ticket_id=?",
            (ticket_id,)
        )
        return [r["user_id"] for r in rows]