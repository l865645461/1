"""Read-only adapter for C's frozen A/B v1.2.1 shadow-evaluation outputs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

import pandas as pd


APP_DIR = Path(__file__).resolve().parent
C_RESULTS_DIR = APP_DIR / "data" / "c_results"
C_RESULT_FILES = {
    "early": C_RESULTS_DIR / "early_decision_summary.csv",
    "scenario": C_RESULTS_DIR / "scenario_summary.csv",
    "historical": C_RESULTS_DIR / "historical_wait_validation.csv",
    "report": C_RESULTS_DIR / "scenario_report.json",
    "figure": C_RESULTS_DIR / "C_optimization_figure.png",
}


def _load_csv(name: str) -> pd.DataFrame:
    path = C_RESULT_FILES[name]
    if not path.is_file():
        raise FileNotFoundError("Missing frozen C result: " + str(path))
    frame = pd.read_csv(path)
    if "port_call_id" not in frame.columns:
        raise ValueError("C result has no port_call_id: " + str(path))
    frame["port_call_id"] = frame["port_call_id"].astype(str)
    return frame


def load_c_results() -> Dict[str, Any]:
    early = _load_csv("early")
    scenario = _load_csv("scenario")
    historical = _load_csv("historical")
    for frame in (early, scenario, historical):
        if frame["port_call_id"].duplicated().any():
            raise ValueError("C result contains duplicate port_call_id")
    for frame in (early, scenario):
        frame["decision_time_utc"] = pd.to_datetime(
            frame["decision_time_utc"], utc=True)
    report = json.loads(C_RESULT_FILES["report"].read_text(encoding="utf-8"))
    return {
        "early": early,
        "scenario": scenario,
        "historical": historical,
        "report": report,
        "figure": C_RESULT_FILES["figure"],
    }


def _one(frame: pd.DataFrame, port_call_id: str) -> Optional[Dict[str, Any]]:
    rows = frame.loc[frame["port_call_id"].eq(str(port_call_id))]
    if rows.empty:
        return None
    return rows.iloc[0].to_dict()


def c_result_for_replay(results: Dict[str, Any], port_call_id: str,
                        replay_time_utc: Any) -> Dict[str, Any]:
    """Expose a frozen C result only once its historical decision time is reached."""
    early = _one(results["early"], port_call_id)
    scenario = _one(results["scenario"], port_call_id)
    historical = _one(results["historical"], port_call_id)
    if early is None:
        return {
            "available": False,
            "reason": "port_call_not_in_frozen_c_evaluation_sample",
            "early": None,
            "scenario": None,
            "historical": historical,
        }
    decision_time = pd.Timestamp(early["decision_time_utc"])
    if decision_time.tzinfo is None:
        raise ValueError("C decision_time_utc must be timezone-aware")
    replay_time = pd.Timestamp(replay_time_utc)
    if replay_time.tzinfo is None:
        raise ValueError("Replay time must be timezone-aware")
    if replay_time.tz_convert("UTC") < decision_time.tz_convert("UTC"):
        return {
            "available": False,
            "reason": "c_decision_not_yet_available",
            "decision_time_utc": decision_time,
            "early": None,
            "scenario": None,
            "historical": historical,
        }
    return {
        "available": True,
        "reason": None,
        "decision_time_utc": decision_time,
        "early": early,
        "scenario": scenario,
        "historical": historical,
    }

