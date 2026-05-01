from datetime import date, datetime, timezone

from gmp_weather.audit_log import (
    build_read_only_audit_notice,
    create_forecast_run_log,
    hash_file,
    load_forecast_run_logs,
    save_forecast_run_log,
)
from gmp_weather.schemas import QMSDataBundle


def test_read_only_audit_notice_states_no_gmp_decision_was_made():
    notice = build_read_only_audit_notice("dashboard_viewed")

    assert notice["action"] == "dashboard_viewed"
    assert notice["mode"] == "local read-only prototype"
    assert "No source data was changed" in notice["note"]
    assert "no GMP decision was made" in notice["note"]


def test_hash_file_returns_stable_sha256(tmp_path):
    path = tmp_path / "sample.csv"
    path.write_text("record_id,value\nDEV-001,42\n", encoding="utf-8")

    first_hash = hash_file(path)
    second_hash = hash_file(path)

    assert first_hash == second_hash
    assert len(first_hash) == 64


def test_create_save_and_load_forecast_run_log(tmp_path):
    source_file = tmp_path / "deviations.csv"
    source_file.write_text("deviation_id,status\nDEV-001,open\n", encoding="utf-8")
    config_file = tmp_path / "scoring_rules_v0_1.yaml"
    config_file.write_text("model_version: rules-v0.1\n", encoding="utf-8")

    log = create_forecast_run_log(
        generated_at=datetime(2026, 4, 30, 12, 0, tzinfo=timezone.utc),
        as_of_date=date(2026, 4, 30),
        model_version="rules-v0.1",
        scoring_config_path=config_file,
        source_files=[source_file],
        bundle=QMSDataBundle(),
        user_selected_filters={"site": ["Berlin Site"], "minimum_band": "advisory"},
        generated_risk_score_count=12,
        generated_evidence_card_count=7,
    )

    saved_path = save_forecast_run_log(log, tmp_path / "logs")
    loaded = load_forecast_run_logs(tmp_path / "logs")

    assert saved_path.exists()
    assert loaded[0].forecast_run_id == log.forecast_run_id
    assert loaded[0].source_file_names == ["deviations.csv"]
    assert loaded[0].source_file_hashes["deviations.csv"] == hash_file(source_file)
    assert loaded[0].scoring_config_hash == hash_file(config_file)
    assert loaded[0].number_of_records_by_domain["deviations"] == 0
    assert loaded[0].generated_risk_score_count == 12
    assert loaded[0].generated_evidence_card_count == 7
