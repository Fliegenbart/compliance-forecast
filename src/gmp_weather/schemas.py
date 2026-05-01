"""Pydantic schemas for synthetic QMS records and advisory outputs.

These models describe advisory data used by the prototype. They are not GMP
decision records and must not be used to approve, reject, close, release, or
disposition regulated quality items.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


RecordType = Literal[
    "deviation",
    "capa",
    "change_control",
    "audit_observation",
    "training_event",
    "complaint",
]

RecordStatus = Literal["open", "in_progress", "closed", "cancelled"]
RiskLevel = Literal["Low", "Medium", "High", "Critical"]


class AdvisoryBaseModel(BaseModel):
    """Base model for advisory records, not final GMP decision records."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
        revalidate_instances="never",
    )


class Deviation(AdvisoryBaseModel):
    """Advisory deviation data model, not a deviation approval or closure record."""

    deviation_id: str = Field(min_length=1)
    opened_date: date
    closed_date: date | None = None
    due_date: date | None = None
    status: str = Field(min_length=1)
    severity: str = Field(min_length=1)
    site: str = Field(min_length=1)
    department: str = Field(min_length=1)
    process: str = Field(min_length=1)
    product: str | None = Field(default=None, min_length=1)
    batch_id: str | None = Field(default=None, min_length=1)
    equipment_id: str | None = Field(default=None, min_length=1)
    supplier_id: str | None = Field(default=None, min_length=1)
    sop_id: str | None = Field(default=None, min_length=1)
    owner: str = Field(min_length=1)
    short_description: str = Field(min_length=1)
    root_cause_category: str | None = Field(default=None, min_length=1)
    capa_id: str | None = Field(default=None, min_length=1)
    recurrence_flag: bool | None = None

    @model_validator(mode="after")
    def _validate_dates(self) -> Deviation:
        _ensure_not_before(self.closed_date, self.opened_date, "closed_date", "opened_date")
        _ensure_not_before(self.due_date, self.opened_date, "due_date", "opened_date")
        return self


class CAPA(AdvisoryBaseModel):
    """Advisory CAPA data model, not a CAPA approval or effectiveness decision."""

    capa_id: str = Field(min_length=1)
    opened_date: date
    closed_date: date | None = None
    due_date: date | None = None
    status: str = Field(min_length=1)
    site: str = Field(min_length=1)
    department: str = Field(min_length=1)
    process: str = Field(min_length=1)
    owner: str = Field(min_length=1)
    linked_deviation_ids: list[str] = Field(default_factory=list)
    root_cause_category: str | None = Field(default=None, min_length=1)
    action_type: str = Field(min_length=1)
    action_description: str = Field(min_length=1)
    effectiveness_check_due_date: date | None = None
    effectiveness_status: str | None = Field(default=None, min_length=1)

    @field_validator("linked_deviation_ids")
    @classmethod
    def _validate_linked_deviation_ids(cls, values: list[str]) -> list[str]:
        return _clean_string_list(values, "linked_deviation_ids")

    @model_validator(mode="after")
    def _validate_dates(self) -> CAPA:
        _ensure_not_before(self.closed_date, self.opened_date, "closed_date", "opened_date")
        _ensure_not_before(self.due_date, self.opened_date, "due_date", "opened_date")
        _ensure_not_before(
            self.effectiveness_check_due_date,
            self.opened_date,
            "effectiveness_check_due_date",
            "opened_date",
        )
        return self


class AuditFinding(AdvisoryBaseModel):
    """Advisory audit finding data model, not a final audit response."""

    finding_id: str = Field(min_length=1)
    audit_date: date
    finding_type: str = Field(min_length=1)
    severity: str = Field(min_length=1)
    site: str = Field(min_length=1)
    department: str = Field(min_length=1)
    process: str = Field(min_length=1)
    linked_capa_id: str | None = Field(default=None, min_length=1)
    description: str = Field(min_length=1)
    status: str = Field(min_length=1)


class TrainingRecord(AdvisoryBaseModel):
    """Advisory training data model, not a final training compliance decision."""

    training_id: str = Field(min_length=1)
    employee_role: str = Field(min_length=1)
    department: str = Field(min_length=1)
    sop_id: str = Field(min_length=1)
    assigned_date: date
    due_date: date
    completion_date: date | None = None
    status: str = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_dates(self) -> TrainingRecord:
        _ensure_not_before(self.due_date, self.assigned_date, "due_date", "assigned_date")
        _ensure_not_before(
            self.completion_date,
            self.assigned_date,
            "completion_date",
            "assigned_date",
        )
        return self


class ChangeControl(AdvisoryBaseModel):
    """Advisory change control data model, not a validation or change approval record."""

    change_id: str = Field(min_length=1)
    opened_date: date
    target_implementation_date: date | None = None
    closed_date: date | None = None
    status: str = Field(min_length=1)
    site: str = Field(min_length=1)
    department: str = Field(min_length=1)
    process: str = Field(min_length=1)
    affected_sop_ids: list[str] = Field(default_factory=list)
    affected_equipment_ids: list[str] = Field(default_factory=list)
    affected_system_ids: list[str] = Field(default_factory=list)
    validation_impact: bool
    training_impact: bool
    owner: str = Field(min_length=1)
    description: str = Field(min_length=1)

    @field_validator("affected_sop_ids", "affected_equipment_ids", "affected_system_ids")
    @classmethod
    def _validate_affected_ids(cls, values: list[str], info) -> list[str]:
        return _clean_string_list(values, info.field_name)

    @model_validator(mode="after")
    def _validate_dates(self) -> ChangeControl:
        _ensure_not_before(
            self.target_implementation_date,
            self.opened_date,
            "target_implementation_date",
            "opened_date",
        )
        _ensure_not_before(self.closed_date, self.opened_date, "closed_date", "opened_date")
        return self


class SOP(AdvisoryBaseModel):
    """Advisory SOP metadata model, not a document approval or release record."""

    sop_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    department: str = Field(min_length=1)
    process: str = Field(min_length=1)
    version: str = Field(min_length=1)
    effective_date: date
    revision_date: date | None = None
    status: str = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_dates(self) -> SOP:
        _ensure_not_before(self.revision_date, self.effective_date, "revision_date", "effective_date")
        return self


class QMSDataBundle(AdvisoryBaseModel):
    """Read-only bundle of advisory QMS data loaded from synthetic CSV files."""

    deviations: list[Deviation] = Field(default_factory=list)
    capas: list[CAPA] = Field(default_factory=list)
    audit_findings: list[AuditFinding] = Field(default_factory=list)
    training_records: list[TrainingRecord] = Field(default_factory=list)
    change_controls: list[ChangeControl] = Field(default_factory=list)
    sops: list[SOP] = Field(default_factory=list)


class RiskHorizon(str, Enum):
    """Advisory time horizon for risk signals."""

    TWO_WEEKS = "2_weeks"
    FOUR_WEEKS = "4_weeks"
    EIGHT_WEEKS = "8_weeks"
    TWELVE_WEEKS = "12_weeks"


class RiskBand(str, Enum):
    """Advisory risk band, not a final GMP disposition."""

    CLEAR = "clear"
    WATCH = "watch"
    ADVISORY = "advisory"
    STORM = "storm"
    SEVERE_STORM = "severe_storm"


class RiskScore(AdvisoryBaseModel):
    """Explainable advisory risk score, not a GMP decision."""

    score: float = Field(ge=0, le=100)
    band: RiskBand
    horizon: RiskHorizon
    entity_type: str = Field(min_length=1)
    entity_id: str = Field(min_length=1)
    risk_type: str = Field(min_length=1)
    drivers: list[str] = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)

    @field_validator("drivers")
    @classmethod
    def _validate_drivers(cls, values: list[str]) -> list[str]:
        return _clean_string_list(values, "drivers")


class QMSRecord(AdvisoryBaseModel):
    """A synthetic or anonymized source record from a quality system."""

    record_id: str = Field(min_length=1)
    record_type: RecordType
    site: str = Field(min_length=1)
    process_area: str = Field(min_length=1)
    severity: int = Field(ge=1, le=5)
    occurrence: int = Field(ge=1, le=5)
    detection: int = Field(ge=1, le=5)
    status: RecordStatus
    opened_date: date
    due_date: date | None = None
    description: str = Field(min_length=1)

    @field_validator("record_id", "site", "process_area", "description", mode="before")
    @classmethod
    def _strip_text(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip()
        return value

    @field_validator("record_type", "status", mode="before")
    @classmethod
    def _normalize_labels(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip().lower().replace(" ", "_")
        return value


class RiskForecast(AdvisoryBaseModel):
    """Explainable advisory risk signal for one process area."""

    process_area: str = Field(min_length=1)
    risk_score: float = Field(ge=0, le=100)
    risk_level: RiskLevel
    advisory_summary: str = Field(min_length=1)
    source_record_ids: list[str] = Field(min_length=1)
    contributing_factors: list[str] = Field(default_factory=list)
    decision_status: Literal["Advisory only"] = "Advisory only"


class EvidenceSourceRecord(AdvisoryBaseModel):
    """Structured source pointer for an advisory evidence card."""

    domain: str = Field(min_length=1)
    record_id: str = Field(min_length=1)


class EvidenceCard(AdvisoryBaseModel):
    """Evidence for an advisory signal, not a final GMP decision record."""

    card_id: str = Field(min_length=1)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    risk_score: RiskScore
    source_records: list[EvidenceSourceRecord] = Field(min_length=1)
    top_drivers: list[str] = Field(min_length=1)
    rationale: str = Field(min_length=1)
    recommended_human_review: str = Field(min_length=1)
    limitations: list[str] = Field(min_length=1)
    department: str | None = Field(default=None, min_length=1)
    process: str | None = Field(default=None, min_length=1)
    owner: str | None = Field(default=None, min_length=1)

    @field_validator("top_drivers", "limitations")
    @classmethod
    def _validate_non_empty_string_lists(cls, values: list[str], info) -> list[str]:
        return _clean_string_list(values, info.field_name)


def _ensure_not_before(value: date | None, baseline: date, value_name: str, baseline_name: str) -> None:
    if value is not None and value < baseline:
        raise ValueError(f"{value_name} cannot be before {baseline_name}")


def _clean_string_list(values: list[str], field_name: str) -> list[str]:
    cleaned: list[str] = []
    for value in values:
        if not isinstance(value, str):
            raise TypeError(f"{field_name} must contain strings")
        stripped = value.strip()
        if not stripped:
            raise ValueError(f"{field_name} cannot contain blank values")
        cleaned.append(stripped)

    if len(set(cleaned)) != len(cleaned):
        raise ValueError(f"{field_name} cannot contain duplicate values")
    return cleaned
