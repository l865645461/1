import unittest

import pandas as pd

from c_results import c_result_for_replay, load_c_results


class CResultsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.results = load_c_results()

    def test_frozen_counts_and_operational_boundary(self):
        early = self.results["early"]
        scenarios = self.results["scenario"]
        historical = self.results["historical"]
        self.assertEqual(len(early), 262)
        self.assertEqual(len(scenarios), 171)
        self.assertEqual((scenarios["research_recommendation"] ==
                          "影子推荐降速").sum(), 75)
        self.assertEqual((historical["historical_berth_jit_evidence_status"] ==
                          "verified_in_historical_replay").sum(), 6)
        self.assertFalse((early["operational_advice"] == "建议执行").any())
        self.assertFalse((scenarios["operational_advice"] == "建议执行").any())

    def test_result_is_hidden_before_c_decision_time(self):
        row = self.results["early"].iloc[0]
        decision = pd.Timestamp(row["decision_time_utc"])
        state = c_result_for_replay(
            self.results, row["port_call_id"], decision - pd.Timedelta(seconds=1))
        self.assertFalse(state["available"])
        self.assertEqual(state["reason"], "c_decision_not_yet_available")

    def test_result_is_visible_at_c_decision_time(self):
        row = self.results["early"].iloc[0]
        state = c_result_for_replay(
            self.results, row["port_call_id"], row["decision_time_utc"])
        self.assertTrue(state["available"])
        self.assertEqual(state["early"]["port_call_id"], row["port_call_id"])

    def test_blocked_record_never_has_scenario(self):
        early = self.results["early"]
        blocked = early.loc[~early["b_recompute_allowed"]].iloc[0]
        state = c_result_for_replay(
            self.results, blocked["port_call_id"], blocked["decision_time_utc"])
        self.assertTrue(state["available"])
        self.assertIsNone(state["scenario"])
        self.assertEqual(blocked["b_blocking_qc_flags"],
                         "insufficient_crop_coverage")


if __name__ == "__main__":
    unittest.main()
