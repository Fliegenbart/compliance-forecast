"""Optional LLM adapter for source-grounded draft text.

The default mode is fully local and deterministic. External LLM calls are not
performed unless ``GMP_WEATHER_ENABLE_LLM=true`` is set, and this module still
requires source-grounded context before draft text can be produced.
"""

from __future__ import annotations

import os
import re
from collections.abc import Mapping, Sequence
from typing import Any


LLM_ENABLE_ENV_VAR = "GMP_WEATHER_ENABLE_LLM"
FORBIDDEN_DECISION_PHRASES = (
    "approved",
    "closed by ai",
    "release recommended",
    "capa accepted",
    "root cause confirmed",
)
RECORD_ID_PATTERN = re.compile(
    r"\b(?:DEV|CAPA|FIND|TRN|SOP|CHG|EQ|SUP|BATCH)-[A-Z0-9-]+\b",
    flags=re.IGNORECASE,
)


def is_llm_enabled() -> bool:
    """Return whether optional LLM generation is explicitly enabled."""

    return os.getenv(LLM_ENABLE_ENV_VAR, "").strip().lower() == "true"


def generate_draft_evidence_rationale(context: Mapping[str, Any]) -> str:
    """Generate a source-grounded draft rationale for an evidence card.

    In the default disabled mode this returns deterministic template text. If
    LLM mode is enabled, the same source-grounding checks are applied before any
    future provider integration can be used.
    """

    normalized = _normalize_context(context)
    if is_llm_enabled():
        _validate_source_grounded_context(normalized)

    source_ids = normalized["source_record_ids"]
    allowed_ids = set(source_ids)
    allowed_ids.add(normalized["entity_id"])
    drivers = [
        _sanitize_record_references(driver, allowed_ids)
        for driver in _string_sequence(normalized["top_drivers"])[:3]
    ]
    driver_text = "; ".join(drivers) if drivers else "available advisory scoring drivers"
    source_text = _format_source_ids(source_ids)

    text = (
        "Draft evidence rationale for human QA review: based on available source-grounded data, "
        f"{normalized['risk_type']} for {normalized['entity_type']} {normalized['entity_id']} shows a "
        f"{normalized['band']} advisory signal with score {normalized['score']}. "
        f"Visible drivers: {driver_text}. Source record IDs: {source_text}. "
        "This is not a final GMP decision."
    )
    return _ensure_safe_draft_text(text)


def generate_draft_weekly_briefing(context: Mapping[str, Any]) -> str:
    """Generate a source-grounded draft weekly briefing.

    The disabled default uses a deterministic local template and never calls a
    network service. Enabled mode is reserved for future optional LLM providers
    and requires source-grounded context.
    """

    normalized = _normalize_context(context)
    if is_llm_enabled():
        _validate_source_grounded_context(normalized)

    source_ids = normalized["source_record_ids"]
    risk_summary = _risk_summary_text(context.get("risk_summary"))
    source_text = _format_source_ids(source_ids)

    text = (
        "Draft weekly forecast briefing for human QA review: based on available source-grounded data, "
        f"the current advisory summary highlights {risk_summary}. "
        f"Source record IDs: {source_text}. "
        "These are advisory risk-ranking signals only and not a final GMP decision."
    )
    return _ensure_safe_draft_text(text)


def _normalize_context(context: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(context, Mapping):
        raise TypeError("LLM adapter context must be a mapping")

    source_record_ids = _extract_source_record_ids(context.get("source_records"))
    return {
        "risk_type": _clean_label(context.get("risk_type"), "advisory risk signal"),
        "entity_type": _clean_label(context.get("entity_type"), "entity"),
        "entity_id": _clean_label(context.get("entity_id"), "source-grounded entity"),
        "band": _clean_label(context.get("band"), "unbanded"),
        "score": _clean_score(context.get("score")),
        "top_drivers": context.get("top_drivers", []),
        "source_record_ids": source_record_ids,
    }


def _extract_source_record_ids(source_records: Any) -> list[str]:
    if source_records is None:
        return []
    if isinstance(source_records, str):
        return [_clean_label(source_records, "")] if source_records.strip() else []
    if not isinstance(source_records, Sequence):
        return []

    source_ids: list[str] = []
    for record in source_records:
        record_id = ""
        if isinstance(record, Mapping):
            record_id = _clean_label(record.get("record_id"), "")
        elif isinstance(record, str):
            record_id = _clean_label(record, "")
        else:
            record_id = _clean_label(getattr(record, "record_id", ""), "")
        if record_id and record_id not in source_ids:
            source_ids.append(record_id)
    return source_ids


def _validate_source_grounded_context(normalized: Mapping[str, Any]) -> None:
    if not normalized.get("source_record_ids"):
        raise ValueError("LLM mode requires source_records with explicit record_id values")


def _risk_summary_text(risk_summary: Any) -> str:
    if not isinstance(risk_summary, Sequence) or isinstance(risk_summary, (str, bytes)):
        return "the advisory signals present in the supplied context"

    items: list[str] = []
    for item in risk_summary[:5]:
        if not isinstance(item, Mapping):
            continue
        risk_type = _clean_label(item.get("risk_type"), "advisory signal")
        band = _clean_label(item.get("band"), "unbanded")
        items.append(f"{risk_type} ({band})")
    if not items:
        return "the advisory signals present in the supplied context"
    return ", ".join(items)


def _string_sequence(values: Any) -> list[str]:
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
        return []
    cleaned: list[str] = []
    for value in values:
        text = _clean_label(value, "")
        if text:
            cleaned.append(text)
    return cleaned


def _sanitize_record_references(text: str, allowed_ids: set[str]) -> str:
    def replace(match: re.Match[str]) -> str:
        value = match.group(0)
        return value if value in allowed_ids else "[source record not listed]"

    return RECORD_ID_PATTERN.sub(replace, text)


def _ensure_safe_draft_text(text: str) -> str:
    normalized = text.lower()
    if "draft" not in normalized:
        text = f"Draft: {text}"
        normalized = text.lower()
    if "for human qa review" not in normalized:
        text = f"{text} For human QA review."
        normalized = text.lower()
    if "final gmp decision" not in normalized:
        text = f"{text} This is not a final GMP decision."
        normalized = text.lower()
    for phrase in FORBIDDEN_DECISION_PHRASES:
        if phrase in normalized:
            raise ValueError(f"LLM adapter text contains forbidden decision phrase: {phrase}")
    return text


def _format_source_ids(source_ids: list[str]) -> str:
    return ", ".join(source_ids) if source_ids else "no source record IDs supplied"


def _clean_score(value: Any) -> str:
    if isinstance(value, (float, int)):
        return f"{float(value):.1f}"
    return "not scored"


def _clean_label(value: Any, default: str) -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text if text else default
