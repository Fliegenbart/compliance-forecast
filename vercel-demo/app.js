const bandOrder = ["clear", "watch", "advisory", "storm", "severe_storm"];
let forecast = null;
let activeStoryId = null;

const storyCopy = {
  "packaging-storm": {
    label: "Packaging-Sturm",
    interpretation:
      "Packaging zeigt in den synthetischen Daten ein ansteigendes Risikosignal. Sichtbar werden Wiederholungen, Owner-Belastung und quellverknüpfte Evidenz für die QA-Priorisierung.",
    review: "QA sollte prüfen, ob die wiederkehrenden Packaging-Abweichungen und verknüpften CAPAs weiterhin angemessen adressiert sind.",
  },
  "capa-014": {
    label: "CAPA-014 im Fokus",
    interpretation:
      "CAPA-014 dient in der Demo als Beispiel für ein überfälliges CAPA-Signal mit Bezug zu wiederholten Packaging-Abweichungen.",
    review: "Der CAPA Owner sollte Maßnahmendesign, Fälligkeit und Wirksamkeitsprüfung fachlich prüfen.",
  },
  "sop-023": {
    label: "Training nach SOP-Revision",
    interpretation:
      "SOP-023 wurde im synthetischen Szenario kürzlich überarbeitet. Das Signal zeigt, wo Training noch nicht vollständig abgeschlossen ist.",
    review: "Der Training Owner sollte SOP-bezogene offene oder überfällige Trainings prüfen.",
  },
  "sterile-filling": {
    label: "Sterile Filling Watch",
    interpretation:
      "Sterile Filling hat weniger Abweichungen, aber höhere Schweregrade. Das erzeugt ein klares Signal für menschliche QA-Prüfung.",
    review: "Die Site Quality Lead sollte schwere offene Abweichungen und zugehörige Kontrollen prüfen.",
  },
  "qc-oos-oot": {
    label: "QC OOS/OOT-Wiederholung",
    interpretation:
      "QC Release Testing enthält wiederkehrende synthetische OOS/OOT-Muster. Die Demo zeigt mögliche Wiederholungskandidaten und Belastungspunkte.",
    review: "QA und QC Owner sollten Wiederholungsmuster und Untersuchungs-Backlog gemeinsam prüfen.",
  },
};

const riskTypeLabels = {
  deviation_recurrence: "Abweichungs-Wiederholungsrisiko",
  capa_failure: "CAPA-Wirksamkeitsrisiko",
  training_drift: "Training-Drift",
  audit_readiness_gap: "Audit-Readiness-Lücke",
  backlog_pressure: "Backlog-Druck",
};

const bandLabels = {
  clear: "Klar",
  watch: "Beobachten",
  advisory: "Hinweis",
  storm: "Sturm",
  severe_storm: "Schwerer Sturm",
};

const domainLabels = {
  deviations: "Abweichung",
  capas: "CAPA",
  audit_findings: "Audit Finding",
  training_records: "Training",
  change_controls: "Change Control",
  sops: "SOP",
};

function byId(id) {
  return document.getElementById(id);
}

function setText(id, value) {
  byId(id).textContent = value;
}

function classForBand(value) {
  return `band-${value || "clear"}`;
}

function formatBand(value) {
  return bandLabels[value] || String(value || "").replaceAll("_", " ");
}

function formatRiskType(value) {
  return riskTypeLabels[value] || String(value || "").replaceAll("_", " ");
}

function formatHorizon(value) {
  const normalized = String(value || "").replaceAll("_", " ");
  return normalized.replace("weeks", "Wochen").replace("week", "Woche");
}

function renderMetrics(data) {
  const recordCount = Object.values(data.summary.source_record_count || {}).reduce((sum, value) => sum + value, 0);
  setText("modelVersion", data.meta.model_version);
  setText("generatedAt", new Date(data.meta.generated_at).toLocaleString("de-DE"));
  setText("asOfDate", new Date(`${data.meta.as_of_date}T00:00:00`).toLocaleDateString("de-DE"));
  setText("sourceRecordCount", `${recordCount} synthetisch`);
  setText("weatherIndex", `${data.summary.overall_weather_index}/100`);
  setText("readinessScore", `${data.summary.data_readiness_score}/100`);
  setText("riskScoreCount", data.summary.risk_score_count);
  setText("evidenceCardCount", data.summary.evidence_card_count);
}

function renderStoryButtons(data) {
  const container = byId("storyButtons");
  container.innerHTML = "";
  data.demo_stories.forEach((story, index) => {
    const localized = storyCopy[story.id] || story;
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = localized.label;
    button.dataset.storyId = story.id;
    button.addEventListener("click", () => selectStory(story.id));
    container.appendChild(button);
    if (index === 0 && !activeStoryId) {
      activeStoryId = story.id;
    }
  });
}

function selectStory(storyId) {
  activeStoryId = storyId;
  const story = forecast.demo_stories.find((item) => item.id === storyId) || forecast.demo_stories[0];
  const localized = storyCopy[story.id] || {
    label: story.label,
    interpretation: story.business_interpretation,
    review: story.suggested_human_review_action,
  };

  document.querySelectorAll(".story-buttons button").forEach((button) => {
    button.classList.toggle("active", button.dataset.storyId === story.id);
  });

  setText("storyTitle", localized.label);
  setText("storyInterpretation", localized.interpretation);
  setText("storyReviewAction", localized.review);

  const riskIds = new Set(story.risk_entity_ids);
  const cardIds = new Set(story.evidence_card_ids);
  const risks = forecast.top_risks.filter((row) => riskIds.has(row.entity_id));
  const cards = forecast.evidence_cards.filter((row) => cardIds.has(row.card_id));
  renderTopRisks(risks.length ? risks : forecast.top_risks.slice(0, 10));
  renderEvidenceCards(cards.length ? cards : forecast.evidence_cards.slice(0, 8));
}

function renderBandCounts(data) {
  const container = byId("bandCounts");
  const max = Math.max(...Object.values(data.risk_band_counts), 1);
  container.innerHTML = "";
  bandOrder.forEach((band) => {
    const count = data.risk_band_counts[band] || 0;
    const row = document.createElement("div");
    row.className = "band-bar";
    row.innerHTML = `
      <strong>${formatBand(band)}</strong>
      <span class="bar-track"><span class="bar-fill ${classForBand(band)}" style="width:${Math.max((count / max) * 100, 4)}%"></span></span>
      <span>${count}</span>
    `;
    container.appendChild(row);
  });
}

function renderTopRisks(rows) {
  const container = byId("topRisks");
  container.innerHTML = "";
  rows.slice(0, 10).forEach((row, index) => {
    const item = document.createElement("article");
    item.className = "risk-row";
    item.innerHTML = `
      <div class="risk-rank">${String(index + 1).padStart(2, "0")}</div>
      <div class="risk-body">
        <div class="risk-topline">
          <div class="risk-title">
            ${escapeHtml(formatRiskType(row.risk_type))}
            <small>${escapeHtml(row.entity_id)} · ${escapeHtml(row.department || "Bereichsübergreifend")}${row.process ? ` · ${escapeHtml(row.process)}` : ""}</small>
          </div>
          <span class="score-pill ${classForBand(row.band)}">${row.score}</span>
        </div>
        <div class="risk-meta">
          <span>${escapeHtml(formatBand(row.band))}</span>
          <span>${escapeHtml(formatHorizon(row.horizon))}</span>
          ${row.owner ? `<span>${escapeHtml(row.owner)}</span>` : ""}
          <span>Konfidenz ${Math.round(row.confidence * 100)}%</span>
        </div>
        <ul class="drivers">${row.top_drivers.map((driver) => `<li>${escapeHtml(translateDriver(driver))}</li>`).join("")}</ul>
      </div>
    `;
    container.appendChild(item);
  });
}

function renderHeatmap(rows) {
  const container = byId("heatmap");
  container.innerHTML = "";
  rows.slice(0, 8).forEach((row) => {
    const item = document.createElement("div");
    item.className = "heat-row";
    item.innerHTML = `
      <div>
        <strong>${escapeHtml(row.department)} / ${escapeHtml(row.process)}</strong>
        <span>${row.signal_count} Signale, Durchschnitt ${row.average_score}</span>
      </div>
      <span class="score-pill ${classForBand(scoreBand(row.max_score))}">${row.max_score}</span>
    `;
    container.appendChild(item);
  });
}

function renderEvidenceCards(rows) {
  const container = byId("evidenceCards");
  container.innerHTML = "";
  rows.slice(0, 8).forEach((row) => {
    const item = document.createElement("article");
    item.className = "evidence-row";
    const visibleSources = row.source_records.slice(0, 8);
    item.innerHTML = `
      <div class="evidence-topline">
        <div class="evidence-title">
          ${escapeHtml(formatRiskType(row.risk_type))}
          <small>${escapeHtml(row.card_id)} · ${escapeHtml(row.entity_id)}</small>
        </div>
        <span class="band-pill ${classForBand(row.band)}">${formatBand(row.band)}</span>
      </div>
      <p>${escapeHtml(germanRationale(row))}</p>
      <strong>Menschliche Prüfung: ${escapeHtml(germanReview(row.risk_type))}</strong>
      <div class="source-list">
        ${visibleSources.map((source) => `<span class="source-chip">${escapeHtml(domainLabels[source.domain] || source.domain)}: ${escapeHtml(source.record_id)}</span>`).join("")}
      </div>
    `;
    container.appendChild(item);
  });
}

function renderQualityIssues(rows) {
  const container = byId("qualityIssues");
  container.innerHTML = "";
  if (!rows.length) {
    container.innerHTML = `<div class="quality-row"><strong>Keine Top-Issues</strong><p>In der statischen Demo wurden keine priorisierten Datenqualitätsprobleme angezeigt.</p></div>`;
    return;
  }
  rows.slice(0, 8).forEach((row) => {
    const item = document.createElement("div");
    item.className = "quality-row";
    item.innerHTML = `
      <strong>${escapeHtml(translateSeverity(row.severity))} · ${escapeHtml(row.record_id)}</strong>
      <p>${escapeHtml(domainLabels[row.domain] || row.domain)}: ${escapeHtml(translateQualityMessage(row.message))}</p>
    `;
    container.appendChild(item);
  });
}

function germanRationale(row) {
  const sourceIds = row.source_record_ids.slice(0, 8).join(", ");
  return `Basierend auf den verfügbaren synthetischen Daten zeigt dieses Element ein erhöhtes Risikosignal (${formatBand(row.band)}, Score ${row.score}). Die Anzeige ist für menschliche QA-Prüfung gedacht und ist keine GMP-Entscheidung. Sichtbare Treiber: ${row.top_drivers.slice(0, 2).map(translateDriver).join("; ")}. Quell-IDs: ${sourceIds}.`;
}

function germanReview(riskType) {
  if (riskType === "deviation_recurrence") return "QA sollte prüfen, ob die verknüpfte CAPA und die Wiederholungsmuster weiterhin angemessen adressiert sind.";
  if (riskType === "capa_failure") return "Der CAPA Owner sollte Maßnahme, Fälligkeit und Wirksamkeitsprüfung fachlich prüfen.";
  if (riskType === "training_drift") return "Der Training Owner sollte SOP-bezogene offene oder überfällige Trainings prüfen.";
  if (riskType === "audit_readiness_gap") return "Quality Council sollte Audit-Readiness-Signale und offene Maßnahmen prüfen.";
  if (riskType === "backlog_pressure") return "Quality Leadership sollte Backlog-Druck und Ressourcenverteilung prüfen.";
  return "QA sollte dieses Signal anhand der Quellrecords fachlich prüfen.";
}

function translateDriver(value) {
  return String(value)
    .replace("severity:", "Schweregrad:")
    .replace("age:", "Alter:")
    .replace("due-date proximity:", "Fälligkeit:")
    .replace("same process recurrence:", "Wiederholung im gleichen Prozess:")
    .replace("same equipment recurrence:", "Wiederholung am gleichen Equipment:")
    .replace("same root cause recurrence:", "Wiederholung gleicher Root-Cause-Kategorie:")
    .replace("linked CAPA overdue:", "Verknüpfte CAPA überfällig:")
    .replace("linked CAPA missing:", "Verknüpfte CAPA fehlt:")
    .replace("owner workload:", "Owner-Belastung:")
    .replace("department backlog acceleration:", "Backlog-Anstieg im Bereich:")
    .replace("overdue or due soon:", "Überfällig oder bald fällig:")
    .replace("linked deviations count:", "Anzahl verknüpfter Abweichungen:")
    .replace("Retraining Only action:", "Nur-Retraining-Maßnahme:")
    .replace("vague action description:", "Unklare Maßnahmenbeschreibung:")
    .replace("effectiveness check missing:", "Wirksamkeitsprüfung fehlt:")
    .replace("effectiveness check overdue:", "Wirksamkeitsprüfung überfällig:")
    .replace("overdue training count:", "Überfällige Trainings:")
    .replace("SOP recently revised:", "SOP kürzlich überarbeitet:")
    .replace("open deviations linked to SOP or process:", "Offene Abweichungen zu SOP oder Prozess:")
    .replace("training-impacting change controls:", "Training-relevante Change Controls:")
    .replace("open major/critical deviations:", "Offene Major/Critical-Abweichungen:")
    .replace("overdue CAPAs:", "Überfällige CAPAs:")
    .replace("open audit findings:", "Offene Audit Findings:")
    .replace("validation-impacting change controls still open:", "Validierungsrelevante Change Controls offen:")
    .replace("open deviations:", "Offene Abweichungen:")
    .replace("open CAPAs:", "Offene CAPAs:")
    .replace("overdue items:", "Überfällige Elemente:")
    .replace("average age:", "Durchschnittsalter:")
    .replace("days open", "Tage offen")
    .replace("due within", "fällig in")
    .replace("overdue by", "überfällig um")
    .replace("days", "Tage")
    .replace("deviations:", "Abweichungen:");
}

function translateQualityMessage(value) {
  return String(value)
    .replace("Record is overdue as of", "Record ist überfällig zum")
    .replace("Duplicate ID", "Doppelte ID")
    .replace("found in", "gefunden in")
    .replace("status", "Status")
    .replace("is not in the expected set for", "ist nicht im erwarteten Wertebereich für")
    .replace("unknown SOP reference", "unbekannte SOP-Referenz")
    .replace("references missing deviation", "referenziert eine fehlende Abweichung")
    .replace("is missing", "fehlt");
}

function translateSeverity(value) {
  const labels = {
    critical: "kritisch",
    high: "hoch",
    medium: "mittel",
    low: "niedrig",
    info: "Info",
  };
  return labels[value] || value;
}

function scoreBand(score) {
  if (score >= 85) return "severe_storm";
  if (score >= 70) return "storm";
  if (score >= 50) return "advisory";
  if (score >= 30) return "watch";
  return "clear";
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

async function loadForecast() {
  const response = await fetch("./data/forecast.json");
  forecast = await response.json();
  renderMetrics(forecast);
  renderStoryButtons(forecast);
  renderBandCounts(forecast);
  renderHeatmap(forecast.heatmap);
  renderQualityIssues(forecast.data_quality_issues);
  selectStory(activeStoryId || forecast.demo_stories[0].id);
}

loadForecast().catch((error) => {
  console.error(error);
  byId("storyTitle").textContent = "Demo-Daten konnten nicht geladen werden";
  byId("storyInterpretation").textContent = "Bitte die statische Demo mit make vercel-demo neu erzeugen.";
});
