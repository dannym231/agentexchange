import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path
import unittest

from core.ledger import NullLedger, SQLiteLedger
from core.market import Market, MockPriceFeed


ROOT = Path(__file__).resolve().parents[1]


def fetch_scalar(db_path, sql):
    with sqlite3.connect(db_path) as conn:
        return conn.execute(sql).fetchone()[0]


class LedgerTests(unittest.TestCase):
    def test_default_null_ledger_preserves_existing_behavior(self):
        market = Market([], price_provider=MockPriceFeed())

        self.assertIsInstance(market.ledger, NullLedger)
        round_ = market.open_round()
        close_price, outcome = market.close_round(round_)

        self.assertEqual(round_.open_price, 1000.0)
        self.assertEqual(close_price, 1002.0)
        self.assertEqual(outcome, "UP")

    def test_sqlite_ledger_creates_database_file_and_schema(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "agentexchange.sqlite3"

            ledger = SQLiteLedger(db_path)
            ledger.close()

            self.assertTrue(db_path.exists())
            with sqlite3.connect(db_path) as conn:
                tables = {
                    row[0]
                    for row in conn.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'table'"
                    )
                }
            self.assertEqual(tables, {"runs", "rounds", "price_observations"})

    def test_mock_cli_with_ledger_records_run_rounds_and_price_observations(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "agentexchange.sqlite3"

            subprocess.run(
                [
                    sys.executable,
                    "run_exchange.py",
                    "--mock",
                    "--rounds=3",
                    f"--ledger={db_path}",
                ],
                cwd=ROOT,
                check=True,
                capture_output=True,
                text=True,
            )

            self.assertEqual(fetch_scalar(db_path, "SELECT COUNT(*) FROM runs"), 1)
            self.assertEqual(fetch_scalar(db_path, "SELECT COUNT(*) FROM rounds"), 3)
            self.assertEqual(
                fetch_scalar(db_path, "SELECT COUNT(*) FROM price_observations"),
                6,
            )
            self.assertEqual(
                fetch_scalar(db_path, "SELECT COUNT(*) FROM rounds WHERE state = 'SETTLED'"),
                3,
            )
            self.assertEqual(
                fetch_scalar(
                    db_path,
                    "SELECT COUNT(*) FROM price_observations WHERE source = 'mock'",
                ),
                6,
            )
            self.assertEqual(
                fetch_scalar(
                    db_path,
                    "SELECT COUNT(*) FROM price_observations WHERE kind = 'open'",
                ),
                3,
            )
            self.assertEqual(
                fetch_scalar(
                    db_path,
                    "SELECT COUNT(*) FROM price_observations WHERE kind = 'close'",
                ),
                3,
            )


if __name__ == "__main__":
    unittest.main()
