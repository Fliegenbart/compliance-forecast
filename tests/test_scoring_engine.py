from datetime import date, timedelta

from gmp_weather.config import SCORING_CONFIG_PATH, load_scoring_config
from gmp_weather.schemas import AuditFinding, CAPA, Deviation, QMSDataBundle, RiskBand
from gmp_weather.scoring import calculate_all_scores, score_to_band


AS_OF = date(2026, 4, 30)


def _deviation(
    deviation_id: str,
    *,
    opened_date: date,
    severity: str = "major",
    status: str = "open",
    due_date: date | None = None,
    process: str = "Packaging",
    department: str = "Packaging",
    equipment_id: str | None = "EQ-001",
    sop_id: str | None = "SOP-001",
    root_cause_category: str | None = "line clearance",
    capa_id: str | None = "CAPA-001",
    owner: str = "QA Owner 01",
) -> Deviation:
    return Deviation(
        deviation_id=deviation_id,
        opened_date=opened_date,
        closed_date=None if status != "closed" else opened_date + timedelta(days=15),
        due_date=due_date or opened_date + timedelta(days=30),
        status=status,
        severity=severity,
        site="Berlin Site",
        department=department,
        process=process,
        product="Product A",
        batch_id="BATCH-001",
        equipment_id=equipment_id,
        supplier_id=None,
        sop_id=sop_id,
        owner=owner,
        short_description="Synthetic deviation for scoring.",
        root_cause_category=root_cause_category,
        capa_id=capa_id,
        recurrence_flag=None,
    )


def _capa(
    capa_id: str,
    *,
    due_date: date,
    status: str = "open",
    action_type: str = "Procedure update",
    action_description: str = "Update procedure and verify effectiveness with trended deviation review.",
    linked_deviation_ids: list[str] | None = None,
    effectiveness_check_due_date: date | None = None,
    owner: str = "QA Owner 01",
) -> CAPA:
    return CAPA(
        capa_id=capa_id,
        opened_date=AS_OF - timedelta(days=45),
        closed_date=None,
        due_date=due_date,
        status=status,
        site="Berlin Site",
        department="QA Operations",
        process="Packaging",
        owner=owner,
        linked_deviation_ids=linked_deviation_ids or ["DEV-001"],
        root_cause_category="line clearance",
        action_type=action_type,
        action_description=action_description,
        effectiveness_check_due_date=effectiveness_check_due_date or AS_OF + timedelta(days=45),
        effectiveness_status="planned",
    )


def _score(scores, risk_type: str, entity_id: str):
    return next(score for score in scores if score.risk_type == risk_type and score.entity_id == entity_id)


def test_score_to_band_maps_score_ranges():
    assert score_to_band(5) is RiskBand.CLEAR
    assert score_to_band(30) is RiskBand.WATCH
    assert score_to_band(55) is RiskBand.ADVISORY
    assert score_to_band(75) is RiskBand.STORM
    assert score_to_band(90) is RiskBand.SEVERE_STORM


def test_overdue_capa_scores_higher_than_non_overdue_capa():
    bundle = QMSDataBundle(
        deviations=[_deviation("DEV-001", opened_date=AS_OF - timedelta(days=20))],
        capas=[
            _capa("CAPA-OVERDUE", due_date=AS_OF - timedelta(days=5)),
            _capa("CAPA-FUTURE", due_date=AS_OF + timedelta(days=45)),
        ],
    )

    scores = calculate_all_scores(bundle, AS_OF)

    overdue = _score(scores, "capa_failure", "CAPA-OVERDUE")
    future = _score(scores, "capa_failure", "CAPA-FUTURE")
    assert overdue.score > future.score
    assert any("overdue" in driver.lower() for driver in overdue.drivers)


def test_repeat_deviations_increase_recurrence_risk():
    target = _deviation(
        "DEV-TARGET",
        opened_date=AS_OF - timedelta(days=5),
        due_date=AS_OF + timedelta(days=5),
        equipment_id="EQ-007",
        root_cause_category="label reconciliation",
    )
    repeated_bundle = QMSDataBundle(
        deviations=[
            target,
            _deviation(
                "DEV-PRIOR-1",
                opened_date=AS_OF - timedelta(days=20),
                status="closed",
                equipment_id="EQ-007",
                root_cause_category="label reconciliation",
            ),
            _deviation(
                "DEV-PRIOR-2",
                opened_date=AS_OF - timedelta(days=50),
                status="closed",
                equipment_id="EQ-007",
                root_cause_category="label reconciliation",
            ),
        ],
        capas=[_capa("CAPA-001", due_date=AS_OF + timedelta(days=30))],
    )
    isolated_bundle = QMSDataBundle(
        deviations=[target],
        capas=[_capa("CAPA-001", due_date=AS_OF + timedelta(days=30))],
    )

    repeated = _score(calculate_all_scores(repeated_bundle, AS_OF), "deviation_recurrence", "DEV-TARGET")
    isolated = _score(calculate_all_scores(isolated_bundle, AS_OF), "deviation_recurrence", "DEV-TARGET")

    assert repeated.score > isolated.score
    assert any("same process recurrence" in driver.lower() for driver in repeated.drivers)
    assert any("same equipment recurrence" in driver.lower() for driver in repeated.drivers)


def test_retraining_only_capa_increases_capa_failure_risk():
    bundle = QMSDataBundle(
        deviations=[_deviation("DEV-001", opened_date=AS_OF - timedelta(days=20))],
        capas=[
            _capa("CAPA-TRAIN", due_date=AS_OF + timedelta(days=30), action_type="Retraining Only"),
            _capa("CAPA-PROC", due_date=AS_OF + timedelta(days=30), action_type="Procedure update"),
        ],
    )

    scores = calculate_all_scores(bundle, AS_OF)

    retraining = _score(scores, "capa_failure", "CAPA-TRAIN")
    procedure = _score(scores, "capa_failure", "CAPA-PROC")
    assert retraining.score > procedure.score
    assert any("retraining only" in driver.lower() for driver in retraining.drivers)


def test_missing_evidence_lowers_confidence():
    complete = _deviation(
        "DEV-COMPLETE",
        opened_date=AS_OF - timedelta(days=10),
        due_date=AS_OF + timedelta(days=20),
        equipment_id="EQ-001",
        root_cause_category="line clearance",
        capa_id="CAPA-001",
        sop_id="SOP-001",
    )
    incomplete = _deviation(
        "DEV-INCOMPLETE",
        opened_date=AS_OF - timedelta(days=10),
        due_date=AS_OF + timedelta(days=20),
        equipment_id=None,
        root_cause_category=None,
        capa_id=None,
        sop_id=None,
    )
    bundle = QMSDataBundle(
        deviations=[complete, incomplete],
        capas=[_capa("CAPA-001", due_date=AS_OF + timedelta(days=30))],
    )

    scores = calculate_all_scores(bundle, AS_OF)

    complete_score = _score(scores, "deviation_recurrence", "DEV-COMPLETE")
    incomplete_score = _score(scores, "deviation_recurrence", "DEV-INCOMPLETE")
    assert incomplete_score.confidence < complete_score.confidence
    assert any("confidence reduced" in driver.lower() for driver in incomplete_score.drivers)


def test_severe_events_produce_higher_scores_than_minor_events():
    bundle = QMSDataBundle(
        deviations=[
            _deviation("DEV-CRITICAL", opened_date=AS_OF - timedelta(days=3), severity="critical"),
            _deviation("DEV-MINOR", opened_date=AS_OF - timedelta(days=3), severity="minor"),
        ],
        capas=[_capa("CAPA-001", due_date=AS_OF + timedelta(days=30))],
    )

    scores = calculate_all_scores(bundle, AS_OF)

    critical = _score(scores, "deviation_recurrence", "DEV-CRITICAL")
    minor = _score(scores, "deviation_recurrence", "DEV-MINOR")
    assert critical.score > minor.score
    assert any("critical" in driver.lower() for driver in critical.drivers)


def test_related_audit_finding_severity_contributes_to_capa_failure_risk():
    bundle = QMSDataBundle(
        deviations=[_deviation("DEV-001", opened_date=AS_OF - timedelta(days=20))],
        capas=[_capa("CAPA-001", due_date=AS_OF + timedelta(days=30))],
        audit_findings=[
            AuditFinding(
                finding_id="FIND-001",
                audit_date=AS_OF - timedelta(days=10),
                finding_type="internal audit",
                severity="critical",
                site="Berlin Site",
                department="QA Operations",
                process="Packaging",
                linked_capa_id="CAPA-001",
                description="Synthetic critical audit finding.",
                status="open",
            )
        ],
    )

    capa_score = _score(calculate_all_scores(bundle, AS_OF), "capa_failure", "CAPA-001")

    assert any("audit finding" in driver.lower() and "critical" in driver.lower() for driver in capa_score.drivers)


def test_changing_yaml_weight_changes_deviation_score(tmp_path):
    config_text = SCORING_CONFIG_PATH.read_text(encoding="utf-8")
    custom_config_path = tmp_path / "scoring_rules_v0_1.yaml"
    custom_config_path.write_text(
        config_text.replace("  severity_critical: 32", "  severity_critical: 52"),
        encoding="utf-8",
    )
    default_config = load_scoring_config(SCORING_CONFIG_PATH)
    custom_config = load_scoring_config(custom_config_path)
    bundle = QMSDataBundle(
        deviations=[
            _deviation(
                "DEV-CRITICAL",
                opened_date=AS_OF - timedelta(days=3),
                severity="critical",
                due_date=AS_OF + timedelta(days=30),
            )
        ],
        capas=[_capa("CAPA-001", due_date=AS_OF + timedelta(days=30))],
    )

    default_score = _score(
        calculate_all_scores(bundle, AS_OF, scoring_config=default_config),
        "deviation_recurrence",
        "DEV-CRITICAL",
    )
    custom_score = _score(
        calculate_all_scores(bundle, AS_OF, scoring_config=custom_config),
        "deviation_recurrence",
        "DEV-CRITICAL",
    )

    assert custom_score.score == default_score.score + 20
    assert any("severity: critical (+52)" in driver for driver in custom_score.drivers)
