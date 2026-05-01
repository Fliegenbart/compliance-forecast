"""Configuration constants and local scoring-rule loading."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SAMPLE_DATA_PATH = PROJECT_ROOT / "data" / "sample" / "synthetic_qms_records.csv"
SAMPLE_DATA_DIR = PROJECT_ROOT / "data" / "sample"
SCORING_CONFIG_PATH = PROJECT_ROOT / "config" / "scoring_rules_v0_1.yaml"
FORECAST_LOG_DIR = PROJECT_ROOT / "logs" / "forecast_runs"
APP_TITLE = "GMP Risiko-Cockpit"
CLIENT_NAME = "Beispiel GmbH"
SAFETY_BOUNDARY = (
    "Advisory prototype only. It must not be used for batch release, CAPA approval, "
    "regulatory filing decisions, or any other final GMP decision."
)


class ScoringConfig(BaseModel):
    """Transparent rule weights for advisory scoring, not GMP acceptance criteria."""

    model_config = ConfigDict(extra="forbid")

    model_version: str = Field(min_length=1)
    risk_bands: dict[str, float]
    deviation_recurrence: dict[str, float]
    capa_failure: dict[str, float]
    training_drift: dict[str, float]
    audit_readiness_gap: dict[str, float]
    backlog_pressure: dict[str, float]
    confidence_penalties: dict[str, float]
    legacy_process_area: dict[str, float]


def load_scoring_config(path: Path | str = SCORING_CONFIG_PATH) -> ScoringConfig:
    """Load transparent scoring weights from the local YAML config file."""

    config_path = Path(path)
    parsed = _parse_simple_yaml(config_path.read_text(encoding="utf-8"))
    return ScoringConfig.model_validate(parsed)


def _parse_simple_yaml(text: str) -> dict[str, Any]:
    """Parse the small YAML subset used for local scoring weights.

    This deliberately supports only top-level keys and one nested mapping level.
    That keeps the prototype dependency-light and avoids external calls.
    """

    data: dict[str, Any] = {}
    current_section: str | None = None
    for raw_line in text.splitlines():
        line = raw_line.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        if not line.startswith(" "):
            key, value = _split_yaml_key_value(line)
            if value == "":
                data[key] = {}
                current_section = key
            else:
                data[key] = _parse_scalar(value)
                current_section = None
            continue

        if current_section is None:
            raise ValueError(f"Nested YAML value without a parent section: {raw_line}")
        key, value = _split_yaml_key_value(line.strip())
        data[current_section][key] = _parse_scalar(value)
    return data


def _split_yaml_key_value(line: str) -> tuple[str, str]:
    if ":" not in line:
        raise ValueError(f"Invalid YAML line: {line}")
    key, value = line.split(":", 1)
    return key.strip(), value.strip()


def _parse_scalar(value: str) -> str | int | float | bool:
    if value.lower() in {"true", "false"}:
        return value.lower() == "true"
    try:
        if "." in value:
            return float(value)
        return int(value)
    except ValueError:
        return value.strip("\"'")
