#!/usr/bin/env python3
"""Generate deterministic, fully synthetic GMP sample CSV files.

The generated files are for advisory prototype development only. They are not
real GMP records and must not be used as GMP decision records.
"""

from __future__ import annotations

import argparse
import csv
import random
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Iterable

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from gmp_weather.schemas import AuditFinding, CAPA, ChangeControl, Deviation, SOP, TrainingRecord


DEFAULT_SEED = 20260430
REFERENCE_DATE = date(2026, 4, 30)
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "sample"

SITES = ["Berlin Site", "Basel Site"]
DEPARTMENTS = ["Production", "QC Lab", "QA Operations", "Engineering", "Warehouse", "Packaging"]
PROCESSES = [
    "Weighing",
    "Granulation",
    "Sterile Filling",
    "Packaging",
    "QC Release Testing",
    "Cleaning",
    "Equipment Maintenance",
    "Supplier Qualification",
]
PRODUCTS = ["Product A", "Product B", "Product C"]
EQUIPMENT_IDS = [f"EQ-{index:03d}" for index in range(1, 21)]
SUPPLIER_IDS = [f"SUP-{index:03d}" for index in range(1, 16)]
SOP_IDS = [f"SOP-{index:03d}" for index in range(1, 101)]

OVERLOADED_OWNERS = ["QA Owner 01", "QA Owner 02", "Packaging Owner 01"]
OWNER_POOL = OVERLOADED_OWNERS + [
    "Production Owner 01",
    "Production Owner 02",
    "QC Owner 01",
    "QC Owner 02",
    "Engineering Owner 01",
    "Warehouse Owner 01",
    "Validation Owner 01",
    "Supplier Quality Owner 01",
]

PROCESS_DEPARTMENT = {
    "Weighing": "Production",
    "Granulation": "Production",
    "Sterile Filling": "Production",
    "Packaging": "Packaging",
    "QC Release Testing": "QC Lab",
    "Cleaning": "Production",
    "Equipment Maintenance": "Engineering",
    "Supplier Qualification": "QA Operations",
}


def generate_all(output_dir: str | Path = DEFAULT_OUTPUT_DIR, seed: int = DEFAULT_SEED) -> dict[str, Path]:
    """Generate all synthetic sample CSV files and return their paths."""

    rng = random.Random(seed)
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)

    sops = generate_sops(rng)
    recent_sop_ids = {
        sop.sop_id
        for sop in sops
        if sop.effective_date >= REFERENCE_DATE - timedelta(weeks=6)
    }
    deviations = generate_deviations(rng)
    capas = generate_capas(rng, deviations)
    capa_ids = [record.capa_id for record in capas]
    audit_findings = generate_audit_findings(rng, capa_ids)
    training_records = generate_training_records(rng, recent_sop_ids)
    change_controls = generate_change_controls(rng)

    outputs = {
        "deviations.csv": _write_models(destination / "deviations.csv", deviations, Deviation),
        "capas.csv": _write_models(destination / "capas.csv", capas, CAPA),
        "audit_findings.csv": _write_models(destination / "audit_findings.csv", audit_findings, AuditFinding),
        "training_records.csv": _write_models(destination / "training_records.csv", training_records, TrainingRecord),
        "change_controls.csv": _write_models(destination / "change_controls.csv", change_controls, ChangeControl),
        "sops.csv": _write_models(destination / "sops.csv", sops, SOP),
    }
    return outputs


def generate_sops(rng: random.Random) -> list[SOP]:
    """Generate synthetic SOP metadata with a recent-change cluster."""

    records: list[SOP] = []
    for index, sop_id in enumerate(SOP_IDS, start=1):
        process = PROCESSES[(index - 1) % len(PROCESSES)]
        department = PROCESS_DEPARTMENT[process]
        if index <= 20:
            effective_date = REFERENCE_DATE - timedelta(days=rng.randint(1, 42))
            status = "effective"
        else:
            effective_date = REFERENCE_DATE - timedelta(days=rng.randint(75, 900))
            status = "under_revision" if index % 17 == 0 else "effective"
        if sop_id == "SOP-023":
            process = "Packaging"
            department = "Packaging"
            effective_date = REFERENCE_DATE - timedelta(days=18)
            status = "effective"

        records.append(
            SOP(
                sop_id=sop_id,
                title=f"Synthetic {process} SOP {index:03d}",
                department=department,
                process=process,
                version=f"{1 + index // 25}.{index % 10}",
                effective_date=effective_date,
                revision_date=REFERENCE_DATE - timedelta(days=12) if sop_id == "SOP-023" else effective_date + timedelta(days=365),
                status=status,
            )
        )
    return records


def generate_deviations(rng: random.Random) -> list[Deviation]:
    """Generate synthetic deviations with requested advisory risk patterns."""

    records: list[Deviation] = []

    def add_record(
        *,
        opened_date: date,
        process: str,
        severity: str,
        short_description: str,
        root_cause_category: str | None,
        owner: str,
        recurrence_flag: bool | None = None,
        capa_id: str | None = None,
        sop_id: str | None = None,
        equipment_id: str | None = None,
    ) -> None:
        deviation_number = len(records) + 1
        status = _status_for_opened_date(rng, opened_date)
        closed_date = (
            opened_date + timedelta(days=rng.randint(5, 45))
            if status == "closed"
            else None
        )
        department = PROCESS_DEPARTMENT[process]
        records.append(
            Deviation(
                deviation_id=f"DEV-{deviation_number:03d}",
                opened_date=opened_date,
                closed_date=closed_date,
                due_date=opened_date + timedelta(days=rng.randint(20, 45)),
                status=status,
                severity=severity,
                site=_choice(rng, SITES),
                department=department,
                process=process,
                product=_choice(rng, PRODUCTS),
                batch_id=f"BATCH-{REFERENCE_DATE.year}-{rng.randint(1, 180):03d}",
                equipment_id=equipment_id if equipment_id else (_choice(rng, EQUIPMENT_IDS) if process != "Supplier Qualification" else None),
                supplier_id=_choice(rng, SUPPLIER_IDS) if process == "Supplier Qualification" else None,
                sop_id=sop_id if sop_id else _choice(rng, SOP_IDS),
                owner=owner,
                short_description=short_description,
                root_cause_category=root_cause_category,
                capa_id=capa_id if capa_id else (f"CAPA-{rng.randint(1, 80):03d}" if rng.random() < 0.35 else None),
                recurrence_flag=recurrence_flag,
            )
        )

    week_start = REFERENCE_DATE - timedelta(days=REFERENCE_DATE.weekday())
    packaging_counts = [4, 6, 8, 10, 12, 14]
    for week_index, count in enumerate(packaging_counts):
        start = week_start - timedelta(weeks=5 - week_index)
        for item_index in range(count):
            is_capa_014_story_record = week_index >= 3 and item_index < 3
            add_record(
                opened_date=start + timedelta(days=rng.randint(0, 3)),
                process="Packaging",
                severity=_weighted_choice(rng, [("minor", 0.62), ("major", 0.34), ("critical", 0.04)]),
                short_description="Synthetic packaging deviation: label reconciliation or line clearance issue.",
                root_cause_category="line clearance" if is_capa_014_story_record else _choice(rng, ["line clearance", "label reconciliation", "manual check gap"]),
                owner=_weighted_choice(
                    rng,
                    [("Packaging Owner 01", 0.60), ("QA Owner 01", 0.25), ("Production Owner 01", 0.15)],
                ),
                recurrence_flag=rng.random() < 0.45,
                capa_id="CAPA-014" if is_capa_014_story_record else None,
                sop_id="SOP-023" if is_capa_014_story_record else None,
                equipment_id="EQ-014" if is_capa_014_story_record else None,
            )

    for _ in range(24):
        add_record(
            opened_date=_date_between(rng, REFERENCE_DATE - timedelta(days=180), REFERENCE_DATE - timedelta(days=5)),
            process="Sterile Filling",
            severity=_weighted_choice(rng, [("major", 0.55), ("critical", 0.45)]),
            short_description="Synthetic sterile filling deviation: aseptic intervention or environmental monitoring concern.",
            root_cause_category=_choice(rng, ["aseptic intervention", "environmental monitoring", "procedural adherence"]),
            owner=_weighted_choice(rng, [("QA Owner 02", 0.50), ("Production Owner 02", 0.30), ("Validation Owner 01", 0.20)]),
            recurrence_flag=rng.random() < 0.25,
        )

    for index in range(45):
        signal = "OOS" if index % 2 == 0 else "OOT"
        add_record(
            opened_date=_date_between(rng, REFERENCE_DATE - timedelta(days=220), REFERENCE_DATE - timedelta(days=7)),
            process="QC Release Testing",
            severity=_weighted_choice(rng, [("minor", 0.25), ("major", 0.65), ("critical", 0.10)]),
            short_description=f"Synthetic QC Lab {signal}-related deviation for release testing trend review.",
            root_cause_category=_choice(rng, ["analytical method", "sample handling", "instrument issue"]),
            owner=_weighted_choice(rng, [("QC Owner 01", 0.45), ("QA Owner 01", 0.35), ("QC Owner 02", 0.20)]),
            recurrence_flag=True,
        )

    filler_processes = [
        "Weighing",
        "Granulation",
        "Cleaning",
        "Equipment Maintenance",
        "Supplier Qualification",
    ]
    while len(records) < 250:
        process = _choice(rng, filler_processes)
        add_record(
            opened_date=_date_between(rng, REFERENCE_DATE - timedelta(days=365), REFERENCE_DATE - timedelta(days=50)),
            process=process,
            severity=_weighted_choice(rng, [("minor", 0.58), ("major", 0.37), ("critical", 0.05)]),
            short_description=f"Synthetic {process.lower()} deviation requiring documented QA review.",
            root_cause_category=_choice(
                rng,
                ["documentation gap", "equipment setup", "supplier documentation", "SOP interpretation"],
            ),
            owner=_choose_owner(rng, overload_bias=rng.random() < 0.25),
            recurrence_flag=rng.random() < 0.20,
        )
    return records


def generate_capas(rng: random.Random, deviations: list[Deviation]) -> list[CAPA]:
    """Generate synthetic CAPAs with overdue, retraining-only, and vague-check patterns."""

    records: list[CAPA] = []
    deviation_ids = [record.deviation_id for record in deviations]
    capa_014_deviation_ids = [
        record.deviation_id
        for record in deviations
        if record.process == "Packaging" and record.capa_id == "CAPA-014"
    ][:6]
    for index in range(1, 81):
        if index <= 15:
            opened_date = REFERENCE_DATE - timedelta(days=rng.randint(70, 150))
            due_date = REFERENCE_DATE - timedelta(days=rng.randint(1, 35))
            status = _choice(rng, ["open", "in_progress"])
        else:
            opened_date = REFERENCE_DATE - timedelta(days=rng.randint(15, 260))
            due_date = opened_date + timedelta(days=rng.randint(45, 120))
            status = _weighted_choice(rng, [("closed", 0.45), ("in_progress", 0.35), ("open", 0.20)])

        closed_date = opened_date + timedelta(days=rng.randint(25, 110)) if status == "closed" else None
        action_type = "Retraining only" if 16 <= index <= 28 else _choice(
            rng,
            ["Procedure update", "Process correction", "Preventive action", "Supplier follow-up"],
        )
        effectiveness_status = (
            "vague - monitor for recurrence"
            if 29 <= index <= 38
            else _choice(rng, ["planned", "not due", "effective", "pending QA review"])
        )
        linked_count = rng.randint(1, 3)
        linked_ids = rng.sample(deviation_ids, linked_count)
        process = _choice(rng, PROCESSES)
        if index == 14:
            process = "Packaging"
            linked_ids = capa_014_deviation_ids or rng.sample(
                [record.deviation_id for record in deviations if record.process == "Packaging"],
                3,
            )
            action_type = "Retraining only"
            effectiveness_status = "vague - monitor for recurrence"

        records.append(
            CAPA(
                capa_id=f"CAPA-{index:03d}",
                opened_date=opened_date,
                closed_date=closed_date,
                due_date=due_date,
                status=status,
                site="Berlin Site" if index == 14 else _choice(rng, SITES),
                department=PROCESS_DEPARTMENT[process],
                process=process,
                owner="Packaging Owner 01" if index == 14 else _choose_owner(rng, overload_bias=index <= 18),
                linked_deviation_ids=linked_ids,
                root_cause_category="line clearance" if index == 14 else _choice(
                    rng,
                    ["procedure gap", "training gap", "equipment condition", "supplier process", "human factors"],
                ),
                action_type=action_type,
                action_description=_capa_action_description(action_type, process),
                effectiveness_check_due_date=due_date + timedelta(days=rng.randint(30, 90)),
                effectiveness_status=effectiveness_status,
            )
        )
    return records


def generate_audit_findings(rng: random.Random, capa_ids: list[str]) -> list[AuditFinding]:
    """Generate synthetic audit findings, many linked to CAPAs."""

    records: list[AuditFinding] = []
    finding_types = ["internal audit", "supplier audit", "self inspection", "mock inspection"]
    for index in range(1, 41):
        process = _choice(rng, PROCESSES)
        records.append(
            AuditFinding(
                finding_id=f"FIND-{index:03d}",
                audit_date=_date_between(rng, REFERENCE_DATE - timedelta(days=360), REFERENCE_DATE - timedelta(days=10)),
                finding_type=_choice(rng, finding_types),
                severity=_weighted_choice(rng, [("minor", 0.55), ("major", 0.38), ("critical", 0.07)]),
                site="Berlin Site" if index == 14 else _choice(rng, SITES),
                department="Packaging" if index == 14 else PROCESS_DEPARTMENT[process],
                process="Packaging" if index == 14 else process,
                linked_capa_id=capa_ids[index - 1] if index <= 25 else None,
                description=f"Synthetic audit finding for {process.lower()} control follow-up.",
                status=_weighted_choice(rng, [("open", 0.35), ("in_progress", 0.35), ("closed", 0.30)]),
            )
        )
    return records


def generate_training_records(rng: random.Random, recent_sop_ids: set[str]) -> list[TrainingRecord]:
    """Generate synthetic training records with incomplete training on recently changed SOPs."""

    records: list[TrainingRecord] = []
    employee_roles = [
        "Operator",
        "QA Specialist",
        "QC Analyst",
        "Engineer",
        "Warehouse Associate",
        "Packaging Technician",
    ]
    recent_sops = sorted(recent_sop_ids)

    for index in range(1, 401):
        if index <= 140:
            sop_id = recent_sops[(index - 1) % len(recent_sops)]
            assigned_date = REFERENCE_DATE - timedelta(days=rng.randint(1, 35))
            if index <= 70:
                status = _choice(rng, ["assigned", "overdue", "in_progress"])
                completion_date = None
            else:
                status = "completed"
                completion_date = assigned_date + timedelta(days=rng.randint(1, 18))
        else:
            sop_id = _choice(rng, SOP_IDS)
            assigned_date = REFERENCE_DATE - timedelta(days=rng.randint(40, 320))
            status = _weighted_choice(rng, [("completed", 0.76), ("assigned", 0.10), ("overdue", 0.09), ("in_progress", 0.05)])
            completion_date = (
                assigned_date + timedelta(days=rng.randint(1, 25))
                if status == "completed"
                else None
            )

        department = _choice(rng, DEPARTMENTS)
        if index <= 8:
            sop_id = "SOP-023"
            department = "Packaging"
            status = _choice(rng, ["assigned", "overdue", "in_progress"])
            completion_date = None

        records.append(
            TrainingRecord(
                training_id=f"TRN-{index:03d}",
                employee_role=_choice(rng, employee_roles),
                department=department,
                sop_id=sop_id,
                assigned_date=assigned_date,
                due_date=assigned_date + timedelta(days=rng.randint(14, 30)),
                completion_date=completion_date,
                status=status,
            )
        )
    return records


def generate_change_controls(rng: random.Random) -> list[ChangeControl]:
    """Generate synthetic change controls with open validation-impacting changes."""

    records: list[ChangeControl] = []
    for index in range(1, 121):
        validation_impact = index <= 35 or rng.random() < 0.25
        training_impact = validation_impact or rng.random() < 0.35
        status = (
            _choice(rng, ["open", "assessment", "implementation", "QA review"])
            if index <= 35
            else _weighted_choice(rng, [("closed", 0.42), ("open", 0.20), ("assessment", 0.20), ("implementation", 0.18)])
        )
        opened_date = _date_between(rng, REFERENCE_DATE - timedelta(days=300), REFERENCE_DATE - timedelta(days=5))
        closed_date = opened_date + timedelta(days=rng.randint(30, 150)) if status == "closed" else None
        process = _choice(rng, PROCESSES)

        records.append(
            ChangeControl(
                change_id=f"CC-{index:03d}",
                opened_date=opened_date,
                target_implementation_date=opened_date + timedelta(days=rng.randint(30, 140)),
                closed_date=closed_date,
                status=status,
                site=_choice(rng, SITES),
                department=PROCESS_DEPARTMENT[process],
                process=process,
                affected_sop_ids=rng.sample(SOP_IDS, rng.randint(1, 3)),
                affected_equipment_ids=rng.sample(EQUIPMENT_IDS, rng.randint(0, 2)),
                affected_system_ids=[f"CSV-{rng.randint(1, 12):03d}"] if validation_impact else [],
                validation_impact=validation_impact,
                training_impact=training_impact,
                owner=_choose_owner(rng, overload_bias=index <= 25),
                description=f"Synthetic change control for {process.lower()} process update.",
            )
        )
    return records


def _write_models(path: Path, records: Iterable[object], model_cls: type) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(model_cls.model_fields)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for record in records:
            writer.writerow(_csv_row(record.model_dump(mode="json"), fieldnames))
    return path


def _csv_row(data: dict[str, object], fieldnames: list[str]) -> dict[str, object]:
    row: dict[str, object] = {}
    for fieldname in fieldnames:
        value = data.get(fieldname)
        if value is None:
            row[fieldname] = ""
        elif isinstance(value, list):
            row[fieldname] = "|".join(str(item) for item in value)
        else:
            row[fieldname] = value
    return row


def _date_between(rng: random.Random, start: date, end: date) -> date:
    return start + timedelta(days=rng.randint(0, (end - start).days))


def _choice(rng: random.Random, values: list[str]) -> str:
    return values[rng.randrange(len(values))]


def _weighted_choice(rng: random.Random, weighted_values: list[tuple[str, float]]) -> str:
    total = sum(weight for _, weight in weighted_values)
    marker = rng.random() * total
    running = 0.0
    for value, weight in weighted_values:
        running += weight
        if marker <= running:
            return value
    return weighted_values[-1][0]


def _choose_owner(rng: random.Random, overload_bias: bool = False) -> str:
    if overload_bias or rng.random() < 0.30:
        return _choice(rng, OVERLOADED_OWNERS)
    return _choice(rng, OWNER_POOL)


def _status_for_opened_date(rng: random.Random, opened_date: date) -> str:
    if opened_date >= REFERENCE_DATE - timedelta(weeks=8):
        return _weighted_choice(rng, [("open", 0.45), ("in_progress", 0.40), ("closed", 0.15)])
    return _weighted_choice(rng, [("closed", 0.58), ("in_progress", 0.24), ("open", 0.16), ("cancelled", 0.02)])


def _capa_action_description(action_type: str, process: str) -> str:
    if action_type == "Retraining only":
        return f"Synthetic retraining-only action for {process.lower()} personnel on applicable SOPs."
    return f"Synthetic {action_type.lower()} for {process.lower()} control improvement."


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate deterministic synthetic GMP sample data.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    args = parser.parse_args()

    outputs = generate_all(output_dir=args.output_dir, seed=args.seed)
    for filename, path in outputs.items():
        print(f"{filename}: {path}")


if __name__ == "__main__":
    main()
