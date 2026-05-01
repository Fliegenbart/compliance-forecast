from datetime import date, timedelta

from gmp_weather.data_quality import assess_data_quality
from gmp_weather.schemas import CAPA, Deviation, QMSDataBundle, SOP, TrainingRecord


AS_OF = date(2026, 4, 30)


def test_assess_data_quality_returns_structured_report_for_clean_bundle():
    sop = SOP(
        sop_id="SOP-001",
        title="Synthetic SOP",
        department="QA Operations",
        process="Supplier Qualification",
        version="1.0",
        effective_date=date(2026, 1, 1),
        revision_date=date(2027, 1, 1),
        status="effective",
    )
    bundle = QMSDataBundle(
        deviations=[],
        capas=[],
        audit_findings=[],
        training_records=[],
        change_controls=[],
        sops=[sop],
    )

    report = assess_data_quality(bundle, as_of=date(2026, 4, 30))

    assert report.total_records_by_domain["sops"] == 1
    assert report.issue_count_by_severity == {}
    assert report.issue_list == []
    assert report.data_readiness_score == 100


def test_assess_data_quality_reports_cross_reference_and_status_issues():
    as_of = date(2026, 4, 30)
    valid_sop = SOP(
        sop_id="SOP-001",
        title="Synthetic SOP",
        department="QA Operations",
        process="Supplier Qualification",
        version="1.0",
        effective_date=date(2026, 1, 1),
        revision_date=date(2027, 1, 1),
        status="effective",
    )
    overdue_deviation = Deviation(
        deviation_id="DEV-001",
        opened_date=as_of - timedelta(days=40),
        closed_date=None,
        due_date=as_of - timedelta(days=5),
        status="open",
        severity="major",
        site="Berlin Site",
        department="Packaging",
        process="Packaging",
        product="Product A",
        batch_id="BATCH-001",
        equipment_id="EQ-001",
        supplier_id=None,
        sop_id="SOP-999",
        owner="QA Owner 01",
        short_description="Synthetic overdue deviation.",
        root_cause_category="line clearance",
        capa_id=None,
        recurrence_flag=True,
    )
    duplicate_closed_without_date = Deviation(
        deviation_id="DEV-001",
        opened_date=as_of - timedelta(days=10),
        closed_date=None,
        due_date=as_of + timedelta(days=10),
        status="closed",
        severity="minor",
        site="Berlin Site",
        department="Packaging",
        process="Packaging",
        product=None,
        batch_id=None,
        equipment_id=None,
        supplier_id=None,
        sop_id="SOP-001",
        owner="QA Owner 01",
        short_description="Synthetic closed deviation without close date.",
        root_cause_category=None,
        capa_id=None,
        recurrence_flag=None,
    )
    unknown_status_capa = CAPA(
        capa_id="CAPA-001",
        opened_date=as_of - timedelta(days=90),
        closed_date=None,
        due_date=as_of - timedelta(days=1),
        status="waiting forever",
        site="Berlin Site",
        department="QA Operations",
        process="Supplier Qualification",
        owner="QA Owner 02",
        linked_deviation_ids=["DEV-404"],
        root_cause_category="procedure gap",
        action_type="Retraining only",
        action_description="Synthetic retraining only.",
        effectiveness_check_due_date=as_of + timedelta(days=30),
        effectiveness_status="vague - monitor",
    )
    unknown_sop_training = TrainingRecord(
        training_id="TRN-001",
        employee_role="Operator",
        department="Production",
        sop_id="SOP-404",
        assigned_date=as_of - timedelta(days=30),
        due_date=as_of - timedelta(days=3),
        completion_date=None,
        status="assigned",
    )
    invalid_date_deviation = Deviation.model_construct(
        deviation_id="DEV-002",
        opened_date=as_of,
        closed_date=None,
        due_date=as_of - timedelta(days=1),
        status="open",
        severity="major",
        site="Berlin Site",
        department="Packaging",
        process="Packaging",
        product=None,
        batch_id=None,
        equipment_id=None,
        supplier_id=None,
        sop_id="SOP-001",
        owner="",
        short_description="",
        root_cause_category=None,
        capa_id=None,
        recurrence_flag=None,
    )
    bundle = QMSDataBundle.model_construct(
        deviations=[overdue_deviation, duplicate_closed_without_date, invalid_date_deviation],
        capas=[unknown_status_capa],
        audit_findings=[],
        training_records=[unknown_sop_training],
        change_controls=[],
        sops=[valid_sop],
    )

    report = assess_data_quality(bundle, as_of=as_of)
    messages = [issue.message for issue in report.issue_list]

    assert report.total_records_by_domain["deviations"] == 3
    assert report.issue_count_by_severity["critical"] >= 1
    assert report.issue_count_by_severity["high"] >= 1
    assert report.data_readiness_score < 100
    assert any("Duplicate ID DEV-001" in message for message in messages)
    assert any("closed but has no closed_date" in message for message in messages)
    assert any("due_date is before opened_date" in message for message in messages)
    assert any("overdue" in message for message in messages)
    assert any("references unknown SOP SOP-999" in message for message in messages)
    assert any("references missing deviation DEV-404" in message for message in messages)
    assert any("references missing SOP SOP-404" in message for message in messages)
    assert any("status 'waiting forever' is not in the expected set" in message for message in messages)
    assert any("owner is missing" in message for message in messages)
    assert any("short_description is missing" in message for message in messages)


def test_duplicate_id_detection_reports_domain_and_record_id():
    bundle = QMSDataBundle(
        deviations=[
            _deviation("DEV-DUP"),
            _deviation("DEV-DUP"),
        ],
        sops=[_sop("SOP-001")],
    )

    report = assess_data_quality(bundle, as_of=AS_OF)

    duplicate_issues = [
        issue
        for issue in report.issue_list
        if issue.message == "Duplicate ID DEV-DUP found in deviations."
    ]
    assert len(duplicate_issues) == 1
    assert duplicate_issues[0].domain == "deviations"
    assert duplicate_issues[0].record_id == "DEV-DUP"
    assert duplicate_issues[0].severity == "critical"


def test_broken_reference_detection_reports_missing_sops_and_deviations():
    bundle = QMSDataBundle(
        deviations=[_deviation("DEV-001", sop_id="SOP-MISSING")],
        capas=[
            CAPA(
                capa_id="CAPA-001",
                opened_date=AS_OF - timedelta(days=10),
                closed_date=None,
                due_date=AS_OF + timedelta(days=20),
                status="open",
                site="Berlin Site",
                department="QA Operations",
                process="Packaging",
                owner="QA Owner 01",
                linked_deviation_ids=["DEV-MISSING"],
                root_cause_category="procedure gap",
                action_type="Procedure update",
                action_description="Synthetic action.",
                effectiveness_check_due_date=AS_OF + timedelta(days=50),
                effectiveness_status="planned",
            )
        ],
        training_records=[
            TrainingRecord(
                training_id="TRN-001",
                employee_role="Operator",
                department="Packaging",
                sop_id="SOP-MISSING",
                assigned_date=AS_OF - timedelta(days=5),
                due_date=AS_OF + timedelta(days=10),
                completion_date=None,
                status="assigned",
            )
        ],
        sops=[_sop("SOP-001")],
    )

    report = assess_data_quality(bundle, as_of=AS_OF)
    messages = {issue.message for issue in report.issue_list}

    assert "Deviation references unknown SOP SOP-MISSING." in messages
    assert "Training record references missing SOP SOP-MISSING." in messages
    assert "CAPA references missing deviation DEV-MISSING." in messages


def _sop(sop_id: str) -> SOP:
    return SOP(
        sop_id=sop_id,
        title="Synthetic SOP",
        department="Packaging",
        process="Packaging",
        version="1.0",
        effective_date=AS_OF - timedelta(days=90),
        revision_date=AS_OF + timedelta(days=365),
        status="effective",
    )


def _deviation(deviation_id: str, sop_id: str = "SOP-001") -> Deviation:
    return Deviation(
        deviation_id=deviation_id,
        opened_date=AS_OF - timedelta(days=5),
        closed_date=None,
        due_date=AS_OF + timedelta(days=25),
        status="open",
        severity="major",
        site="Berlin Site",
        department="Packaging",
        process="Packaging",
        product="Product A",
        batch_id="BATCH-001",
        equipment_id="EQ-001",
        supplier_id=None,
        sop_id=sop_id,
        owner="QA Owner 01",
        short_description="Synthetic deviation.",
        root_cause_category="line clearance",
        capa_id=None,
        recurrence_flag=None,
    )
