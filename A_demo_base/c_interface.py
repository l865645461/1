"""Online-safe A+B replay record exported to the C module.

The contract deliberately excludes future A truth, B source ``lead_time_min``
and every evaluation-only field. It is a replay contract, not an operational
port instruction.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

import pandas as pd

from b_runtime_adapter import lead_time_bin_ascii, utc_timestamp


INTERFACE_VERSION = "A_B_C_replay_interface_v1_2_1"
A_INTERFACE_VERSION = "A_INTERFACE_V1.2.1"
B_INTERFACE_VERSION = "B_to_C_A_INTERFACE_V1_2_1_update_20261014"


def _iso(value: Any) -> Optional[str]:
    if value is None or pd.isna(value):
        return None
    return utc_timestamp(value).isoformat()


def _number(value: Any) -> Optional[float]:
    return None if value is None or pd.isna(value) else float(value)


def _prediction_payload(row: Optional[Dict[str, Any]], *, kind: str,
                        replay_time_utc: Any) -> Dict[str, Any]:
    if row is None:
        return {
            "source_type": "unavailable/not_applicable",
            "reason": "no_frozen_prediction_available_at_replay_time",
            "task": kind,
        }
    forbidden = [key for key in row
                 if key == "lead_time_min" or key.endswith("_evaluation_only")]
    if forbidden:
        raise ValueError("Forbidden B fields reached the C interface: " +
                         ", ".join(sorted(forbidden)))
    replay_time = utc_timestamp(replay_time_utc)
    prediction_time = utc_timestamp(row["prediction_time_utc"])
    available_until = utc_timestamp(row["data_available_until_utc"])
    if not (available_until <= prediction_time <= replay_time):
        raise ValueError("B prediction violates replay-time causality")
    payload = {
        "source_type": row.get("source_type", "model_prediction"),
        "task": row.get("task", kind),
        "model_version": row.get("model_version"),
        "model_sha256": row.get("model_sha256"),
        "feature_schema_version": row.get("feature_schema_version"),
        "target_definition": row.get("target_definition"),
        "prediction": _number(row.get("prediction")),
        "unit": row.get("unit"),
        "prediction_time_utc": prediction_time.isoformat(),
        "data_available_until_utc": available_until.isoformat(),
        "prediction_age_min": round(
            (replay_time - prediction_time).total_seconds() / 60.0, 6),
        "lead_time_definition": "elapsed_since_prediction",
        "confidence": _number(row.get("confidence")),
        "uncertainty": row.get("uncertainty"),
        "qc_flag": row.get("qc_flag"),
        "a_input_version": row.get("a_input_version"),
        "a_input_sha256": row.get("a_input_sha256"),
        "a_context_interface_version": row.get(
            "a_context_interface_version", A_INTERFACE_VERSION),
        "historical_precomputed_source": row.get("historical_precomputed_source"),
    }
    if payload["source_type"] != "model_prediction":
        payload["prediction"] = None
    if kind == "VAT" and payload["prediction"] is not None:
        payload["prediction_lead_time_bin"] = lead_time_bin_ascii(
            payload["prediction"])
    if kind == "DIRECT_INDIRECT":
        payload["predicted_class"] = row.get("predicted_class")
        payload["decision_threshold"] = _number(row.get("decision_threshold"))
        payload["probability_calibration"] = "uncalibrated"
    if kind == "ARR_TO_BER":
        payload["arrival_gate_trigger_policy"] = (
            "independent_online_gate_trigger_required; finalized_A_ARR_is_not_a_trigger")
    return payload


def build_c_interface_record(*, port_call: Dict[str, Any], replay_time_utc: Any,
                             current_a_status: str, observed_events: pd.DataFrame,
                             predictions: Dict[str, Optional[Dict[str, Any]]],
                             current_ais: Optional[Dict[str, Any]],
                             ais_age_min: Optional[float],
                             port_status: Optional[Dict[str, Any]],
                             port_status_age_min: Optional[float]) -> Dict[str, Any]:
    """Build one replay-time record without future truth or evaluation labels."""
    replay_time = utc_timestamp(replay_time_utc)
    # A v1.2.1 explicitly distinguishes event occurrence from the time at
    # which a finalized event/linkage became knowable.  The public historical
    # overlay may contain events at or before replay time, but they are not C
    # inputs because verified availability timestamps are absent.
    for event in observed_events.itertuples(index=False):
        event_time = utc_timestamp(event.event_time_utc)
        if event_time > replay_time:
            raise AssertionError("C interface attempted to expose a future event")

    if current_ais is None:
        ais_payload: Dict[str, Any] = {
            "source_type": "unavailable/not_applicable"}
    else:
        ais_time = utc_timestamp(current_ais["timestamp_utc"])
        if ais_time > replay_time:
            raise AssertionError("C interface attempted to expose future AIS")
        ais_payload = {
            "source_type": "observed_fact",
            "ais_time_utc": ais_time.isoformat(),
            "lon": _number(current_ais.get("lon")),
            "lat": _number(current_ais.get("lat")),
            "sog_knots": _number(current_ais.get("sog_knots")),
            "cog_deg": _number(current_ais.get("cog_deg")),
            "heading_deg": _number(current_ais.get("heading_deg")),
            "ais_age_min": _number(ais_age_min),
        }

    if port_status is None:
        status_payload: Dict[str, Any] = {
            "source_type": "unavailable/not_applicable"}
    else:
        snapshot_time = utc_timestamp(port_status["snapshot_time_utc"])
        if snapshot_time > replay_time:
            raise AssertionError("C interface attempted to expose future Port Status")
        status_payload = {
            "source_type": "observed_fact",
            "snapshot_time_utc": snapshot_time.isoformat(),
            "snapshot_age_min": _number(port_status_age_min),
            "unique_inbound_vessels_60m": int(
                port_status.get("unique_inbound_vessels_60m", 0)),
            "unique_outbound_vessels_60m": int(
                port_status.get("unique_outbound_vessels_60m", 0)),
            "raw_crossing_semantics": "repeat_crossing_counts_not_vessel_counts",
        }

    return {
        "interface_version": INTERFACE_VERSION,
        "a_interface_version": A_INTERFACE_VERSION,
        "b_interface_version": B_INTERFACE_VERSION,
        "record_type": "A_B_historical_replay_input_for_C",
        "replay_mode_note": "historical_shadow_replay_not_production_dispatch",
        "port_call_id": str(port_call["port_call_id"]),
        "mmsi": str(port_call["mmsi"]),
        "current_replay_time_utc": replay_time.isoformat(),
        "current_a_status": {
            "source_type": "unavailable/not_applicable",
            "value": None,
            "note": "historical event-derived stage is presentation-only",
        },
        "current_ais": ais_payload,
        "port_status": status_payload,
        "observed_formal_events": [],
        "formal_event_online_input_policy": (
            "disabled_unverified_availability_a_v1_2_1"),
        "vat_prediction": _prediction_payload(
            predictions.get("vat"), kind="VAT", replay_time_utc=replay_time),
        "direct_indirect_prediction": _prediction_payload(
            predictions.get("direct_indirect"), kind="DIRECT_INDIRECT",
            replay_time_utc=replay_time),
        "arr_to_ber_prediction": _prediction_payload(
            predictions.get("arr_to_ber"), kind="ARR_TO_BER",
            replay_time_utc=replay_time),
        "b_runtime_qc": {
            "mode": "frozen_precomputed_prediction_display_only",
            "recompute_allowed": False,
            "blocking_qc_flags": ["demo_does_not_recompute_frozen_B_features"],
        },
        "historical_truth": {
            "source_type": "unavailable/not_applicable",
            "note": "Future and evaluation-only truth is omitted from the C input contract.",
        },
    }
