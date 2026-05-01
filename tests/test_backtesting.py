from datetime import date, timedelta

from gmp_weather.backtesting import run_backtest
from gmp_weather.schemas import AuditFinding, CAPA, Deviation, QMSDataBundle


FORECAST_DATE = date(2026, 1, 31)


def _deviation(
    deviation_id: str,
    *,
    opened_date: date,
    department: str = "Packaging",
    process: str = "Packaging",
    severity: str = "minor",
    root_cause_category: str | None = "label reconciliation",
    equipment_id: str | None = "EQ-001",
    status: str = "open",
    owner: str = "QA Owner 01",
    capa_id: str | None = None,
) -> Deviation:
    return Deviation(
        deviation_id=deviation_id,
        opened_date=opened_date,
        closed_date=None,
        due_date=opened_date + timedelta(days=90),
        status=status,
        severity=severity,
        site="Berlin Site",
        department=department,
        process=process,
        product="Product A",
        batch_id="BATCH-001",
        equipment_id=equipment_id,
        supplier_id=None,
        sop_id="SOP-001",
        owner=owner,
        short_description="Synthetic test deviation.",
        root_cause_category=root_cause_category,
        capa_id=capa_id,
        recurrence_flag=None,
    )


def _capa(
    capa_id: str,
    *,
    opened_date: date,
    due_date: date,
    department: str = "Packaging",
    process: str = "Packaging",
    owner: str = "QA Owner 01",
) -> CAPA:
    return CAPA(
        capa_id=capa_id,
        opened_date=opened_date,
        closed_date=None,
        due_date=due_date,
        status="open",
        site="Berlin Site",
        department=department,
        process=process,
        owner=owner,
        linked_deviation_ids=["DEV-SIGNAL"],
        root_cause_category="label reconciliation",
        action_type="Retraining Only",
        action_description="Review as needed",
        effectiveness_check_due_date=due_date + timedelta(days=20),
        effectiveness_status="planned",
    )


def test_run_backtest_uses_only_records_available_at_forecast_date():
    bundle = QMSDataBundle(
        deviations=[
            _deviation("DEV-SIGNAL", opened_date=FORECAST_DATE - timedelta(days=8), severity="critical"),
            _deviation("DEV-FUTURE", opened_date=FORECAST_DATE + timedelta(days=10), severity="critical"),
        ],
        capas=[_capa("CAPA-SIGNAL", opened_date=FORECAST_DATE - timedelta(days=12), due_date=FORECAST_DATE + timedelta(days=7))],
    )

    result = run_backtest(bundle, [FORECAST_DATE], horizon_days=30)
    model_predictions = result.predictions_frame[result.predictions_frame["method"] == "rules-v0.1"]

    assert "DEV-FUTURE" not in set(model_predictions["entity_id"])
    assert "DEV-FUTURE" in set(result.events_frame["event_id"])


def test_risk_ranking_beats_oldest_backlog_baseline_on_targeted_future_event():
    old_unrelated = [
        _deviation(
            f"DEV-OLD-{index:02d}",
            opened_date=FORECAST_DATE - timedelta(days=220 + index),
            department="Engineering",
            process=f"Maintenance Area {index}",
            root_cause_category=f"maintenance category {index}",
            equipment_id=f"EQ-{index:03d}",
            owner=f"Owner {index:02d}",
        )
        for index in range(25)
    ]
    bundle = QMSDataBundle(
        deviations=[
            *old_unrelated,
            _deviation("DEV-PRIOR", opened_date=FORECAST_DATE - timedelta(days=24), status="closed"),
            _deviation(
                "DEV-SIGNAL",
                opened_date=FORECAST_DATE - timedelta(days=7),
                severity="critical",
                capa_id="CAPA-SIGNAL",
            ),
            _deviation(
                "DEV-FUTURE",
                opened_date=FORECAST_DATE + timedelta(days=9),
                severity="critical",
                status="open",
            ),
        ],
        capas=[_capa("CAPA-SIGNAL", opened_date=FORECAST_DATE - timedelta(days=10), due_date=FORECAST_DATE + timedelta(days=6))],
    )

    result = run_backtest(bundle, [FORECAST_DATE], horizon_days=30)

    assert result.metric_summary["precision_at_10"] > result.baseline_metric_summary["precision_at_10"]
    assert result.metric_summary["recall_for_future_major_events"] == 1.0
    assert result.baseline_metric_summary["recall_for_future_major_events"] == 0.0


def test_backtest_identifies_capa_overdue_and_audit_finding_future_events():
    bundle = QMSDataBundle(
        deviations=[_deviation("DEV-SIGNAL", opened_date=FORECAST_DATE - timedelta(days=8), severity="major")],
        capas=[_capa("CAPA-SIGNAL", opened_date=FORECAST_DATE - timedelta(days=12), due_date=FORECAST_DATE + timedelta(days=5))],
        audit_findings=[
            AuditFinding(
                finding_id="FIND-FUTURE",
                audit_date=FORECAST_DATE + timedelta(days=11),
                finding_type="internal audit",
                severity="major",
                site="Berlin Site",
                department="Packaging",
                process="Packaging",
                linked_capa_id="CAPA-SIGNAL",
                description="Synthetic future finding.",
                status="open",
            )
        ],
    )

    result = run_backtest(bundle, [FORECAST_DATE], horizon_days=30)

    assert {"capa_becoming_overdue", "audit_finding_opened"}.issubset(set(result.events_frame["event_type"]))
    assert result.metric_summary["lead_time_days"] >= 5
    assert not result.predictions_frame.empty


def test_backtest_metric_summary_exposes_expected_comparison_metrics():
    bundle = QMSDataBundle(
        deviations=[
            _deviation("DEV-SIGNAL", opened_date=FORECAST_DATE - timedelta(days=8), severity="critical"),
            _deviation("DEV-FUTURE", opened_date=FORECAST_DATE + timedelta(days=6), severity="critical"),
        ],
        capas=[_capa("CAPA-SIGNAL", opened_date=FORECAST_DATE - timedelta(days=12), due_date=FORECAST_DATE + timedelta(days=5))],
    )

    result = run_backtest(bundle, [FORECAST_DATE], horizon_days=30)
    expected_metrics = {
        "precision_at_10",
        "precision_at_20",
        "recall_for_future_major_events",
        "top_decile_lift",
        "lead_time_days",
    }

    assert set(result.metric_summary) == expected_metrics
    assert set(result.baseline_metric_summary) == expected_metrics
    assert result.forecast_summary_frame["forecast_date"].tolist() == [FORECAST_DATE]
    assert result.horizon_days == 30
    assert all(isinstance(value, float) for value in result.metric_summary.values())
