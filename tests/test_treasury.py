from decimal import Decimal
import unittest

from agents.trader import TraderAgent
from core.treasury import MarketTreasury


class MarketTreasuryTests(unittest.TestCase):
    def test_default_treasuries_have_distinct_wallet_addresses(self):
        first = MarketTreasury()
        second = MarketTreasury()

        self.assertNotEqual(first.cred.identity.agent_id, second.cred.identity.agent_id)
        self.assertNotEqual(first.cred.wallet.address, second.cred.wallet.address)

    def test_explicit_treasury_id_is_deterministic(self):
        first = MarketTreasury(treasury_id="market-treasury-test")
        second = MarketTreasury("market-treasury-test")

        self.assertEqual(first.cred.identity.name, "market-treasury-test")
        self.assertTrue(first.cred.identity.agent_id)
        self.assertEqual(first.cred.identity.agent_id, second.cred.identity.agent_id)
        self.assertEqual(first.cred.wallet.address, second.cred.wallet.address)

    def test_collect_and_pay_transfer_credits_between_real_wallets(self):
        trader = TraderAgent("trader", "conservative", wallet_balance="10.00")
        treasury = MarketTreasury()

        collection = treasury.collect(trader, "2.50", memo="test stake")

        self.assertEqual(trader.wallet_credits, Decimal("7.50"))
        self.assertEqual(treasury.wallet_credits, Decimal("2.50"))
        self.assertEqual(trader.wallet_credits + treasury.wallet_credits, Decimal("10.00"))
        self.assertEqual(collection.recipient, treasury.cred.wallet.address)

        payment = treasury.pay(trader, "2.50", memo="test refund")

        self.assertEqual(trader.wallet_credits, Decimal("10.00"))
        self.assertEqual(treasury.wallet_credits, Decimal("0.00"))
        self.assertEqual(payment.sender, treasury.cred.wallet.address)


if __name__ == "__main__":
    unittest.main()
