import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path
import unittest

from agents.trader import MockTraderAgent
from core.ledger import NullLedger, SQLiteLedger
from core.market import Market, MockPriceFeed


ROOT = Path(__file__).resolve().parents[1]


def fetch_scalar(db_path, sql):
    with sqlite3.connect(db_path) as conn:
        return conn.execute(sql).fetchone()[0]


class FailingTreasury:
    def collect(self, trader, amount, memo=None):
        raise RuntimeError("stake transfer failed")


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
            self.assertEqual(tables, {"runs", "rounds", "price_observations", "predictions"})

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
            self.assertEqual(fetch_scalar(db_path, "SELECT COUNT(*) FROM predictions"), 12)
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
            self.assertEqual(
                fetch_scalar(
                    db_path,
                    "SELECT COUNT(*) FROM predictions WHERE stake_transaction_id IS NOT NULL",
                ),
                12,
            )
            self.assertEqual(
                fetch_scalar(db_path, "SELECT COUNT(*) FROM predictions WHERE state = 'PENDING'"),
                12,
            )
            self.assertEqual(
                fetch_scalar(db_path, "SELECT COUNT(*) FROM predictions WHERE pnl IS NULL"),
                12,
            )
            self.assertEqual(
                fetch_scalar(db_path, "SELECT COUNT(*) FROM predictions WHERE typeof(stake) = 'text'"),
                12,
            )

    def test_failed_stake_transfer_does_not_record_prediction(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "agentexchange.sqlite3"
            ledger = SQLiteLedger(db_path)
            trader = MockTraderAgent("momentum-01", "momentum", wallet_balance=20.0)
            market = Market(
                [trader],
                price_provider=MockPriceFeed(),
                treasury=FailingTreasury(),
                ledger=ledger,
            )

            round_ = market.open_round()
            with self.assertRaisesRegex(RuntimeError, "stake transfer failed"):
                market.collect_predictions(round_)

            self.assertEqual(round_.predictions, [])
            self.assertEqual(fetch_scalar(db_path, "SELECT COUNT(*) FROM predictions"), 0)
            ledger.close()


if __name__ == "__main__":
    unittest.main()
