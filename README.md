# GMP Risiko-Cockpit

Client-facing technical demo for a local, read-only GMP quality-risk prioritization dashboard.

Backlog age is not the same as GMP risk. This prototype helps QA teams identify which quality issues deserve human attention first.

## 1. What This Prototype Is

GMP Risiko-Cockpit is a Streamlit-based prototype that turns local QMS-style CSV data into advisory quality-risk signals.

It demonstrates how deviations, CAPAs, audit findings, training records, SOPs, and change controls can be reviewed together in a transparent dashboard. The goal is to support QA prioritization discussions, not to automate regulated decisions.

The demo is built for Beispiel GmbH as a consulting prototype. The repository does not ship stored example records; synthetic data can be generated locally when needed.

## 2. What This Prototype Is Not

This prototype is not a validated GMP system. It is not an electronic Quality Management System, not a batch release tool, and not a replacement for QA judgment.

It must not be used to:

- approve, reject, close, certify, release, qualify, accept, or disposition regulated records
- approve CAPAs or close deviations
- make batch release recommendations
- make regulatory reportability decisions
- provide final audit responses
- make supplier qualification decisions
- approve validation outcomes
- confirm final root cause

## Regulatory Safety Boundary

- Advisory only: outputs are quality-risk signals for review, not GMP decisions.
- Read-only MVP: the app reads local CSV files and does not write back to a QMS.
- Human QA review required: every recommendation is framed for qualified human review.
- No autonomous GMP decisions: the app does not approve, reject, close, release, certify, qualify, or disposition anything.
- Source-linked evidence: evidence cards link advisory signals to source record IDs.
- Model versioning and audit log: risk runs record model version, scoring config hash, source file hashes, selected filters, and generated output counts.

## 3. Target Users

The prototype is intended for technical and business demo discussions with:

- QA leadership
- Quality Systems teams
- CAPA owners
- Deviation investigators
- Training owners
- Audit readiness teams
- Validation and Engineering quality stakeholders
- Life-science consulting teams evaluating quality-risk analytics concepts

## 4. Supported Data Domains

The current MVP supports these synthetic QMS-style domains:

- Deviations
- CAPAs
- Audit findings
- Training records
- Change controls
- SOP metadata

No real client data is included. If data is needed for a demo run, generate synthetic records locally with the sample-data command below.

## 5. Core Workflow

1. Load local CSV data from `data/sample/` after generating or adding approved synthetic/anonymized files.
2. Validate data structure and references.
3. Calculate transparent advisory risk scores.
4. Generate source-linked evidence cards for medium and high signals.
5. Display risk views across dashboard tabs.
6. Show a weekly priority briefing and guided review context.
7. Create a local risk run log for traceability.
8. Export a 30-day Markdown diagnostic report for consulting review.

The dashboard is designed for review conversations. It helps teams ask better prioritization questions, such as which overdue item has the strongest recurrence pattern or which SOP change has the clearest training drift signal.

## 6. Risk Scoring Model

The MVP uses transparent rule-based scoring, not black-box machine learning.

Scores range from 0 to 100 and map to advisory risk bands:

- Niedrig
- Beobachten
- Erhöht
- Hoch
- Kritisch

The active scoring rules are stored in:

```text
config/scoring_rules_v0_1.yaml
```

The scoring engine covers:

- Deviation recurrence risk
- CAPA failure risk
- Training drift risk
- Audit readiness gap risk
- Backlog pressure risk

Each score includes visible drivers, such as severity, overdue status, recurrence, linked CAPA status, owner workload, training incompletion, and open validation-impacting changes. Confidence is reduced when important fields or evidence are missing.

## 7. Evidence Cards

Evidence cards explain why a score deserves human QA review.

Each card includes:

- risk type, entity, score, band, and horizon
- top scoring drivers
- source record IDs
- plain-English rationale
- recommended human review action
- limitations

Evidence card wording is intentionally cautious. It uses language such as "based on available data", "elevated risk signal", and "recommended for QA review". It does not claim regulatory non-compliance or determine root cause.

## 8. Dashboard Tabs

The Streamlit dashboard includes:

- Executive Priority Map: overall index, top risks, band counts, heatmap, weekly briefing, and Demo Story mode
- Deviation & CAPA Priority View: risky deviations, risky CAPAs, recurrence clusters, and owner workload
- Audit Readiness: department/process gap scores, open findings, CAPA links, and SOP/training indicators
- Training Drift: overdue training, recent SOP changes, and training drift scores
- Evidence Cards: searchable source-linked evidence cards
- Data Quality: readiness score, issue list, missing fields, broken references, and duplicate IDs
- Backtesting: historical risk-ranking utility comparison
- Governance: intended use, non-intended use, latest risk run, config metadata, and source hashes

The sidebar also includes an `Export Diagnostic Report` button. It writes a local Markdown report to:

```text
output/diagnostic_report.md
```

The report summarizes the current prioritization, evidence cards, data quality assessment, historical backtest, audit log metadata, and recommended 90-day pilot scope. It remains advisory only and is not a GMP decision.

Optional Vercel static preview:

```bash
make vercel-demo
vercel deploy vercel-demo -y --target=preview
```

The Vercel preview is a lightweight static demo generated from the same synthetic data and transparent scores. It is not the full Streamlit dashboard and remains advisory only.

Screenshot placeholders:

- [Screenshot placeholder: Executive Priority Map]
- [Screenshot placeholder: Demo Story panel]
- [Screenshot placeholder: Evidence Cards tab]
- [Screenshot placeholder: Governance and audit trail]

## 9. Backtesting Method

The backtesting module evaluates historical risk-ranking utility.

For selected historical historical review dates, the app:

1. Uses only records available up to the historical review date.
2. Calculates advisory risk scores.
3. Looks forward over the selected horizon.
4. Checks whether future synthetic quality events appeared in top-ranked areas or entities.
5. Compares the rule-based ranking against a simple baseline that sorts by oldest open backlog item.

Metrics include:

- precision at 10
- precision at 20
- recall for future major events
- top-decile lift
- lead time days where possible
- comparison versus backlog-age sorting

The backtest is not proof of prevention and not a guarantee of future performance. It is a way to discuss whether the ranking approach may be more useful than backlog age alone.

## 10. Governance And Audit Trail

Every risk run can produce a local audit log with:

- risk run ID
- generated timestamp
- as-of date
- model version
- scoring config hash
- source file names and hashes
- record counts by domain
- user-selected filters
- number of generated risk scores
- number of generated evidence cards

These logs support transparency for demo and review purposes. They do not create GMP records and do not write back to any source system.

Optional LLM functionality is disabled by default. If future LLM support is enabled with `GMP_RISK_COCKPIT_ENABLE_LLM=true`, outputs must remain source-grounded, marked as draft, and for human QA review only. Do not send real client data, personal data, batch records, deviation narratives, CAPA records, or other real GMP records to an LLM through this prototype.

## 11. How To Run Locally

Use Python 3.11 or newer.

```bash
cd gmp-compliance-weather-forecast
make install
make sample-data
make run
```

If Plotly charts are not needed:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

Run tests with:

```bash
make test
```

## 12. How To Generate Synthetic Data

The repository intentionally does not include stored example CSV records. Generate deterministic synthetic data locally into:

```text
data/sample/
```

Files generated for the main dashboard when `make sample-data` is run:

- `deviations.csv`
- `capas.csv`
- `audit_findings.csv`
- `training_records.csv`
- `change_controls.csv`
- `sops.csv`
- `demo_story.md`

Regenerate the default sample data:

```bash
make sample-data
```

Use a different deterministic seed or output directory:

```bash
python scripts/generate_sample_data.py --seed 12345 --output-dir data/sample
```

Generated sample data is fictional. It must not be replaced with real client GMP records without a separate privacy, validation, security, and governance review.

## 13. Known Limitations

- Not validated for regulated use.
- Uses synthetic data only.
- Rule weights are illustrative and require SME review before any pilot.
- Data quality checks are basic and do not replace source-system controls.
- Backtesting is retrospective and synthetic; it does not prove real-world prevention.
- No external integrations are enabled by default.
- No automated write-back to QMS, LMS, ERP, MES, LIMS, document management, or validation systems.
- LLM adapter is optional, disabled by default, and currently local-template based unless explicitly enabled.
- Charts and dashboard interactions are suitable for demo use, not production deployment.

## 14. Roadmap Toward A Validated Pilot

Potential next steps toward a controlled pilot:

1. Confirm intended use, non-intended use, and governance model with QA stakeholders.
2. Map real source-system fields to the advisory schema without storing real records in the repository.
3. Define data privacy, security, access control, and retention requirements.
4. Review scoring drivers and weights with GMP SMEs.
5. Add controlled configuration management for scoring rules.
6. Expand data quality checks for client-specific source-system rules.
7. Run historical backtesting on approved anonymized or governed data extracts.
8. Define validation strategy, test evidence, SOP impact, and operational controls.
9. Add role-based review workflows outside this read-only MVP if justified.
10. Decide whether optional LLM draft support is acceptable under client governance.
