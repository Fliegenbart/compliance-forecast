from datetime import date
from pathlib import Path

from scripts.build_vercel_demo import build_vercel_demo, build_vercel_demo_payload
from scripts.generate_sample_data import generate_all


def test_build_vercel_demo_payload_is_advisory_and_source_linked(tmp_path: Path):
    generate_all(output_dir=tmp_path, seed=12345)

    payload = build_vercel_demo_payload(sample_data_dir=tmp_path, as_of_date=date(2026, 4, 30))

    assert payload["meta"]["model_version"] == "rules-v0.1"
    assert "does not make GMP decisions" in payload["meta"]["safety_boundary"]
    assert payload["summary"]["risk_score_count"] > 0
    assert payload["summary"]["evidence_card_count"] > 0
    assert payload["top_risks"][0]["top_drivers"]
    assert payload["evidence_cards"][0]["source_record_ids"]
    assert payload["demo_stories"]


def test_build_vercel_demo_writes_forecast_json(tmp_path: Path):
    sample_dir = tmp_path / "sample"
    output_path = tmp_path / "vercel-demo" / "data" / "forecast.json"
    generate_all(output_dir=sample_dir, seed=12345)

    written_path = build_vercel_demo(
        sample_data_dir=sample_dir,
        output_path=output_path,
        as_of_date=date(2026, 4, 30),
    )

    assert written_path == output_path
    text = output_path.read_text(encoding="utf-8")
    assert "GMP Compliance Weather Forecast" in text
    assert "source_record_ids" in text
