"""Read-only CSV loader for synthetic QMS sample data."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
from pydantic import BaseModel, ValidationError

from gmp_weather.schemas import (
    AuditFinding,
    CAPA,
    ChangeControl,
    Deviation,
    QMSDataBundle,
    QMSRecord,
    SOP,
    TrainingRecord,
)


REQUIRED_COLUMNS = {
    "record_id",
    "record_type",
    "site",
    "process_area",
    "severity",
    "occurrence",
    "detection",
    "status",
    "opened_date",
    "due_date",
    "description",
}

DOMAIN_LOADERS = {
    "deviations": {
        "filename": "deviations.csv",
        "model": Deviation,
        "list_fields": set(),
        "date_fields": {"opened_date", "closed_date", "due_date"},
    },
    "capas": {
        "filename": "capas.csv",
        "model": CAPA,
        "list_fields": {"linked_deviation_ids"},
        "date_fields": {"opened_date", "closed_date", "due_date", "effectiveness_check_due_date"},
    },
    "audit_findings": {
        "filename": "audit_findings.csv",
        "model": AuditFinding,
        "list_fields": set(),
        "date_fields": {"audit_date"},
    },
    "training_records": {
        "filename": "training_records.csv",
        "model": TrainingRecord,
        "list_fields": set(),
        "date_fields": {"assigned_date", "due_date", "completion_date"},
    },
    "change_controls": {
        "filename": "change_controls.csv",
        "model": ChangeControl,
        "list_fields": {"affected_sop_ids", "affected_equipment_ids", "affected_system_ids"},
        "date_fields": {"opened_date", "target_implementation_date", "closed_date"},
    },
    "sops": {
        "filename": "sops.csv",
        "model": SOP,
        "list_fields": set(),
        "date_fields": {"effective_date", "revision_date"},
    },
}


def load_qms_records(csv_path: str | Path) -> list[QMSRecord]:
    """Load QMS records from a local CSV file without modifying the file."""

    path = Path(csv_path)
    if not path.exists():
        raise FileNotFoundError(f"QMS data file not found: {path}")

    frame = pd.read_csv(path)
    missing = sorted(REQUIRED_COLUMNS.difference(frame.columns))
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(missing)}")

    frame = frame.copy()
    frame["opened_date"] = pd.to_datetime(frame["opened_date"], errors="raise").dt.date
    frame["due_date"] = pd.to_datetime(frame["due_date"], errors="coerce").dt.date

    records: list[QMSRecord] = []
    for row in frame.to_dict(orient="records"):
        cleaned = {key: _clean_value(value) for key, value in row.items()}
        records.append(QMSRecord(**cleaned))
    return records


def load_qms_data_bundle(folder_path: str | Path) -> QMSDataBundle:
    """Load all domain CSV files from a folder into a read-only QMS data bundle."""

    folder = Path(folder_path)
    if not folder.exists():
        raise FileNotFoundError(f"QMS data folder not found: {folder}")
    if not folder.is_dir():
        raise NotADirectoryError(f"QMS data path is not a folder: {folder}")

    loaded_domains: dict[str, list[BaseModel]] = {}
    for domain, spec in DOMAIN_LOADERS.items():
        filename = str(spec["filename"])
        path = folder / filename
        if not path.exists():
            raise FileNotFoundError(f"Missing required QMS data file: {filename}")

        model_cls = spec["model"]
        if not isinstance(model_cls, type) or not issubclass(model_cls, BaseModel):
            raise TypeError(f"Invalid model for domain {domain}")

        loaded_domains[domain] = _load_domain_csv(
            path=path,
            model_cls=model_cls,
            list_fields=set(spec["list_fields"]),
            date_fields=set(spec["date_fields"]),
        )

    return QMSDataBundle(**loaded_domains)


def records_to_frame(records: list[QMSRecord]) -> pd.DataFrame:
    """Convert records to a display-friendly pandas DataFrame."""

    return pd.DataFrame([record.model_dump() for record in records])


def bundle_domain_to_frame(records: list[BaseModel]) -> pd.DataFrame:
    """Convert loaded domain records to a display-friendly DataFrame."""

    return pd.DataFrame([record.model_dump(mode="json") for record in records])


def _load_domain_csv(
    path: Path,
    model_cls: type[BaseModel],
    list_fields: set[str],
    date_fields: set[str],
) -> list[BaseModel]:
    frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    required_columns, optional_columns = _model_columns(model_cls)
    missing_required = sorted(required_columns.difference(frame.columns))
    if missing_required:
        raise ValueError(f"{path.name} missing required columns: {', '.join(missing_required)}")

    frame = frame.copy()
    for column in sorted(optional_columns.difference(frame.columns)):
        frame[column] = ""

    records: list[BaseModel] = []
    for row_number, row in enumerate(frame.to_dict(orient="records"), start=2):
        cleaned = _clean_domain_row(row, list_fields=list_fields, date_fields=date_fields)
        try:
            records.append(model_cls(**cleaned))
        except ValidationError as error:
            raise ValueError(f"{path.name} row {row_number} failed schema validation: {error}") from error
    return records


def _model_columns(model_cls: type[BaseModel]) -> tuple[set[str], set[str]]:
    required: set[str] = set()
    optional: set[str] = set()
    for field_name, field_info in model_cls.model_fields.items():
        if field_info.is_required():
            required.add(field_name)
        else:
            optional.add(field_name)
    return required, optional


def _clean_domain_row(row: dict[str, Any], list_fields: set[str], date_fields: set[str]) -> dict[str, Any]:
    cleaned: dict[str, Any] = {}
    for key, value in row.items():
        if key in list_fields:
            cleaned[key] = _parse_list(value)
        elif key in date_fields:
            cleaned[key] = _parse_optional_date(value)
        elif isinstance(value, str) and value == "":
            cleaned[key] = None
        else:
            cleaned[key] = value
    return cleaned


def _parse_list(value: Any) -> list[str]:
    if value is None or value == "":
        return []
    if isinstance(value, list):
        return value
    return [item.strip() for item in str(value).split("|") if item.strip()]


def _parse_optional_date(value: Any):
    if value is None or value == "":
        return None
    try:
        return pd.to_datetime(value, errors="raise").date()
    except Exception as error:
        raise ValueError(f"invalid date value '{value}'") from error


def _clean_value(value: Any) -> Any:
    if pd.isna(value):
        return None
    return value
