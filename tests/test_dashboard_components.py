from datetime import datetime, timezone

from gmp_weather.dashboard_components import (
    demo_story_options,
    demo_story_score_frame,
    expand_scores_for_dashboard_horizons,
    filter_scores,
    get_demo_story,
    overall_weather_index,
    risk_band_counts,
    select_demo_story_evidence_cards,
)
from gmp_weather.schemas import EvidenceCard, EvidenceSourceRecord, RiskBand, RiskHorizon, RiskScore


def _risk_score(score: float, band: RiskBand, entity_id: str = "DEV-001") -> RiskScore:
    return RiskScore(
        score=score,
        band=band,
        horizon=RiskHorizon.FOUR_WEEKS,
        entity_type="deviation",
        entity_id=entity_id,
        risk_type="deviation_recurrence",
        drivers=["severity: major (+22)"],
        confidence=0.8,
    )


def test_expand_scores_for_dashboard_horizons_creates_2_4_8_week_views():
    expanded = expand_scores_for_dashboard_horizons([_risk_score(80, RiskBand.STORM)])

    assert {score.horizon for score in expanded} == {
        RiskHorizon.TWO_WEEKS,
        RiskHorizon.FOUR_WEEKS,
        RiskHorizon.EIGHT_WEEKS,
    }
    assert all(any("horizon view" in driver for driver in score.drivers) for score in expanded)


def test_filter_scores_applies_horizon_and_minimum_band():
    scores = expand_scores_for_dashboard_horizons(
        [
            _risk_score(80, RiskBand.STORM, "DEV-001"),
            _risk_score(30, RiskBand.WATCH, "DEV-002"),
        ]
    )

    filtered = filter_scores(
        scores,
        horizons={RiskHorizon.FOUR_WEEKS},
        minimum_band=RiskBand.ADVISORY,
    )

    assert [score.entity_id for score in filtered] == ["DEV-001"]
    assert all(score.horizon is RiskHorizon.FOUR_WEEKS for score in filtered)


def test_overall_weather_index_uses_top_risks():
    score = overall_weather_index(
        [
            _risk_score(90, RiskBand.SEVERE_STORM, "A"),
            _risk_score(70, RiskBand.STORM, "B"),
            _risk_score(10, RiskBand.CLEAR, "C"),
        ]
    )

    assert score == 57


def test_risk_band_counts_returns_all_bands():
    counts = risk_band_counts([_risk_score(90, RiskBand.SEVERE_STORM), _risk_score(30, RiskBand.WATCH)])

    assert counts["severe_storm"] == 1
    assert counts["watch"] == 1
    assert counts["clear"] == 0


def test_demo_story_options_cover_required_scenarios():
    stories = {story.key: story for story in demo_story_options()}

    assert set(stories) == {
        "packaging_priority",
        "capa_recurrence_risk",
        "training_drift_sop_revision",
        "sterile_filling_watch",
        "qc_lab_oos_oot_recurrence",
    }
    assert stories["packaging_priority"].label == "Packaging-Priorität"
    assert stories["capa_recurrence_risk"].suggested_human_review_action


def test_demo_story_selects_relevant_scores_and_evidence_cards():
    story = get_demo_story("capa_recurrence_risk")
    matching_score = RiskScore(
        score=88,
        band=RiskBand.SEVERE_STORM,
        horizon=RiskHorizon.FOUR_WEEKS,
        entity_type="capa",
        entity_id="CAPA-014",
        risk_type="capa_failure",
        drivers=["overdue CAPA: CAPA-014 overdue by 3 days (+25)"],
        confidence=0.9,
    )
    unrelated_score = RiskScore(
        score=91,
        band=RiskBand.SEVERE_STORM,
        horizon=RiskHorizon.FOUR_WEEKS,
        entity_type="capa",
        entity_id="CAPA-999",
        risk_type="capa_failure",
        drivers=["overdue CAPA: CAPA-999 overdue by 8 days (+25)"],
        confidence=0.8,
    )
    matching_card = _evidence_card(matching_score, "CAPA-014", "DEV-014")
    unrelated_card = _evidence_card(unrelated_score, "CAPA-999", "DEV-999")

    frame = demo_story_score_frame(story, [unrelated_score, matching_score], [matching_card, unrelated_card])
    cards = select_demo_story_evidence_cards(story, [matching_card, unrelated_card])

    assert frame["entity_id"].tolist() == ["CAPA-014"]
    assert cards == [matching_card]
    assert "CAPA-014" in frame["source_record_ids"].iloc[0]


def _evidence_card(score: RiskScore, *record_ids: str) -> EvidenceCard:
    return EvidenceCard(
        card_id=f"EC-{score.entity_id}",
        generated_at=datetime(2026, 4, 30, tzinfo=timezone.utc),
        risk_score=score,
        source_records=[
            EvidenceSourceRecord(domain="synthetic", record_id=record_id)
            for record_id in record_ids
        ],
        top_drivers=score.drivers,
        rationale="Based on available data, this elevated risk signal is recommended for QA review.",
        recommended_human_review="QA should review the advisory signal before any quality action.",
        limitations=["Advisory decision support only; this card does not make a GMP decision."],
        department="Packaging",
        process="Packaging",
        owner="QA Owner 01",
    )
