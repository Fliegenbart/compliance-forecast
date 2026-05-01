# AGENTS.md

Strict engineering guidance for all future Codex tasks in this repository.

This repository contains a regulated-life-science consulting prototype for GMP advisory decision support. Treat the regulatory safety boundary as a core product requirement, not as wording that can be refactored away.

## Core Safety Boundary

- This application is advisory decision support only.
- The application must never approve, reject, close, certify, release, qualify, or disposition anything.
- Human QA review is mandatory for all recommendations, risk outputs, summaries, and next-step prompts.
- Do not add autonomous GMP decision-making.
- Do not create workflows that imply system authority over regulated quality decisions.
- Every user-facing recommendation must be phrased as a prompt for qualified human review.

## Explainability Requirements

- All risk scores must be explainable through visible drivers.
- Every score must expose the records, factors, weights, thresholds, or rule outputs that contributed to it.
- All evidence cards must include source record IDs.
- Evidence cards must never make unsupported claims.
- If a record contributes to a score or evidence card, the user must be able to trace that output back to the source record ID.
- Prefer transparent rule-based scoring for the MVP.
- Do not use black-box ML unless there is a clear baseline, documented rationale, validation plan, and user-visible explainability.

## Data Protection And Local-Only Operation

- Do not add external API calls, cloud storage, telemetry, analytics beacons, background uploads, or data exfiltration.
- Do not store real personal data in the repository.
- Do not store real client GMP records in the repository.
- All sample data must be synthetic.
- Synthetic data must be clearly labeled as synthetic in file names, documentation, and user-facing app context where practical.
- Keep the dashboard local and read-only by default.
- Do not introduce write-back behavior to source QMS records unless the user explicitly requests a separate scoped design and safety review.

## LLM Functionality

- Any LLM functionality must be optional.
- Any LLM functionality must be disabled by default.
- Any LLM functionality must be source-grounded.
- Any LLM-generated text must be clearly marked as draft.
- LLM outputs must not approve, reject, close, certify, release, qualify, disposition, or finalize any GMP item.
- LLM outputs must cite or link the source record IDs used as grounding.
- Do not send source data to an external LLM or API unless the user explicitly requests it and the data-sharing boundary is documented.

## Testing Requirements

- Maintain tests for scoring.
- Maintain tests for evidence generation.
- Maintain tests for data loading.
- Maintain tests for audit logging.
- Add or update tests when changing risk-score logic, evidence-card logic, schema validation, sample-data assumptions, or dashboard behavior that changes regulated meaning.
- Tests should verify advisory wording, source record traceability, and read-only safety boundaries when relevant.

## GMP Terminology

Keep terminology aligned with GMP and quality-system usage. Prefer these terms where applicable:

- deviations
- CAPAs
- change controls
- audit findings
- training
- SOPs
- validation
- supplier quality
- batch review

Do not replace regulated terminology with vague product language if it weakens the meaning of the workflow.

## Forbidden Features

The following features must not be implemented:

- automated CAPA approval
- automated deviation closure
- batch release recommendations
- regulatory reportability decisions
- final audit responses
- supplier qualification decisions
- validation approval decisions
- final root cause approval
