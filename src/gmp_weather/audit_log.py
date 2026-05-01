"""Local governance logging for advisory forecast runs.

The log captures reproducibility metadata only. It does not approve, reject,
close, certify, release, qualify, or disposition any GMP item.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from pydantic import BaseModel, ConfigDict, Field

from gmp_weather.schemas import QMSDataBundle


class ForecastRunLog(BaseModel):
    """Metadata for one advisory forecast generation run."""

    model_config = ConfigDict(extra="forbid")

    forecast_run_id: str = Field(min_length=1)
    generated_at: datetime
    as_of_date: date
    model_version: str = Field(min_length=1)
    scoring_config_hash: str = Field(min_length=64, max_length=64)
    source_file_names: list[str]
    source_file_hashes: dict[str, str]
    number_of_records_by_domain: dict[str, int]
    user_selected_filters: dict[str, Any]
    generated_risk_score_count: int = Field(ge=0)
    generated_evidence_card_count: int = Field(ge=0)


def build_read_only_audit_notice(action: str) -> dict[str, str]:
    """Return an in-memory notice instead of changing QMS source records."""

    return {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "action": action,
        "mode": "local read-only prototype",
        "note": "No source data was changed and no GMP decision was made.",
    }


def hash_file(path: Path | str) -> str:
    """Return the SHA-256 hash for a local file."""

    file_path = Path(path)
    digest = hashlib.sha256()
    with file_path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def create_forecast_run_log(
    *,
    generated_at: datetime,
    as_of_date: date,
    model_version: str,
    scoring_config_path: Path | str,
    source_files: Iterable[Path | str],
    bundle: QMSDataBundle,
    user_selected_filters: dict[str, Any],
    generated_risk_score_count: int,
    generated_evidence_card_count: int,
) -> ForecastRunLog:
    """Create reproducibility metadata for one advisory forecast run."""

    source_paths = sorted((Path(path) for path in source_files), key=lambda item: item.name)
    source_file_hashes = {path.name: hash_file(path) for path in source_paths}
    payload = {
        "generated_at": generated_at.isoformat(),
        "as_of_date": as_of_date.isoformat(),
        "model_version": model_version,
        "scoring_config_hash": hash_file(scoring_config_path),
        "source_file_hashes": source_file_hashes,
        "number_of_records_by_domain": _record_counts(bundle),
        "user_selected_filters": user_selected_filters,
        "generated_risk_score_count": generated_risk_score_count,
        "generated_evidence_card_count": generated_evidence_card_count,
    }
    forecast_run_id = "forecast-" + hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()[:16]
    return ForecastRunLog(
        forecast_run_id=forecast_run_id,
        source_file_names=list(source_file_hashes),
        **payload,
    )


def save_forecast_run_log(log: ForecastRunLog, output_folder: Path | str) -> Path:
    """Persist one forecast run log as local JSON."""

    folder = Path(output_folder)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{log.forecast_run_id}.json"
    path.write_text(json.dumps(log.model_dump(mode="json"), indent=2, sort_keys=True), encoding="utf-8")
    return path


def load_forecast_run_logs(output_folder: Path | str) -> list[ForecastRunLog]:
    """Load forecast run logs from a local folder."""

    folder = Path(output_folder)
    if not folder.exists():
        return []
    logs = [
        ForecastRunLog.model_validate_json(path.read_text(encoding="utf-8"))
        for path in sorted(folder.glob("forecast-*.json"))
    ]
    return sorted(logs, key=lambda item: item.generated_at, reverse=True)


def _record_counts(bundle: QMSDataBundle) -> dict[str, int]:
    return {
        "deviations": len(bundle.deviations),
        "capas": len(bundle.capas),
        "audit_findings": len(bundle.audit_findings),
        "training_records": len(bundle.training_records),
        "change_controls": len(bundle.change_controls),
        "sops": len(bundle.sops),
    }
