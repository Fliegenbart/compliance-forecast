"""Structured data quality checks for advisory GMP data.

These checks support human review. They do not make GMP decisions, close
records, approve CAPAs, or certify data fitness for regulated use.
"""

from __future__ import annotations

from collections import Counter
from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from gmp_weather.schemas import (
    CAPA,
    QMSDataBundle,
    TrainingRecord,
)


IssueSeverity = Literal["critical", "high", "medium", "low", "info"]

EXPECTED_STATUSES = {
    "deviations": {"open", "in_progress", "closed", "cancelled"},
    "capas": {"open", "in_progress", "closed", "cancelled"},
    "audit_findings": {"open", "in_progress", "closed", "cancelled"},
    "training_records": {"assigned", "in_progress", "completed", "overdue", "cancelled"},
    "change_controls": {"open", "assessment", "implementation", "QA review", "closed", "cancelled"},
    "sops": {"effective", "under_revision", "retired", "draft"},
}

OPEN_STATUSES = {"open", "in_progress", "assigned", "assessment", "implementation", "QA review", "overdue"}
CLOSED_STATUSES = {"closed", "completed", "retired"}


class DataQualityIssue(BaseModel):
    """One advisory data quality issue linked to a domain and record ID."""

    model_config = ConfigDict(extra="forbid")

    domain: str = Field(min_length=1)
    record_id: str = Field(min_length=1)
    severity: IssueSeverity
    message: str = Field(min_length=1)


class DataQualityReport(BaseModel):
    """Structured advisory report for data readiness review."""

    model_config = ConfigDict(extra="forbid")

    total_records_by_domain: dict[str, int]
    issue_count_by_severity: dict[str, int]
    issue_list: list[DataQualityIssue]
    data_readiness_score: int = Field(ge=0, le=100)
    recommended_for_human_review: str = (
        "QA data owner should review data readiness issues before relying on advisory signals."
    )


def assess_data_quality(bundle: QMSDataBundle, as_of: date | None = None) -> DataQualityReport:
    """Assess loaded QMS data and return a structured advisory report."""

    reference_date = as_of or date.today()
    issues: list[DataQualityIssue] = []
    total_records_by_domain = {
        "deviations": len(bundle.deviations),
        "capas": len(bundle.capas),
        "audit_findings": len(bundle.audit_findings),
        "training_records": len(bundle.training_records),
        "change_controls": len(bundle.change_controls),
        "sops": len(bundle.sops),
    }

    domain_records: dict[str, list[Any]] = {
        "deviations": bundle.deviations,
        "capas": bundle.capas,
        "audit_findings": bundle.audit_findings,
        "training_records": bundle.training_records,
        "change_controls": bundle.change_controls,
        "sops": bundle.sops,
    }

    for domain, records in domain_records.items():
        issues.extend(_missing_required_value_issues(domain, records))
        issues.extend(_duplicate_id_issues(domain, records))
        issues.extend(_inconsistent_status_issues(domain, records))
        issues.extend(_date_issues(domain, records, reference_date))

    sop_ids = {record.sop_id for record in bundle.sops}
    deviation_ids = {record.deviation_id for record in bundle.deviations}

    issues.extend(_unknown_sop_reference_issues(bundle, sop_ids))
    issues.extend(_missing_deviation_reference_issues(bundle.capas, deviation_ids))

    issue_count_by_severity = dict(Counter(issue.severity for issue in issues))
    data_readiness_score = _readiness_score(issues, sum(total_records_by_domain.values()))
    return DataQualityReport(
        total_records_by_domain=total_records_by_domain,
        issue_count_by_severity=issue_count_by_severity,
        issue_list=issues,
        data_readiness_score=data_readiness_score,
    )


def _missing_required_value_issues(domain: str, records: list[Any]) -> list[DataQualityIssue]:
    issues: list[DataQualityIssue] = []
    for record in records:
        record_id = _record_id(domain, record)
        required_fields = _required_fields(type(record))
        for field_name in required_fields:
            value = getattr(record, field_name, None)
            if value is None or (isinstance(value, str) and not value.strip()):
                issues.append(
                    DataQualityIssue(
                        domain=domain,
                        record_id=record_id,
                        severity="critical",
                        message=f"{field_name} is missing.",
                    )
                )
    return issues


def _duplicate_id_issues(domain: str, records: list[Any]) -> list[DataQualityIssue]:
    ids = [_record_id(domain, record) for record in records]
    duplicates = sorted(record_id for record_id, count in Counter(ids).items() if count > 1)
    return [
        DataQualityIssue(
            domain=domain,
            record_id=record_id,
            severity="critical",
            message=f"Duplicate ID {record_id} found in {domain}.",
        )
        for record_id in duplicates
    ]


def _inconsistent_status_issues(domain: str, records: list[Any]) -> list[DataQualityIssue]:
    expected = EXPECTED_STATUSES[domain]
    issues: list[DataQualityIssue] = []
    for record in records:
        status = getattr(record, "status", None)
        if status and status not in expected:
            issues.append(
                DataQualityIssue(
                    domain=domain,
                    record_id=_record_id(domain, record),
                    severity="medium",
                    message=f"status '{status}' is not in the expected set for {domain}.",
                )
            )
    return issues


def _date_issues(domain: str, records: list[Any], as_of: date) -> list[DataQualityIssue]:
    issues: list[DataQualityIssue] = []
    for record in records:
        record_id = _record_id(domain, record)
        issues.extend(_invalid_date_type_issues(domain, record_id, record))

        opened_date = getattr(record, "opened_date", None)
        due_date = getattr(record, "due_date", None)
        closed_date = getattr(record, "closed_date", None)
        status = getattr(record, "status", None)

        if _is_date(opened_date) and _is_date(due_date) and due_date < opened_date:
            issues.append(
                DataQualityIssue(
                    domain=domain,
                    record_id=record_id,
                    severity="high",
                    message="due_date is before opened_date.",
                )
            )

        if status in CLOSED_STATUSES and hasattr(record, "closed_date") and closed_date is None:
            issues.append(
                DataQualityIssue(
                    domain=domain,
                    record_id=record_id,
                    severity="high",
                    message=f"{domain} record is closed but has no closed_date.",
                )
            )

        if status in OPEN_STATUSES and _is_date(due_date) and due_date < as_of:
            issues.append(
                DataQualityIssue(
                    domain=domain,
                    record_id=record_id,
                    severity="medium",
                    message=f"Record is overdue as of {as_of.isoformat()}.",
                )
            )

        if isinstance(record, TrainingRecord):
            if _is_date(record.completion_date) and record.completion_date < record.assigned_date:
                issues.append(
                    DataQualityIssue(
                        domain=domain,
                        record_id=record_id,
                        severity="high",
                        message="completion_date is before assigned_date.",
                    )
                )
            if record.due_date < record.assigned_date:
                issues.append(
                    DataQualityIssue(
                        domain=domain,
                        record_id=record_id,
                        severity="high",
                        message="due_date is before assigned_date.",
                    )
                )
    return issues


def _invalid_date_type_issues(domain: str, record_id: str, record: Any) -> list[DataQualityIssue]:
    issues: list[DataQualityIssue] = []
    for field_name, value in vars(record).items():
        if not field_name.endswith("_date") or value is None:
            continue
        if not _is_date(value):
            issues.append(
                DataQualityIssue(
                    domain=domain,
                    record_id=record_id,
                    severity="critical",
                    message=f"{field_name} is not a valid date.",
                )
            )
    return issues


def _unknown_sop_reference_issues(bundle: QMSDataBundle, sop_ids: set[str]) -> list[DataQualityIssue]:
    issues: list[DataQualityIssue] = []
    for deviation in bundle.deviations:
        if deviation.sop_id and deviation.sop_id not in sop_ids:
            issues.append(
                DataQualityIssue(
                    domain="deviations",
                    record_id=deviation.deviation_id,
                    severity="medium",
                    message=f"Deviation references unknown SOP {deviation.sop_id}.",
                )
            )

    for training in bundle.training_records:
        if training.sop_id not in sop_ids:
            issues.append(
                DataQualityIssue(
                    domain="training_records",
                    record_id=training.training_id,
                    severity="high",
                    message=f"Training record references missing SOP {training.sop_id}.",
                )
            )

    for change in bundle.change_controls:
        for sop_id in change.affected_sop_ids:
            if sop_id not in sop_ids:
                issues.append(
                    DataQualityIssue(
                        domain="change_controls",
                        record_id=change.change_id,
                        severity="medium",
                        message=f"Change control references unknown SOP {sop_id}.",
                    )
                )
    return issues


def _missing_deviation_reference_issues(capas: list[CAPA], deviation_ids: set[str]) -> list[DataQualityIssue]:
    issues: list[DataQualityIssue] = []
    for capa in capas:
        for deviation_id in capa.linked_deviation_ids:
            if deviation_id not in deviation_ids:
                issues.append(
                    DataQualityIssue(
                        domain="capas",
                        record_id=capa.capa_id,
                        severity="high",
                        message=f"CAPA references missing deviation {deviation_id}.",
                    )
                )
    return issues


def _readiness_score(issues: list[DataQualityIssue], total_records: int) -> int:
    penalty_by_severity = {
        "critical": 12,
        "high": 6,
        "medium": 2,
        "low": 1,
        "info": 0,
    }
    weighted_issues = sum(penalty_by_severity[issue.severity] for issue in issues)
    denominator = max(total_records, 1)
    penalty = round((weighted_issues / denominator) * 100)
    return max(0, 100 - penalty)


def _required_fields(model_cls: type) -> list[str]:
    if not hasattr(model_cls, "model_fields"):
        return []
    return [field_name for field_name, field_info in model_cls.model_fields.items() if field_info.is_required()]


def _record_id(domain: str, record: Any) -> str:
    id_fields = {
        "deviations": "deviation_id",
        "capas": "capa_id",
        "audit_findings": "finding_id",
        "training_records": "training_id",
        "change_controls": "change_id",
        "sops": "sop_id",
    }
    return str(getattr(record, id_fields[domain], "UNKNOWN"))


def _is_date(value: Any) -> bool:
    return isinstance(value, date)
