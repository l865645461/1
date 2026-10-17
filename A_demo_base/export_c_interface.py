"""Export one online-safe A+B replay record for the C module.

Example:
python export_c_interface.py --port-call-id PC_... \
  --replay-time-utc 2024-01-01T00:00:00Z --output current_input.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from b_runtime_adapter import load_predictions, prediction_bundle, utc_timestamp
from c_interface import build_c_interface_record
from data_loader import (SOURCES, get_port_call_bundle, query_visit_ais)
from replay_utils import (current_ais_at_or_before, events_as_replayed,
                          history_at_or_before, port_status_at_or_before,
                          visit_query_window)


def stage_from_observed_events(events):
    kinds = set(events["event_type"].astype(str))
    if "DEP" in kinds:
        return "已离港"
    if "UNB" in kinds:
        return "已离泊"
    if "BER" in kinds:
        return "已靠泊"
    if "ARR" in kinds:
        return "到港后进港／待靠泊"
    if "ANC" in kinds:
        return "锚泊阶段"
    return "到港前航行"


def main():
    parser = argparse.ArgumentParser(description="Export a frozen A+B replay record for C")
    parser.add_argument("--port-call-id", required=True)
    parser.add_argument("--replay-time-utc", required=True,
                        help="Timezone-aware ISO-8601 timestamp, e.g. 2024-01-01T00:00:00Z")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    replay_time = utc_timestamp(args.replay_time_utc)
    bundle = get_port_call_bundle(args.port_call_id)
    observed = events_as_replayed(bundle["events"], replay_time, include_future_truth=False)
    start, end, _, _ = visit_query_window(bundle["events"])
    ais = query_visit_ais(str(bundle["port_call"]["mmsi"]), start, end)
    history = history_at_or_before(ais, replay_time)
    current_ais, ais_age_min = current_ais_at_or_before(history, replay_time)
    port_status, port_status_age_min = port_status_at_or_before(
        SOURCES["port_status"], replay_time)
    vat = load_predictions("vat")
    direct = load_predictions("direct_indirect")
    waiting = load_predictions("arr_to_ber")
    predictions = prediction_bundle(bundle["port_call"], replay_time, vat, direct, waiting)
    payload = build_c_interface_record(
        port_call=bundle["port_call"],
        replay_time_utc=replay_time,
        current_a_status=stage_from_observed_events(observed),
        observed_events=observed,
        predictions=predictions,
        current_ais=current_ais,
        ais_age_min=ais_age_min,
        port_status=port_status,
        port_status_age_min=port_status_age_min,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(
        payload, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    print("Wrote online-safe C interface record: {}".format(args.output))


if __name__ == "__main__":
    main()
