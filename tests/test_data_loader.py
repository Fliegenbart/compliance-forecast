from pathlib import Path

import pandas as pd
import pytest

from gmp_weather.data_loader import load_qms_data_bundle, load_qms_records
from scripts.generate_sample_data import generate_all


def test_load_qms_records_returns_valid_records(tmp_path: Path):
    csv_path = tmp_path / "qms_records.csv"
    pd.DataFrame(
        [
            {
                "record_id": "DEV-001",
                "record_type": "deviation",
                "site": "Site Alpha",
                "process_area": "sterile manufacturing",
                "severity": 4,
                "occurrence": 3,
                "detection": 2,
                "status": "open",
                "opened_date": "2026-04-01",
                "due_date": "2026-04-25",
                "description": "Synthetic record.",
            }
        ]
    ).to_csv(csv_path, index=False)

    records = load_qms_records(csv_path)

    assert len(records) == 1
    assert records[0].record_id == "DEV-001"
    assert records[0].due_date.isoformat() == "2026-04-25"


def test_load_qms_records_rejects_missing_required_columns(tmp_path: Path):
    csv_path = tmp_path / "qms_records.csv"
    pd.DataFrame([{"record_id": "DEV-001"}]).to_csv(csv_path, index=False)

    with pytest.raises(ValueError, match="Missing required columns"):
        load_qms_records(csv_path)


def test_load_qms_data_bundle_parses_generated_domain_csv_files(tmp_path: Path):
    generate_all(output_dir=tmp_path, seed=12345)

    bundle = load_qms_data_bundle(tmp_path)

    assert len(bundle.deviations) == 250
    assert len(bundle.capas) == 80
    assert len(bundle.audit_findings) == 40
    assert len(bundle.training_records) == 400
    assert len(bundle.change_controls) == 120
    assert len(bundle.sops) == 100
    assert bundle.deviations[0].deviation_id == "DEV-001"
    assert bundle.capas[0].linked_deviation_ids
    assert bundle.change_controls[0].affected_sop_ids


def test_load_qms_data_bundle_handles_missing_optional_columns(tmp_path: Path):
    generate_all(output_dir=tmp_path, seed=12345)
    deviations_path = tmp_path / "deviations.csv"
    deviations = pd.read_csv(deviations_path)
    deviations = deviations.drop(columns=["product", "batch_id", "equipment_id", "supplier_id"])
    deviations.to_csv(deviations_path, index=False)

    bundle = load_qms_data_bundle(tmp_path)

    assert bundle.deviations[0].product is None
    assert bundle.deviations[0].batch_id is None
    assert bundle.deviations[0].equipment_id is None
    assert bundle.deviations[0].supplier_id is None


def test_load_qms_data_bundle_rejects_missing_required_file(tmp_path: Path):
    generate_all(output_dir=tmp_path, seed=12345)
    (tmp_path / "capas.csv").unlink()

    with pytest.raises(FileNotFoundError, match="Missing required QMS data file: capas.csv"):
        load_qms_data_bundle(tmp_path)


def test_load_qms_data_bundle_rejects_missing_required_columns(tmp_path: Path):
    generate_all(output_dir=tmp_path, seed=12345)
    capas_path = tmp_path / "capas.csv"
    capas = pd.read_csv(capas_path).drop(columns=["status"])
    capas.to_csv(capas_path, index=False)

    with pytest.raises(ValueError, match="capas.csv missing required columns: status"):
        load_qms_data_bundle(tmp_path)
