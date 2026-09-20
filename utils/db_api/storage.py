import sqlite3
from pathlib import Path

from data import config
from utils.i18n import DEFAULT_LANG

# In production DB_PATH points at a mounted volume so the data survives deploys
DB_PATH = Path(config.DB_PATH) if config.DB_PATH else Path(__file__).resolve().parents[2] / "data" / "bot.db"


class Storage:
    def __init__(self, path: Path = DB_PATH):
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(f"""
            CREATE TABLE IF NOT EXISTS subscribers (
                chat_id INTEGER PRIMARY KEY,
                lang TEXT NOT NULL DEFAULT '{DEFAULT_LANG}'
            );
            CREATE TABLE IF NOT EXISTS setups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                signal_time TEXT NOT NULL,      -- end of the signal candle (ISO)
                active INTEGER NOT NULL DEFAULT 1,
                state TEXT NOT NULL             -- Setup.to_json()
            );
            DROP TABLE IF EXISTS trades;        -- replaced by `setups`
        """)
        # Databases created before the language feature have no `lang` column
        columns = [r["name"] for r in self.conn.execute("PRAGMA table_info(subscribers)")]
        if "lang" not in columns:
            self.conn.execute(
                f"ALTER TABLE subscribers ADD COLUMN lang TEXT NOT NULL DEFAULT '{DEFAULT_LANG}'")
        self.conn.commit()

    # --- subscribers ---
    def subscribe(self, chat_id: int):
        self.conn.execute("INSERT OR IGNORE INTO subscribers (chat_id) VALUES (?)", (chat_id,))
        self.conn.commit()

    def unsubscribe(self, chat_id: int):
        self.conn.execute("DELETE FROM subscribers WHERE chat_id = ?", (chat_id,))
        self.conn.commit()

    def subscribers(self) -> list:
        """List of (chat_id, lang)."""
        return [(r["chat_id"], r["lang"]) for r in
                self.conn.execute("SELECT chat_id, lang FROM subscribers")]

    def set_lang(self, chat_id: int, lang: str):
        self.conn.execute(
            "INSERT INTO subscribers (chat_id, lang) VALUES (?, ?) "
            "ON CONFLICT(chat_id) DO UPDATE SET lang = excluded.lang", (chat_id, lang))
        self.conn.commit()

    def get_lang(self, chat_id: int) -> str:
        row = self.conn.execute("SELECT lang FROM subscribers WHERE chat_id = ?", (chat_id,)).fetchone()
        return row["lang"] if row else DEFAULT_LANG

    # --- setups (stored as JSON, see trading/setups.py) ---
    def last_setup(self, symbol: str):
        """Most recent setup row for the symbol (id, active, state), or None."""
        return self.conn.execute(
            "SELECT * FROM setups WHERE symbol = ? ORDER BY id DESC LIMIT 1", (symbol,)).fetchone()

    def add_setup(self, symbol: str, signal_time: str, state: str) -> int:
        cur = self.conn.execute(
            "INSERT INTO setups (symbol, signal_time, state) VALUES (?, ?, ?)", (symbol, signal_time, state))
        self.conn.commit()
        return cur.lastrowid

    def save_setup(self, setup_id: int, state: str, active: bool):
        self.conn.execute("UPDATE setups SET state = ?, active = ? WHERE id = ?",
                          (state, int(active), setup_id))
        self.conn.commit()

    def finished_setups(self) -> list:
        return [r["state"] for r in self.conn.execute("SELECT state FROM setups WHERE active = 0")]
