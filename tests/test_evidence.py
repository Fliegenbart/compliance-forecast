from datetime import date, datetime, timedelta, timezone

from gmp_weather.evidence import generate_evidence_cards
from gmp_weather.schemas import CAPA, Deviation, QMSDataBundle, RiskBand, RiskHorizon, RiskScore


AS_OF = date(2026, 4, 30)


def _deviation(deviation_id: str, severity: str = "major") -> Deviation:
    return Deviation(
        deviation_id=deviation_id,
        opened_date=AS_OF - timedelta(days=20),
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
        supplier_id=None,
        sop_id="SOP-001",
        owner="QA Owner 01",
        short_description="Synthetic deviation.",
        root_cause_category="line clearance",
        capa_id="CAPA-001",
        recurrence_flag=True,
    )


def _capa(capa_id: str = "CAPA-001") -> CAPA:
    return CAPA(
        capa_id=capa_id,
        opened_date=AS_OF - timedelta(days=45),
        closed_date=None,
        due_date=AS_OF - timedelta(days=5),
        status="open",
        site="Berlin Site",
        department="QA Operations",
        process="Packaging",
        owner="CAPA Owner 01",
        linked_deviation_ids=["DEV-001"],
        root_cause_category="line clearance",
        action_type="Retraining Only",
        action_description="Monitor and review as needed.",
        effectiveness_check_due_date=AS_OF - timedelta(days=1),
        effectiveness_status="vague - monitor",
    )


def _risk_score(
    *,
    score: float,
    band: RiskBand,
    entity_type: str,
    entity_id: str,
    risk_type: str,
) -> RiskScore:
    return RiskScore(
        score=score,
        band=band,
        horizon=RiskHorizon.FOUR_WEEKS,
        entity_type=entity_type,
        entity_id=entity_id,
        risk_type=risk_type,
        drivers=[
            "overdue CAPA: CAPA-001 overdue by 5 days (+25)",
            "linked deviation: DEV-001 elevated recurrence signal (+12)",
            "owner workload: QA Owner 01 has 7 open items (+8)",
            "additional lower priority driver (+4)",
        ],
        confidence=0.76,
    )


def test_generate_evidence_cards_for_medium_and_high_scores_only():
    bundle = QMSDataBundle(deviations=[_deviation("DEV-001")], capas=[_capa()])
    generated_at = datetime(2026, 4, 30, 12, 0, tzinfo=timezone.utc)
    scores = [
        _risk_score(
            score=62,
            band=RiskBand.ADVISORY,
            entity_type="deviation",
            entity_id="DEV-001",
            risk_type="deviation_recurrence",
        ),
        _risk_score(
            score=20,
            band=RiskBand.CLEAR,
            entity_type="capa",
            entity_id="CAPA-001",
            risk_type="capa_failure",
        ),
    ]

    cards = generate_evidence_cards(scores, bundle, generated_at=generated_at)

    assert len(cards) == 1
    assert cards[0].generated_at == generated_at
    assert cards[0].risk_score.entity_id == "DEV-001"
    assert cards[0].risk_score.band is RiskBand.ADVISORY


def test_every_evidence_card_has_structured_source_records_and_top_drivers():
    bundle = QMSDataBundle(deviations=[_deviation("DEV-001")], capas=[_capa()])
    score = _risk_score(
        score=78,
        band=RiskBand.STORM,
        entity_type="capa",
        entity_id="CAPA-001",
        risk_type="capa_failure",
    )

    card = generate_evidence_cards([score], bundle)[0]

    assert card.source_records
    assert {source.domain for source in card.source_records} >= {"capas", "deviations"}
    assert {source.record_id for source in card.source_records} >= {"CAPA-001", "DEV-001"}
    assert len(card.top_drivers) == 3
    assert all(card.top_drivers)
    assert card.department == "QA Operations"
    assert card.process == "Packaging"
    assert card.owner == "CAPA Owner 01"


def test_evidence_card_wording_is_safe_and_source_grounded():
    bundle = QMSDataBundle(deviations=[_deviation("DEV-001")], capas=[_capa()])
    score = _risk_score(
        score=92,
        band=RiskBand.SEVERE_STORM,
        entity_type="deviation",
        entity_id="DEV-001",
        risk_type="deviation_recurrence",
    )

    card = generate_evidence_cards([score], bundle)[0]
    text = " ".join(
        [
            card.rationale,
            card.recommended_human_review,
            " ".join(card.limitations),
        ]
    ).lower()

    assert "based on available data" in text
    assert "elevated risk signal" in text
    assert "recommended for qa review" in text
    assert "dev-001" in text
    assert "non-compliance" not in text
    assert "determined root cause" not in text
    assert "system has determined" not in text
    assert card.recommended_human_review == "QA should review whether linked CAPA remains adequate."
