"""Markdown diagnostic reporting for advisory GMP risk-prioritization demos.

Reports generated here are source-linked diagnostic summaries for human QA
review. They are not GMP decisions, validation evidence, or regulatory
conclusions.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from gmp_weather.audit_log import ForecastRunLog
from gmp_weather.backtesting import BacktestResult
from gmp_weather.data_quality import DataQualityReport
from gmp_weather.schemas import EvidenceCard, QMSDataBundle, RiskScore


DEFAULT_REPORT_PATH = Path("output") / "diagnostic_report.md"
SAFE_WORDING = (
    "This diagnostic report is based on available data, highlights elevated risk signal patterns, "
    "is recommended for human QA review, and is not a GMP decision."
)


def generate_markdown_diagnostic_report(
    bundle: QMSDataBundle,
    scores: list[RiskScore],
    evidence_cards: list[EvidenceCard],
    data_quality_report: DataQualityReport,
    backtest_results: BacktestResult,
    forecast_run_log: ForecastRunLog,
) -> str:
    """Generate an exportable 30-day advisory diagnostic report as Markdown."""

    sorted_scores = sorted(scores, key=lambda item: item.score, reverse=True)
    sections = [
        "# GMP Risiko-Cockpit - 30-Day Diagnostic Report",
        "",
        SAFE_WORDING,
        "",
        _executive_summary(sorted_scores, evidence_cards, data_quality_report, backtest_results, forecast_run_log),
        _intended_use_and_limitations(),
        _data_sources_analyzed(bundle, forecast_run_log),
        _data_quality_assessment(data_quality_report),
        _overall_risk_prioritization(sorted_scores),
        _top_forecasted_risks(sorted_scores),
        _risk_type_section("7. Deviation Recurrence Signals", "deviation_recurrence", sorted_scores, evidence_cards),
        _risk_type_section("8. CAPA Failure Risk Signals", "capa_failure", sorted_scores, evidence_cards),
        _risk_type_section("9. Training Drift Signals", "training_drift", sorted_scores, evidence_cards),
        _risk_type_section("10. Audit Readiness Gap Signals", "audit_readiness_gap", sorted_scores, evidence_cards),
        _risk_type_section("11. Backlog Pressure Analysis", "backlog_pressure", sorted_scores, evidence_cards),
        _evidence_card_appendix(evidence_cards),
        _backtesting_summary(backtest_results),
        _recommended_pilot_scope(),
        _human_decision_boundaries(),
    ]
    return "\n\n".join(section.rstrip() for section in sections if section.strip()) + "\n"


def export_diagnostic_report(report_markdown: str, output_path: Path | str = DEFAULT_REPORT_PATH) -> Path:
    """Export Markdown report text to ``output/diagnostic_report.md`` by default."""

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report_markdown, encoding="utf-8")
    return path


def _executive_summary(
    sorted_scores: list[RiskScore],
    evidence_cards: list[EvidenceCard],
    data_quality_report: DataQualityReport,
    backtest_results: BacktestResult,
    forecast_run_log: ForecastRunLog,
) -> str:
    top_score = sorted_scores[0] if sorted_scores else None
    top_signal = (
        f"{top_score.risk_type} for {top_score.entity_type} {top_score.entity_id} "
        f"with score {top_score.score:.1f} ({top_score.band.value})"
        if top_score
        else "no visible advisory score"
    )
    return "\n".join(
        [
            "## 1. Executive Summary",
            "",
            (
                "Based on available data, the 30-day diagnostic view identifies elevated risk signal "
                "patterns for prioritization and recommended for human QA review. The highest current "
                f"signal is {top_signal}. This report is not a GMP decision and does not claim prediction certainty."
            ),
            "",
            _bullet_list(
                [
                    f"Risk run ID: {forecast_run_log.forecast_run_id}",
                    f"As-of date: {forecast_run_log.as_of_date.isoformat()}",
                    f"Model version: {forecast_run_log.model_version}",
                    f"Risk scores reviewed: {len(sorted_scores)}",
                    f"Evidence cards reviewed: {len(evidence_cards)}",
                    f"Data readiness score: {data_quality_report.data_readiness_score}/100",
                    (
                        "Historical backtest suggests "
                        f"Precision@10 of {backtest_results.metric_summary.get('precision_at_10', 0.0):.2f}; "
                        "this is risk-ranking utility only, not proof of prevention."
                    ),
                ]
            ),
        ]
    )


def _intended_use_and_limitations() -> str:
    return "\n".join(
        [
            "## 2. Intended Use And Limitations",
            "",
            "This report supports advisory quality-risk discussion for a read-only MVP. It is recommended for human QA review and is not a GMP decision.",
            "",
            _bullet_list(
                [
                    "Intended use: prioritize human review of deviations, CAPAs, training drift, audit readiness, and backlog pressure.",
                    "Limitation: rule weights are illustrative and require SME review before a controlled pilot.",
                    "Limitation: the report does not approve, reject, close, release, certify, qualify, or disposition any GMP item.",
                    "Limitation: the diagnostic report does not claim prediction certainty or regulatory non-compliance.",
                    "Boundary: all conclusions must remain with qualified human QA personnel.",
                ]
            ),
        ]
    )


def _data_sources_analyzed(bundle: QMSDataBundle, forecast_run_log: ForecastRunLog) -> str:
    rows = [
        ("deviations", len(bundle.deviations)),
        ("capas", len(bundle.capas)),
        ("audit_findings", len(bundle.audit_findings)),
        ("training_records", len(bundle.training_records)),
        ("change_controls", len(bundle.change_controls)),
        ("sops", len(bundle.sops)),
    ]
    source_rows = [(name, forecast_run_log.source_file_hashes.get(name, "")[:12]) for name in forecast_run_log.source_file_names]
    return "\n".join(
        [
            "## 3. Data Sources Analyzed",
            "",
            "The report uses local source files recorded in the risk run log. Source hashes support traceability; they do not make this output a GMP record.",
            "",
            _markdown_table(["Domain", "Record count"], rows),
            "",
            _markdown_table(["Source file", "SHA-256 prefix"], source_rows),
        ]
    )


def _data_quality_assessment(report: DataQualityReport) -> str:
    issue_rows = [(severity, count) for severity, count in sorted(report.issue_count_by_severity.items())]
    top_issues = [
        (issue.domain, issue.record_id, issue.severity, issue.message)
        for issue in report.issue_list[:15]
    ]
    return "\n".join(
        [
            "## 4. Data Quality Assessment",
            "",
            (
                f"Data readiness score is {report.data_readiness_score}/100. Based on available data, "
                "data quality issues should be reviewed before relying on advisory signals."
            ),
            "",
            _markdown_table(["Severity", "Issue count"], issue_rows or [("none", 0)]),
            "",
            _markdown_table(["Domain", "Record ID", "Severity", "Message"], top_issues or [("none", "none", "info", "No data quality issues detected.")]),
        ]
    )


def _overall_risk_prioritization(sorted_scores: list[RiskScore]) -> str:
    top_scores = sorted_scores[:10]
    index = round(sum(score.score for score in top_scores) / len(top_scores)) if top_scores else 0
    band_counts = Counter(score.band.value for score in sorted_scores)
    rows = [(_band_label(band), count) for band, count in sorted(band_counts.items())]
    return "\n".join(
        [
            "## 5. Overall GMP Risk Prioritization",
            "",
            (
                f"The QA prioritization index is {index}/100 for the visible advisory scores. "
                "This is an elevated risk signal summary for prioritization and not a GMP decision."
            ),
            "",
            _markdown_table(["Priority level", "Count"], rows or [("none", 0)]),
        ]
    )


def _top_forecasted_risks(sorted_scores: list[RiskScore]) -> str:
    rows = [_score_row(score) for score in sorted_scores[:20]]
    return "\n".join(
        [
            "## 6. Top 20 Prioritized Risks",
            "",
            "These prioritized risks are recommended for human QA review based on available data.",
            "",
            _markdown_table(
                ["Rank", "Score", "Band", "Risk type", "Entity type", "Entity ID", "Confidence", "Top driver"],
                rows or [("none", 0, "none", "none", "none", "none", 0, "No advisory scores available.")],
            ),
        ]
    )


def _risk_type_section(
    title: str,
    risk_type: str,
    sorted_scores: list[RiskScore],
    evidence_cards: list[EvidenceCard],
) -> str:
    filtered_scores = [score for score in sorted_scores if score.risk_type == risk_type][:10]
    rows = []
    for score in filtered_scores:
        source_ids = _source_ids_for_score(score, evidence_cards)
        rows.append(
            (
                f"{score.score:.1f}",
                _band_label(score.band.value),
                score.entity_type,
                score.entity_id,
                score.drivers[0] if score.drivers else "",
                ", ".join(source_ids[:8]),
            )
        )
    return "\n".join(
        [
            f"## {title}",
            "",
            (
                "Based on available data, each item below is an elevated risk signal and is recommended "
                "for human QA review. The table is not a GMP decision."
            ),
            "",
            _markdown_table(
                ["Score", "Priority level", "Entity type", "Entity ID", "Top driver", "Source record IDs"],
                rows or [("none", "none", "none", "none", "No matching signals.", "none")],
            ),
        ]
    )


def _evidence_card_appendix(evidence_cards: list[EvidenceCard]) -> str:
    rows = []
    for card in sorted(evidence_cards, key=lambda item: item.risk_score.score, reverse=True)[:50]:
        rows.append(
            (
                card.card_id,
                f"{card.risk_score.score:.1f}",
                _band_label(card.risk_score.band.value),
                card.risk_score.risk_type,
                card.risk_score.entity_id,
                ", ".join(source.record_id for source in card.source_records[:10]),
                card.recommended_human_review,
            )
        )
    return "\n".join(
        [
            "## 12. Evidence Card Appendix",
            "",
            "Evidence cards remain source-linked and recommended for human QA review. Rationale text is advisory and not a GMP decision.",
            "",
            _markdown_table(
                ["Card ID", "Score", "Priority level", "Risk type", "Entity ID", "Source record IDs", "Recommended human review"],
                rows or [("none", "none", "none", "none", "none", "none", "No evidence cards generated.")],
            ),
        ]
    )


def _backtesting_summary(result: BacktestResult) -> str:
    metrics = result.metric_summary
    baseline = result.baseline_metric_summary
    return "\n".join(
        [
            "## 13. Backtesting Summary",
            "",
            (
                "The historical backtest suggests risk-ranking utility compared with oldest-open backlog sorting. "
                "It is not proof of prevention, not prediction certainty, and not a GMP decision."
            ),
            "",
            _markdown_table(
                ["Metric", "Rules v0.1", "Backlog-age baseline"],
                [
                    ("precision_at_10", f"{metrics.get('precision_at_10', 0.0):.3f}", f"{baseline.get('precision_at_10', 0.0):.3f}"),
                    ("precision_at_20", f"{metrics.get('precision_at_20', 0.0):.3f}", f"{baseline.get('precision_at_20', 0.0):.3f}"),
                    (
                        "recall_for_future_major_events",
                        f"{metrics.get('recall_for_future_major_events', 0.0):.3f}",
                        f"{baseline.get('recall_for_future_major_events', 0.0):.3f}",
                    ),
                    ("top_decile_lift", f"{metrics.get('top_decile_lift', 0.0):.3f}", f"{baseline.get('top_decile_lift', 0.0):.3f}"),
                    ("lead_time_days", f"{metrics.get('lead_time_days', 0.0):.1f}", f"{baseline.get('lead_time_days', 0.0):.1f}"),
                ],
            ),
            "",
            "Limitations:",
            _bullet_list(result.limitations),
        ]
    )


def _recommended_pilot_scope() -> str:
    return "\n".join(
        [
            "## 14. Recommended 90-Day Pilot Scope",
            "",
            "A controlled 90-day pilot should remain read-only and advisory while QA reviews whether the signals are useful.",
            "",
            _bullet_list(
                [
                    "Confirm intended use, non-intended use, and escalation paths with QA leadership.",
                    "Use approved synthetic, anonymized, or governed extracts only.",
                    "Review scoring drivers and thresholds with GMP SMEs.",
                    "Compare prioritization outcomes against backlog-age sorting and existing quality council triage.",
                    "Document human QA feedback on false positives, missed signals, and evidence usefulness.",
                    "Define validation, privacy, security, and data retention expectations before any production pilot.",
                ]
            ),
        ]
    )


def _human_decision_boundaries() -> str:
    return "\n".join(
        [
            "## 15. Human Decision Boundaries",
            "",
            "This report is not a GMP decision. Human QA review is mandatory before any regulated quality action.",
            "",
            _bullet_list(
                [
                    "The report does not approve or close deviations.",
                    "The report does not approve, accept, or close CAPAs.",
                    "The report does not recommend batch release.",
                    "The report does not make regulatory reportability decisions.",
                    "The report does not provide final audit responses.",
                    "The report does not approve supplier qualification, validation outcomes, or final root cause.",
                    "All advisory outputs must remain source-linked and explainable.",
                ]
            ),
        ]
    )


def _score_row(score: RiskScore) -> tuple[Any, ...]:
    return (
        "",
        f"{score.score:.1f}",
        _band_label(score.band.value),
        score.risk_type,
        score.entity_type,
        score.entity_id,
        f"{score.confidence:.2f}",
        score.drivers[0] if score.drivers else "",
    )


def _source_ids_for_score(score: RiskScore, evidence_cards: list[EvidenceCard]) -> list[str]:
    for card in evidence_cards:
        if card.risk_score.risk_type == score.risk_type and card.risk_score.entity_id == score.entity_id:
            return [source.record_id for source in card.source_records]
    return [score.entity_id]


def _markdown_table(headers: list[str], rows: list[tuple[Any, ...]]) -> str:
    safe_headers = [_escape_cell(header) for header in headers]
    lines = [
        "| " + " | ".join(safe_headers) + " |",
        "| " + " | ".join("---" for _ in safe_headers) + " |",
    ]
    for index, row in enumerate(rows, start=1):
        normalized = list(row)
        if headers and headers[0] == "Rank" and (not normalized[0]):
            normalized[0] = index
        padded = normalized + [""] * (len(headers) - len(normalized))
        lines.append("| " + " | ".join(_escape_cell(value) for value in padded[: len(headers)]) + " |")
    return "\n".join(lines)


def _bullet_list(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items)


def _band_label(band: str) -> str:
    return {
        "clear": "low",
        "watch": "watch",
        "advisory": "elevated",
        "storm": "high",
        "severe_storm": "critical",
    }.get(band, band.replace("_", " "))


def _escape_cell(value: Any) -> str:
    text = str(value).replace("\n", " ").replace("|", "\\|")
    return " ".join(text.split())
