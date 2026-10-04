"""SQLite storage: price history and the watchlist."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

SCHEMA = """
CREATE TABLE IF NOT EXISTS watchlist (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT UNIQUE NOT NULL,
    title TEXT NOT NULL,
    source TEXT NOT NULL,
    target_price REAL,                 -- alert when price <= this (optional)
    added_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS price_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    watch_id INTEGER NOT NULL REFERENCES watchlist(id) ON DELETE CASCADE,
    price REAL NOT NULL,
    mrp REAL,
    checked_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_history_watch ON price_history(watch_id, checked_at);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Store:
    def __init__(self, path: str = "shopper.db"):
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys = ON")
        self.db.executescript(SCHEMA)

    def add_watch(self, product, target_price: float | None = None) -> int:
        self.db.execute(
            "INSERT INTO watchlist(url,title,source,target_price,added_at) VALUES(?,?,?,?,?) "
            "ON CONFLICT(url) DO UPDATE SET target_price=excluded.target_price",
            (product.url, product.title, product.source, target_price, _now()),
        )
        watch_id = self.db.execute("SELECT id FROM watchlist WHERE url=?", (product.url,)).fetchone()[0]
        self.record_price(watch_id, product.price, product.mrp)
        return watch_id

    def record_price(self, watch_id: int, price: float, mrp: float | None = None) -> None:
        self.db.execute(
            "INSERT INTO price_history(watch_id,price,mrp,checked_at) VALUES(?,?,?,?)",
            (watch_id, price, mrp, _now()),
        )
        self.db.commit()

    def watches(self) -> list[sqlite3.Row]:
        return self.db.execute("SELECT * FROM watchlist ORDER BY id").fetchall()

    def remove_watch(self, watch_id: int) -> bool:
        cur = self.db.execute("DELETE FROM watchlist WHERE id=?", (watch_id,))
        self.db.commit()
        return cur.rowcount > 0

    def history(self, watch_id: int) -> list[sqlite3.Row]:
        return self.db.execute(
            "SELECT price, mrp, checked_at FROM price_history WHERE watch_id=? ORDER BY id",
            (watch_id,),
        ).fetchall()

    def stats(self, watch_id: int) -> dict:
        """Lowest / highest / latest / previous price for a watched product."""
        rows = self.history(watch_id)
        prices = [r["price"] for r in rows]
        return {
            "latest": prices[-1],
            "previous": prices[-2] if len(prices) > 1 else None,
            "lowest": min(prices),
            "highest": max(prices),
            "checks": len(prices),
        }
