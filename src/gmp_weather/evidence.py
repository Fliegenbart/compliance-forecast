"""Evidence card generation for advisory GMP risk scores.

Evidence cards explain why a transparent score deserves human review. They do
not claim regulatory non-compliance, determine root cause, approve records, or
replace QA judgment.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from gmp_weather.schemas import (
    CAPA,
    Deviation,
    EvidenceCard,
    EvidenceSourceRecord,
    QMSDataBundle,
    RiskBand,
    RiskScore,
)


EVIDENCE_BANDS = {RiskBand.ADVISORY, RiskBand.STORM, RiskBand.SEVERE_STORM}


def generate_evidence_cards(
    risk_scores: list[RiskScore],
    bundle: QMSDataBundle,
    generated_at: datetime | None = None,
) -> list[EvidenceCard]:
    """Generate source-grounded cards for medium and high advisory risk scores."""

    timestamp = generated_at or datetime.now(timezone.utc)
    cards: list[EvidenceCard] = []
    for risk_score in risk_scores:
        if risk_score.band not in EVIDENCE_BANDS:
            continue

        source_records = _source_records_for_score(risk_score, bundle)
        if not source_records:
            source_records = [EvidenceSourceRecord(domain=risk_score.entity_type, record_id=risk_score.entity_id)]

        context = _context_for_score(risk_score, bundle)
        top_drivers = risk_score.drivers[:3]
        source_ids = ", ".join(source.record_id for source in source_records)
        rationale = _rationale(risk_score, top_drivers, source_ids)

        cards.append(
            EvidenceCard(
                card_id=f"EC-{_slug(risk_score.risk_type)}-{_slug(risk_score.entity_id)}",
                generated_at=timestamp,
                risk_score=risk_score,
                source_records=source_records,
                top_drivers=top_drivers,
                rationale=rationale,
                recommended_human_review=_recommended_review(risk_score.risk_type),
                limitations=_limitations(),
                department=context.get("department"),
                process=context.get("process"),
                owner=context.get("owner"),
            )
        )
    return cards


def evidence_cards_to_frame(cards: list[EvidenceCard]):
    """Convert evidence cards into a table-friendly pandas DataFrame."""

    import pandas as pd

    return pd.DataFrame(
        [
            {
                "card_id": card.card_id,
                "generated_at": card.generated_at.isoformat(),
                "score": card.risk_score.score,
                "band": card.risk_score.band.value,
                "entity_type": card.risk_score.entity_type,
                "entity_id": card.risk_score.entity_id,
                "horizon": card.risk_score.horizon.value,
                "risk_type": card.risk_score.risk_type,
                "department": card.department or "",
                "process": card.process or "",
                "owner": card.owner or "",
                "top_drivers": " | ".join(card.top_drivers),
                "source_records": _format_sources(card.source_records),
                "rationale": card.rationale,
                "recommended_human_review": card.recommended_human_review,
                "limitations": " | ".join(card.limitations),
            }
            for card in cards
        ]
    )


def _source_records_for_score(risk_score: RiskScore, bundle: QMSDataBundle) -> list[EvidenceSourceRecord]:
    if risk_score.risk_type == "deviation_recurrence":
        return _deviation_sources(risk_score.entity_id, bundle)
    if risk_score.risk_type == "capa_failure":
        return _capa_sources(risk_score.entity_id, bundle)
    if risk_score.risk_type == "training_drift":
        return _training_drift_sources(risk_score.entity_id, bundle)
    if risk_score.risk_type == "audit_readiness_gap":
        return _department_process_sources(risk_score.entity_id, bundle)
    if risk_score.risk_type == "backlog_pressure":
        return _backlog_sources(risk_score, bundle)
    return []


def _deviation_sources(deviation_id: str, bundle: QMSDataBundle) -> list[EvidenceSourceRecord]:
    sources = [EvidenceSourceRecord(domain="deviations", record_id=deviation_id)]
    deviation = _find_by_id(bundle.deviations, "deviation_id", deviation_id)
    if isinstance(deviation, Deviation) and deviation.capa_id:
        sources.append(EvidenceSourceRecord(domain="capas", record_id=deviation.capa_id))
    return _dedupe_sources(sources)


def _capa_sources(capa_id: str, bundle: QMSDataBundle) -> list[EvidenceSourceRecord]:
    sources = [EvidenceSourceRecord(domain="capas", record_id=capa_id)]
    capa = _find_by_id(bundle.capas, "capa_id", capa_id)
    if isinstance(capa, CAPA):
        sources.extend(EvidenceSourceRecord(domain="deviations", record_id=item) for item in capa.linked_deviation_ids)
    sources.extend(
        EvidenceSourceRecord(domain="audit_findings", record_id=finding.finding_id)
        for finding in bundle.audit_findings
        if finding.linked_capa_id == capa_id
    )
    return _dedupe_sources(sources)


def _training_drift_sources(entity_id: str, bundle: QMSDataBundle) -> list[EvidenceSourceRecord]:
    department, process, sop_id = _split_entity(entity_id, 3)
    sources: list[EvidenceSourceRecord] = []
    sources.extend(
        EvidenceSourceRecord(domain="training_records", record_id=record.training_id)
        for record in bundle.training_records
        if record.department == department and record.sop_id == sop_id
    )
    sources.extend(EvidenceSourceRecord(domain="sops", record_id=sop.sop_id) for sop in bundle.sops if sop.sop_id == sop_id)
    sources.extend(
        EvidenceSourceRecord(domain="deviations", record_id=deviation.deviation_id)
        for deviation in bundle.deviations
        if deviation.sop_id == sop_id or deviation.process == process
    )
    sources.extend(
        EvidenceSourceRecord(domain="change_controls", record_id=change.change_id)
        for change in bundle.change_controls
        if change.training_impact and (sop_id in change.affected_sop_ids or change.process == process)
    )
    return _dedupe_sources(sources[:25])


def _department_process_sources(entity_id: str, bundle: QMSDataBundle) -> list[EvidenceSourceRecord]:
    department, process = _split_entity(entity_id, 2)
    sources: list[EvidenceSourceRecord] = []
    sources.extend(
        EvidenceSourceRecord(domain="deviations", record_id=record.deviation_id)
        for record in bundle.deviations
        if record.department == department and record.process == process
    )
    sources.extend(
        EvidenceSourceRecord(domain="capas", record_id=record.capa_id)
        for record in bundle.capas
        if record.department == department and record.process == process
    )
    sources.extend(
        EvidenceSourceRecord(domain="audit_findings", record_id=record.finding_id)
        for record in bundle.audit_findings
        if record.department == department and record.process == process
    )
    sources.extend(
        EvidenceSourceRecord(domain="change_controls", record_id=record.change_id)
        for record in bundle.change_controls
        if record.department == department and record.process == process
    )
    sources.extend(
        EvidenceSourceRecord(domain="sops", record_id=record.sop_id)
        for record in bundle.sops
        if record.department == department and record.process == process
    )
    return _dedupe_sources(sources[:25])


def _backlog_sources(risk_score: RiskScore, bundle: QMSDataBundle) -> list[EvidenceSourceRecord]:
    sources: list[EvidenceSourceRecord] = []
    if risk_score.entity_type == "department":
        sources.extend(
            EvidenceSourceRecord(domain="deviations", record_id=record.deviation_id)
            for record in bundle.deviations
            if record.department == risk_score.entity_id
        )
        sources.extend(
            EvidenceSourceRecord(domain="capas", record_id=record.capa_id)
            for record in bundle.capas
            if record.department == risk_score.entity_id
        )
    elif risk_score.entity_type == "owner":
        sources.extend(
            EvidenceSourceRecord(domain="deviations", record_id=record.deviation_id)
            for record in bundle.deviations
            if record.owner == risk_score.entity_id
        )
        sources.extend(
            EvidenceSourceRecord(domain="capas", record_id=record.capa_id)
            for record in bundle.capas
            if record.owner == risk_score.entity_id
        )
    return _dedupe_sources(sources[:25])


def _context_for_score(risk_score: RiskScore, bundle: QMSDataBundle) -> dict[str, str | None]:
    if risk_score.risk_type == "deviation_recurrence":
        deviation = _find_by_id(bundle.deviations, "deviation_id", risk_score.entity_id)
        return _record_context(deviation)
    if risk_score.risk_type == "capa_failure":
        capa = _find_by_id(bundle.capas, "capa_id", risk_score.entity_id)
        return _record_context(capa)
    if risk_score.risk_type == "training_drift":
        department, process, _ = _split_entity(risk_score.entity_id, 3)
        return {"department": department, "process": process, "owner": None}
    if risk_score.risk_type == "audit_readiness_gap":
        department, process = _split_entity(risk_score.entity_id, 2)
        return {"department": department, "process": process, "owner": None}
    if risk_score.risk_type == "backlog_pressure":
        if risk_score.entity_type == "department":
            return {"department": risk_score.entity_id, "process": None, "owner": None}
        if risk_score.entity_type == "owner":
            return {"department": None, "process": None, "owner": risk_score.entity_id}
    return {"department": None, "process": None, "owner": None}


def _record_context(record: Any) -> dict[str, str | None]:
    return {
        "department": getattr(record, "department", None),
        "process": getattr(record, "process", None),
        "owner": getattr(record, "owner", None),
    }


def _rationale(risk_score: RiskScore, top_drivers: list[str], source_ids: str) -> str:
    driver_text = "; ".join(top_drivers)
    return (
        f"Based on available data, this elevated risk signal is recommended for QA review. "
        f"The advisory score is {risk_score.score:.1f} ({_band_label(risk_score.band.value)}) "
        f"for {risk_score.entity_type} {risk_score.entity_id} over horizon {risk_score.horizon.value}. "
        f"Top drivers: {driver_text}. Source record IDs: {source_ids}."
    )


def _band_label(band: str) -> str:
    return {
        "clear": "low",
        "watch": "watch",
        "advisory": "elevated",
        "storm": "high",
        "severe_storm": "critical",
    }.get(band, band.replace("_", " "))


def _recommended_review(risk_type: str) -> str:
    if risk_type == "deviation_recurrence":
        return "QA should review whether linked CAPA remains adequate."
    if risk_type == "capa_failure":
        return "CAPA owner should review effectiveness check design."
    if risk_type == "training_drift":
        return "Training owner should review SOP-related overdue training."
    if risk_type == "audit_readiness_gap":
        return "Quality council should review audit readiness signals and open quality-system actions."
    if risk_type == "backlog_pressure":
        return "Quality council should review backlog pressure and resource allocation."
    return "QA should review this elevated risk signal before any quality action."


def _limitations() -> list[str]:
    return [
        "Advisory decision support only; this card does not make a GMP decision.",
        "Based on available data in the loaded synthetic or anonymized dataset.",
        "Human QA review is mandatory before any regulated quality action.",
    ]


def _find_by_id(records: list[Any], field_name: str, record_id: str) -> Any | None:
    return next((record for record in records if getattr(record, field_name) == record_id), None)


def _dedupe_sources(sources: list[EvidenceSourceRecord]) -> list[EvidenceSourceRecord]:
    seen: set[tuple[str, str]] = set()
    deduped: list[EvidenceSourceRecord] = []
    for source in sources:
        key = (source.domain, source.record_id)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(source)
    return deduped


def _format_sources(sources: list[EvidenceSourceRecord]) -> str:
    return ", ".join(f"{source.domain}:{source.record_id}" for source in sources)


def _split_entity(entity_id: str, expected_parts: int) -> list[str]:
    parts = entity_id.split("|")
    if len(parts) != expected_parts:
        return parts + [""] * (expected_parts - len(parts))
    return parts


def _slug(value: str) -> str:
    return value.strip().lower().replace("_", "-").replace(" ", "-").replace("|", "-")
