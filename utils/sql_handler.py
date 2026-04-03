import sqlite3
import threading
from pathlib import Path


class SQLHandler:

    def __init__(self, db_path="data/bot.db"):
        Path("data").mkdir(exist_ok=True)

        self.conn = sqlite3.connect(
            db_path,
            check_same_thread=False
        )

        self.conn.row_factory = sqlite3.Row
        self.cursor = self.conn.cursor()

        self.lock = threading.Lock()

        self.conn.execute("PRAGMA journal_mode=WAL;")
        self.conn.execute("PRAGMA synchronous=NORMAL;")

    def execute(self, query, params=(), return_rowcount=False):
        with self.lock:
            self.cursor.execute(query, params)
            self.conn.commit()
            if return_rowcount:
                return self.cursor.rowcount

    def executemany(self, query, params):
        with self.lock:
            self.cursor.executemany(query, params)
            self.conn.commit()

    def fetchone(self, query, params=()):
        with self.lock:
            self.cursor.execute(query, params)
            return self.cursor.fetchone()

    def fetchall(self, query, params=()):
        with self.lock:
            self.cursor.execute(query, params)
            return self.cursor.fetchall()

    def close(self):
        self.conn.close()
