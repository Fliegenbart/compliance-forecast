from datetime import date, datetime, timezone
from pathlib import Path

from gmp_weather.audit_log import create_forecast_run_log
from gmp_weather.backtesting import run_backtest
from gmp_weather.data_loader import load_qms_data_bundle
from gmp_weather.data_quality import assess_data_quality
from gmp_weather.evidence import generate_evidence_cards
from gmp_weather.reporting import export_diagnostic_report, generate_markdown_diagnostic_report
from gmp_weather.scoring import calculate_all_scores
from scripts.generate_sample_data import generate_all


AS_OF = date(2026, 4, 30)


def test_generate_markdown_diagnostic_report_contains_required_sections_and_safe_wording(tmp_path: Path):
    generate_all(output_dir=tmp_path, seed=12345)
    bundle = load_qms_data_bundle(tmp_path)
    scores = calculate_all_scores(bundle, AS_OF)
    evidence_cards = generate_evidence_cards(scores, bundle, generated_at=datetime(2026, 4, 30, tzinfo=timezone.utc))
    data_quality_report = assess_data_quality(bundle, as_of=AS_OF)
    backtest_results = run_backtest(bundle, [date(2026, 3, 1)], horizon_days=30)
    config_file = tmp_path / "scoring_rules_v0_1.yaml"
    config_file.write_text("model_version: rules-v0.1\n", encoding="utf-8")
    forecast_run_log = create_forecast_run_log(
        generated_at=datetime(2026, 4, 30, 12, 0, tzinfo=timezone.utc),
        as_of_date=AS_OF,
        model_version="rules-v0.1",
        scoring_config_path=config_file,
        source_files=sorted(tmp_path.glob("*.csv")),
        bundle=bundle,
        user_selected_filters={"horizon": "30 days", "minimum_band": "watch"},
        generated_risk_score_count=len(scores),
        generated_evidence_card_count=len(evidence_cards),
    )

    report = generate_markdown_diagnostic_report(
        bundle,
        scores,
        evidence_cards,
        data_quality_report,
        backtest_results,
        forecast_run_log,
    )

    for heading in [
        "## 1. Executive Summary",
        "## 2. Intended Use And Limitations",
        "## 3. Data Sources Analyzed",
        "## 4. Data Quality Assessment",
        "## 5. Overall Compliance Weather",
        "## 6. Top 20 Forecasted Risks",
        "## 7. Deviation Recurrence Signals",
        "## 8. CAPA Failure Risk Signals",
        "## 9. Training Drift Signals",
        "## 10. Audit Readiness Gap Signals",
        "## 11. Backlog Pressure Analysis",
        "## 12. Evidence Card Appendix",
        "## 13. Backtesting Summary",
        "## 14. Recommended 90-Day Pilot Scope",
        "## 15. Human Decision Boundaries",
    ]:
        assert heading in report

    normalized = report.lower()
    assert "elevated risk signal" in normalized
    assert "recommended for human qa review" in normalized
    assert "based on available data" in normalized
    assert "historical backtest suggests" in normalized
    assert "not a gmp decision" in normalized
    assert "source record ids" in normalized
    assert "does not claim prediction certainty" in normalized


def test_export_diagnostic_report_writes_markdown_file(tmp_path: Path):
    output_path = tmp_path / "output" / "diagnostic_report.md"
    path = export_diagnostic_report("# Diagnostic Report\n\nThis is not a GMP decision.\n", output_path=output_path)

    assert path == output_path
    assert path.exists()
    assert path.read_text(encoding="utf-8").startswith("# Diagnostic Report")
