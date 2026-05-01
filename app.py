from __future__ import annotations

import sys
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from gmp_weather.audit_log import create_forecast_run_log, load_forecast_run_logs, save_forecast_run_log
from gmp_weather.agents import ForecastBriefingAgent
from gmp_weather.backtesting import run_backtest
from gmp_weather.config import FORECAST_LOG_DIR, SAMPLE_DATA_DIR, SCORING_CONFIG_PATH, load_scoring_config
from gmp_weather.dashboard_components import (
    band_label,
    data_quality_issue_frame,
    demo_story_options,
    demo_story_score_frame,
    expand_scores_for_dashboard_horizons,
    filter_bundle,
    filter_evidence_cards,
    filter_scores,
    get_demo_story,
    heatmap_frame,
    inject_dashboard_css,
    load_demo_story_markdown,
    open_audit_findings_frame,
    overall_weather_index,
    owner_workload_frame,
    recent_sop_training_frame,
    recurrence_cluster_frame,
    render_band_counts,
    render_dashboard_header,
    render_evidence_cards_expanders,
    render_heatmap,
    render_metric_row,
    render_table,
    risk_band_counts,
    score_context_frame,
    scores_to_frame,
    select_demo_story_evidence_cards,
    sidebar_options,
    training_overdue_frame,
)
from gmp_weather.data_loader import load_qms_data_bundle
from gmp_weather.data_quality import assess_data_quality
from gmp_weather.evidence import evidence_cards_to_frame, generate_evidence_cards
from gmp_weather.reporting import export_diagnostic_report, generate_markdown_diagnostic_report
from gmp_weather.schemas import QMSDataBundle, RiskBand, RiskHorizon
from gmp_weather.scoring import calculate_all_scores


@st.cache_data
def _load_bundle(folder_path: str):
    try:
        return load_qms_data_bundle(folder_path)
    except FileNotFoundError:
        return QMSDataBundle()


@st.cache_data
def _load_scoring_config(config_path: str, modified_ns: int):
    del modified_ns
    return load_scoring_config(Path(config_path))


def main() -> None:
    st.set_page_config(
        page_title="GMP Risiko-Cockpit — Prototype",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    inject_dashboard_css()

    generated_at = datetime.now(timezone.utc)
    source_bundle = _load_bundle(str(SAMPLE_DATA_DIR))
    scoring_config = _load_scoring_config(str(SCORING_CONFIG_PATH), SCORING_CONFIG_PATH.stat().st_mtime_ns)
    source_files = sorted(SAMPLE_DATA_DIR.glob("*.csv"))
    options = sidebar_options(source_bundle)
    demo_stories = demo_story_options()
    if "demo_story_key" not in st.session_state:
        st.session_state["demo_story_key"] = demo_stories[0].key

    with st.sidebar:
        st.header("Risk Controls")
        as_of_date = st.date_input("as_of_date", value=date(2026, 4, 30))
        selected_sites = st.multiselect("site filter", options=options["sites"], default=options["sites"])
        selected_departments = st.multiselect(
            "department filter",
            options=options["departments"],
            default=options["departments"],
        )
        selected_horizons = st.multiselect(
            "horizon filter",
            options=[RiskHorizon.TWO_WEEKS, RiskHorizon.FOUR_WEEKS, RiskHorizon.EIGHT_WEEKS],
            default=[RiskHorizon.FOUR_WEEKS],
            format_func=lambda item: item.value.replace("_", " "),
        )
        minimum_band = st.selectbox(
            "minimum risk band",
            options=[RiskBand.CLEAR, RiskBand.WATCH, RiskBand.ADVISORY, RiskBand.STORM, RiskBand.SEVERE_STORM],
            index=2,
            format_func=lambda item: band_label(item.value),
        )
        st.divider()
        st.caption(f"Model version: {scoring_config.model_version}")
        st.caption("Local synthetic sample data only.")
        st.divider()
        st.subheader("Demo-Fokus")
        st.caption("Geführte synthetische QA-Szenarien.")
        for story in demo_stories:
            if st.button(story.label, key=f"demo_story_button_{story.key}", use_container_width=True):
                st.session_state["demo_story_key"] = story.key
        selected_demo_story_key = st.selectbox(
            "selected demo story",
            options=[story.key for story in demo_stories],
            index=[story.key for story in demo_stories].index(st.session_state["demo_story_key"]),
            format_func=lambda key: get_demo_story(key).label,
        )
        st.session_state["demo_story_key"] = selected_demo_story_key

    working_bundle = filter_bundle(source_bundle, set(selected_sites), set(selected_departments))
    base_scores = calculate_all_scores(working_bundle, as_of_date, scoring_config=scoring_config)
    horizon_scores = expand_scores_for_dashboard_horizons(base_scores, scoring_config=scoring_config)
    visible_scores = filter_scores(
        horizon_scores,
        horizons=set(selected_horizons),
        minimum_band=minimum_band,
    )
    evidence_cards = generate_evidence_cards(visible_scores, working_bundle, generated_at=generated_at)
    weekly_briefing = ForecastBriefingAgent().run(visible_scores, evidence_cards)
    demo_base_scores = calculate_all_scores(source_bundle, as_of_date, scoring_config=scoring_config)
    demo_horizon_scores = expand_scores_for_dashboard_horizons(demo_base_scores, scoring_config=scoring_config)
    demo_visible_scores = filter_scores(
        demo_horizon_scores,
        horizons=set(selected_horizons),
        minimum_band=RiskBand.WATCH,
    )
    demo_evidence_cards = generate_evidence_cards(demo_visible_scores, source_bundle, generated_at=generated_at)
    demo_story_markdown = load_demo_story_markdown(SAMPLE_DATA_DIR / "demo_story.md")
    quality_report = assess_data_quality(working_bundle, as_of=as_of_date)
    user_selected_filters = {
        "sites": list(selected_sites),
        "departments": list(selected_departments),
        "horizons": [horizon.value for horizon in selected_horizons],
        "minimum_risk_band": minimum_band.value,
    }
    forecast_run_log = create_forecast_run_log(
        generated_at=generated_at,
        as_of_date=as_of_date,
        model_version=scoring_config.model_version,
        scoring_config_path=SCORING_CONFIG_PATH,
        source_files=source_files,
        bundle=working_bundle,
        user_selected_filters=user_selected_filters,
        generated_risk_score_count=len(visible_scores),
        generated_evidence_card_count=len(evidence_cards),
    )
    save_forecast_run_log(forecast_run_log, FORECAST_LOG_DIR)
    recent_forecast_logs = load_forecast_run_logs(FORECAST_LOG_DIR)

    with st.sidebar:
        st.divider()
        st.subheader("Governance")
        st.caption(f"Risk run: {forecast_run_log.forecast_run_id}")
        st.caption(f"Scoring config hash: {forecast_run_log.scoring_config_hash[:12]}...")
        st.caption("Audit log is local metadata only; no QMS source data is changed.")
        if st.button("Export Diagnostic Report", use_container_width=True):
            diagnostic_backtest = run_backtest(
                working_bundle,
                _backtest_forecast_dates(as_of_date, 30),
                horizon_days=30,
                scoring_config=scoring_config,
            )
            report_markdown = generate_markdown_diagnostic_report(
                working_bundle,
                visible_scores,
                evidence_cards,
                quality_report,
                diagnostic_backtest,
                forecast_run_log,
            )
            report_path = export_diagnostic_report(report_markdown)
            st.success(f"Exported to {report_path}")
            st.download_button(
                "Download Diagnostic Report",
                data=report_markdown,
                file_name="diagnostic_report.md",
                mime="text/markdown",
                use_container_width=True,
            )

    render_dashboard_header(generated_at, model_version=scoring_config.model_version)

    (
        tab_weather,
        tab_storm,
        tab_audit,
        tab_training,
        tab_evidence,
        tab_quality,
        tab_backtesting,
        tab_governance,
    ) = st.tabs(
        [
            "Executive Priority Map",
            "Deviation & CAPA Priority View",
            "Audit Readiness",
            "Training Drift",
            "Evidence Cards",
            "Data Quality",
            "Backtesting",
            "Governance",
        ]
    )

    with tab_weather:
        _render_executive_weather_map(
            visible_scores,
            evidence_cards,
            working_bundle,
            weekly_briefing,
            selected_demo_story_key,
            demo_story_markdown,
            demo_visible_scores,
            demo_evidence_cards,
        )

    with tab_storm:
        _render_deviation_capa_storm(visible_scores, evidence_cards, working_bundle, as_of_date)

    with tab_audit:
        _render_audit_readiness(visible_scores, evidence_cards, working_bundle, as_of_date)

    with tab_training:
        _render_training_drift(visible_scores, working_bundle, as_of_date)

    with tab_evidence:
        _render_evidence_cards(evidence_cards)

    with tab_quality:
        _render_data_quality(quality_report)

    with tab_backtesting:
        _render_backtesting(working_bundle, as_of_date, selected_horizons, scoring_config)

    with tab_governance:
        _render_governance(forecast_run_log, recent_forecast_logs, scoring_config, visible_scores)


def _render_executive_weather_map(
    visible_scores,
    evidence_cards,
    bundle,
    weekly_briefing,
    selected_demo_story_key: str,
    demo_story_markdown: str,
    demo_scores,
    demo_evidence_cards,
) -> None:
    st.subheader("Executive Priority Map")
    st.markdown(
        '<div class="section-note">A consolidated advisory view for QA leadership. '
        "Scores are rule-based signals and require human QA review.</div>",
        unsafe_allow_html=True,
    )
    _render_demo_story_panel(
        selected_demo_story_key,
        demo_story_markdown,
        demo_scores,
        demo_evidence_cards,
    )

    st.markdown("### Weekly Priority Briefing")
    st.info(weekly_briefing.briefing_text)
    st.caption("Source record IDs: " + ", ".join(weekly_briefing.source_record_ids[:20]))

    weather_index = overall_weather_index(visible_scores)
    render_metric_row(
        [
            ("QA-Priorisierungsindex", f"{weather_index}/100", "Average of the top visible advisory risks."),
            ("Visible risk entities", str(len(visible_scores)), "Filtered by sidebar controls."),
            ("Evidence cards", str(len(evidence_cards)), "Generated for elevated, high, and critical scores."),
        ]
    )

    st.markdown("### Top 10 Risk Entities")
    top_frame = score_context_frame(visible_scores[:10], evidence_cards)
    render_table(top_frame, "No risk entities match the current filters.", height=360)

    left, right = st.columns([1, 2])
    with left:
        st.markdown("### Prioritätsverteilung")
        render_band_counts(risk_band_counts(visible_scores))
    with right:
        st.markdown("### Heatmap by Department / Process")
        render_heatmap(heatmap_frame(evidence_cards))


def _render_demo_story_panel(
    selected_demo_story_key: str,
    demo_story_markdown: str,
    demo_scores,
    demo_evidence_cards,
) -> None:
    story = get_demo_story(selected_demo_story_key)
    story_scores = demo_story_score_frame(story, demo_scores, demo_evidence_cards)
    story_cards = select_demo_story_evidence_cards(story, demo_evidence_cards)

    st.markdown("### Demo-Szenario")
    st.markdown(
        '<div class="section-note">A guided walkthrough of the synthetic GMP consulting scenario. '
        "It is advisory only and intended to support human QA review discussions.</div>",
        unsafe_allow_html=True,
    )
    with st.expander("Full synthetic scenario", expanded=False):
        st.markdown(demo_story_markdown)

    left, right = st.columns([1.2, 1])
    with left:
        st.markdown(f"#### {story.label}")
        st.write(story.business_interpretation)
    with right:
        st.markdown("#### Suggested Human Review Action")
        st.write(story.suggested_human_review_action)

    st.markdown("#### Relevant Risk Scores")
    render_table(story_scores, "No relevant advisory risk scores found for this demo story and horizon selection.", height=260)

    st.markdown("#### Evidence Cards")
    render_evidence_cards_expanders(story_cards)


def _render_deviation_capa_storm(visible_scores, evidence_cards, bundle, as_of_date: date) -> None:
    st.subheader("Deviation & CAPA Priority View")
    score_frame = score_context_frame(visible_scores, evidence_cards)

    deviation_scores = score_frame[score_frame["risk_type"] == "deviation_recurrence"].head(15)
    capa_scores = score_frame[score_frame["risk_type"] == "capa_failure"].head(15)
    left, right = st.columns(2)
    with left:
        st.markdown("### Top Risky Deviations")
        render_table(deviation_scores, "No deviation recurrence scores match the current filters.", height=420)
    with right:
        st.markdown("### Top Risky CAPAs")
        render_table(capa_scores, "No CAPA failure scores match the current filters.", height=420)

    left, right = st.columns(2)
    with left:
        st.markdown("### Recurrence Clusters by Process / Root Cause / Equipment")
        render_table(recurrence_cluster_frame(bundle), "No recurrence clusters found in the current filter scope.", height=360)
    with right:
        st.markdown("### Owner Workload Pressure")
        render_table(
            owner_workload_frame(bundle, as_of_date),
            "No open owner workload found in the current filter scope.",
            height=360,
        )


def _render_audit_readiness(visible_scores, evidence_cards, bundle, as_of_date: date) -> None:
    st.subheader("Audit Readiness")
    score_frame = score_context_frame(visible_scores, evidence_cards)
    audit_scores = score_frame[score_frame["risk_type"] == "audit_readiness_gap"].head(20)
    st.markdown("### Department / Process Audit Readiness Gap Scores")
    render_table(audit_scores, "No audit readiness gap scores match the current filters.", height=360)

    left, right = st.columns(2)
    with left:
        st.markdown("### Open Audit Findings")
        render_table(open_audit_findings_frame(bundle), "No open audit findings in the current filter scope.", height=360)
    with right:
        st.markdown("### CAPA Links")
        capa_links = pd.DataFrame(
            [
                {
                    "capa_id": capa.capa_id,
                    "status": capa.status,
                    "due_date": capa.due_date,
                    "linked_deviation_ids": ", ".join(capa.linked_deviation_ids),
                    "owner": capa.owner,
                }
                for capa in bundle.capas
                if capa.linked_deviation_ids
            ]
        )
        render_table(capa_links, "No CAPA links in the current filter scope.", height=360)

    st.markdown("### SOP / Training Risk Indicators")
    render_table(
        recent_sop_training_frame(bundle, as_of_date),
        "No recent SOP changes with incomplete training found.",
        height=320,
    )


def _render_training_drift(visible_scores, bundle, as_of_date: date) -> None:
    st.subheader("Training Drift")
    drift_scores = scores_to_frame([score for score in visible_scores if score.risk_type == "training_drift"]).head(25)
    left, right = st.columns(2)
    with left:
        st.markdown("### Overdue Training by SOP and Department")
        render_table(training_overdue_frame(bundle, as_of_date), "No overdue training found in the current filter scope.", height=420)
    with right:
        st.markdown("### Recent SOP Changes with Incomplete Training")
        render_table(recent_sop_training_frame(bundle, as_of_date), "No incomplete training linked to recent SOP changes.", height=420)

    st.markdown("### Training Drift Scores")
    render_table(drift_scores, "No training drift scores match the current filters.", height=360)


def _render_evidence_cards(evidence_cards: list) -> None:
    st.subheader("Evidence Cards")
    if not evidence_cards:
        st.info("No evidence cards match the current filter selection.")
        return

    evidence_frame = evidence_cards_to_frame(evidence_cards)
    search = st.text_input("Search evidence cards", value="")
    cols = st.columns(6)
    selected_risk_types = cols[0].multiselect("risk type", sorted(evidence_frame["risk_type"].unique()), default=sorted(evidence_frame["risk_type"].unique()))
    selected_departments = cols[1].multiselect("department", _non_empty_options(evidence_frame["department"]), default=_non_empty_options(evidence_frame["department"]))
    selected_processes = cols[2].multiselect("process", _non_empty_options(evidence_frame["process"]), default=_non_empty_options(evidence_frame["process"]))
    selected_bands = cols[3].multiselect("band", sorted(evidence_frame["band"].unique()), default=sorted(evidence_frame["band"].unique()))
    selected_owners = cols[4].multiselect("owner", _non_empty_options(evidence_frame["owner"]), default=_non_empty_options(evidence_frame["owner"]))
    selected_horizons = cols[5].multiselect("horizon", sorted(evidence_frame["horizon"].unique()), default=sorted(evidence_frame["horizon"].unique()))

    filtered_cards = filter_evidence_cards(
        evidence_cards,
        search=search,
        risk_types=set(selected_risk_types),
        departments=set(selected_departments),
        processes=set(selected_processes),
        bands=set(selected_bands),
        owners=set(selected_owners),
        horizons=set(selected_horizons),
    )
    st.caption(f"{len(filtered_cards)} evidence card(s) shown from {len(evidence_cards)} generated cards.")
    render_evidence_cards_expanders(filtered_cards)


def _render_data_quality(quality_report) -> None:
    st.subheader("Data Quality")
    render_metric_row(
        [
            ("Data readiness score", f"{quality_report.data_readiness_score}/100", "Rule-based data quality score."),
            ("Quality issues", str(len(quality_report.issue_list)), "Issues found by data quality checks."),
            ("Loaded records", str(sum(quality_report.total_records_by_domain.values())), "Loaded synthetic records."),
        ]
    )

    issues = data_quality_issue_frame(quality_report.issue_list)
    st.markdown("### Issue List")
    render_table(issues, "No data quality issues detected.", height=380)

    left, middle, right = st.columns(3)
    with left:
        st.markdown("### Missing Fields")
        render_table(_issue_subset(issues, "is missing"), "No missing required fields found.", height=260)
    with middle:
        st.markdown("### Broken References")
        render_table(_issue_subset(issues, "references"), "No broken references found.", height=260)
    with right:
        st.markdown("### Duplicate IDs")
        render_table(_issue_subset(issues, "Duplicate ID"), "No duplicate IDs found.", height=260)


def _render_backtesting(bundle, as_of_date: date, selected_horizons: list[RiskHorizon], scoring_config) -> None:
    st.subheader("Backtesting")
    horizon_days = _horizon_days_from_selection(selected_horizons)
    forecast_dates = _backtest_forecast_dates(as_of_date, horizon_days)
    result = run_backtest(bundle, forecast_dates, horizon_days=horizon_days, scoring_config=scoring_config)

    st.markdown(
        '<div class="section-note">This historical backtest estimates risk-ranking utility only. '
        "It is not proof of prevention and not a guarantee of future performance. "
        "Human QA review is required for interpretation.</div>",
        unsafe_allow_html=True,
    )

    render_metric_row(
        [
            (
                "Precision@10",
                f"{result.metric_summary['precision_at_10']:.2f}",
                "Share of top 10 risk ranks with a later synthetic quality event.",
            ),
            (
                "Major-event recall",
                f"{result.metric_summary['recall_for_future_major_events']:.2f}",
                "Share of future major/critical deviations seen in top-ranked areas or entities.",
            ),
            (
                "Top-decile lift",
                f"{result.metric_summary['top_decile_lift']:.2f}x",
                "Hit-rate lift for the highest-risk decile versus all ranked rows.",
            ),
            (
                "Avg. lead time",
                f"{result.metric_summary['lead_time_days']:.1f} days",
                "Average days from risk date to matched later synthetic event.",
            ),
        ]
    )

    st.markdown("### Metric Summary")
    render_table(_metric_comparison_frame(result), "No backtesting metrics are available.", height=180)

    st.markdown("### Risk Dates Tested")
    render_table(result.forecast_summary_frame, "No risk dates were tested.", height=260)

    st.markdown("### Top Predicted Risks and Later Outcomes")
    render_table(
        _top_prediction_outcomes_frame(result.predictions_frame),
        "No prediction rows were produced for this historical backtest.",
        height=420,
    )

    st.markdown("### Future Events Used for Outcome Matching")
    render_table(result.events_frame, "No future events were found in the selected backtest horizon.", height=320)

    st.markdown("### Limitations")
    for limitation in result.limitations:
        st.write(f"- {limitation}")


def _render_governance(forecast_run_log, recent_forecast_logs, scoring_config, visible_scores) -> None:
    st.subheader("Governance")
    st.markdown(
        '<div class="section-note">This governance view documents how the advisory prioritization was generated. '
        "It supports traceability for human QA review and does not create GMP decisions.</div>",
        unsafe_allow_html=True,
    )

    left, right = st.columns(2)
    with left:
        st.markdown("### Intended Use")
        st.write("- Local advisory decision support for synthetic or anonymized QMS trend review.")
        st.write("- Prioritization aid for QA review of deviations, CAPAs, training, audit readiness, and backlog pressure.")
        st.write("- Explainable risk-ranking utility review using visible scoring drivers and source record IDs.")
    with right:
        st.markdown("### Non-Intended Use")
        st.write("- No approval, rejection, closure, certification, release, qualification, or disposition decisions.")
        st.write("- No automated CAPA approval, deviation closure, batch release, supplier qualification, or validation approval.")
        st.write("- No regulatory reportability decisions or final audit responses.")

    st.markdown("### Latest Risk Run Details")
    render_table(_forecast_log_summary_frame(forecast_run_log), "No risk run log is available.", height=300)

    st.markdown("### Active Scoring Configuration")
    render_metric_row(
        [
            ("Model version", scoring_config.model_version, "Transparent ruleset loaded from local YAML."),
            ("Active scoring config file", str(SCORING_CONFIG_PATH), "Local config file used for this run."),
            ("Risk scores", str(len(visible_scores)), "Generated scores after sidebar filters."),
        ]
    )

    left, right = st.columns(2)
    with left:
        st.markdown("### Priority Thresholds")
        render_table(_risk_band_threshold_frame(scoring_config), "No risk band thresholds are available.", height=260)
    with right:
        st.markdown("### Top Scoring Drivers Used")
        render_table(_top_driver_frame(visible_scores), "No scoring drivers were used for the current filters.", height=260)

    st.markdown("### Source File Hashes")
    render_table(_source_hash_frame(forecast_run_log), "No source file hashes are available.", height=260)

    st.markdown("### Recent Risk Runs")
    render_table(_recent_logs_frame(recent_forecast_logs[:10]), "No previous risk run logs are available.", height=320)


def _issue_subset(frame: pd.DataFrame, pattern: str) -> pd.DataFrame:
    if frame.empty:
        return frame
    return frame[frame["message"].str.contains(pattern, case=False, na=False)]


def _non_empty_options(series) -> list[str]:
    return sorted(value for value in series.dropna().unique() if value)


def _horizon_days_from_selection(selected_horizons: list[RiskHorizon]) -> int:
    horizon_days = {
        RiskHorizon.TWO_WEEKS: 14,
        RiskHorizon.FOUR_WEEKS: 28,
        RiskHorizon.EIGHT_WEEKS: 56,
        RiskHorizon.TWELVE_WEEKS: 84,
    }
    if not selected_horizons:
        return horizon_days[RiskHorizon.FOUR_WEEKS]
    return max(horizon_days[horizon] for horizon in selected_horizons)


def _backtest_forecast_dates(as_of_date: date, horizon_days: int, periods: int = 6) -> list[date]:
    last_complete_forecast = as_of_date - timedelta(days=horizon_days)
    return [
        last_complete_forecast - timedelta(days=14 * offset)
        for offset in reversed(range(periods))
    ]


def _metric_comparison_frame(result) -> pd.DataFrame:
    rows = []
    labels = [
        ("rules-v0.1 risk ranking", result.metric_summary),
        ("oldest open backlog baseline", result.baseline_metric_summary),
    ]
    for method, metrics in labels:
        rows.append(
            {
                "method": method,
                "precision_at_10": metrics["precision_at_10"],
                "precision_at_20": metrics["precision_at_20"],
                "recall_for_future_major_events": metrics["recall_for_future_major_events"],
                "top_decile_lift": metrics["top_decile_lift"],
                "lead_time_days": metrics["lead_time_days"],
            }
        )
    return pd.DataFrame(rows)


def _top_prediction_outcomes_frame(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame
    columns = [
        "method",
        "forecast_date",
        "rank",
        "score",
        "risk_type",
        "entity_type",
        "entity_id",
        "department",
        "process",
        "matched_future_event_count",
        "matched_event_ids",
        "later_outcomes",
        "lead_time_days",
    ]
    return frame[frame["rank"] <= 20][columns]


def _forecast_log_summary_frame(log) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"field": "forecast_run_id", "value": log.forecast_run_id},
            {"field": "generated_at", "value": log.generated_at.isoformat()},
            {"field": "as_of_date", "value": log.as_of_date.isoformat()},
            {"field": "model_version", "value": log.model_version},
            {"field": "scoring_config_hash", "value": log.scoring_config_hash},
            {"field": "source_file_names", "value": ", ".join(log.source_file_names)},
            {"field": "generated_risk_score_count", "value": log.generated_risk_score_count},
            {"field": "generated_evidence_card_count", "value": log.generated_evidence_card_count},
            {"field": "user_selected_filters", "value": str(log.user_selected_filters)},
            {"field": "number_of_records_by_domain", "value": str(log.number_of_records_by_domain)},
        ]
    )


def _source_hash_frame(log) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"source_file_name": name, "sha256": digest}
            for name, digest in sorted(log.source_file_hashes.items())
        ]
    )


def _recent_logs_frame(logs) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "generated_at": log.generated_at.isoformat(),
                "forecast_run_id": log.forecast_run_id,
                "as_of_date": log.as_of_date.isoformat(),
                "model_version": log.model_version,
                "risk_scores": log.generated_risk_score_count,
                "evidence_cards": log.generated_evidence_card_count,
            }
            for log in logs
        ]
    )


def _risk_band_threshold_frame(scoring_config) -> pd.DataFrame:
    bands = scoring_config.risk_bands
    return pd.DataFrame(
        [
            {"band": band_label("clear"), "threshold": f"<= {bands['clear_max']:g}"},
            {"band": band_label("watch"), "threshold": f"{bands['clear_max'] + 1:g} to {bands['watch_max']:g}"},
            {"band": band_label("advisory"), "threshold": f"{bands['watch_max'] + 1:g} to {bands['advisory_max']:g}"},
            {"band": band_label("storm"), "threshold": f"{bands['advisory_max'] + 1:g} to {bands['storm_max']:g}"},
            {"band": band_label("severe_storm"), "threshold": f">= {bands['severe_storm_min']:g}"},
        ]
    )


def _top_driver_frame(scores) -> pd.DataFrame:
    counter: Counter[str] = Counter()
    for score in scores:
        for driver in score.drivers:
            if driver.startswith("confidence reduced"):
                continue
            driver_name = driver.split(":", 1)[0]
            counter[driver_name] += 1
    return pd.DataFrame(
        [{"driver": driver, "count": count} for driver, count in counter.most_common(15)]
    )


if __name__ == "__main__":
    main()
