import json
import math
import unittest
from unittest.mock import Mock, patch

import requests

from agents.base import BaseAgent
from agents.trader import MockTraderAgent, TraderAgent
from core.market import Market, MarketDataError, MockPriceFeed, fetch_eth_price
from core.models import AgentRole, Prediction, Round
from core.treasury import MarketTreasury


class AgentCredAdapterTests(unittest.TestCase):
    def test_base_agent_owns_matching_agentcred_identity(self):
        agent = BaseAgent("adapter", AgentRole.TRADER, wallet_balance="12.50")

        self.assertIsNotNone(agent.cred)
        self.assertEqual(agent.agent_id, "adapter")
        self.assertTrue(agent.cred.identity.agent_id)
        self.assertEqual(agent.cred.identity.name, "adapter")

    def test_wallet_compatibility_uses_agentcred_as_source_of_truth(self):
        agent = BaseAgent("adapter", AgentRole.TRADER, wallet_balance="10.00")

        self.assertEqual(agent.wallet_balance, 10.0)
        self.assertEqual(agent.wallet_credits, agent.cred.wallet.balance)
        treasury = MarketTreasury()

        agent.debit("2.25", treasury.cred.wallet)
        self.assertEqual(agent.wallet_balance, 7.75)
        self.assertEqual(agent.wallet_credits, agent.cred.wallet.balance)

        agent.credit("1.50", treasury.cred.wallet)
        self.assertEqual(agent.wallet_balance, 9.25)
        self.assertEqual(agent.wallet_credits, agent.cred.wallet.balance)


class WalletAndStakeTests(unittest.TestCase):
    def test_debit_rejects_invalid_amounts_and_overdrafts(self):
        trader = TraderAgent("trader", "conservative", wallet_balance=1.0)
        treasury = MarketTreasury()
        for amount in (0.0, -1.0, math.nan, math.inf):
            with self.subTest(amount=amount), self.assertRaises(ValueError):
                trader.debit(amount, treasury.cred.wallet)
        with self.assertRaises(ValueError):
            trader.debit(1.01, treasury.cred.wallet)
        self.assertEqual(trader.wallet_balance, 1.0)

    def test_credit_rejects_invalid_amounts(self):
        trader = TraderAgent("trader", "conservative")
        for amount in (0.0, -1.0, math.nan, math.inf):
            with self.subTest(amount=amount), self.assertRaises(ValueError):
                trader.credit(amount)

    def test_low_balance_trader_is_skipped(self):
        trader = TraderAgent("trader", "conservative", wallet_balance=0.49)
        trader.predict = Mock()
        market = Market([trader])
        predictions = market.collect_predictions(Round(id=1, open_price=100.0))
        self.assertEqual(predictions, [])
        trader.predict.assert_not_called()
        self.assertEqual(trader.wallet_balance, 0.49)

    def test_stake_is_capped_at_wallet_balance(self):
        trader = TraderAgent("trader", "degen", wallet_balance=1.25)
        with patch.object(trader, "think_json", return_value={"direction": "UP", "stake": 5.0}):
            prediction = trader.predict(100.0)
        self.assertEqual(prediction.stake, 1.25)

    def test_invalid_model_stakes_are_rejected(self):
        trader = TraderAgent("trader", "degen")
        for stake in (0.0, -1.0, math.nan, math.inf):
            with self.subTest(stake=stake):
                with patch.object(trader, "think_json", return_value={"direction": "UP", "stake": stake}):
                    with self.assertRaises(ValueError):
                        trader.predict(100.0)

    def test_invalid_prediction_is_skipped_without_debit(self):
        valid = TraderAgent("valid", "momentum", wallet_balance=10.0)
        invalid = TraderAgent("invalid", "degen", wallet_balance=10.0)
        valid.predict = Mock(return_value=Prediction("valid", "UP", 2.0, "test"))
        invalid.predict = Mock(side_effect=ValueError("bad stake"))

        market = Market([valid, invalid])
        predictions = market.collect_predictions(Round(id=1, open_price=100.0))

        self.assertEqual([p.agent_id for p in predictions], ["valid"])
        self.assertEqual(valid.wallet_balance, 8.0)
        self.assertEqual(invalid.wallet_balance, 10.0)
        self.assertEqual(market.treasury.wallet_credits, 2.0)
        self.assertEqual(
            valid.wallet_credits + invalid.wallet_credits + market.treasury.wallet_credits,
            20.0,
        )


class SettlementTests(unittest.TestCase):
    def reputation_event_details(self, trader):
        [event] = trader.cred.reputation.history
        return event, json.loads(event.details)

    def test_no_winner_voids_and_refunds_round(self):
        traders = [
            TraderAgent("one", "momentum", wallet_balance=10.0),
            TraderAgent("two", "contrarian", wallet_balance=10.0),
        ]
        predictions = [
            Prediction("one", "UP", 2.0, "test"),
            Prediction("two", "FLAT", 3.0, "test"),
        ]
        market = Market(traders)
        for trader, prediction in zip(traders, predictions):
            market.treasury.collect(trader, prediction.stake)
        round_ = Round(id=1, open_price=100.0, close_price=99.0, outcome="DOWN", predictions=predictions)

        pnl = market.settle(round_)

        self.assertEqual(pnl, {"one": 0.0, "two": 0.0})
        self.assertEqual([t.wallet_balance for t in traders], [10.0, 10.0])
        self.assertEqual([t.pushes for t in traders], [1, 1])
        self.assertTrue(all(p.outcome == "VOID" and p.pnl == 0.0 for p in predictions))
        self.assertEqual(sum(t.wallet_balance for t in traders), 20.0)
        self.assertEqual(market.treasury.wallet_credits, 0)

    def test_void_refund_records_neutral_reputation_events(self):
        traders = [
            TraderAgent("one", "momentum", wallet_balance=10.0),
            TraderAgent("two", "contrarian", wallet_balance=10.0),
        ]
        predictions = [
            Prediction("one", "UP", 2.0, "test"),
            Prediction("two", "FLAT", 3.0, "test"),
        ]
        market = Market(traders)
        for trader, prediction in zip(traders, predictions):
            market.treasury.collect(trader, prediction.stake)
        round_ = Round(id=7, open_price=100.0, close_price=99.0, outcome="DOWN", predictions=predictions)

        market.settle(round_)

        for trader, direction, stake in (
            (traders[0], "UP", "2.00"),
            (traders[1], "FLAT", "3.00"),
        ):
            event, details = self.reputation_event_details(trader)
            self.assertEqual(event.outcome, "void")
            self.assertEqual(event.category, "agentexchange.prediction")
            self.assertEqual(trader.cred.reputation.score, 50.0)
            self.assertEqual(details["round_id"], 7)
            self.assertEqual(details["prediction_direction"], direction)
            self.assertEqual(details["actual_outcome"], "DOWN")
            self.assertEqual(details["stake"], stake)
            self.assertEqual(details["pnl"], "0.00")
            self.assertEqual(details["result"], "void")
            self.assertEqual(details["wallet_balance_after"], "10.00")

    def test_normal_settlement_preserves_total_credits(self):
        winner = TraderAgent("winner", "momentum", wallet_balance=10.0)
        loser = TraderAgent("loser", "contrarian", wallet_balance=10.0)
        predictions = [
            Prediction("winner", "UP", 2.0, "test"),
            Prediction("loser", "DOWN", 3.0, "test"),
        ]
        market = Market([winner, loser])
        market.treasury.collect(winner, 2.0)
        market.treasury.collect(loser, 3.0)
        round_ = Round(id=1, open_price=100.0, close_price=101.0, outcome="UP", predictions=predictions)

        market.settle(round_)

        self.assertEqual(sum(t.wallet_balance for t in (winner, loser)), 20.0)
        self.assertEqual(winner.wallet_balance, 13.0)
        self.assertEqual(loser.wallet_balance, 7.0)
        self.assertEqual(market.treasury.wallet_credits, 0)

    def test_win_loss_settlement_records_completed_and_failed_reputation_events(self):
        winner = TraderAgent("winner", "momentum", wallet_balance=10.0)
        loser = TraderAgent("loser", "contrarian", wallet_balance=10.0)
        predictions = [
            Prediction("winner", "UP", 2.0, "test"),
            Prediction("loser", "DOWN", 3.0, "test"),
        ]
        market = Market([winner, loser])
        market.treasury.collect(winner, 2.0)
        market.treasury.collect(loser, 3.0)
        round_ = Round(id=3, open_price=100.0, close_price=101.0, outcome="UP", predictions=predictions)

        market.settle(round_)

        winner_event, winner_details = self.reputation_event_details(winner)
        self.assertEqual(winner_event.outcome, "completed")
        self.assertEqual(winner_event.category, "agentexchange.prediction")
        self.assertEqual(winner.cred.reputation.score, 55.0)
        self.assertEqual(
            winner_details,
            {
                "round_id": 3,
                "prediction_direction": "UP",
                "actual_outcome": "UP",
                "stake": "2.00",
                "pnl": "3.00",
                "result": "win",
                "wallet_balance_after": "13.00",
            },
        )

        loser_event, loser_details = self.reputation_event_details(loser)
        self.assertEqual(loser_event.outcome, "failed")
        self.assertEqual(loser_event.category, "agentexchange.prediction")
        self.assertEqual(loser.cred.reputation.score, 40.0)
        self.assertEqual(
            loser_details,
            {
                "round_id": 3,
                "prediction_direction": "DOWN",
                "actual_outcome": "UP",
                "stake": "3.00",
                "pnl": "-3.00",
                "result": "loss",
                "wallet_balance_after": "7.00",
            },
        )

    def test_duplicate_settlement_does_not_duplicate_reputation_history(self):
        winner = TraderAgent("winner", "momentum", wallet_balance=10.0)
        loser = TraderAgent("loser", "contrarian", wallet_balance=10.0)
        predictions = [
            Prediction("winner", "UP", 2.0, "test"),
            Prediction("loser", "DOWN", 3.0, "test"),
        ]
        market = Market([winner, loser])
        market.treasury.collect(winner, 2.0)
        market.treasury.collect(loser, 3.0)
        round_ = Round(id=1, open_price=100.0, close_price=101.0, outcome="UP", predictions=predictions)
        market.settle(round_)

        with self.assertRaisesRegex(ValueError, "closed round"):
            market.settle(round_)

        self.assertEqual(len(winner.cred.reputation.history), 1)
        self.assertEqual(len(loser.cred.reputation.history), 1)


class MarketDataTests(unittest.TestCase):
    @patch("core.market.time.sleep")
    @patch("core.market.requests.get", side_effect=requests.ConnectionError("offline"))
    def test_price_failures_are_wrapped_cleanly(self, get, sleep):
        with self.assertRaisesRegex(MarketDataError, "Unable to fetch"):
            fetch_eth_price()
        self.assertEqual(get.call_count, 3)
        self.assertEqual(sleep.call_count, 2)

    @patch("core.market.fetch_eth_price", side_effect=MarketDataError("offline"))
    def test_open_failure_creates_no_round(self, fetch):
        market = Market([])
        with self.assertRaises(MarketDataError):
            market.open_round()
        self.assertEqual(market.rounds, [])

    @patch("core.market.fetch_eth_price", side_effect=MarketDataError("offline"))
    def test_close_failure_voids_and_refunds(self, fetch):
        trader = TraderAgent("trader", "momentum", wallet_balance=10.0)
        prediction = Prediction("trader", "UP", 2.0, "test")
        market = Market([trader])
        market.treasury.collect(trader, 2.0)
        round_ = Round(id=1, open_price=100.0, predictions=[prediction])

        with self.assertRaises(MarketDataError):
            market.close_round(round_)

        self.assertEqual(trader.wallet_balance, 10.0)
        self.assertEqual(trader.pushes, 1)
        self.assertEqual(prediction.outcome, "VOID")
        self.assertEqual(prediction.pnl, 0.0)
        self.assertEqual(market.treasury.wallet_credits, 0)


class MockModeTests(unittest.TestCase):
    @patch("core.market.requests.get")
    def test_mock_price_feed_never_calls_coingecko(self, get):
        market = Market([], price_provider=MockPriceFeed())
        outcomes = []
        for _ in range(3):
            round_ = market.open_round()
            market.close_round(round_)
            outcomes.append(round_.outcome)

        self.assertEqual(outcomes, ["UP", "DOWN", "FLAT"])
        get.assert_not_called()

    @patch.object(TraderAgent, "think_json", side_effect=AssertionError("Anthropic path called"))
    def test_mock_traders_never_call_anthropic(self, think_json):
        traders = [
            MockTraderAgent("momentum", "momentum"),
            MockTraderAgent("contrarian", "contrarian"),
            MockTraderAgent("conservative", "conservative"),
            MockTraderAgent("degen", "degen"),
        ]
        market = Market(traders, price_provider=MockPriceFeed())
        round_ = market.open_round()
        predictions = market.collect_predictions(round_)

        self.assertEqual(
            [p.direction for p in predictions],
            ["UP", "DOWN", "FLAT", "UP"],
        )
        think_json.assert_not_called()


if __name__ == "__main__":
    unittest.main()
