from datetime import date

import pytest
from pydantic import ValidationError

from gmp_weather.schemas import (
    AuditFinding,
    CAPA,
    ChangeControl,
    Deviation,
    EvidenceCard,
    EvidenceSourceRecord,
    QMSRecord,
    RiskBand,
    RiskForecast,
    RiskHorizon,
    RiskScore,
    SOP,
    TrainingRecord,
)


def test_qms_record_accepts_required_anonymized_fields():
    record = QMSRecord(
        record_id="DEV-001",
        record_type="deviation",
        site="Site Alpha",
        process_area="sterile manufacturing",
        severity=4,
        occurrence=3,
        detection=2,
        status="open",
        opened_date=date(2026, 4, 1),
        due_date=date(2026, 4, 25),
        description="Synthetic deviation about delayed environmental monitoring review.",
    )

    assert record.record_id == "DEV-001"
    assert record.severity == 4


def test_qms_record_rejects_out_of_range_scores():
    with pytest.raises(ValidationError):
        QMSRecord(
            record_id="CAPA-001",
            record_type="capa",
            site="Site Alpha",
            process_area="packaging",
            severity=6,
            occurrence=1,
            detection=1,
            status="open",
            opened_date=date(2026, 4, 1),
            due_date=None,
            description="Synthetic record.",
        )


def test_risk_forecast_is_advisory_not_decision():
    forecast = RiskForecast(
        process_area="sterile manufacturing",
        risk_score=72.0,
        risk_level="High",
        advisory_summary="Human review recommended.",
        source_record_ids=["DEV-001", "CAPA-002"],
    )

    assert forecast.decision_status == "Advisory only"
    assert forecast.source_record_ids == ["DEV-001", "CAPA-002"]


def test_evidence_card_requires_source_record_ids():
    risk_score = RiskScore(
        score=68.0,
        band=RiskBand.ADVISORY,
        horizon=RiskHorizon.FOUR_WEEKS,
        entity_type="process",
        entity_id="quality control",
        risk_type="overdue_deviation_signal",
        drivers=["DEV-001 overdue by 20 days"],
        confidence=0.72,
    )

    with pytest.raises(ValidationError):
        EvidenceCard(
            card_id="CARD-001",
            risk_score=risk_score,
            source_records=[],
            top_drivers=["DEV-001 overdue by 20 days"],
            rationale="Several overdue records are present.",
            recommended_human_review="QA should review the linked records before action.",
            limitations=["Synthetic sample only."],
        )


def test_core_gmp_record_models_accept_required_fields():
    deviation = Deviation(
        deviation_id="DEV-001",
        opened_date=date(2026, 4, 1),
        closed_date=None,
        due_date=date(2026, 4, 30),
        status="open",
        severity="major",
        site="Site Alpha",
        department="Quality",
        process="batch review",
        product="Product A",
        batch_id="BATCH-001",
        equipment_id=None,
        supplier_id=None,
        sop_id="SOP-001",
        owner="QA Reviewer",
        short_description="Synthetic deviation awaiting QA review.",
        root_cause_category=None,
        capa_id="CAPA-001",
        recurrence_flag=True,
    )
    capa = CAPA(
        capa_id="CAPA-001",
        opened_date=date(2026, 4, 2),
        closed_date=None,
        due_date=date(2026, 5, 15),
        status="in_progress",
        site="Site Alpha",
        department="Quality",
        process="batch review",
        owner="CAPA Owner",
        linked_deviation_ids=["DEV-001"],
        root_cause_category="procedure gap",
        action_type="corrective",
        action_description="Synthetic action for procedure update.",
        effectiveness_check_due_date=date(2026, 7, 1),
        effectiveness_status=None,
    )
    finding = AuditFinding(
        finding_id="FIND-001",
        audit_date=date(2026, 3, 20),
        finding_type="internal audit",
        severity="minor",
        site="Site Alpha",
        department="Quality",
        process="SOP management",
        linked_capa_id="CAPA-001",
        description="Synthetic audit finding.",
        status="open",
    )
    training = TrainingRecord(
        training_id="TRN-001",
        employee_role="Operator",
        department="Manufacturing",
        sop_id="SOP-001",
        assigned_date=date(2026, 4, 1),
        due_date=date(2026, 4, 20),
        completion_date=None,
        status="assigned",
    )
    change = ChangeControl(
        change_id="CC-001",
        opened_date=date(2026, 4, 5),
        target_implementation_date=date(2026, 6, 1),
        closed_date=None,
        status="assessment",
        site="Site Alpha",
        department="Validation",
        process="validation",
        affected_sop_ids=["SOP-001"],
        affected_equipment_ids=[],
        affected_system_ids=["CSV-001"],
        validation_impact=True,
        training_impact=True,
        owner="Change Owner",
        description="Synthetic validation-impacting change.",
    )
    sop = SOP(
        sop_id="SOP-001",
        title="Synthetic Batch Review SOP",
        department="Quality",
        process="batch review",
        version="1.0",
        effective_date=date(2026, 1, 1),
        revision_date=date(2027, 1, 1),
        status="effective",
    )

    assert deviation.deviation_id == "DEV-001"
    assert capa.linked_deviation_ids == ["DEV-001"]
    assert finding.linked_capa_id == "CAPA-001"
    assert training.sop_id == "SOP-001"
    assert change.validation_impact is True
    assert sop.status == "effective"


def test_core_gmp_models_reject_dates_that_close_before_opening():
    with pytest.raises(ValidationError, match="closed_date cannot be before opened_date"):
        Deviation(
            deviation_id="DEV-001",
            opened_date=date(2026, 4, 10),
            closed_date=date(2026, 4, 1),
            due_date=None,
            status="closed",
            severity="minor",
            site="Site Alpha",
            department="Quality",
            process="deviation management",
            product=None,
            batch_id=None,
            equipment_id=None,
            supplier_id=None,
            sop_id=None,
            owner="QA Reviewer",
            short_description="Synthetic deviation.",
            root_cause_category=None,
            capa_id=None,
            recurrence_flag=None,
        )


def test_training_record_rejects_completion_before_assignment():
    with pytest.raises(ValidationError, match="completion_date cannot be before assigned_date"):
        TrainingRecord(
            training_id="TRN-001",
            employee_role="Operator",
            department="Manufacturing",
            sop_id="SOP-001",
            assigned_date=date(2026, 4, 10),
            due_date=date(2026, 4, 20),
            completion_date=date(2026, 4, 1),
            status="completed",
        )


def test_risk_score_requires_visible_drivers_and_valid_confidence():
    with pytest.raises(ValidationError):
        RiskScore(
            score=40.0,
            band=RiskBand.WATCH,
            horizon=RiskHorizon.TWO_WEEKS,
            entity_type="site",
            entity_id="Site Alpha",
            risk_type="training_overdue_signal",
            drivers=[],
            confidence=1.2,
        )


def test_evidence_card_contains_risk_score_and_human_review_text():
    risk_score = RiskScore(
        score=82.0,
        band=RiskBand.STORM,
        horizon=RiskHorizon.EIGHT_WEEKS,
        entity_type="process",
        entity_id="sterile manufacturing",
        risk_type="recurring_deviation_signal",
        drivers=["DEV-001 severity major", "DEV-002 recurrence flag"],
        confidence=0.8,
    )

    card = EvidenceCard(
        card_id="CARD-001",
        risk_score=risk_score,
        source_records=[
            EvidenceSourceRecord(domain="deviations", record_id="DEV-001"),
            EvidenceSourceRecord(domain="deviations", record_id="DEV-002"),
        ],
        top_drivers=["DEV-001 severity major", "DEV-002 recurrence flag"],
        rationale="Two synthetic deviations indicate a recurring advisory signal.",
        recommended_human_review="Qualified QA reviewer should assess recurrence before any action.",
        limitations=["Synthetic data only.", "Rule-based advisory output."],
    )

    assert card.risk_score.band is RiskBand.STORM
    assert [source.record_id for source in card.source_records] == ["DEV-001", "DEV-002"]
    assert "QA reviewer" in card.recommended_human_review
