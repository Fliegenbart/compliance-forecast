"""Advisory agent layer for local GMP risk-prioritization support.

These agents summarize rule-based signals for human QA review. They do not
approve, reject, close, certify, release, qualify, accept, or disposition any
GMP record.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date

from pydantic import BaseModel, ConfigDict, Field, field_validator

from gmp_weather.config import ScoringConfig
from gmp_weather.data_quality import DataQualityReport, assess_data_quality
from gmp_weather.schemas import EvidenceCard, QMSDataBundle, RiskBand, RiskScore
from gmp_weather.scoring import calculate_all_scores


REVIEW_TEXT = "Recommended for human QA review; this is an advisory signal only."
SAFE_LIMITATION = "Based on available data; this agent does not make GMP decisions."
REVIEW_BANDS = {RiskBand.WATCH, RiskBand.ADVISORY, RiskBand.STORM, RiskBand.SEVERE_STORM}
FORBIDDEN_DECISION_PHRASES = (
    "approved",
    "closed by ai",
    "release recommended",
    "capa accepted",
    "root cause confirmed",
)


class AdvisoryAgentModel(BaseModel):
    """Base output model for source-grounded advisory agent signals."""

    model_config = ConfigDict(extra="forbid")

    @field_validator("*", mode="after")
    @classmethod
    def _validate_safe_strings(cls, value):
        if isinstance(value, str):
            _ensure_safe_language(value)
        if isinstance(value, list):
            for item in value:
                if isinstance(item, str):
                    _ensure_safe_language(item)
        return value


class DeviationClusterSignal(AdvisoryAgentModel):
    """Potential recurrence candidate for human QA review."""

    agent_name: str = "DeviationPatternAgent"
    role: str = "identify recurrence candidates"
    cluster_key: str = Field(min_length=1)
    process: str = Field(min_length=1)
    equipment_id: str | None = None
    root_cause_category: str | None = None
    sop_id: str | None = None
    supplier_id: str | None = None
    deviation_count: int = Field(ge=2)
    source_record_ids: list[str] = Field(min_length=1)
    rationale: str = Field(min_length=1)
    recommended_for_human_review: str = REVIEW_TEXT
    limitations: list[str] = Field(default_factory=lambda: [SAFE_LIMITATION])


class AgentReviewSignal(AdvisoryAgentModel):
    """Generic source-grounded advisory review signal."""

    agent_name: str = Field(min_length=1)
    role: str = Field(min_length=1)
    signal_type: str = Field(min_length=1)
    entity_type: str = Field(min_length=1)
    entity_id: str = Field(min_length=1)
    score: float | None = None
    band: str | None = None
    department: str | None = None
    process: str | None = None
    source_record_ids: list[str] = Field(min_length=1)
    rationale: str = Field(min_length=1)
    recommended_for_human_review: str = REVIEW_TEXT
    limitations: list[str] = Field(default_factory=lambda: [SAFE_LIMITATION])


class ForecastBriefing(AdvisoryAgentModel):
    """Short advisory priority briefing for weekly human QA review."""

    agent_name: str = "ForecastBriefingAgent"
    role: str = "summarize advisory signals with safe wording"
    briefing_text: str = Field(min_length=1)
    source_record_ids: list[str] = Field(min_length=1)
    recommended_for_human_review: str = REVIEW_TEXT
    limitations: list[str] = Field(default_factory=lambda: [SAFE_LIMITATION])


class DataQualityAgent:
    """Identify data readiness issues for human QA review."""

    role = "identify data readiness issues"

    def run(self, bundle: QMSDataBundle, as_of_date: date | None = None) -> DataQualityReport:
        return assess_data_quality(bundle, as_of=as_of_date)


class DeviationPatternAgent:
    """Identify potential recurrence candidates among similar deviations."""

    role = "identify recurrence candidates"

    def run(self, bundle: QMSDataBundle, minimum_cluster_size: int = 2) -> list[DeviationClusterSignal]:
        grouped: dict[tuple[str, str, str, str, str], list[str]] = defaultdict(list)
        for deviation in bundle.deviations:
            key = (
                deviation.process,
                deviation.equipment_id or "No equipment ID",
                deviation.root_cause_category or "No root cause category",
                deviation.sop_id or "No SOP ID",
                deviation.supplier_id or "No supplier ID",
            )
            grouped[key].append(deviation.deviation_id)

        clusters: list[DeviationClusterSignal] = []
        for (process, equipment_id, root_cause, sop_id, supplier_id), source_ids in grouped.items():
            if len(source_ids) < minimum_cluster_size:
                continue
            clusters.append(
                DeviationClusterSignal(
                    cluster_key="|".join([process, equipment_id, root_cause, sop_id, supplier_id]),
                    process=process,
                    equipment_id=None if equipment_id.startswith("No ") else equipment_id,
                    root_cause_category=None if root_cause.startswith("No ") else root_cause,
                    sop_id=None if sop_id.startswith("No ") else sop_id,
                    supplier_id=None if supplier_id.startswith("No ") else supplier_id,
                    deviation_count=len(source_ids),
                    source_record_ids=sorted(source_ids),
                    rationale=(
                        "Based on available data, these deviations share process, equipment, "
                        "root cause category, SOP, or supplier attributes and are recurrence candidates "
                        "for human QA review."
                    ),
                )
            )
        return sorted(clusters, key=lambda item: item.deviation_count, reverse=True)


class CAPAReviewSignalAgent:
    """Identify elevated CAPA failure or recurrence-risk signals."""

    role = "identify elevated CAPA failure or recurrence risk"

    def run(
        self,
        bundle: QMSDataBundle,
        as_of_date: date | None = None,
        scoring_config: ScoringConfig | None = None,
    ) -> list[AgentReviewSignal]:
        reference_date = as_of_date or date.today()
        scores = calculate_all_scores(bundle, reference_date, scoring_config=scoring_config)
        signals: list[AgentReviewSignal] = []
        for score in scores:
            if score.risk_type != "capa_failure" or score.band not in REVIEW_BANDS:
                continue
            source_ids = _source_ids_for_capa(score.entity_id, bundle)
            context = _capa_context(score.entity_id, bundle)
            signals.append(
                AgentReviewSignal(
                    agent_name="CAPAReviewSignalAgent",
                    role=self.role,
                    signal_type="capa_review_signal",
                    entity_type=score.entity_type,
                    entity_id=score.entity_id,
                    score=score.score,
                    band=score.band.value,
                    department=context["department"],
                    process=context["process"],
                    source_record_ids=source_ids,
                    rationale=(
                        "Based on available data, this CAPA has an elevated risk signal and should be "
                        "reviewed by QA for adequacy of actions and effectiveness-check design."
                    ),
                )
            )
        return signals


class TrainingDriftAgent:
    """Identify department/SOP combinations with training drift risk."""

    role = "identify department and SOP training drift risk"

    def run(
        self,
        bundle: QMSDataBundle,
        as_of_date: date | None = None,
        scoring_config: ScoringConfig | None = None,
    ) -> list[AgentReviewSignal]:
        reference_date = as_of_date or date.today()
        scores = calculate_all_scores(bundle, reference_date, scoring_config=scoring_config)
        signals: list[AgentReviewSignal] = []
        for score in scores:
            if score.risk_type != "training_drift" or score.band not in REVIEW_BANDS:
                continue
            department, process, sop_id = _split_entity(score.entity_id, 3)
            source_ids = _training_source_ids(department, process, sop_id, bundle)
            signals.append(
                AgentReviewSignal(
                    agent_name="TrainingDriftAgent",
                    role=self.role,
                    signal_type="training_drift_signal",
                    entity_type=score.entity_type,
                    entity_id=score.entity_id,
                    score=score.score,
                    band=score.band.value,
                    department=department,
                    process=process,
                    source_record_ids=source_ids,
                    rationale=(
                        "Based on available data, this department and SOP combination shows a training "
                        "drift signal that is recommended for training owner and QA review."
                    ),
                )
            )
        return signals


class AuditReadinessAgent:
    """Identify audit readiness gap signals."""

    role = "identify audit readiness gap signals"

    def run(
        self,
        bundle: QMSDataBundle,
        as_of_date: date | None = None,
        scoring_config: ScoringConfig | None = None,
    ) -> list[AgentReviewSignal]:
        reference_date = as_of_date or date.today()
        scores = calculate_all_scores(bundle, reference_date, scoring_config=scoring_config)
        signals: list[AgentReviewSignal] = []
        for score in scores:
            if score.risk_type != "audit_readiness_gap" or score.band not in REVIEW_BANDS:
                continue
            department, process = _split_entity(score.entity_id, 2)
            signals.append(
                AgentReviewSignal(
                    agent_name="AuditReadinessAgent",
                    role=self.role,
                    signal_type="audit_readiness_gap_signal",
                    entity_type=score.entity_type,
                    entity_id=score.entity_id,
                    score=score.score,
                    band=score.band.value,
                    department=department,
                    process=process,
                    source_record_ids=_department_process_source_ids(department, process, bundle),
                    rationale=(
                        "Based on available data, this department and process combination shows an "
                        "audit readiness gap signal for QA review."
                    ),
                )
            )
        return signals


class ForecastBriefingAgent:
    """Summarize advisory signals with safe weekly priority wording."""

    role = "summarize advisory signals with safe wording"

    def run(self, risk_scores: list[RiskScore], evidence_cards: list[EvidenceCard], limit: int = 3) -> ForecastBriefing:
        top_scores = sorted(risk_scores, key=lambda item: item.score, reverse=True)[:limit]
        source_ids = _briefing_source_ids(evidence_cards, top_scores)
        if not top_scores:
            return ForecastBriefing(
                briefing_text=(
                    "Weekly advisory priority briefing: based on available data, no elevated risk "
                    "signals were generated for the current filters. Routine human QA review remains expected."
                ),
                source_record_ids=["no-elevated-signal"],
            )

        band_counts = Counter(score.band.value for score in risk_scores)
        top_items = ", ".join(f"{score.risk_type} {score.entity_id} ({score.score:.1f})" for score in top_scores)
        briefing = (
            "Weekly advisory priority briefing: based on available data, the current prioritization shows "
            f"{len(risk_scores)} advisory risk signals, including {band_counts.get(RiskBand.STORM.value, 0)} high "
            f"and {band_counts.get(RiskBand.SEVERE_STORM.value, 0)} critical signals. "
            f"Top signals for review: {top_items}. These signals are recommended for human QA review "
            "and are not GMP decisions."
        )
        return ForecastBriefing(briefing_text=briefing, source_record_ids=source_ids)


def _source_ids_for_capa(capa_id: str, bundle: QMSDataBundle) -> list[str]:
    source_ids = [capa_id]
    for capa in bundle.capas:
        if capa.capa_id == capa_id:
            source_ids.extend(capa.linked_deviation_ids)
    source_ids.extend(finding.finding_id for finding in bundle.audit_findings if finding.linked_capa_id == capa_id)
    return _dedupe(source_ids)


def _capa_context(capa_id: str, bundle: QMSDataBundle) -> dict[str, str | None]:
    for capa in bundle.capas:
        if capa.capa_id == capa_id:
            return {"department": capa.department, "process": capa.process}
    return {"department": None, "process": None}


def _training_source_ids(department: str, process: str, sop_id: str, bundle: QMSDataBundle) -> list[str]:
    source_ids: list[str] = []
    source_ids.extend(record.training_id for record in bundle.training_records if record.department == department and record.sop_id == sop_id)
    source_ids.extend(record.sop_id for record in bundle.sops if record.sop_id == sop_id)
    source_ids.extend(record.deviation_id for record in bundle.deviations if record.sop_id == sop_id or record.process == process)
    source_ids.extend(
        record.change_id
        for record in bundle.change_controls
        if record.training_impact and (sop_id in record.affected_sop_ids or record.process == process)
    )
    return _dedupe(source_ids)


def _department_process_source_ids(department: str, process: str, bundle: QMSDataBundle) -> list[str]:
    source_ids: list[str] = []
    source_ids.extend(record.deviation_id for record in bundle.deviations if record.department == department and record.process == process)
    source_ids.extend(record.capa_id for record in bundle.capas if record.department == department and record.process == process)
    source_ids.extend(record.finding_id for record in bundle.audit_findings if record.department == department and record.process == process)
    source_ids.extend(record.change_id for record in bundle.change_controls if record.department == department and record.process == process)
    source_ids.extend(record.sop_id for record in bundle.sops if record.department == department and record.process == process)
    return _dedupe(source_ids)


def _briefing_source_ids(evidence_cards: list[EvidenceCard], top_scores: list[RiskScore]) -> list[str]:
    top_keys = {(score.risk_type, score.entity_id) for score in top_scores}
    source_ids: list[str] = []
    for card in evidence_cards:
        key = (card.risk_score.risk_type, card.risk_score.entity_id)
        if key in top_keys:
            source_ids.extend(source.record_id for source in card.source_records)
    if not source_ids:
        source_ids.extend(score.entity_id for score in top_scores)
    return _dedupe(source_ids)


def _split_entity(entity_id: str, expected_parts: int) -> list[str]:
    parts = entity_id.split("|")
    if len(parts) < expected_parts:
        parts.extend([""] * (expected_parts - len(parts)))
    return parts[:expected_parts]


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            deduped.append(value)
    return deduped


def _ensure_safe_language(value: str) -> None:
    normalized = value.lower()
    for phrase in FORBIDDEN_DECISION_PHRASES:
        if phrase in normalized:
            raise ValueError(f"Agent output contains forbidden decision phrase: {phrase}")
