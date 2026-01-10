import unittest

from kalshi_arbitrage.arbitrage import Strategy, find_up_down_arbs
from kalshi_arbitrage.models import TopOfBook


class TestUpDownArbitrage(unittest.TestCase):
    def test_buy_yes_both_detected(self) -> None:
        up = TopOfBook(yes_ask=0.40, yes_ask_size=10)
        down = TopOfBook(yes_ask=0.50, yes_ask_size=8)
        opps = find_up_down_arbs(up, down, fee_per_contract=0.0, min_profit_per_pair=0.0)
        self.assertTrue(any(o.strategy == Strategy.BUY_YES_BOTH for o in opps))
        best = next(o for o in opps if o.strategy == Strategy.BUY_YES_BOTH)
        self.assertAlmostEqual(best.profit_per_pair, 0.10, places=9)
        self.assertEqual(best.max_pairs_at_top, 8)

    def test_fee_can_eliminate_arb(self) -> None:
        up = TopOfBook(yes_ask=0.40, yes_ask_size=10)
        down = TopOfBook(yes_ask=0.50, yes_ask_size=8)
        # Two legs => 2 fees. Profit would be 0.10 - 2*0.06 = -0.02.
        opps = find_up_down_arbs(up, down, fee_per_contract=0.06, min_profit_per_pair=0.0)
        self.assertFalse(any(o.strategy == Strategy.BUY_YES_BOTH for o in opps))

    def test_buy_no_both_detected(self) -> None:
        up = TopOfBook(no_ask=0.30, no_ask_size=5)
        down = TopOfBook(no_ask=0.60, no_ask_size=7)
        opps = find_up_down_arbs(up, down, fee_per_contract=0.0, min_profit_per_pair=0.0)
        self.assertTrue(any(o.strategy == Strategy.BUY_NO_BOTH for o in opps))
        best = next(o for o in opps if o.strategy == Strategy.BUY_NO_BOTH)
        self.assertAlmostEqual(best.profit_per_pair, 0.10, places=9)
        self.assertEqual(best.max_pairs_at_top, 5)


if __name__ == "__main__":
    unittest.main()

