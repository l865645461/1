import unittest

import pandas as pd

from b_runtime_adapter import load_predictions, prediction_bundle
from c_interface import build_c_interface_record
from c_results import c_result_for_replay, load_c_results


def all_keys(value):
    if isinstance(value, dict):
        for key, item in value.items():
            yield key
            yield from all_keys(item)
    elif isinstance(value, list):
        for item in value:
            yield from all_keys(item)


class DemoContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.vat = load_predictions("vat")
        cls.direct = load_predictions("direct_indirect")
        cls.wait = load_predictions("arr_to_ber")
        cls.c_results = load_c_results()

    def test_b_tables_are_online_safe(self):
        for frame in (self.vat, self.direct, self.wait):
            self.assertNotIn("lead_time_min", frame.columns)
            self.assertFalse(any(name.endswith("_evaluation_only")
                                 for name in frame.columns))
            self.assertTrue((frame["data_available_until_utc"] <=
                             frame["prediction_time_utc"]).all())

    def test_arr_to_ber_requires_independent_trigger(self):
        source = self.wait.iloc[0]
        port_call = {
            "port_call_id": source["port_call_id"],
            "arr_event_id": source["event_id"],
        }
        replay = pd.Timestamp(source["prediction_time_utc"])
        bundle = prediction_bundle(port_call, replay, self.vat, self.direct,
                                   self.wait, arrival_gate_trigger=False)
        record = bundle["arr_to_ber"]
        self.assertIsNotNone(record)
        self.assertEqual(record["source_type"], "unavailable/not_applicable")
        self.assertIsNone(record["prediction"])
        self.assertEqual(record["qc_flag"],
                         "independent_arrival_gate_trigger_required")

    def test_c_interface_has_no_future_or_evaluation_fields(self):
        source = self.direct.iloc[0]
        replay = pd.Timestamp(source["prediction_time_utc"])
        port_call = {
            "port_call_id": source["port_call_id"],
            "mmsi": "000000000",
            "arr_event_id": source["event_id"],
        }
        bundle = prediction_bundle(port_call, replay, self.vat, self.direct,
                                   self.wait, arrival_gate_trigger=False)
        events = pd.DataFrame(columns=[
            "event_id", "event_type", "event_time_utc",
            "confidence_level", "qc_flag"])
        record = build_c_interface_record(
            port_call=port_call,
            replay_time_utc=replay,
            current_a_status="pre_arrival",
            observed_events=events,
            predictions=bundle,
            current_ais=None,
            ais_age_min=None,
            port_status=None,
            port_status_age_min=None,
        )
        keys = list(all_keys(record))
        self.assertNotIn("lead_time_min", keys)
        self.assertFalse(any(key.endswith("_evaluation_only") for key in keys))
        self.assertEqual(record["interface_version"],
                         "A_B_C_replay_interface_v1_2_1")
        self.assertEqual(record["observed_formal_events"], [])
        self.assertEqual(
            record["formal_event_online_input_policy"],
            "disabled_unverified_availability_a_v1_2_1")

    def test_c_frozen_counts_and_block(self):
        early = self.c_results["early"]
        scenarios = self.c_results["scenario"]
        self.assertEqual(len(early), 262)
        self.assertEqual(len(scenarios), 171)
        self.assertEqual((scenarios["research_recommendation"] ==
                          "影子推荐降速").sum(), 75)
        self.assertFalse((early["operational_advice"] == "建议执行").any())
        blocked = early.loc[~early["b_recompute_allowed"]].iloc[0]
        self.assertEqual(str(blocked["mmsi"]), "211886810")
        state = c_result_for_replay(
            self.c_results, blocked["port_call_id"], blocked["decision_time_utc"])
        self.assertIsNone(state["scenario"])


if __name__ == "__main__":
    unittest.main()
