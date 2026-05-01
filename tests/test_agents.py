from datetime import date, timedelta

from gmp_weather.agents import (
    AuditReadinessAgent,
    CAPAReviewSignalAgent,
    DataQualityAgent,
    DeviationPatternAgent,
    ForecastBriefingAgent,
    TrainingDriftAgent,
)
from gmp_weather.evidence import generate_evidence_cards
from gmp_weather.schemas import AuditFinding, CAPA, ChangeControl, Deviation, QMSDataBundle, SOP, TrainingRecord
from gmp_weather.scoring import calculate_all_scores


AS_OF = date(2026, 4, 30)
FORBIDDEN_DECISION_PHRASES = [
    "approved",
    "closed by ai",
    "release recommended",
    "capa accepted",
    "root cause confirmed",
]


def _deviation(deviation_id: str, opened_offset: int = 20, severity: str = "major") -> Deviation:
    return Deviation(
        deviation_id=deviation_id,
        opened_date=AS_OF - timedelta(days=opened_offset),
        closed_date=None,
        due_date=AS_OF - timedelta(days=2),
        status="open",
        severity=severity,
        site="Berlin Site",
        department="Packaging",
        process="Packaging",
        product="Product A",
        batch_id="BATCH-001",
        equipment_id="EQ-001",
        supplier_id="SUP-001",
        sop_id="SOP-001",
        owner="QA Owner 01",
        short_description="Synthetic deviation.",
        root_cause_category="line clearance",
        capa_id="CAPA-001",
        recurrence_flag=True,
    )


def _bundle() -> QMSDataBundle:
    return QMSDataBundle(
        deviations=[
            _deviation("DEV-001", opened_offset=20),
            _deviation("DEV-002", opened_offset=35),
            _deviation("DEV-003", opened_offset=5, severity="critical"),
        ],
        capas=[
            CAPA(
                capa_id="CAPA-001",
                opened_date=AS_OF - timedelta(days=60),
                closed_date=None,
                due_date=AS_OF - timedelta(days=1),
                status="open",
                site="Berlin Site",
                department="QA Operations",
                process="Packaging",
                owner="CAPA Owner 01",
                linked_deviation_ids=["DEV-001", "DEV-002"],
                root_cause_category="line clearance",
                action_type="Retraining Only",
                action_description="Monitor and review as needed.",
                effectiveness_check_due_date=AS_OF - timedelta(days=1),
                effectiveness_status="planned",
            )
        ],
        audit_findings=[
            AuditFinding(
                finding_id="FIND-001",
                audit_date=AS_OF - timedelta(days=7),
                finding_type="internal audit",
                severity="major",
                site="Berlin Site",
                department="Packaging",
                process="Packaging",
                linked_capa_id="CAPA-001",
                description="Synthetic finding.",
                status="open",
            )
        ],
        training_records=[
            TrainingRecord(
                training_id="TRN-001",
                employee_role="Operator",
                department="Packaging",
                sop_id="SOP-001",
                assigned_date=AS_OF - timedelta(days=20),
                due_date=AS_OF - timedelta(days=3),
                completion_date=None,
                status="assigned",
            )
        ],
        change_controls=[
            ChangeControl(
                change_id="CHG-001",
                opened_date=AS_OF - timedelta(days=10),
                target_implementation_date=AS_OF + timedelta(days=20),
                closed_date=None,
                status="open",
                site="Berlin Site",
                department="Packaging",
                process="Packaging",
                affected_sop_ids=["SOP-001"],
                affected_equipment_ids=["EQ-001"],
                affected_system_ids=[],
                validation_impact=True,
                training_impact=True,
                owner="QA Owner 02",
                description="Synthetic change.",
            )
        ],
        sops=[
            SOP(
                sop_id="SOP-001",
                title="Packaging line clearance",
                department="Packaging",
                process="Packaging",
                version="2.0",
                effective_date=AS_OF - timedelta(days=15),
                revision_date=None,
                status="effective",
            )
        ],
    )


def _assert_safe_text(text: str) -> None:
    normalized = text.lower()
    for phrase in FORBIDDEN_DECISION_PHRASES:
        assert phrase not in normalized


def test_agents_return_source_ids_and_human_review_recommendations():
    bundle = _bundle()

    data_quality = DataQualityAgent().run(bundle, as_of_date=AS_OF)
    deviation_clusters = DeviationPatternAgent().run(bundle)
    capa_signals = CAPAReviewSignalAgent().run(bundle, as_of_date=AS_OF)
    training_signals = TrainingDriftAgent().run(bundle, as_of_date=AS_OF)
    audit_signals = AuditReadinessAgent().run(bundle, as_of_date=AS_OF)

    assert data_quality.recommended_for_human_review
    assert deviation_clusters[0].recommended_for_human_review
    assert {"DEV-001", "DEV-002", "DEV-003"}.issubset(set(deviation_clusters[0].source_record_ids))
    assert capa_signals[0].recommended_for_human_review
    assert "CAPA-001" in capa_signals[0].source_record_ids
    assert training_signals[0].recommended_for_human_review
    assert "TRN-001" in training_signals[0].source_record_ids
    assert audit_signals[0].recommended_for_human_review
    assert "FIND-001" in audit_signals[0].source_record_ids


def test_forecast_briefing_agent_uses_safe_wording_and_source_ids():
    bundle = _bundle()
    scores = calculate_all_scores(bundle, AS_OF)
    cards = generate_evidence_cards(scores, bundle)

    briefing = ForecastBriefingAgent().run(scores, cards)

    assert "based on available data" in briefing.briefing_text.lower()
    assert "recommended for human qa review" in briefing.briefing_text.lower()
    assert briefing.recommended_for_human_review
    assert briefing.source_record_ids
    assert "DEV-001" in briefing.source_record_ids or "CAPA-001" in briefing.source_record_ids
    _assert_safe_text(briefing.model_dump_json())


def test_agent_outputs_do_not_use_forbidden_decision_phrases():
    bundle = _bundle()
    scores = calculate_all_scores(bundle, AS_OF)
    cards = generate_evidence_cards(scores, bundle)
    outputs = [
        DataQualityAgent().run(bundle, as_of_date=AS_OF).model_dump_json(),
        *[item.model_dump_json() for item in DeviationPatternAgent().run(bundle)],
        *[item.model_dump_json() for item in CAPAReviewSignalAgent().run(bundle, as_of_date=AS_OF)],
        *[item.model_dump_json() for item in TrainingDriftAgent().run(bundle, as_of_date=AS_OF)],
        *[item.model_dump_json() for item in AuditReadinessAgent().run(bundle, as_of_date=AS_OF)],
        ForecastBriefingAgent().run(scores, cards).model_dump_json(),
    ]

    for output in outputs:
        _assert_safe_text(output)
