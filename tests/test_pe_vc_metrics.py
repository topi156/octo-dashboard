import unittest

from pe_vc_metrics import (
    format_report_currency,
    format_report_multiple,
    format_report_percent,
    normalize_quarterly_report_metrics,
)


class ThriveCapitalAccountStatementTests(unittest.TestCase):
    def test_report_formatting_helpers(self):
        self.assertEqual(format_report_multiple(2.1486446512974466), "2.15x")
        self.assertEqual(format_report_multiple(0), "0.00x")
        self.assertEqual(format_report_percent(None), "N/A")
        self.assertEqual(format_report_percent(0.1234), "0.1%")
        self.assertEqual(format_report_currency(-1247, accounting=True), "($1,247)")

    def test_growth_a_statement_derives_net_metrics_and_reconciles(self):
        result = normalize_quarterly_report_metrics({
            "nav": 341396,
            "capital_contributions": 158889,
            "investment_contributions": 157143,
            "expense_contributions": 1746,
            "distributions": "\u2014",
            "other_expenses": -1247,
            "unrealized_gain_loss": 245006,
            "special_reallocation": -61252,
            "tvpi": 0,
            "net_moic": 0,
            "irr": None,
        })

        self.assertEqual(result["nav"], 341396)
        self.assertEqual(result["paid_in_capital"], 158889)
        self.assertEqual(result["investment_contributions"], 157143)
        self.assertEqual(result["expense_contributions"], 1746)
        self.assertEqual(result["distributions"], 0)
        self.assertEqual(result["total_value"], 341396)
        self.assertEqual(result["total_realized"], 0)
        self.assertEqual(result["total_unrealized"], 341396)
        self.assertEqual(result["unrealized_gain_loss"], 245006)
        self.assertEqual(result["special_reallocation"], -61252)
        self.assertAlmostEqual(result["dpi"], 0.0, places=4)
        self.assertAlmostEqual(result["tvpi"], 341396 / 158889, places=4)
        self.assertAlmostEqual(result["net_moic"], 341396 / 158889, places=4)
        self.assertIsNone(result["irr"])
        self.assertAlmostEqual(result["capital_account_reconciliation"], 341396, places=2)
        self.assertAlmostEqual(result["capital_account_reconciliation_difference"], 0, places=2)

    def test_growth_statement_normalizes_negative_paid_in_and_derives_moic(self):
        result = normalize_quarterly_report_metrics({
            "nav": 605740,
            "contributions_to_date": -292670,
            "capital_contributions": 292670,
            "distributions": "-",
            "management_fee": -6476,
            "organizational_costs": -1194,
            "other_expenses": -5572,
            "unrealized_gain_loss": 430669,
            "special_reallocation": -104357,
            "tvpi": 0,
            "gross_moic": 0,
            "gross_irr": 0,
            "net_irr": 0,
        })

        self.assertEqual(result["nav"], 605740)
        self.assertEqual(result["paid_in_capital"], 292670)
        self.assertEqual(result["distributions"], 0)
        self.assertEqual(result["total_value"], 605740)
        self.assertEqual(result["total_realized"], 0)
        self.assertEqual(result["total_unrealized"], 605740)
        self.assertEqual(result["unrealized_gain_loss"], 430669)
        self.assertEqual(result["special_reallocation"], -104357)
        self.assertAlmostEqual(result["dpi"], 0.0, places=4)
        self.assertAlmostEqual(result["tvpi"], 605740 / 292670, places=4)
        self.assertAlmostEqual(result["net_moic"], 605740 / 292670, places=4)
        self.assertIsNone(result["gross_moic"])
        self.assertIsNone(result["gross_irr"])
        self.assertIsNone(result["net_irr"])
        self.assertAlmostEqual(result["capital_account_reconciliation"], 605740, places=2)
        self.assertAlmostEqual(result["capital_account_reconciliation_difference"], 0, places=2)


if __name__ == "__main__":
    unittest.main()
