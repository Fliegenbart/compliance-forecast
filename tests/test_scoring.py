from datetime import date

from gmp_weather.schemas import QMSRecord
from gmp_weather.scoring import score_process_areas


def _record(
    record_id: str,
    process_area: str,
    severity: int,
    occurrence: int,
    detection: int,
    status: str = "open",
    due_date: date | None = None,
) -> QMSRecord:
    return QMSRecord(
        record_id=record_id,
        record_type="deviation",
        site="Site Alpha",
        process_area=process_area,
        severity=severity,
        occurrence=occurrence,
        detection=detection,
        status=status,
        opened_date=date(2026, 4, 1),
        due_date=due_date,
        description="Synthetic record.",
    )


def test_score_process_areas_returns_explainable_advisory_scores():
    records = [
        _record("DEV-001", "sterile manufacturing", 5, 4, 4, due_date=date(2026, 4, 15)),
        _record("CAPA-001", "sterile manufacturing", 4, 3, 3),
        _record("CC-001", "packaging", 2, 2, 2, status="closed"),
    ]

    forecasts = score_process_areas(records, as_of=date(2026, 4, 30))

    sterile = next(item for item in forecasts if item.process_area == "sterile manufacturing")
    packaging = next(item for item in forecasts if item.process_area == "packaging")
    assert sterile.risk_score > packaging.risk_score
    assert sterile.risk_level in {"Medium", "High", "Critical"}
    assert sterile.decision_status == "Advisory only"
    assert "DEV-001" in sterile.source_record_ids
    assert sterile.contributing_factors
