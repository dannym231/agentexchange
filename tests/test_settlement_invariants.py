from decimal import Decimal
import unittest

from agents.trader import TraderAgent
from core.market import Market, calculate_settlement, determine_outcome
from core.models import Prediction, PredictionState, Round, RoundState


def prediction(agent_id, direction, stake):
    return Prediction(agent_id, direction, stake, "invariant test")


class PureSettlementTests(unittest.TestCase):
    def test_flat_threshold_is_inclusive(self):
        self.assertEqual(determine_outcome(100.0, 100.15), "FLAT")
        self.assertEqual(determine_outcome(100.0, 99.85), "FLAT")

    def test_proportional_rounding_conserves_every_cent(self):
        predictions = [
            prediction("winner-a", "UP", "0.50"),
            prediction("winner-b", "UP", "1.00"),
            prediction("loser", "DOWN", "1.00"),
        ]

        lines = calculate_settlement(predictions, "UP")

        self.assertEqual(sum((line.credit for line in lines), Decimal("0.00")), Decimal("2.50"))
        self.assertEqual(sum((line.pnl for line in lines), Decimal("0.00")), Decimal("0.00"))
        self.assertEqual([line.pnl for line in lines[:2]], [Decimal("0.33"), Decimal("0.67")])
        self.assertTrue(all(p.state == PredictionState.PENDING for p in predictions))

    def test_up_down_and_flat_outcomes_select_the_correct_winner(self):
        cases = [
            (100.0, 101.0, "UP"),
            (100.0, 99.0, "DOWN"),
            (100.0, 100.1, "FLAT"),
        ]
        for open_price, close_price, expected in cases:
            with self.subTest(expected=expected):
                actual = determine_outcome(open_price, close_price)
                predictions = [prediction(direction, direction, "1.00") for direction in ("UP", "DOWN", "FLAT")]
                lines = calculate_settlement(predictions, actual)
                winners = [line.agent_id for line in lines if line.state == PredictionState.WON]
                self.assertEqual(actual, expected)
                self.assertEqual(winners, [expected])


class AppliedSettlementInvariantTests(unittest.TestCase):
    def make_market(self, directions, stakes):
        traders = [TraderAgent(str(i), "conservative", wallet_balance="10.00") for i in range(len(stakes))]
        predictions = []
        for trader, direction, stake in zip(traders, directions, stakes):
            item = prediction(trader.agent_id, direction, stake)
            trader.debit(item.stake)
            predictions.append(item)
        return traders, Market(traders), predictions

    def test_total_credits_are_conserved_and_wallets_remain_non_negative(self):
        traders, market, predictions = self.make_market(
            ["UP", "UP", "DOWN"], ["0.50", "1.00", "5.00"]
        )
        round_ = Round(1, 100.0, 101.0, "UP", predictions)

        market.settle(round_)

        self.assertEqual(sum((t.wallet_credits for t in traders), Decimal("0.00")), Decimal("30.00"))
        self.assertTrue(all(t.wallet_credits >= 0 for t in traders))
        self.assertEqual(round_.state, RoundState.SETTLED)

    def test_no_winner_round_is_voided_and_fully_refunded(self):
        traders, market, predictions = self.make_market(["UP", "FLAT"], ["2.00", "3.00"])
        round_ = Round(1, 100.0, 99.0, "DOWN", predictions)

        market.settle(round_)

        self.assertEqual([t.wallet_credits for t in traders], [Decimal("10.00"), Decimal("10.00")])
        self.assertEqual(round_.state, RoundState.VOID)
        self.assertTrue(all(p.state == PredictionState.VOID for p in predictions))

    def test_duplicate_settlement_is_rejected_without_changing_balances(self):
        traders, market, predictions = self.make_market(["UP", "DOWN"], ["2.00", "3.00"])
        round_ = Round(1, 100.0, 101.0, "UP", predictions)
        market.settle(round_)
        balances = [t.wallet_credits for t in traders]

        with self.assertRaisesRegex(ValueError, "closed round"):
            market.settle(round_)

        self.assertEqual([t.wallet_credits for t in traders], balances)


if __name__ == "__main__":
    unittest.main()
