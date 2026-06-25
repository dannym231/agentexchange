from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from uuid import uuid4


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class NullLedger:
    """No-op ledger used when persistence is not configured."""

    def record_run(self, *, run_id: str, price_source: str, round_duration: int) -> None:
        pass

    def record_round(self, *, run_id: str, round_) -> None:
        pass

    def update_round(self, *, run_id: str, round_) -> None:
        pass

    def record_price_observation(
        self,
        *,
        run_id: str,
        round_id: int,
        kind: str,
        price,
        source: str,
    ) -> None:
        pass


class SQLiteLedger:
    """Small SQLite audit ledger for AgentExchange runs and prices."""

    def __init__(self, path):
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self._ensure_schema()

    def close(self) -> None:
        self.conn.close()

    def _ensure_schema(self) -> None:
        with self.conn:
            self.conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    price_source TEXT NOT NULL,
                    round_duration INTEGER NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS rounds (
                    run_id TEXT NOT NULL,
                    round_id INTEGER NOT NULL,
                    state TEXT NOT NULL,
                    open_price TEXT NOT NULL,
                    close_price TEXT,
                    outcome TEXT,
                    created_at REAL NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (run_id, round_id),
                    FOREIGN KEY (run_id) REFERENCES runs(run_id)
                );

                CREATE TABLE IF NOT EXISTS price_observations (
                    observation_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    round_id INTEGER NOT NULL,
                    kind TEXT NOT NULL,
                    price TEXT NOT NULL,
                    source TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (run_id, round_id) REFERENCES rounds(run_id, round_id)
                );
                """
            )

    def record_run(self, *, run_id: str, price_source: str, round_duration: int) -> None:
        with self.conn:
            self.conn.execute(
                """
                INSERT OR IGNORE INTO runs (
                    run_id, price_source, round_duration, created_at
                ) VALUES (?, ?, ?, ?)
                """,
                (run_id, price_source, round_duration, utc_now()),
            )

    def record_round(self, *, run_id: str, round_) -> None:
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO rounds (
                    run_id, round_id, state, open_price, close_price, outcome,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                self._round_values(run_id, round_),
            )

    def update_round(self, *, run_id: str, round_) -> None:
        with self.conn:
            self.conn.execute(
                """
                UPDATE rounds
                SET state = ?,
                    open_price = ?,
                    close_price = ?,
                    outcome = ?,
                    created_at = ?,
                    updated_at = ?
                WHERE run_id = ? AND round_id = ?
                """,
                (
                    round_.state.value,
                    str(round_.open_price),
                    None if round_.close_price is None else str(round_.close_price),
                    round_.outcome,
                    round_.created_at,
                    utc_now(),
                    run_id,
                    round_.id,
                ),
            )

    def record_price_observation(
        self,
        *,
        run_id: str,
        round_id: int,
        kind: str,
        price,
        source: str,
    ) -> None:
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO price_observations (
                    observation_id, run_id, round_id, kind, price, source, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (uuid4().hex, run_id, round_id, kind, str(price), source, utc_now()),
            )

    def _round_values(self, run_id: str, round_) -> tuple:
        return (
            run_id,
            round_.id,
            round_.state.value,
            str(round_.open_price),
            None if round_.close_price is None else str(round_.close_price),
            round_.outcome,
            round_.created_at,
            utc_now(),
        )
