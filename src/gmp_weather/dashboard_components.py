"""Streamlit dashboard helpers for the GMP advisory prototype."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Iterable

import pandas as pd

from gmp_weather.config import ScoringConfig
from gmp_weather.schemas import EvidenceCard, QMSDataBundle, RiskBand, RiskHorizon, RiskScore
from gmp_weather.scoring import score_to_band


MODEL_VERSION = "rules-v0.1"
BAND_ORDER = {
    RiskBand.CLEAR: 0,
    RiskBand.WATCH: 1,
    RiskBand.ADVISORY: 2,
    RiskBand.STORM: 3,
    RiskBand.SEVERE_STORM: 4,
}
HORIZON_FACTORS = {
    RiskHorizon.TWO_WEEKS: 0.88,
    RiskHorizon.FOUR_WEEKS: 1.0,
    RiskHorizon.EIGHT_WEEKS: 1.08,
}


@dataclass(frozen=True)
class DemoStory:
    """A guided synthetic scenario for GMP consulting demos."""

    key: str
    label: str
    business_interpretation: str
    suggested_human_review_action: str
    risk_types: tuple[str, ...]
    departments: tuple[str, ...] = ()
    processes: tuple[str, ...] = ()
    entity_terms: tuple[str, ...] = ()
    source_record_ids: tuple[str, ...] = ()


DEMO_STORIES: tuple[DemoStory, ...] = (
    DemoStory(
        key="packaging_storm",
        label="Packaging storm",
        business_interpretation=(
            "Packaging shows a rising synthetic deviation pattern over the last six weeks. "
            "This is an elevated operational risk signal for trend review, not a finding of non-compliance."
        ),
        suggested_human_review_action=(
            "QA Operations and Packaging leadership should review deviation recurrence, owner workload, "
            "and whether existing CAPA coverage remains adequate."
        ),
        risk_types=("deviation_recurrence", "backlog_pressure", "audit_readiness_gap"),
        departments=("Packaging",),
        processes=("Packaging",),
        entity_terms=("Packaging",),
    ),
    DemoStory(
        key="capa_recurrence_risk",
        label="CAPA recurrence risk",
        business_interpretation=(
            "CAPA-014 is positioned as an overdue synthetic CAPA linked to repeated Packaging deviations. "
            "The signal highlights potential recurrence pressure for human QA review."
        ),
        suggested_human_review_action=(
            "The CAPA owner and QA should review CAPA-014, linked deviation records, and the planned "
            "effectiveness-check design before any quality action."
        ),
        risk_types=("capa_failure",),
        departments=("Packaging",),
        processes=("Packaging",),
        entity_terms=("CAPA-014",),
        source_record_ids=("CAPA-014",),
    ),
    DemoStory(
        key="training_drift_sop_revision",
        label="Training drift after SOP revision",
        business_interpretation=(
            "SOP-023 was recently revised in the synthetic scenario while related training remains incomplete. "
            "This creates a training drift signal for review."
        ),
        suggested_human_review_action=(
            "The training owner should review SOP-023 assignments, overdue training records, and any linked "
            "change controls with training impact."
        ),
        risk_types=("training_drift", "audit_readiness_gap"),
        departments=("Packaging",),
        processes=("Packaging",),
        entity_terms=("SOP-023",),
        source_record_ids=("SOP-023",),
    ),
    DemoStory(
        key="sterile_filling_watch",
        label="Sterile Filling high-severity watch",
        business_interpretation=(
            "Sterile Filling has fewer synthetic deviations than Packaging, but a higher severity mix. "
            "This is a watch area for QA review because severity can matter even when counts are lower."
        ),
        suggested_human_review_action=(
            "QA and Production should review high-severity Sterile Filling deviations, related CAPAs, "
            "and any aseptic-process control themes."
        ),
        risk_types=("deviation_recurrence", "audit_readiness_gap"),
        departments=("Production",),
        processes=("Sterile Filling",),
        entity_terms=("Sterile Filling",),
    ),
    DemoStory(
        key="qc_lab_oos_oot_recurrence",
        label="QC Lab OOS/OOT recurrence",
        business_interpretation=(
            "The QC Lab scenario contains recurring synthetic OOS/OOT-related investigations. "
            "The signal is intended to support trend discussion and prioritization for human QA review."
        ),
        suggested_human_review_action=(
            "QC and QA should review recurring OOS/OOT investigation themes, linked deviations, "
            "and whether method or sample-handling controls need further human assessment."
        ),
        risk_types=("deviation_recurrence", "audit_readiness_gap", "backlog_pressure"),
        departments=("QC Lab",),
        processes=("QC Release Testing",),
        entity_terms=("QC Lab", "QC Release Testing", "OOS", "OOT"),
    ),
)


def inject_dashboard_css() -> None:
    import streamlit as st

    st.markdown(
        """
        <style>
        .main .block-container {
            padding-top: 2rem;
            max-width: 1360px;
        }
        h1, h2, h3 {
            letter-spacing: 0;
        }
        .gmp-disclaimer {
            border-left: 5px solid #9a5b00;
            background: #fff8e7;
            color: #382400;
            padding: 1rem 1.15rem;
            border-radius: .45rem;
            font-weight: 650;
            margin: .75rem 0 1rem 0;
        }
        .gmp-meta {
            color: #5f6368;
            font-size: .92rem;
            margin-bottom: .75rem;
        }
        .section-note {
            color: #626a73;
            font-size: .92rem;
        }
        div[data-testid="stMetric"] {
            background: #ffffff;
            border: 1px solid #e3e7ed;
            border-radius: 8px;
            padding: .75rem .85rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_dashboard_header(generated_at: datetime, model_version: str = MODEL_VERSION) -> None:
    import streamlit as st

    st.title("GMP Compliance Weather Forecast — Prototype")
    st.markdown(
        '<div class="gmp-disclaimer">'
        "This prototype provides advisory quality-risk signals only. It does not make GMP decisions. "
        "Human QA review is required."
        "</div>",
        unsafe_allow_html=True,
    )
    st.markdown(
        f'<div class="gmp-meta">Last forecast generated at: {generated_at.strftime("%Y-%m-%d %H:%M:%S")} | '
        f"Model version: {model_version}</div>",
        unsafe_allow_html=True,
    )


def expand_scores_for_dashboard_horizons(
    scores: list[RiskScore],
    scoring_config: ScoringConfig | None = None,
) -> list[RiskScore]:
    """Create 2-, 4-, and 8-week dashboard views from rules-v0.1 scores."""

    expanded: list[RiskScore] = []
    for score in scores:
        for horizon, factor in HORIZON_FACTORS.items():
            adjusted = max(0.0, min(round(score.score * factor, 1), 100.0))
            drivers = [
                *score.drivers,
                f"horizon view: {horizon.value} dashboard view uses rules-v0.1 factor {factor:g}",
            ]
            expanded.append(
                score.model_copy(
                    update={
                        "score": adjusted,
                        "band": score_to_band(adjusted, scoring_config=scoring_config),
                        "horizon": horizon,
                        "drivers": drivers,
                    }
                )
            )
    return expanded


def filter_bundle(bundle: QMSDataBundle, sites: set[str], departments: set[str]) -> QMSDataBundle:
    """Filter QMS bundle by site and department without mutating source data."""

    return QMSDataBundle(
        deviations=[
            record
            for record in bundle.deviations
            if _site_allowed(record.site, sites) and _department_allowed(record.department, departments)
        ],
        capas=[
            record
            for record in bundle.capas
            if _site_allowed(record.site, sites) and _department_allowed(record.department, departments)
        ],
        audit_findings=[
            record
            for record in bundle.audit_findings
            if _site_allowed(record.site, sites) and _department_allowed(record.department, departments)
        ],
        training_records=[
            record for record in bundle.training_records if _department_allowed(record.department, departments)
        ],
        change_controls=[
            record
            for record in bundle.change_controls
            if _site_allowed(record.site, sites) and _department_allowed(record.department, departments)
        ],
        sops=[record for record in bundle.sops if _department_allowed(record.department, departments)],
    )


def filter_scores(
    scores: list[RiskScore],
    *,
    horizons: set[RiskHorizon],
    minimum_band: RiskBand,
) -> list[RiskScore]:
    """Filter advisory scores by horizon and minimum risk band."""

    return [
        score
        for score in scores
        if score.horizon in horizons and BAND_ORDER[score.band] >= BAND_ORDER[minimum_band]
    ]


def overall_weather_index(scores: list[RiskScore]) -> int:
    """Return a simple top-risk weighted compliance weather index."""

    if not scores:
        return 0
    top_scores = sorted((score.score for score in scores), reverse=True)[:10]
    return round(sum(top_scores) / len(top_scores))


def risk_band_counts(scores: list[RiskScore]) -> dict[str, int]:
    counts = Counter(score.band.value for score in scores)
    return {band.value: counts.get(band.value, 0) for band in RiskBand}


def demo_story_options() -> tuple[DemoStory, ...]:
    """Return the available guided synthetic demo scenarios."""

    return DEMO_STORIES


def get_demo_story(key: str) -> DemoStory:
    """Return one demo story by key, falling back to the first story."""

    return next((story for story in DEMO_STORIES if story.key == key), DEMO_STORIES[0])


def load_demo_story_markdown(path: Path) -> str:
    """Load the demo story narrative from the synthetic sample-data folder."""

    if not path.exists():
        return "Demo story narrative is not available in the current sample-data folder."
    return path.read_text(encoding="utf-8")


def demo_story_score_frame(
    story: DemoStory,
    scores: list[RiskScore],
    cards: list[EvidenceCard],
) -> pd.DataFrame:
    """Build a table of scores relevant to a selected guided demo story."""

    card_by_key = {
        (card.risk_score.risk_type, card.risk_score.entity_id, card.risk_score.horizon.value): card
        for card in cards
    }
    rows: list[dict[str, object]] = []
    for score in sorted(scores, key=lambda item: item.score, reverse=True):
        card = card_by_key.get((score.risk_type, score.entity_id, score.horizon.value))
        if not _demo_story_score_matches(story, score, card):
            continue
        source_ids = _source_ids_from_card(card)
        rows.append(
            {
                "score": score.score,
                "band": score.band.value,
                "horizon": score.horizon.value,
                "risk_type": score.risk_type,
                "entity_type": score.entity_type,
                "entity_id": score.entity_id,
                "department": card.department if card else _matched_label(story.departments, score),
                "process": card.process if card else _matched_label(story.processes, score),
                "confidence": score.confidence,
                "top_driver": score.drivers[0] if score.drivers else "",
                "source_record_ids": ", ".join(source_ids),
            }
        )
    columns = [
        "score",
        "band",
        "horizon",
        "risk_type",
        "entity_type",
        "entity_id",
        "department",
        "process",
        "confidence",
        "top_driver",
        "source_record_ids",
    ]
    return pd.DataFrame(rows[:15], columns=columns)


def select_demo_story_evidence_cards(story: DemoStory, cards: list[EvidenceCard]) -> list[EvidenceCard]:
    """Return evidence cards relevant to a selected guided demo story."""

    matching_cards = [card for card in cards if _demo_story_card_matches(story, card)]
    return sorted(matching_cards, key=lambda card: card.risk_score.score, reverse=True)[:8]


def scores_to_frame(scores: list[RiskScore]) -> pd.DataFrame:
    columns = ["score", "band", "horizon", "risk_type", "entity_type", "entity_id", "confidence", "top_driver"]
    rows = [
        {
            "score": score.score,
            "band": score.band.value,
            "horizon": score.horizon.value,
            "risk_type": score.risk_type,
            "entity_type": score.entity_type,
            "entity_id": score.entity_id,
            "confidence": score.confidence,
            "top_driver": score.drivers[0] if score.drivers else "",
        }
        for score in scores
    ]
    return pd.DataFrame(rows, columns=columns)


def score_context_frame(scores: list[RiskScore], cards: list[EvidenceCard]) -> pd.DataFrame:
    columns = [
        "score",
        "band",
        "risk_type",
        "entity_type",
        "entity_id",
        "horizon",
        "department",
        "process",
        "owner",
        "confidence",
        "top_driver",
    ]
    context_by_key = {
        (card.risk_score.risk_type, card.risk_score.entity_id, card.risk_score.horizon.value): card
        for card in cards
    }
    rows: list[dict[str, object]] = []
    for score in scores:
        card = context_by_key.get((score.risk_type, score.entity_id, score.horizon.value))
        rows.append(
            {
                "score": score.score,
                "band": score.band.value,
                "risk_type": score.risk_type,
                "entity_type": score.entity_type,
                "entity_id": score.entity_id,
                "horizon": score.horizon.value,
                "department": card.department if card else "",
                "process": card.process if card else "",
                "owner": card.owner if card else "",
                "confidence": score.confidence,
                "top_driver": score.drivers[0] if score.drivers else "",
            }
        )
    return pd.DataFrame(rows, columns=columns)


def heatmap_frame(cards: list[EvidenceCard]) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    grouped: dict[tuple[str, str], list[float]] = defaultdict(list)
    for card in cards:
        if card.department and card.process:
            grouped[(card.department, card.process)].append(card.risk_score.score)
    for (department, process), values in grouped.items():
        rows.append({"department": department, "process": process, "score": round(sum(values) / len(values), 1)})
    return pd.DataFrame(rows)


def recurrence_cluster_frame(bundle: QMSDataBundle) -> pd.DataFrame:
    grouped: Counter[tuple[str, str, str]] = Counter()
    for deviation in bundle.deviations:
        key = (
            deviation.process,
            deviation.root_cause_category or "Unknown root cause",
            deviation.equipment_id or "No equipment ID",
        )
        grouped[key] += 1
    return pd.DataFrame(
        [
            {"process": process, "root_cause": root_cause, "equipment_id": equipment_id, "records": count}
            for (process, root_cause, equipment_id), count in grouped.most_common(20)
            if count > 1
        ]
    )


def owner_workload_frame(bundle: QMSDataBundle, as_of_date: date) -> pd.DataFrame:
    counts: Counter[str] = Counter()
    overdue: Counter[str] = Counter()
    for record in [*bundle.deviations, *bundle.capas, *bundle.change_controls]:
        if getattr(record, "status", "").lower() not in {"closed", "completed", "cancelled"}:
            counts[record.owner] += 1
            due_date = getattr(record, "due_date", None)
            if due_date and due_date < as_of_date:
                overdue[record.owner] += 1
    return pd.DataFrame(
        [
            {"owner": owner, "open_items": count, "overdue_items": overdue.get(owner, 0)}
            for owner, count in counts.most_common()
        ]
    )


def open_audit_findings_frame(bundle: QMSDataBundle) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "finding_id": finding.finding_id,
                "severity": finding.severity,
                "site": finding.site,
                "department": finding.department,
                "process": finding.process,
                "linked_capa_id": finding.linked_capa_id or "",
                "status": finding.status,
                "description": finding.description,
            }
            for finding in bundle.audit_findings
            if finding.status.lower() != "closed"
        ]
    )


def training_overdue_frame(bundle: QMSDataBundle, as_of_date: date) -> pd.DataFrame:
    grouped: Counter[tuple[str, str]] = Counter()
    for record in bundle.training_records:
        if record.status.lower() != "completed" and record.due_date < as_of_date:
            grouped[(record.department, record.sop_id)] += 1
    return pd.DataFrame(
        [
            {"department": department, "sop_id": sop_id, "overdue_training": count}
            for (department, sop_id), count in grouped.most_common(30)
        ]
    )


def recent_sop_training_frame(bundle: QMSDataBundle, as_of_date: date) -> pd.DataFrame:
    recent_sops = {
        sop.sop_id: sop
        for sop in bundle.sops
        if 0 <= (as_of_date - sop.effective_date).days <= 60
        or (sop.revision_date and 0 <= (as_of_date - sop.revision_date).days <= 60)
    }
    incomplete_counts: Counter[str] = Counter()
    for record in bundle.training_records:
        if record.sop_id in recent_sops and record.status.lower() != "completed":
            incomplete_counts[record.sop_id] += 1
    return pd.DataFrame(
        [
            {
                "sop_id": sop_id,
                "title": recent_sops[sop_id].title,
                "department": recent_sops[sop_id].department,
                "process": recent_sops[sop_id].process,
                "incomplete_training": count,
            }
            for sop_id, count in incomplete_counts.most_common()
        ]
    )


def data_quality_issue_frame(issue_list) -> pd.DataFrame:
    return pd.DataFrame([issue.model_dump() for issue in issue_list])


def render_metric_row(metrics: Iterable[tuple[str, str, str | None]]) -> None:
    import streamlit as st

    metric_list = list(metrics)
    columns = st.columns(len(metric_list))
    for column, (label, value, help_text) in zip(columns, metric_list, strict=True):
        column.metric(label, value, help=help_text)


def render_table(frame: pd.DataFrame, empty_message: str, height: int | None = None) -> None:
    import streamlit as st

    if frame.empty:
        st.info(empty_message)
        return
    st.dataframe(frame, use_container_width=True, hide_index=True, height=height)


def render_heatmap(frame: pd.DataFrame) -> None:
    import streamlit as st

    if frame.empty:
        st.info("No department/process heatmap data is available for the current filters.")
        return
    try:
        import plotly.express as px

        pivot = frame.pivot_table(index="department", columns="process", values="score", aggfunc="mean", fill_value=0)
        fig = px.imshow(
            pivot,
            text_auto=".0f",
            aspect="auto",
            color_continuous_scale="YlOrRd",
            labels={"color": "Advisory score"},
        )
        fig.update_layout(margin=dict(l=10, r=10, t=20, b=10), height=360)
        st.plotly_chart(fig, use_container_width=True)
    except Exception:
        st.dataframe(frame, use_container_width=True, hide_index=True)


def render_band_counts(counts: dict[str, int]) -> None:
    import streamlit as st

    frame = pd.DataFrame([{"band": band, "count": count} for band, count in counts.items()])
    st.bar_chart(frame, x="band", y="count")


def render_evidence_cards_expanders(cards: list[EvidenceCard]) -> None:
    import streamlit as st

    if not cards:
        st.info("No evidence cards match the current filters.")
        return
    for card in cards:
        label = (
            f"{card.risk_score.band.value.replace('_', ' ').title()} | "
            f"{card.risk_score.risk_type} | {card.risk_score.entity_id} | {card.risk_score.score:.1f}"
        )
        with st.expander(label):
            st.write(card.rationale)
            st.markdown("**Top drivers**")
            for driver in card.top_drivers:
                st.write(f"- {driver}")
            st.markdown("**Source record IDs**")
            st.write(", ".join(f"{source.domain}:{source.record_id}" for source in card.source_records))
            st.markdown("**Recommended human review**")
            st.write(card.recommended_human_review)
            st.markdown("**Limitations**")
            for limitation in card.limitations:
                st.caption(limitation)


def filter_evidence_cards(
    cards: list[EvidenceCard],
    *,
    search: str,
    risk_types: set[str],
    departments: set[str],
    processes: set[str],
    bands: set[str],
    owners: set[str],
    horizons: set[str],
) -> list[EvidenceCard]:
    needle = search.strip().lower()
    filtered: list[EvidenceCard] = []
    for card in cards:
        haystack = " ".join(
            [
                card.card_id,
                card.risk_score.entity_id,
                card.risk_score.risk_type,
                card.rationale,
                card.recommended_human_review,
                " ".join(card.top_drivers),
                " ".join(source.record_id for source in card.source_records),
            ]
        ).lower()
        if needle and needle not in haystack:
            continue
        if risk_types and card.risk_score.risk_type not in risk_types:
            continue
        if bands and card.risk_score.band.value not in bands:
            continue
        if horizons and card.risk_score.horizon.value not in horizons:
            continue
        if card.department and departments and card.department not in departments:
            continue
        if card.process and processes and card.process not in processes:
            continue
        if card.owner and owners and card.owner not in owners:
            continue
        filtered.append(card)
    return filtered


def sidebar_options(bundle: QMSDataBundle) -> dict[str, list[str]]:
    sites = sorted(
        {
            record.site
            for record in [*bundle.deviations, *bundle.capas, *bundle.audit_findings, *bundle.change_controls]
        }
    )
    departments = sorted(
        {
            record.department
            for record in [
                *bundle.deviations,
                *bundle.capas,
                *bundle.audit_findings,
                *bundle.training_records,
                *bundle.change_controls,
                *bundle.sops,
            ]
        }
    )
    return {"sites": sites, "departments": departments}


def _site_allowed(site: str, selected_sites: set[str]) -> bool:
    return not selected_sites or site in selected_sites


def _department_allowed(department: str, selected_departments: set[str]) -> bool:
    return not selected_departments or department in selected_departments


def _demo_story_score_matches(story: DemoStory, score: RiskScore, card: EvidenceCard | None) -> bool:
    if story.risk_types and score.risk_type not in story.risk_types:
        return False
    return _demo_story_context_matches(story, score, card)


def _demo_story_card_matches(story: DemoStory, card: EvidenceCard) -> bool:
    if story.risk_types and card.risk_score.risk_type not in story.risk_types:
        return False
    return _demo_story_context_matches(story, card.risk_score, card)


def _demo_story_context_matches(story: DemoStory, score: RiskScore, card: EvidenceCard | None) -> bool:
    source_ids = set(_source_ids_from_card(card))
    if story.source_record_ids:
        return any(
            source_id == score.entity_id or source_id in source_ids
            for source_id in story.source_record_ids
        )

    if card and story.processes and card.process in story.processes:
        return True
    if card and story.departments and card.department in story.departments:
        return True

    entity_text = score.entity_id.lower()
    if any(term.lower() in entity_text for term in story.entity_terms):
        return True

    return False


def _demo_story_haystack(score: RiskScore, card: EvidenceCard | None) -> str:
    values = [
        score.risk_type,
        score.entity_type,
        score.entity_id,
        *score.drivers,
    ]
    if card:
        values.extend(
            [
                card.department or "",
                card.process or "",
                card.owner or "",
                card.rationale,
                card.recommended_human_review,
                *card.top_drivers,
                *[source.record_id for source in card.source_records],
            ]
        )
    return " ".join(values)


def _source_ids_from_card(card: EvidenceCard | None) -> list[str]:
    if not card:
        return []
    return [source.record_id for source in card.source_records]


def _matched_label(candidates: tuple[str, ...], score: RiskScore) -> str:
    haystack = _demo_story_haystack(score, None).lower()
    return next((candidate for candidate in candidates if candidate.lower() in haystack), "")
