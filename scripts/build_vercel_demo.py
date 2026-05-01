#!/usr/bin/env python3
"""Build a static Vercel-friendly demo from synthetic GMP risk-prioritization data."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from gmp_weather.config import SAMPLE_DATA_DIR, SCORING_CONFIG_PATH, load_scoring_config
from gmp_weather.data_loader import load_qms_data_bundle
from gmp_weather.data_quality import assess_data_quality
from gmp_weather.evidence import generate_evidence_cards
from gmp_weather.schemas import EvidenceCard, QMSDataBundle, RiskScore
from gmp_weather.scoring import calculate_all_scores


DEFAULT_AS_OF_DATE = date(2026, 4, 30)
DEFAULT_OUTPUT_PATH = PROJECT_ROOT / "vercel-demo" / "data" / "forecast.json"


def build_vercel_demo_payload(
    sample_data_dir: Path | str = SAMPLE_DATA_DIR,
    as_of_date: date = DEFAULT_AS_OF_DATE,
) -> dict[str, Any]:
    """Build a source-linked, advisory-only payload for the static Vercel demo."""

    bundle = load_qms_data_bundle(sample_data_dir)
    scoring_config = load_scoring_config(SCORING_CONFIG_PATH)
    scores = calculate_all_scores(bundle, as_of_date=as_of_date, scoring_config=scoring_config)
    generated_at = datetime.now(timezone.utc)
    evidence_cards = generate_evidence_cards(scores, bundle, generated_at=generated_at)
    data_quality_report = assess_data_quality(bundle, as_of=as_of_date)

    top_scores = sorted(scores, key=lambda score: score.score, reverse=True)
    overall_index = round(sum(score.score for score in top_scores[:10]) / min(len(top_scores), 10), 1) if top_scores else 0
    band_counts = Counter(score.band.value for score in scores)
    risk_type_counts = Counter(score.risk_type for score in scores)

    score_rows = [_score_row(score, bundle) for score in _select_demo_scores(top_scores)]
    evidence_rows = [_evidence_row(card) for card in evidence_cards[:40]]

    payload = {
        "meta": {
            "app_name": "GMP Risiko-Cockpit",
            "client_name": "Beispiel GmbH",
            "generated_at": generated_at.isoformat(),
            "as_of_date": as_of_date.isoformat(),
            "model_version": scoring_config.model_version,
            "scoring_config_file": "config/scoring_rules_v0_1.yaml",
            "safety_boundary": (
                "Advisory quality-risk signals only. This static demo does not make GMP decisions. "
                "Human QA review is required."
            ),
        },
        "summary": {
            "qa_prioritization_index": overall_index,
            "data_readiness_score": data_quality_report.data_readiness_score,
            "risk_score_count": len(scores),
            "evidence_card_count": len(evidence_cards),
            "source_record_count": {
                "deviations": len(bundle.deviations),
                "capas": len(bundle.capas),
                "audit_findings": len(bundle.audit_findings),
                "training_records": len(bundle.training_records),
                "change_controls": len(bundle.change_controls),
                "sops": len(bundle.sops),
            },
        },
        "risk_band_counts": dict(sorted(band_counts.items())),
        "risk_type_counts": dict(sorted(risk_type_counts.items())),
        "top_risks": score_rows,
        "heatmap": _heatmap_rows(scores, bundle),
        "evidence_cards": evidence_rows,
        "data_quality_issues": [
            {
                "domain": issue.domain,
                "record_id": issue.record_id,
                "severity": issue.severity,
                "message": issue.message,
            }
            for issue in data_quality_report.issue_list[:25]
        ],
        "demo_stories": _demo_stories(score_rows, evidence_rows),
    }
    return payload


def build_vercel_demo(
    sample_data_dir: Path | str = SAMPLE_DATA_DIR,
    output_path: Path | str = DEFAULT_OUTPUT_PATH,
    as_of_date: date = DEFAULT_AS_OF_DATE,
) -> Path:
    """Write the static Vercel demo payload to ``vercel-demo/data/forecast.json``."""

    payload = build_vercel_demo_payload(sample_data_dir=sample_data_dir, as_of_date=as_of_date)
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return destination


def _select_demo_scores(sorted_scores: list[RiskScore]) -> list[RiskScore]:
    """Keep overall top risks plus enough per-risk-type rows for static forecast filters."""

    selected: list[RiskScore] = []
    seen: set[tuple[str, str, str]] = set()

    def add(score: RiskScore) -> None:
        key = (score.risk_type, score.entity_type, score.entity_id)
        if key not in seen:
            selected.append(score)
            seen.add(key)

    for score in sorted_scores[:28]:
        add(score)

    for risk_type in [
        "deviation_recurrence",
        "capa_failure",
        "training_drift",
        "audit_readiness_gap",
        "backlog_pressure",
    ]:
        for score in [item for item in sorted_scores if item.risk_type == risk_type][:8]:
            add(score)

    return selected[:68]


def _score_row(score: RiskScore, bundle: QMSDataBundle) -> dict[str, Any]:
    context = _score_context(score, bundle)
    return {
        "score": score.score,
        "band": score.band.value,
        "horizon": score.horizon.value,
        "entity_type": score.entity_type,
        "entity_id": score.entity_id,
        "risk_type": score.risk_type,
        "department": context.get("department", ""),
        "process": context.get("process", ""),
        "owner": context.get("owner", ""),
        "confidence": score.confidence,
        "top_drivers": score.drivers[:4],
    }


def _evidence_row(card: EvidenceCard) -> dict[str, Any]:
    return {
        "card_id": card.card_id,
        "score": card.risk_score.score,
        "band": card.risk_score.band.value,
        "horizon": card.risk_score.horizon.value,
        "risk_type": card.risk_score.risk_type,
        "entity_type": card.risk_score.entity_type,
        "entity_id": card.risk_score.entity_id,
        "department": card.department or "",
        "process": card.process or "",
        "owner": card.owner or "",
        "top_drivers": card.top_drivers,
        "source_record_ids": [source.record_id for source in card.source_records],
        "source_records": [
            {"domain": source.domain, "record_id": source.record_id}
            for source in card.source_records
        ],
        "rationale": card.rationale,
        "recommended_human_review": card.recommended_human_review,
        "limitations": card.limitations,
    }


def _heatmap_rows(scores: list[RiskScore], bundle: QMSDataBundle) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[float]] = defaultdict(list)
    for score in scores:
        context = _score_context(score, bundle)
        department = context.get("department") or "Cross-functional"
        process = context.get("process") or "All processes"
        grouped[(department, process)].append(score.score)

    rows = []
    for (department, process), values in grouped.items():
        rows.append(
            {
                "department": department,
                "process": process,
                "max_score": round(max(values), 1),
                "average_score": round(sum(values) / len(values), 1),
                "signal_count": len(values),
            }
        )
    return sorted(rows, key=lambda row: row["max_score"], reverse=True)[:24]


def _score_context(score: RiskScore, bundle: QMSDataBundle) -> dict[str, str]:
    if score.risk_type == "deviation_recurrence":
        deviation = next((item for item in bundle.deviations if item.deviation_id == score.entity_id), None)
        if deviation:
            return {
                "department": deviation.department,
                "process": deviation.process,
                "owner": deviation.owner,
            }
    if score.risk_type == "capa_failure":
        capa = next((item for item in bundle.capas if item.capa_id == score.entity_id), None)
        if capa:
            return {
                "department": capa.department,
                "process": capa.process,
                "owner": capa.owner,
            }
    if score.risk_type == "training_drift":
        department, process, _sop_id = _split_entity(score.entity_id, 3)
        return {"department": department, "process": process, "owner": ""}
    if score.risk_type == "audit_readiness_gap":
        department, process = _split_entity(score.entity_id, 2)
        return {"department": department, "process": process, "owner": ""}
    if score.risk_type == "backlog_pressure" and score.entity_type == "department":
        return {"department": score.entity_id, "process": "", "owner": ""}
    if score.risk_type == "backlog_pressure" and score.entity_type == "owner":
        return {"department": "", "process": "", "owner": score.entity_id}
    return {"department": "", "process": "", "owner": ""}


def _split_entity(entity_id: str, expected_parts: int) -> list[str]:
    parts = entity_id.split("|")
    while len(parts) < expected_parts:
        parts.append("")
    return parts[:expected_parts]


def _demo_stories(score_rows: list[dict[str, Any]], evidence_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        _story(
            story_id="packaging-priority",
            label="Packaging priority",
            interpretation=(
                "Packaging shows a rising advisory signal. The demo highlights repeat deviations, "
                "owner pressure, and source-linked evidence for QA prioritization."
            ),
            human_review="QA should review packaging recurrence patterns and whether linked CAPAs remain adequate.",
            score_rows=score_rows,
            evidence_rows=evidence_rows,
            match=lambda item: item.get("department") == "Packaging" or item.get("process") == "Packaging",
        ),
        _story(
            story_id="capa-014",
            label="CAPA recurrence risk",
            interpretation=(
                "CAPA-014 is used as the synthetic story record for overdue CAPA and repeat packaging deviation signals."
            ),
            human_review="CAPA owner should review action adequacy and effectiveness check design.",
            score_rows=score_rows,
            evidence_rows=evidence_rows,
            match=lambda item: item.get("entity_id") == "CAPA-014" or "CAPA-014" in item.get("source_record_ids", []),
        ),
        _story(
            story_id="sop-023",
            label="Training drift after SOP revision",
            interpretation=(
                "SOP-023 was recently revised in the synthetic scenario. The demo highlights training drift signals "
                "where records remain incomplete."
            ),
            human_review="Training owner should review SOP-related overdue or incomplete training.",
            score_rows=score_rows,
            evidence_rows=evidence_rows,
            match=lambda item: "SOP-023" in item.get("entity_id", "") or "SOP-023" in item.get("source_record_ids", []),
        ),
        _story(
            story_id="sterile-filling",
            label="Sterile Filling high-severity watch",
            interpretation=(
                "Sterile Filling has fewer synthetic deviations, but severity can increase the advisory risk signal."
            ),
            human_review="Site Quality Lead should review severe open deviation context and related controls.",
            score_rows=score_rows,
            evidence_rows=evidence_rows,
            match=lambda item: item.get("process") == "Sterile Filling",
        ),
        _story(
            story_id="qc-oos-oot",
            label="QC Lab OOS/OOT recurrence",
            interpretation=(
                "QC Lab release testing contains repeated synthetic OOS/OOT-related deviation patterns."
            ),
            human_review="QA and QC owners should review recurrence candidates and investigation workload.",
            score_rows=score_rows,
            evidence_rows=evidence_rows,
            match=lambda item: item.get("department") == "QC Lab" or item.get("process") == "QC Release Testing",
        ),
    ]


def _story(
    *,
    story_id: str,
    label: str,
    interpretation: str,
    human_review: str,
    score_rows: list[dict[str, Any]],
    evidence_rows: list[dict[str, Any]],
    match,
) -> dict[str, Any]:
    matched_scores = [row for row in score_rows if match(row)][:6]
    matched_evidence = [row for row in evidence_rows if match(row)][:4]
    return {
        "id": story_id,
        "label": label,
        "business_interpretation": interpretation,
        "suggested_human_review_action": human_review,
        "risk_entity_ids": [row["entity_id"] for row in matched_scores],
        "evidence_card_ids": [row["card_id"] for row in matched_evidence],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build static Vercel demo data from synthetic GMP sample data.")
    parser.add_argument("--sample-data-dir", type=Path, default=SAMPLE_DATA_DIR)
    parser.add_argument("--output-path", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--as-of-date", type=date.fromisoformat, default=DEFAULT_AS_OF_DATE)
    args = parser.parse_args()
    output_path = build_vercel_demo(
        sample_data_dir=args.sample_data_dir,
        output_path=args.output_path,
        as_of_date=args.as_of_date,
    )
    print(f"Wrote static Vercel demo data to {output_path}")


if __name__ == "__main__":
    main()
