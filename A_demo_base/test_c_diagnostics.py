import unittest

import pandas as pd

from c_diagnostics import candidates_for_port_call, load_c_diagnostics


class CDiagnosticClosureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = load_c_diagnostics()

    def metric(self, name):
        return float(self.data["metrics"][name])

    def test_frozen_diagnostic_counts(self):
        self.assertEqual(self.metric("diagnostic_population"), 34)
        self.assertEqual(self.metric("candidate_times_found_by_fixed_AIS_screen"), 4)
        self.assertEqual(
            self.metric("candidate_times_with_complete_30min_A_context"), 2)
        self.assertEqual(self.metric("B_exact_PortCall_candidateUTC_matches"), 2)
        self.assertEqual(self.metric("B_same_PortCall_candidateUTC_mismatches"), 0)
        self.assertEqual(
            self.metric("currently_eligible_wait_driven_JIT_samples"), 0)

    def test_candidate_joint_keys_are_unique_and_exact_checks_match(self):
        rows = self.data["reconciliation"]
        self.assertFalse(rows["candidate_key"].duplicated().any())
        exact = rows.loc[rows["joint_key_match_status"].eq("exact_joint_key_match")]
        self.assertEqual(len(exact), 2)
        self.assertTrue(pd.to_numeric(exact["b_candidate_time_delta_min"]).eq(0).all())

    def test_477454100_original_and_alternate_times_are_not_conflated(self):
        port_call_id = "PC_202401_477454100_20240111T042304"
        row = candidates_for_port_call(self.data, port_call_id).iloc[0]
        self.assertEqual(row["c_candidate_time_utc"], "2024-01-10T13:36:54Z")
        self.assertEqual(row["b_checked_candidate_time_utc"],
                         "2024-01-10T13:36:54Z")
        self.assertEqual(row["b_other_same_port_call_candidate_times_utc"],
                         "2024-01-10T14:54:42Z")

    def test_scope_prevents_overclaiming(self):
        qc = self.data["qc"]
        self.assertFalse(qc["selection_uses_final_truth"])
        self.assertFalse(qc["models_retrained"])
        self.assertFalse(qc["fuel_or_co2_recomputed"])
        self.assertEqual(
            qc["candidate_selection_scope"],
            "offline_retrospective_fixed_24h_screen_not_realtime_trigger")
        self.assertEqual(
            qc["zero_eligible_scope"],
            "this_packaged_crop_and_fixed_screen_only_not_full_AIS")


if __name__ == "__main__":
    unittest.main()
