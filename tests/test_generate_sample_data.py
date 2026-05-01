from datetime import timedelta
from pathlib import Path

import pandas as pd

from scripts.generate_sample_data import REFERENCE_DATE, generate_all


EXPECTED_COUNTS = {
    "deviations.csv": 250,
    "capas.csv": 80,
    "audit_findings.csv": 40,
    "training_records.csv": 400,
    "change_controls.csv": 120,
    "sops.csv": 100,
}


def test_generate_all_creates_expected_csv_files(tmp_path: Path):
    output_dir = tmp_path / "sample"

    generated = generate_all(output_dir=output_dir, seed=12345)

    assert set(generated) == set(EXPECTED_COUNTS)
    for filename, expected_count in EXPECTED_COUNTS.items():
        frame = pd.read_csv(output_dir / filename)
        assert len(frame) == expected_count


def test_generate_all_is_deterministic_for_same_seed(tmp_path: Path):
    first_dir = tmp_path / "first"
    second_dir = tmp_path / "second"

    generate_all(output_dir=first_dir, seed=777)
    generate_all(output_dir=second_dir, seed=777)

    for filename in EXPECTED_COUNTS:
        assert (first_dir / filename).read_text() == (second_dir / filename).read_text()


def test_generated_data_contains_requested_risk_patterns(tmp_path: Path):
    output_dir = tmp_path / "sample"
    generate_all(output_dir=output_dir, seed=12345)

    deviations = pd.read_csv(output_dir / "deviations.csv", parse_dates=["opened_date"])
    capas = pd.read_csv(output_dir / "capas.csv", parse_dates=["due_date"])
    findings = pd.read_csv(output_dir / "audit_findings.csv")
    training = pd.read_csv(output_dir / "training_records.csv")
    changes = pd.read_csv(output_dir / "change_controls.csv")
    sops = pd.read_csv(output_dir / "sops.csv", parse_dates=["effective_date"])

    packaging_recent = deviations[
        (deviations["process"] == "Packaging")
        & (deviations["opened_date"].dt.date >= REFERENCE_DATE - timedelta(weeks=6))
    ].copy()
    week_counts = (
        packaging_recent.assign(week=packaging_recent["opened_date"].dt.isocalendar().week)
        .groupby("week")
        .size()
        .tolist()
    )
    assert week_counts == sorted(week_counts)
    assert len(week_counts) >= 6

    severity_rank = {"minor": 1, "major": 2, "critical": 3}
    deviations["severity_rank"] = deviations["severity"].str.lower().map(severity_rank)
    sterile_mean = deviations.loc[deviations["process"] == "Sterile Filling", "severity_rank"].mean()
    packaging_mean = deviations.loc[deviations["process"] == "Packaging", "severity_rank"].mean()
    assert sterile_mean > packaging_mean

    qc_oos_count = deviations[
        (deviations["department"] == "QC Lab")
        & deviations["short_description"].str.contains("OOS|OOT", regex=True)
    ].shape[0]
    assert qc_oos_count >= 35

    overdue_capas = capas[(capas["status"] != "closed") & (capas["due_date"].dt.date < REFERENCE_DATE)]
    assert len(overdue_capas) >= 10
    assert capas["action_type"].str.contains("Retraining", case=False).sum() >= 10
    assert capas["effectiveness_status"].fillna("").str.contains("vague", case=False).sum() >= 8

    recent_sops = set(sops.loc[sops["effective_date"].dt.date >= REFERENCE_DATE - timedelta(weeks=6), "sop_id"])
    incomplete_recent_sop_training = training[
        training["sop_id"].isin(recent_sops) & (training["status"] != "completed")
    ]
    assert len(recent_sops) >= 15
    assert len(incomplete_recent_sop_training) >= 40

    open_validation_changes = changes[
        (changes["validation_impact"] == True) & (changes["status"] != "closed")  # noqa: E712
    ]
    assert len(open_validation_changes) >= 20

    assert findings["linked_capa_id"].fillna("").str.startswith("CAPA-").sum() >= 20

    owner_counts = pd.concat(
        [
            deviations["owner"],
            capas["owner"],
            changes["owner"],
        ]
    ).value_counts()
    assert owner_counts.max() >= 35


def test_generated_data_contains_demo_story_anchor_records(tmp_path: Path):
    output_dir = tmp_path / "sample"
    generate_all(output_dir=output_dir, seed=12345)

    deviations = pd.read_csv(output_dir / "deviations.csv")
    capas = pd.read_csv(output_dir / "capas.csv", parse_dates=["due_date"])
    training = pd.read_csv(output_dir / "training_records.csv")
    sops = pd.read_csv(output_dir / "sops.csv", parse_dates=["effective_date"])

    capa_014 = capas.loc[capas["capa_id"] == "CAPA-014"].iloc[0]
    linked_ids = str(capa_014["linked_deviation_ids"]).split("|")
    linked_deviations = deviations[deviations["deviation_id"].isin(linked_ids)]

    assert capa_014["status"] != "closed"
    assert capa_014["due_date"].date() < REFERENCE_DATE
    assert capa_014["department"] == "Packaging"
    assert capa_014["process"] == "Packaging"
    assert len(linked_deviations) >= 3
    assert set(linked_deviations["process"]) == {"Packaging"}
    assert "SOP-023" in set(linked_deviations["sop_id"])

    sop_023 = sops.loc[sops["sop_id"] == "SOP-023"].iloc[0]
    incomplete_sop_023_training = training[
        (training["sop_id"] == "SOP-023")
        & (training["department"] == "Packaging")
        & (training["status"] != "completed")
    ]

    assert sop_023["department"] == "Packaging"
    assert sop_023["process"] == "Packaging"
    assert sop_023["effective_date"].date() >= REFERENCE_DATE - timedelta(weeks=6)
    assert len(incomplete_sop_023_training) >= 5
