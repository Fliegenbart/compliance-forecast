"""Retrospective backtesting helpers for transparent risk-ranking review.

The functions in this module estimate historical risk-ranking utility on
synthetic or anonymized data. They are not proof of prevention, not a validated
prediction model, and not a guarantee of future GMP performance.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from math import ceil
from statistics import mean
from typing import Iterable

import pandas as pd

from gmp_weather.config import ScoringConfig
from gmp_weather.schemas import (
    CAPA,
    ChangeControl,
    Deviation,
    QMSDataBundle,
    QMSRecord,
    RiskForecast,
    RiskScore,
    SOP,
    TrainingRecord,
)
from gmp_weather.scoring import calculate_all_scores, score_process_areas


MODEL_METHOD = "rules-v0.1"
BASELINE_METHOD = "oldest_open_backlog_baseline"
OPEN_STATUSES = {"open", "in_progress", "assigned", "assessment", "implementation", "qa review", "overdue"}
CLOSED_STATUSES = {"closed", "completed", "cancelled", "retired"}
PREDICTION_COLUMNS = [
    "method",
    "forecast_date",
    "rank",
    "score",
    "risk_type",
    "entity_type",
    "entity_id",
    "department",
    "process",
    "owner",
    "top_driver",
    "matched_future_event_count",
    "matched_event_ids",
    "later_outcomes",
    "earliest_outcome_date",
    "lead_time_days",
]
EVENT_COLUMNS = [
    "forecast_date",
    "event_id",
    "event_type",
    "event_date",
    "domain",
    "entity_id",
    "department",
    "process",
    "owner",
    "severity",
    "root_cause_category",
    "equipment_id",
    "related_record_ids",
]
FORECAST_SUMMARY_COLUMNS = [
    "forecast_date",
    "historical_scores",
    "baseline_items",
    "future_events",
    "future_major_events",
    "model_precision_at_10",
    "baseline_precision_at_10",
]


@dataclass(frozen=True)
class FutureQualityEvent:
    """A synthetic future quality event used only for retrospective review."""

    forecast_date: date
    event_id: str
    event_type: str
    event_date: date
    domain: str
    entity_id: str
    department: str
    process: str
    owner: str = ""
    severity: str = ""
    root_cause_category: str = ""
    equipment_id: str = ""
    related_record_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class BacktestResult:
    """Structured historical backtest output for dashboard display and tests."""

    forecast_dates: list[date]
    horizon_days: int
    metric_summary: dict[str, float]
    baseline_metric_summary: dict[str, float]
    predictions_frame: pd.DataFrame
    events_frame: pd.DataFrame
    forecast_summary_frame: pd.DataFrame
    limitations: list[str]


def run_backtest(
    bundle: QMSDataBundle,
    forecast_dates: Iterable[date],
    horizon_days: int,
    scoring_config: ScoringConfig | None = None,
) -> BacktestResult:
    """Run a retrospective historical backtest of advisory risk-ranking utility.

    For each forecast date, the scoring engine sees only records available as of
    that date. Future events are then checked in the next ``horizon_days``. The
    output compares the transparent risk ranking with a simple oldest-open-item
    backlog baseline.
    """

    if horizon_days <= 0:
        raise ValueError("horizon_days must be greater than zero")

    normalized_dates = sorted(set(forecast_dates))
    all_model_rows: list[dict[str, object]] = []
    all_baseline_rows: list[dict[str, object]] = []
    all_events: list[FutureQualityEvent] = []
    summary_rows: list[dict[str, object]] = []

    for forecast_date in normalized_dates:
        historical_bundle = _historical_bundle(bundle, forecast_date)
        future_events = _future_events(bundle, historical_bundle, forecast_date, horizon_days)
        model_rows = _attach_outcomes(
            _risk_prediction_rows(historical_bundle, forecast_date, scoring_config),
            future_events,
        )
        baseline_rows = _attach_outcomes(_baseline_prediction_rows(historical_bundle, forecast_date), future_events)

        all_model_rows.extend(model_rows)
        all_baseline_rows.extend(baseline_rows)
        all_events.extend(future_events)

        model_metrics = _calculate_metrics(model_rows, future_events, [forecast_date])
        baseline_metrics = _calculate_metrics(baseline_rows, future_events, [forecast_date])
        summary_rows.append(
            {
                "forecast_date": forecast_date,
                "historical_scores": len(model_rows),
                "baseline_items": len(baseline_rows),
                "future_events": len(future_events),
                "future_major_events": sum(1 for event in future_events if event.event_type == "major_or_critical_deviation"),
                "model_precision_at_10": model_metrics["precision_at_10"],
                "baseline_precision_at_10": baseline_metrics["precision_at_10"],
            }
        )

    metric_summary = _calculate_metrics(all_model_rows, all_events, normalized_dates)
    baseline_metric_summary = _calculate_metrics(all_baseline_rows, all_events, normalized_dates)
    return BacktestResult(
        forecast_dates=normalized_dates,
        horizon_days=horizon_days,
        metric_summary=metric_summary,
        baseline_metric_summary=baseline_metric_summary,
        predictions_frame=_prediction_frame([*all_model_rows, *all_baseline_rows]),
        events_frame=_events_frame(all_events),
        forecast_summary_frame=pd.DataFrame(summary_rows, columns=FORECAST_SUMMARY_COLUMNS),
        limitations=[
            "This is a historical backtest of risk-ranking utility on synthetic data.",
            "The results are not proof of prevention and do not demonstrate GMP control effectiveness.",
            "The results are not a guarantee of future performance.",
            "Outcome matching uses transparent department, process, owner, and entity overlap heuristics.",
            "Human QA review remains mandatory for interpreting every signal.",
        ],
    )


def build_backtest_frame(records: list[QMSRecord], end_date: date | None = None, periods: int = 4) -> pd.DataFrame:
    """Create a simple historical score view without predicting GMP outcomes."""

    reference_end = end_date or date.today()
    rows: list[dict[str, object]] = []
    for index in range(periods):
        as_of = reference_end - timedelta(days=7 * (periods - index - 1))
        visible_records = [record for record in records if record.opened_date <= as_of]
        for forecast in score_process_areas(visible_records, as_of=as_of):
            rows.append(_legacy_forecast_row(as_of, forecast))
    return pd.DataFrame(rows)


def _legacy_forecast_row(as_of: date, forecast: RiskForecast) -> dict[str, object]:
    return {
        "as_of": as_of,
        "process_area": forecast.process_area,
        "risk_score": forecast.risk_score,
        "risk_level": forecast.risk_level,
    }


def _historical_bundle(bundle: QMSDataBundle, as_of_date: date) -> QMSDataBundle:
    return QMSDataBundle(
        deviations=[
            _deviation_as_of(record, as_of_date)
            for record in bundle.deviations
            if record.opened_date <= as_of_date
        ],
        capas=[_capa_as_of(record, as_of_date) for record in bundle.capas if record.opened_date <= as_of_date],
        audit_findings=[record for record in bundle.audit_findings if record.audit_date <= as_of_date],
        training_records=[
            _training_as_of(record, as_of_date)
            for record in bundle.training_records
            if record.assigned_date <= as_of_date
        ],
        change_controls=[
            _change_as_of(record, as_of_date)
            for record in bundle.change_controls
            if record.opened_date <= as_of_date
        ],
        sops=[_sop_as_of(record, as_of_date) for record in bundle.sops if record.effective_date <= as_of_date],
    )


def _deviation_as_of(record: Deviation, as_of_date: date) -> Deviation:
    if record.closed_date and record.closed_date > as_of_date:
        return record.model_copy(update={"status": "open", "closed_date": None})
    return record


def _capa_as_of(record: CAPA, as_of_date: date) -> CAPA:
    if record.closed_date and record.closed_date > as_of_date:
        return record.model_copy(update={"status": "open", "closed_date": None})
    return record


def _training_as_of(record: TrainingRecord, as_of_date: date) -> TrainingRecord:
    if record.completion_date and record.completion_date > as_of_date:
        return record.model_copy(update={"status": "assigned", "completion_date": None})
    return record


def _change_as_of(record: ChangeControl, as_of_date: date) -> ChangeControl:
    if record.closed_date and record.closed_date > as_of_date:
        return record.model_copy(update={"status": "open", "closed_date": None})
    return record


def _sop_as_of(record: SOP, as_of_date: date) -> SOP:
    if record.revision_date and record.revision_date > as_of_date:
        return record.model_copy(update={"revision_date": None})
    return record


def _future_events(
    full_bundle: QMSDataBundle,
    historical_bundle: QMSDataBundle,
    forecast_date: date,
    horizon_days: int,
) -> list[FutureQualityEvent]:
    horizon_end = forecast_date + timedelta(days=horizon_days)
    events: list[FutureQualityEvent] = []

    for deviation in full_bundle.deviations:
        if not forecast_date < deviation.opened_date <= horizon_end:
            continue
        if _severity_rank(deviation.severity) >= _severity_rank("major"):
            events.append(_event_from_deviation(forecast_date, deviation, "major_or_critical_deviation"))
        related_prior = _historical_repeat_sources(deviation, historical_bundle.deviations)
        if related_prior:
            events.append(
                _event_from_deviation(
                    forecast_date,
                    deviation,
                    "repeat_deviation",
                    related_record_ids=tuple(item.deviation_id for item in related_prior),
                )
            )

    for capa in full_bundle.capas:
        if (
            capa.opened_date <= forecast_date
            and capa.due_date
            and forecast_date < capa.due_date <= horizon_end
            and not (capa.closed_date and capa.closed_date <= capa.due_date)
        ):
            events.append(
                FutureQualityEvent(
                    forecast_date=forecast_date,
                    event_id=capa.capa_id,
                    event_type="capa_becoming_overdue",
                    event_date=capa.due_date,
                    domain="capa",
                    entity_id=capa.capa_id,
                    department=capa.department,
                    process=capa.process,
                    owner=capa.owner,
                    root_cause_category=capa.root_cause_category or "",
                    related_record_ids=tuple(capa.linked_deviation_ids),
                )
            )

    for finding in full_bundle.audit_findings:
        if forecast_date < finding.audit_date <= horizon_end:
            events.append(
                FutureQualityEvent(
                    forecast_date=forecast_date,
                    event_id=finding.finding_id,
                    event_type="audit_finding_opened",
                    event_date=finding.audit_date,
                    domain="audit_finding",
                    entity_id=finding.finding_id,
                    department=finding.department,
                    process=finding.process,
                    owner="",
                    severity=finding.severity,
                    related_record_ids=(finding.linked_capa_id,) if finding.linked_capa_id else (),
                )
            )

    return sorted(events, key=lambda item: (item.event_date, item.event_type, item.event_id))


def _event_from_deviation(
    forecast_date: date,
    deviation: Deviation,
    event_type: str,
    related_record_ids: tuple[str, ...] = (),
) -> FutureQualityEvent:
    return FutureQualityEvent(
        forecast_date=forecast_date,
        event_id=deviation.deviation_id,
        event_type=event_type,
        event_date=deviation.opened_date,
        domain="deviation",
        entity_id=deviation.deviation_id,
        department=deviation.department,
        process=deviation.process,
        owner=deviation.owner,
        severity=deviation.severity,
        root_cause_category=deviation.root_cause_category or "",
        equipment_id=deviation.equipment_id or "",
        related_record_ids=related_record_ids,
    )


def _historical_repeat_sources(deviation: Deviation, prior_deviations: list[Deviation]) -> list[Deviation]:
    if not deviation.root_cause_category and not deviation.equipment_id:
        return []
    return [
        prior
        for prior in prior_deviations
        if prior.opened_date < deviation.opened_date
        and prior.process == deviation.process
        and (
            bool(deviation.root_cause_category and prior.root_cause_category == deviation.root_cause_category)
            or bool(deviation.equipment_id and prior.equipment_id == deviation.equipment_id)
        )
    ]


def _risk_prediction_rows(
    bundle: QMSDataBundle,
    forecast_date: date,
    scoring_config: ScoringConfig | None,
) -> list[dict[str, object]]:
    scores = calculate_all_scores(bundle, forecast_date, scoring_config=scoring_config)
    rows: list[dict[str, object]] = []
    for rank, score in enumerate(scores, start=1):
        context = _score_context(score, bundle)
        rows.append(
            {
                "method": MODEL_METHOD,
                "forecast_date": forecast_date,
                "rank": rank,
                "score": score.score,
                "risk_type": score.risk_type,
                "entity_type": score.entity_type,
                "entity_id": score.entity_id,
                "department": context["department"],
                "process": context["process"],
                "owner": context["owner"],
                "root_cause_category": context["root_cause_category"],
                "equipment_id": context["equipment_id"],
                "top_driver": score.drivers[0] if score.drivers else "",
            }
        )
    return rows


def _score_context(score: RiskScore, bundle: QMSDataBundle) -> dict[str, str]:
    deviations = {record.deviation_id: record for record in bundle.deviations}
    capas = {record.capa_id: record for record in bundle.capas}
    changes = {record.change_id: record for record in bundle.change_controls}
    context = {"department": "", "process": "", "owner": "", "root_cause_category": "", "equipment_id": ""}

    if score.entity_type == "deviation" and score.entity_id in deviations:
        deviation = deviations[score.entity_id]
        context.update(
            {
                "department": deviation.department,
                "process": deviation.process,
                "owner": deviation.owner,
                "root_cause_category": deviation.root_cause_category or "",
                "equipment_id": deviation.equipment_id or "",
            }
        )
    elif score.entity_type == "capa" and score.entity_id in capas:
        capa = capas[score.entity_id]
        context.update(
            {
                "department": capa.department,
                "process": capa.process,
                "owner": capa.owner,
                "root_cause_category": capa.root_cause_category or "",
            }
        )
    elif score.entity_type == "change_control" and score.entity_id in changes:
        change = changes[score.entity_id]
        context.update({"department": change.department, "process": change.process, "owner": change.owner})
    elif score.entity_type in {"department_process", "department_process_sop"}:
        parts = score.entity_id.split("|")
        if len(parts) >= 2:
            context.update({"department": parts[0], "process": parts[1]})
    elif score.entity_type == "department":
        context["department"] = score.entity_id
    elif score.entity_type == "owner":
        context["owner"] = score.entity_id

    return context


def _baseline_prediction_rows(bundle: QMSDataBundle, forecast_date: date) -> list[dict[str, object]]:
    backlog_items: list[tuple[int, str, Deviation | CAPA | ChangeControl]] = []
    for record in bundle.deviations:
        if _is_open_status(record.status):
            backlog_items.append(((forecast_date - record.opened_date).days, "deviation", record))
    for record in bundle.capas:
        if _is_open_status(record.status):
            backlog_items.append(((forecast_date - record.opened_date).days, "capa", record))
    for record in bundle.change_controls:
        if _is_open_status(record.status):
            backlog_items.append(((forecast_date - record.opened_date).days, "change_control", record))

    rows: list[dict[str, object]] = []
    for rank, (age_days, entity_type, record) in enumerate(
        sorted(backlog_items, key=lambda item: (item[0], item[2].department, item[2].process), reverse=True),
        start=1,
    ):
        entity_id = _record_id(entity_type, record)
        rows.append(
            {
                "method": BASELINE_METHOD,
                "forecast_date": forecast_date,
                "rank": rank,
                "score": float(max(age_days, 0)),
                "risk_type": "oldest_open_item",
                "entity_type": entity_type,
                "entity_id": entity_id,
                "department": record.department,
                "process": record.process,
                "owner": record.owner,
                "root_cause_category": getattr(record, "root_cause_category", "") or "",
                "equipment_id": getattr(record, "equipment_id", "") or "",
                "top_driver": f"oldest open item: {age_days} days open",
            }
        )
    return rows


def _record_id(entity_type: str, record: Deviation | CAPA | ChangeControl) -> str:
    if entity_type == "deviation":
        return record.deviation_id
    if entity_type == "capa":
        return record.capa_id
    return record.change_id


def _attach_outcomes(
    prediction_rows: list[dict[str, object]],
    future_events: list[FutureQualityEvent],
) -> list[dict[str, object]]:
    enriched: list[dict[str, object]] = []
    for row in prediction_rows:
        matches = [event for event in future_events if _prediction_matches_event(row, event)]
        sorted_matches = sorted(matches, key=lambda item: (item.event_date, item.event_type, item.event_id))
        lead_times = [(event.event_date - row["forecast_date"]).days for event in sorted_matches]
        enriched_row = {
            **row,
            "_matched_event_ids": [event.event_id for event in sorted_matches],
            "_matched_events": sorted_matches,
            "matched_future_event_count": len(sorted_matches),
            "hit": bool(sorted_matches),
            "later_outcomes": "; ".join(f"{event.event_type}:{event.event_id}" for event in sorted_matches),
            "earliest_outcome_date": sorted_matches[0].event_date if sorted_matches else None,
            "lead_time_days": min(lead_times) if lead_times else None,
        }
        enriched.append(enriched_row)
    return enriched


def _prediction_matches_event(row: dict[str, object], event: FutureQualityEvent) -> bool:
    entity_type = str(row.get("entity_type", ""))
    entity_id = str(row.get("entity_id", ""))
    department = str(row.get("department", ""))
    process = str(row.get("process", ""))
    owner = str(row.get("owner", ""))
    root_cause_category = str(row.get("root_cause_category", ""))
    equipment_id = str(row.get("equipment_id", ""))

    if entity_id and entity_id == event.entity_id:
        return True
    if entity_type == "department" and entity_id == event.department:
        return True
    if entity_type == "owner" and owner and owner == event.owner:
        return True
    if department and process and department == event.department and process == event.process:
        return True
    if (
        process
        and process == event.process
        and (
            bool(root_cause_category and root_cause_category == event.root_cause_category)
            or bool(equipment_id and equipment_id == event.equipment_id)
        )
    ):
        return True
    return False


def _calculate_metrics(
    prediction_rows: list[dict[str, object]],
    future_events: list[FutureQualityEvent],
    forecast_dates: list[date],
) -> dict[str, float]:
    return {
        "precision_at_10": _precision_at(prediction_rows, forecast_dates, 10),
        "precision_at_20": _precision_at(prediction_rows, forecast_dates, 20),
        "recall_for_future_major_events": _major_event_recall(prediction_rows, future_events, top_k=20),
        "top_decile_lift": _top_decile_lift(prediction_rows, forecast_dates),
        "lead_time_days": _lead_time_days(prediction_rows, top_k=20),
    }


def _precision_at(prediction_rows: list[dict[str, object]], forecast_dates: list[date], k: int) -> float:
    if not forecast_dates:
        return 0.0
    values: list[float] = []
    for forecast_date in forecast_dates:
        rows = sorted(
            [row for row in prediction_rows if row["forecast_date"] == forecast_date],
            key=lambda item: int(item["rank"]),
        )
        top_rows = rows[:k]
        values.append(_ratio(sum(1 for row in top_rows if row["hit"]), len(top_rows)))
    return round(mean(values), 3) if values else 0.0


def _major_event_recall(
    prediction_rows: list[dict[str, object]],
    future_events: list[FutureQualityEvent],
    top_k: int,
) -> float:
    major_event_keys = {
        (event.forecast_date, event.event_id)
        for event in future_events
        if event.event_type == "major_or_critical_deviation"
    }
    if not major_event_keys:
        return 0.0

    captured: set[tuple[date, str]] = set()
    for row in prediction_rows:
        if int(row["rank"]) > top_k:
            continue
        for event in row["_matched_events"]:
            key = (event.forecast_date, event.event_id)
            if key in major_event_keys:
                captured.add(key)
    return _ratio(len(captured), len(major_event_keys))


def _top_decile_lift(prediction_rows: list[dict[str, object]], forecast_dates: list[date]) -> float:
    if not prediction_rows:
        return 0.0
    top_decile_rows: list[dict[str, object]] = []
    for forecast_date in forecast_dates:
        rows = sorted(
            [row for row in prediction_rows if row["forecast_date"] == forecast_date],
            key=lambda item: int(item["rank"]),
        )
        if rows:
            cutoff = max(1, ceil(len(rows) * 0.10))
            top_decile_rows.extend(rows[:cutoff])

    overall_hit_rate = _ratio(sum(1 for row in prediction_rows if row["hit"]), len(prediction_rows))
    top_hit_rate = _ratio(sum(1 for row in top_decile_rows if row["hit"]), len(top_decile_rows))
    if overall_hit_rate == 0:
        return 0.0
    return round(top_hit_rate / overall_hit_rate, 3)


def _lead_time_days(prediction_rows: list[dict[str, object]], top_k: int) -> float:
    lead_times: list[int] = []
    seen: set[tuple[date, str]] = set()
    for row in prediction_rows:
        if int(row["rank"]) > top_k:
            continue
        for event in row["_matched_events"]:
            key = (event.forecast_date, event.event_id)
            if key in seen:
                continue
            seen.add(key)
            lead_times.append((event.event_date - event.forecast_date).days)
    return round(mean(lead_times), 1) if lead_times else 0.0


def _prediction_frame(rows: list[dict[str, object]]) -> pd.DataFrame:
    display_rows = []
    for row in rows:
        display_rows.append(
            {
                **{column: row.get(column, "") for column in PREDICTION_COLUMNS},
                "matched_event_ids": ", ".join(row.get("_matched_event_ids", [])),
                "earliest_outcome_date": row["earliest_outcome_date"].isoformat()
                if row.get("earliest_outcome_date")
                else "",
                "lead_time_days": row["lead_time_days"] if row.get("lead_time_days") is not None else "",
            }
        )
    return pd.DataFrame(display_rows, columns=PREDICTION_COLUMNS)


def _events_frame(events: list[FutureQualityEvent]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "forecast_date": event.forecast_date,
                "event_id": event.event_id,
                "event_type": event.event_type,
                "event_date": event.event_date,
                "domain": event.domain,
                "entity_id": event.entity_id,
                "department": event.department,
                "process": event.process,
                "owner": event.owner,
                "severity": event.severity,
                "root_cause_category": event.root_cause_category,
                "equipment_id": event.equipment_id,
                "related_record_ids": ", ".join(event.related_record_ids),
            }
            for event in events
        ],
        columns=EVENT_COLUMNS,
    )


def _ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 3) if denominator else 0.0


def _is_open_status(status: str | None) -> bool:
    return str(status or "").strip().lower() in OPEN_STATUSES


def _severity_rank(severity: str | int | None) -> int:
    if isinstance(severity, int):
        return severity
    return {
        "minor": 1,
        "medium": 2,
        "major": 3,
        "critical": 4,
    }.get(str(severity or "").strip().lower(), 2)
