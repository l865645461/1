"""Read-only loader for C's 2026-10-17 wait-driven JIT diagnostic closure."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

import pandas as pd


APP_DIR = Path(__file__).resolve().parent
DIAGNOSTIC_DIR = APP_DIR / "data" / "c_diagnostics"
DIAGNOSTIC_FILES = {
    "summary": DIAGNOSTIC_DIR / "summary_metrics.csv",
    "reconciliation": DIAGNOSTIC_DIR / "candidate_time_reconciliation.csv",
    "availability": DIAGNOSTIC_DIR / "early_decision_availability_diagnostic.csv",
    "b_request": DIAGNOSTIC_DIR / "b_prediction_request.csv",
    "split_audit": DIAGNOSTIC_DIR / "full_chain_split_audit.csv",
    "qc": DIAGNOSTIC_DIR / "diagnostic_qc.json",
}


def _read_csv(name: str) -> pd.DataFrame:
    path = DIAGNOSTIC_FILES[name]
    if not path.is_file():
        raise FileNotFoundError("Missing C diagnostic file: " + str(path))
    return pd.read_csv(path)


def load_c_diagnostics() -> Dict[str, Any]:
    """Load the frozen diagnostic tables without recomputing candidates."""
    summary = _read_csv("summary")
    if summary["metric"].duplicated().any():
        raise ValueError("C diagnostic summary contains duplicate metrics")
    metrics = dict(zip(summary["metric"], summary["value"]))

    reconciliation = _read_csv("reconciliation")
    if reconciliation["candidate_key"].duplicated().any():
        raise ValueError("C diagnostic reconciliation contains duplicate candidate keys")
    if not reconciliation["candidate_key"].str.contains(r"\|").all():
        raise ValueError("Candidate key must combine Port Call ID and candidate UTC")

    availability = _read_csv("availability")
    b_request = _read_csv("b_request")
    split_audit = _read_csv("split_audit")
    qc = json.loads(DIAGNOSTIC_FILES["qc"].read_text(encoding="utf-8"))

    return {
        "summary": summary,
        "metrics": metrics,
        "reconciliation": reconciliation,
        "availability": availability,
        "b_request": b_request,
        "split_audit": split_audit,
        "qc": qc,
    }


def candidates_for_port_call(diagnostics: Dict[str, Any],
                             port_call_id: str) -> pd.DataFrame:
    rows = diagnostics["reconciliation"]
    return rows.loc[rows["port_call_id"].astype(str).eq(str(port_call_id))].copy()
