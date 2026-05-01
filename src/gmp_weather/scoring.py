"""Transparent advisory scoring for GMP risk signals."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date

from gmp_weather.config import ScoringConfig, load_scoring_config
from gmp_weather.ontology import RECORD_TYPE_WEIGHTS
from gmp_weather.schemas import (
    AuditFinding,
    CAPA,
    Deviation,
    QMSDataBundle,
    QMSRecord,
    RiskBand,
    RiskForecast,
    RiskHorizon,
    RiskScore,
    SOP,
    TrainingRecord,
)


OPEN_STATUSES = {"open", "in_progress", "assigned", "assessment", "implementation", "qa review", "overdue"}
CLOSED_STATUSES = {"closed", "completed", "cancelled", "retired"}


def score_to_band(score: float, scoring_config: ScoringConfig | None = None) -> RiskBand:
    """Map an advisory score from 0 to 100 into a transparent risk band."""

    bands = (scoring_config or load_scoring_config()).risk_bands
    if score >= bands["severe_storm_min"]:
        return RiskBand.SEVERE_STORM
    if score <= bands["clear_max"]:
        return RiskBand.CLEAR
    if score <= bands["watch_max"]:
        return RiskBand.WATCH
    if score <= bands["advisory_max"]:
        return RiskBand.ADVISORY
    if score <= bands["storm_max"]:
        return RiskBand.STORM
    return RiskBand.SEVERE_STORM


def calculate_all_scores(
    bundle: QMSDataBundle,
    as_of_date: date,
    scoring_config: ScoringConfig | None = None,
) -> list[RiskScore]:
    """Calculate all transparent advisory GMP risk scores for a QMS data bundle."""

    context = _ScoringContext(
        bundle=bundle,
        as_of_date=as_of_date,
        scoring_config=scoring_config or load_scoring_config(),
    )
    scores: list[RiskScore] = []
    scores.extend(_score_deviation_recurrence(context))
    scores.extend(_score_capa_failure(context))
    scores.extend(_score_training_drift(context))
    scores.extend(_score_audit_readiness_gap(context))
    scores.extend(_score_backlog_pressure(context))
    return sorted(scores, key=lambda risk_score: risk_score.score, reverse=True)


class _ScoringContext:
    def __init__(self, bundle: QMSDataBundle, as_of_date: date, scoring_config: ScoringConfig) -> None:
        self.bundle = bundle
        self.as_of_date = as_of_date
        self.scoring_config = scoring_config
        self.capas_by_id = {capa.capa_id: capa for capa in bundle.capas}
        self.sops_by_id = {sop.sop_id: sop for sop in bundle.sops}
        self.audit_findings_by_capa = _group_by_linked_capa(bundle.audit_findings)
        self.owner_workload = _owner_workload(bundle)
        self.department_acceleration = _department_acceleration(bundle, as_of_date, scoring_config)


def _score_deviation_recurrence(context: _ScoringContext) -> list[RiskScore]:
    scores: list[RiskScore] = []
    open_deviations = [deviation for deviation in context.bundle.deviations if _is_open(deviation.status)]

    for deviation in open_deviations:
        points = 0.0
        drivers: list[str] = []
        confidence_penalty = 0.0

        config = context.scoring_config
        deviation_weights = config.deviation_recurrence

        points += _add_driver(drivers, "severity", _severity_points(config, deviation.severity), deviation.severity)
        age_days = (context.as_of_date - deviation.opened_date).days
        if age_days >= deviation_weights["age_60_day_threshold"]:
            points += _add_driver(drivers, "age", deviation_weights["age_at_least_60_days"], f"{age_days} days open")
        elif age_days >= deviation_weights["age_30_day_threshold"]:
            points += _add_driver(drivers, "age", deviation_weights["age_at_least_30_days"], f"{age_days} days open")
        elif age_days >= deviation_weights["age_14_day_threshold"]:
            points += _add_driver(drivers, "age", deviation_weights["age_at_least_14_days"], f"{age_days} days open")

        due_points, due_driver = _due_date_signal(
            deviation.due_date,
            context.as_of_date,
            "deviation due date",
            deviation_weights,
        )
        if due_driver:
            points += _add_driver(drivers, "due-date proximity", due_points, due_driver)
        else:
            confidence_penalty += _missing_field(drivers, "due_date", config)

        prior_deviations = [
            prior
            for prior in context.bundle.deviations
            if prior.deviation_id != deviation.deviation_id and prior.opened_date < deviation.opened_date
        ]
        process_repeats = [
            prior
            for prior in prior_deviations
            if prior.process == deviation.process
            and (deviation.opened_date - prior.opened_date).days
            <= deviation_weights["process_recurrence_lookback_days"]
        ]
        if process_repeats:
            points += _add_driver(
                drivers,
                "same process recurrence",
                min(
                    deviation_weights["same_process_max"],
                    deviation_weights["same_process_per_record"] * len(process_repeats),
                ),
                _ids("deviations", [item.deviation_id for item in process_repeats]),
            )

        if deviation.equipment_id:
            equipment_repeats = [
                prior
                for prior in prior_deviations
                if prior.equipment_id == deviation.equipment_id
                and (deviation.opened_date - prior.opened_date).days
                <= deviation_weights["equipment_recurrence_lookback_days"]
            ]
            if equipment_repeats:
                points += _add_driver(
                    drivers,
                    "same equipment recurrence",
                    min(
                        deviation_weights["same_equipment_max"],
                        deviation_weights["same_equipment_per_record"] * len(equipment_repeats),
                    ),
                    f"{deviation.equipment_id}; {_ids('deviations', [item.deviation_id for item in equipment_repeats])}",
                )
        else:
            confidence_penalty += _missing_field(drivers, "equipment_id", config)

        if deviation.root_cause_category:
            root_cause_repeats = [
                prior
                for prior in prior_deviations
                if prior.root_cause_category == deviation.root_cause_category
                and (deviation.opened_date - prior.opened_date).days
                <= deviation_weights["root_cause_recurrence_lookback_days"]
            ]
            if root_cause_repeats:
                points += _add_driver(
                    drivers,
                    "same root cause recurrence",
                    min(
                        deviation_weights["same_root_cause_max"],
                        deviation_weights["same_root_cause_per_record"] * len(root_cause_repeats),
                    ),
                    f"{deviation.root_cause_category}; {_ids('deviations', [item.deviation_id for item in root_cause_repeats])}",
                )
        else:
            confidence_penalty += _missing_field(drivers, "root_cause_category", config)

        if deviation.capa_id:
            capa = context.capas_by_id.get(deviation.capa_id)
            if capa is None:
                points += _add_driver(
                    drivers,
                    "linked CAPA missing",
                    deviation_weights["linked_capa_missing"],
                    deviation.capa_id,
                )
                confidence_penalty += config.confidence_penalties["missing_field_penalty"]
            elif _is_open(capa.status) and capa.due_date and capa.due_date < context.as_of_date:
                points += _add_driver(
                    drivers,
                    "linked CAPA overdue",
                    deviation_weights["linked_capa_overdue"],
                    deviation.capa_id,
                )
        else:
            points += _add_driver(
                drivers,
                "linked CAPA missing",
                deviation_weights["no_capa_id_present"],
                "no CAPA ID present",
            )
            confidence_penalty += _missing_field(drivers, "capa_id", config)

        workload = context.owner_workload.get(deviation.owner, 0)
        points += _owner_workload_points(drivers, workload, deviation.owner, deviation_weights)

        acceleration = context.department_acceleration.get(deviation.department, 0)
        if acceleration > 0:
            points += _add_driver(
                drivers,
                "department backlog acceleration",
                min(
                    deviation_weights["department_acceleration_max"],
                    acceleration * deviation_weights["department_acceleration_per_record"],
                ),
                f"{deviation.department} increased by {acceleration} new records versus prior "
                f"{deviation_weights['department_prior_window_end_days']:g} days",
            )

        if deviation.sop_id is None:
            confidence_penalty += _missing_field(drivers, "sop_id", config)

        scores.append(
            _risk_score(
                score=points,
                entity_type="deviation",
                entity_id=deviation.deviation_id,
                risk_type="deviation_recurrence",
                drivers=drivers,
                confidence=_confidence(
                    config.confidence_penalties["deviation_recurrence_base"],
                    confidence_penalty,
                    config,
                ),
                scoring_config=config,
            )
        )
    return scores


def _score_capa_failure(context: _ScoringContext) -> list[RiskScore]:
    scores: list[RiskScore] = []
    for capa in [item for item in context.bundle.capas if _is_open(item.status)]:
        points = 0.0
        drivers: list[str] = []
        confidence_penalty = 0.0
        config = context.scoring_config
        capa_weights = config.capa_failure

        due_points, due_driver = _due_date_signal(capa.due_date, context.as_of_date, "CAPA due date", capa_weights)
        if due_driver:
            points += _add_driver(drivers, "overdue or due soon", due_points, due_driver)
        else:
            confidence_penalty += _missing_field(drivers, "due_date", config)

        linked_count = len(capa.linked_deviation_ids)
        if linked_count:
            points += _add_driver(
                drivers,
                "linked deviations count",
                min(capa_weights["linked_deviation_max"], linked_count * capa_weights["linked_deviation_per_record"]),
                f"{linked_count} linked",
            )
        else:
            confidence_penalty += _missing_field(drivers, "linked_deviation_ids", config)

        repeated_after_open = [
            deviation
            for deviation in context.bundle.deviations
            if deviation.opened_date > capa.opened_date
            and deviation.root_cause_category
            and capa.root_cause_category
            and deviation.root_cause_category == capa.root_cause_category
        ]
        if repeated_after_open:
            points += _add_driver(
                drivers,
                "repeated root cause after CAPA opened",
                min(
                    capa_weights["repeated_root_cause_max"],
                    len(repeated_after_open) * capa_weights["repeated_root_cause_per_record"],
                ),
                _ids("deviations", [item.deviation_id for item in repeated_after_open]),
            )

        if capa.action_type.strip().lower() == "retraining only":
            points += _add_driver(
                drivers,
                "Retraining Only action",
                capa_weights["retraining_only_action"],
                "action_type equals Retraining Only",
            )

        if _is_vague_text(capa.action_description, capa_weights):
            points += _add_driver(
                drivers,
                "vague action description",
                capa_weights["vague_action_description"],
                "action description lacks specific verification detail",
            )

        if capa.effectiveness_check_due_date is None:
            points += _add_driver(
                drivers,
                "effectiveness check missing",
                capa_weights["effectiveness_check_missing"],
                "no due date for effectiveness check",
            )
            confidence_penalty += _missing_field(drivers, "effectiveness_check_due_date", config)
        elif capa.effectiveness_check_due_date < context.as_of_date:
            points += _add_driver(
                drivers,
                "effectiveness check overdue",
                capa_weights["effectiveness_check_overdue"],
                f"due {capa.effectiveness_check_due_date.isoformat()}",
            )

        workload = context.owner_workload.get(capa.owner, 0)
        points += _owner_workload_points(drivers, workload, capa.owner, capa_weights)

        for finding in context.audit_findings_by_capa.get(capa.capa_id, []):
            points += _add_driver(
                drivers,
                "related audit finding severity",
                min(
                    capa_weights["related_audit_finding_max"],
                    _severity_points_from_weights(capa_weights, finding.severity)
                    / capa_weights["related_audit_finding_severity_divisor"],
                ),
                f"audit finding {finding.finding_id} is {finding.severity}",
            )

        scores.append(
            _risk_score(
                score=points,
                entity_type="capa",
                entity_id=capa.capa_id,
                risk_type="capa_failure",
                drivers=drivers,
                confidence=_confidence(config.confidence_penalties["capa_failure_base"], confidence_penalty, config),
                scoring_config=config,
            )
        )
    return scores


def _score_training_drift(context: _ScoringContext) -> list[RiskScore]:
    grouped: dict[tuple[str, str, str], list[TrainingRecord]] = defaultdict(list)
    for training in context.bundle.training_records:
        sop = context.sops_by_id.get(training.sop_id)
        process = sop.process if sop else "unknown process"
        grouped[(training.department, process, training.sop_id)].append(training)

    scores: list[RiskScore] = []
    for (department, process, sop_id), records in grouped.items():
        drivers: list[str] = []
        confidence_penalty = 0.0
        points = 0.0
        sop = context.sops_by_id.get(sop_id)
        config = context.scoring_config
        training_weights = config.training_drift

        overdue = [record for record in records if _training_is_overdue(record, context.as_of_date)]
        if overdue:
            points += _add_driver(
                drivers,
                "overdue training count",
                min(
                    training_weights["overdue_training_max"],
                    len(overdue) * training_weights["overdue_training_per_record"],
                ),
                f"{len(overdue)} overdue",
            )

        if sop is None:
            confidence_penalty += _missing_field(drivers, f"SOP {sop_id}", config)
        elif _sop_recently_revised(sop, context.as_of_date, training_weights):
            points += _add_driver(drivers, "SOP recently revised", training_weights["sop_recently_revised"], sop.sop_id)

        due_soon = [
            record
            for record in records
            if _is_open(record.status)
            and record.due_date >= context.as_of_date
            and (record.due_date - context.as_of_date).days <= training_weights["due_soon_day_threshold"]
        ]
        if due_soon:
            points += _add_driver(
                drivers,
                "training due date proximity",
                min(training_weights["due_soon_max"], len(due_soon) * training_weights["due_soon_per_record"]),
                f"{len(due_soon)} due within {training_weights['due_soon_day_threshold']:g} days",
            )

        open_related_deviations = [
            deviation
            for deviation in context.bundle.deviations
            if _is_open(deviation.status) and (deviation.sop_id == sop_id or deviation.process == process)
        ]
        if open_related_deviations:
            points += _add_driver(
                drivers,
                "open deviations linked to SOP or process",
                min(
                    training_weights["open_deviation_max"],
                    len(open_related_deviations) * training_weights["open_deviation_per_record"],
                ),
                _ids("deviations", [item.deviation_id for item in open_related_deviations]),
            )

        related_changes = [
            change
            for change in context.bundle.change_controls
            if _is_open(change.status)
            and change.training_impact
            and (sop_id in change.affected_sop_ids or change.process == process)
        ]
        if related_changes:
            points += _add_driver(
                drivers,
                "training-impacting change controls",
                min(
                    training_weights["training_impacting_change_max"],
                    len(related_changes) * training_weights["training_impacting_change_per_record"],
                ),
                _ids("change controls", [item.change_id for item in related_changes]),
            )

        if drivers:
            scores.append(
                _risk_score(
                    score=points,
                    entity_type="department_process_sop",
                    entity_id=f"{department}|{process}|{sop_id}",
                    risk_type="training_drift",
                    drivers=drivers,
                    confidence=_confidence(config.confidence_penalties["training_drift_base"], confidence_penalty, config),
                    scoring_config=config,
                )
            )
    return scores


def _score_audit_readiness_gap(context: _ScoringContext) -> list[RiskScore]:
    pairs = _department_process_pairs(context.bundle)
    scores: list[RiskScore] = []
    for department, process in sorted(pairs):
        drivers: list[str] = []
        points = 0.0
        config = context.scoring_config
        audit_weights = config.audit_readiness_gap

        severe_open_deviations = [
            deviation
            for deviation in context.bundle.deviations
            if deviation.department == department
            and deviation.process == process
            and _is_open(deviation.status)
            and _severity_rank(deviation.severity, audit_weights) >= audit_weights["major_or_critical_min_rank"]
        ]
        if severe_open_deviations:
            points += _add_driver(
                drivers,
                "open major/critical deviations",
                min(
                    audit_weights["open_major_critical_deviation_max"],
                    len(severe_open_deviations) * audit_weights["open_major_critical_deviation_per_record"],
                ),
                _ids("deviations", [item.deviation_id for item in severe_open_deviations]),
            )

        overdue_capas = [
            capa
            for capa in context.bundle.capas
            if capa.department == department and capa.process == process and _is_open(capa.status) and capa.due_date and capa.due_date < context.as_of_date
        ]
        if overdue_capas:
            points += _add_driver(
                drivers,
                "overdue CAPAs",
                min(audit_weights["overdue_capa_max"], len(overdue_capas) * audit_weights["overdue_capa_per_record"]),
                _ids("CAPAs", [item.capa_id for item in overdue_capas]),
            )

        open_findings = [
            finding
            for finding in context.bundle.audit_findings
            if finding.department == department and finding.process == process and _is_open(finding.status)
        ]
        if open_findings:
            points += _add_driver(
                drivers,
                "open audit findings",
                min(
                    audit_weights["open_audit_finding_max"],
                    len(open_findings) * audit_weights["open_audit_finding_per_record"],
                ),
                _ids("audit findings", [item.finding_id for item in open_findings]),
            )

        recent_sops = [
            sop
            for sop in context.bundle.sops
            if sop.department == department
            and sop.process == process
            and _sop_recently_revised(sop, context.as_of_date, audit_weights)
        ]
        incomplete_training = [
            training
            for training in context.bundle.training_records
            if training.sop_id in {sop.sop_id for sop in recent_sops} and not _is_closed(training.status)
        ]
        if recent_sops and incomplete_training:
            points += _add_driver(
                drivers,
                "recent SOP changes with incomplete training",
                min(
                    audit_weights["incomplete_training_max"],
                    len(incomplete_training) * audit_weights["incomplete_training_per_record"],
                ),
                f"{len(incomplete_training)} incomplete training records",
            )

        open_validation_changes = [
            change
            for change in context.bundle.change_controls
            if change.department == department and change.process == process and change.validation_impact and _is_open(change.status)
        ]
        if open_validation_changes:
            points += _add_driver(
                drivers,
                "validation-impacting change controls still open",
                min(
                    audit_weights["validation_change_max"],
                    len(open_validation_changes) * audit_weights["validation_change_per_record"],
                ),
                _ids("change controls", [item.change_id for item in open_validation_changes]),
            )

        if drivers:
            scores.append(
                _risk_score(
                    score=points,
                    entity_type="department_process",
                    entity_id=f"{department}|{process}",
                    risk_type="audit_readiness_gap",
                    drivers=drivers,
                    confidence=config.confidence_penalties["audit_readiness_gap_base"],
                    scoring_config=config,
                )
            )
    return scores


def _score_backlog_pressure(context: _ScoringContext) -> list[RiskScore]:
    scores: list[RiskScore] = []
    scores.extend(_score_backlog_group(context, "department", _department_key))
    scores.extend(_score_backlog_group(context, "owner", _owner_key))
    return scores


def _score_backlog_group(context: _ScoringContext, entity_type: str, key_fn) -> list[RiskScore]:
    grouped: dict[str, list[Deviation | CAPA]] = defaultdict(list)
    for record in [*context.bundle.deviations, *context.bundle.capas]:
        grouped[key_fn(record)].append(record)

    scores: list[RiskScore] = []
    for entity_id, records in sorted(grouped.items()):
        drivers: list[str] = []
        points = 0.0
        config = context.scoring_config
        backlog_weights = config.backlog_pressure
        open_items = [record for record in records if _is_open(record.status)]
        open_deviations = [record for record in open_items if isinstance(record, Deviation)]
        open_capas = [record for record in open_items if isinstance(record, CAPA)]
        overdue_items = [
            record
            for record in open_items
            if getattr(record, "due_date", None) and record.due_date < context.as_of_date
        ]
        ages = [(context.as_of_date - record.opened_date).days for record in open_items if hasattr(record, "opened_date")]
        recent = [
            record
            for record in records
            if 0 <= (context.as_of_date - record.opened_date).days <= backlog_weights["recent_window_days"]
        ]
        prior = [
            record
            for record in records
            if backlog_weights["prior_window_start_days"]
            <= (context.as_of_date - record.opened_date).days
            <= backlog_weights["prior_window_end_days"]
        ]
        acceleration = max(len(recent) - len(prior), 0)

        if open_deviations:
            points += _add_driver(
                drivers,
                "open deviations",
                min(
                    backlog_weights["open_deviation_max"],
                    len(open_deviations) * backlog_weights["open_deviation_per_record"],
                ),
                str(len(open_deviations)),
            )
        if open_capas:
            points += _add_driver(
                drivers,
                "open CAPAs",
                min(backlog_weights["open_capa_max"], len(open_capas) * backlog_weights["open_capa_per_record"]),
                str(len(open_capas)),
            )
        if overdue_items:
            points += _add_driver(
                drivers,
                "overdue items",
                min(
                    backlog_weights["overdue_item_max"],
                    len(overdue_items) * backlog_weights["overdue_item_per_record"],
                ),
                str(len(overdue_items)),
            )
        if ages:
            average_age = sum(ages) / len(ages)
            if average_age >= backlog_weights["average_age_60_day_threshold"]:
                points += _add_driver(
                    drivers,
                    "average age",
                    backlog_weights["average_age_at_least_60_days"],
                    f"{average_age:.1f} days",
                )
            elif average_age >= backlog_weights["average_age_30_day_threshold"]:
                points += _add_driver(
                    drivers,
                    "average age",
                    backlog_weights["average_age_at_least_30_days"],
                    f"{average_age:.1f} days",
                )
        if acceleration:
            points += _add_driver(
                drivers,
                f"{backlog_weights['recent_window_days']:g}-day intake increase",
                min(
                    backlog_weights["intake_increase_max"],
                    acceleration * backlog_weights["intake_increase_per_record"],
                ),
                f"{len(recent)} recent versus {len(prior)} prior",
            )

        if drivers:
            scores.append(
                _risk_score(
                    score=points,
                    entity_type=entity_type,
                    entity_id=entity_id,
                    risk_type="backlog_pressure",
                    drivers=drivers,
                    confidence=config.confidence_penalties["backlog_pressure_base"],
                    scoring_config=config,
                )
            )
    return scores


def _risk_score(
    *,
    score: float,
    entity_type: str,
    entity_id: str,
    risk_type: str,
    drivers: list[str],
    confidence: float,
    scoring_config: ScoringConfig,
) -> RiskScore:
    bounded_score = max(
        scoring_config.risk_bands["score_min"],
        min(round(score, 1), scoring_config.risk_bands["score_max"]),
    )
    if not drivers:
        drivers = ["No elevated advisory driver found by the transparent rules (+0)"]
    return RiskScore(
        score=bounded_score,
        band=score_to_band(bounded_score, scoring_config=scoring_config),
        horizon=RiskHorizon.FOUR_WEEKS,
        entity_type=entity_type,
        entity_id=entity_id,
        risk_type=risk_type,
        drivers=drivers,
        confidence=max(
            scoring_config.confidence_penalties["confidence_min_output"],
            min(round(confidence, 2), scoring_config.confidence_penalties["confidence_max_output"]),
        ),
    )


def _add_driver(drivers: list[str], name: str, points: float, detail: str) -> float:
    if points <= 0:
        return 0.0
    drivers.append(f"{name}: {detail} (+{points:g})")
    return points


def _missing_field(drivers: list[str], field_name: str, config: ScoringConfig) -> float:
    drivers.append(f"confidence reduced: missing {field_name}")
    return config.confidence_penalties["missing_field_penalty"]


def _confidence(base: float, penalty: float, config: ScoringConfig) -> float:
    return max(config.confidence_penalties["min_confidence"], base - penalty)


def _is_open(status: str | None) -> bool:
    return str(status or "").strip().lower() in OPEN_STATUSES


def _is_closed(status: str | None) -> bool:
    return str(status or "").strip().lower() in CLOSED_STATUSES


def _severity_points(config: ScoringConfig, severity: str | int | None) -> float:
    return _severity_points_from_weights(config.deviation_recurrence, severity)


def _severity_points_from_weights(weights: dict[str, float], severity: str | int | None) -> float:
    if isinstance(severity, int):
        return min(max(severity, 1), 5) * weights["integer_severity_multiplier"]
    normalized = str(severity or "").strip().lower()
    return weights.get(f"severity_{normalized}", weights["severity_medium"])


def _severity_rank(severity: str | int | None, weights: dict[str, float]) -> int:
    if isinstance(severity, int):
        return severity
    normalized = str(severity or "").strip().lower()
    return int(weights.get(f"severity_rank_{normalized}", weights["severity_rank_medium"]))


def _due_date_signal(
    due_date: date | None,
    as_of_date: date,
    label: str,
    weights: dict[str, float],
) -> tuple[float, str | None]:
    if due_date is None:
        return 0.0, None
    days = (due_date - as_of_date).days
    if days < 0:
        return weights["due_overdue"], f"{label} overdue by {abs(days)} days"
    if days <= weights["due_soon_7_day_threshold"]:
        return weights["due_within_7_days"], f"{label} due within {days} days"
    if days <= weights["due_soon_14_day_threshold"]:
        return weights["due_within_14_days"], f"{label} due within {days} days"
    return 0.0, None


def _owner_workload(bundle: QMSDataBundle) -> dict[str, int]:
    owners: Counter[str] = Counter()
    for record in [*bundle.deviations, *bundle.capas, *bundle.change_controls]:
        if _is_open(record.status):
            owners[record.owner] += 1
    return dict(owners)


def _owner_workload_points(drivers: list[str], workload: int, owner: str, weights: dict[str, float]) -> float:
    if workload >= weights["owner_workload_10_item_threshold"]:
        return _add_driver(
            drivers,
            "owner workload",
            weights["owner_workload_at_least_10"],
            f"{owner} has {workload} open items",
        )
    if workload >= weights["owner_workload_5_item_threshold"]:
        return _add_driver(
            drivers,
            "owner workload",
            weights["owner_workload_at_least_5"],
            f"{owner} has {workload} open items",
        )
    if workload >= weights["owner_workload_3_item_threshold"]:
        return _add_driver(
            drivers,
            "owner workload",
            weights["owner_workload_at_least_3"],
            f"{owner} has {workload} open items",
        )
    return 0.0


def _department_acceleration(
    bundle: QMSDataBundle,
    as_of_date: date,
    config: ScoringConfig,
) -> dict[str, int]:
    weights = config.deviation_recurrence
    departments = {record.department for record in [*bundle.deviations, *bundle.capas]}
    acceleration: dict[str, int] = {}
    for department in departments:
        records = [
            record
            for record in [*bundle.deviations, *bundle.capas]
            if record.department == department
        ]
        recent = [
            record
            for record in records
            if 0 <= (as_of_date - record.opened_date).days <= weights["department_recent_window_days"]
        ]
        prior = [
            record
            for record in records
            if weights["department_prior_window_start_days"]
            <= (as_of_date - record.opened_date).days
            <= weights["department_prior_window_end_days"]
        ]
        acceleration[department] = max(len(recent) - len(prior), 0)
    return acceleration


def _group_by_linked_capa(findings: list[AuditFinding]) -> dict[str, list[AuditFinding]]:
    grouped: dict[str, list[AuditFinding]] = defaultdict(list)
    for finding in findings:
        if finding.linked_capa_id:
            grouped[finding.linked_capa_id].append(finding)
    return grouped


def _ids(label: str, ids: list[str]) -> str:
    return f"{label}: {', '.join(ids)}"


def _is_vague_text(value: str, weights: dict[str, float]) -> bool:
    normalized = value.strip().lower()
    vague_terms = ["monitor", "review", "as needed", "tbd", "follow up", "check later"]
    has_specific_evidence = any(term in normalized for term in ["trend", "metric", "sample", "audit", "effectiveness", "verify"])
    return len(normalized.split()) < weights["vague_description_word_threshold"] or (
        any(term in normalized for term in vague_terms) and not has_specific_evidence
    )


def _training_is_overdue(training: TrainingRecord, as_of_date: date) -> bool:
    return not _is_closed(training.status) and training.due_date < as_of_date


def _sop_recently_revised(sop: SOP, as_of_date: date, weights: dict[str, float]) -> bool:
    relevant_dates = [sop.effective_date]
    if sop.revision_date:
        relevant_dates.append(sop.revision_date)
    return any(0 <= (as_of_date - item).days <= weights["sop_recent_window_days"] for item in relevant_dates)


def _department_process_pairs(bundle: QMSDataBundle) -> set[tuple[str, str]]:
    pairs: set[tuple[str, str]] = set()
    for record in [*bundle.deviations, *bundle.capas, *bundle.audit_findings, *bundle.change_controls, *bundle.sops]:
        pairs.add((record.department, record.process))
    return pairs


def _department_key(record: Deviation | CAPA) -> str:
    return record.department


def _owner_key(record: Deviation | CAPA) -> str:
    return record.owner


def score_process_areas(
    records: list[QMSRecord],
    as_of: date | None = None,
    scoring_config: ScoringConfig | None = None,
) -> list[RiskForecast]:
    """Score each process area with a transparent rule-based method."""

    reference_date = as_of or date.today()
    config = scoring_config or load_scoring_config()
    grouped: dict[str, list[QMSRecord]] = defaultdict(list)
    for record in records:
        grouped[record.process_area].append(record)

    forecasts = [
        _score_one_area(process_area, area_records, reference_date, config)
        for process_area, area_records in sorted(grouped.items())
    ]
    return sorted(forecasts, key=lambda item: item.risk_score, reverse=True)


def _score_one_area(
    process_area: str,
    records: list[QMSRecord],
    as_of: date,
    config: ScoringConfig,
) -> RiskForecast:
    weights = config.legacy_process_area
    source_ids = [record.record_id for record in records]
    record_scores = [_score_one_record(record, as_of, config) for record in records]
    open_records = [record for record in records if record.status in {"open", "in_progress"}]
    overdue_records = [record for record in open_records if record.due_date and record.due_date < as_of]
    high_severity_records = [record for record in records if record.severity >= weights["high_severity_min"]]

    average_score = sum(record_scores) / len(record_scores)
    volume_signal = min(
        len(open_records) * weights["process_volume_per_open_record"],
        weights["process_volume_max"],
    )
    overdue_signal = min(
        len(overdue_records) * weights["process_overdue_per_record"],
        weights["process_overdue_max"],
    )
    score = min(round(average_score + volume_signal + overdue_signal, 1), weights["record_score_max"])

    factors: list[str] = []
    if high_severity_records:
        factors.append("High severity records: " + ", ".join(r.record_id for r in high_severity_records))
    if open_records:
        factors.append("Open or in-progress records: " + ", ".join(r.record_id for r in open_records))
    if overdue_records:
        factors.append("Overdue records: " + ", ".join(r.record_id for r in overdue_records))
    if not factors:
        factors.append("No elevated signal found in the current synthetic sample.")

    level = risk_level(score, config)
    return RiskForecast(
        process_area=process_area,
        risk_score=score,
        risk_level=level,
        advisory_summary=_summary_for_level(level),
        source_record_ids=source_ids,
        contributing_factors=factors,
    )


def _score_one_record(record: QMSRecord, as_of: date, config: ScoringConfig) -> float:
    weights = config.legacy_process_area
    rpn_score = (
        (record.severity * record.occurrence * record.detection)
        / weights["qms_rpn_denominator"]
        * weights["qms_rpn_scale"]
    )
    status_signal = weights["open_status_signal"] if record.status in {"open", "in_progress"} else 0
    overdue_signal = (
        weights["overdue_signal"]
        if record.status in {"open", "in_progress"} and record.due_date and record.due_date < as_of
        else 0
    )
    type_weight = RECORD_TYPE_WEIGHTS.get(record.record_type, 1.0)
    return min((rpn_score + status_signal + overdue_signal) * type_weight, weights["record_score_max"])


def risk_level(score: float, scoring_config: ScoringConfig | None = None) -> str:
    """Map a numeric score to a human-readable advisory band."""

    weights = (scoring_config or load_scoring_config()).legacy_process_area
    if score >= weights["risk_level_critical_min"]:
        return "Critical"
    if score >= weights["risk_level_high_min"]:
        return "High"
    if score >= weights["risk_level_medium_min"]:
        return "Medium"
    return "Low"


def _summary_for_level(level: str) -> str:
    if level == "Critical":
        return "Immediate QA human review is recommended before relying on this signal."
    if level == "High":
        return "QA human review is recommended soon; this is not a GMP decision."
    if level == "Medium":
        return "Monitor and review during the next quality governance discussion."
    return "No elevated signal in this sample, but normal human oversight still applies."
