const bandOrder = ["clear", "watch", "advisory", "storm", "severe_storm"];
let forecast = null;
let activeStoryId = null;

function formatBand(value) {
  return String(value || "").replaceAll("_", " ");
}

function formatRiskType(value) {
  return String(value || "").replaceAll("_", " ");
}

function classForBand(value) {
  return `band-${value || "clear"}`;
}

function byId(id) {
  return document.getElementById(id);
}

function setText(id, value) {
  byId(id).textContent = value;
}

function renderMetrics(data) {
  const recordCount = Object.values(data.summary.source_record_count || {}).reduce((sum, value) => sum + value, 0);
  setText("modelVersion", data.meta.model_version);
  setText("generatedAt", new Date(data.meta.generated_at).toLocaleString());
  setText("asOfDate", data.meta.as_of_date);
  setText("sourceRecordCount", `${recordCount} synthetic`);
  setText("weatherIndex", `${data.summary.overall_weather_index}/100`);
  setText("readinessScore", `${data.summary.data_readiness_score}/100`);
  setText("riskScoreCount", data.summary.risk_score_count);
  setText("evidenceCardCount", data.summary.evidence_card_count);
}

function renderStoryButtons(data) {
  const container = byId("storyButtons");
  container.innerHTML = "";
  data.demo_stories.forEach((story, index) => {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = story.label;
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
  document.querySelectorAll(".story-buttons button").forEach((button) => {
    button.classList.toggle("active", button.dataset.storyId === story.id);
  });
  setText("storyTitle", story.label);
  setText("storyInterpretation", story.business_interpretation);
  setText("storyReviewAction", story.suggested_human_review_action);

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
  rows.slice(0, 10).forEach((row) => {
    const item = document.createElement("article");
    item.className = "risk-row";
    item.innerHTML = `
      <div class="risk-topline">
        <div class="risk-title">
          ${escapeHtml(formatRiskType(row.risk_type))} - ${escapeHtml(row.entity_id)}
          <small>${escapeHtml(row.department || "Cross-functional")}${row.process ? ` / ${escapeHtml(row.process)}` : ""}</small>
          <div class="risk-meta">
            <span>${escapeHtml(formatBand(row.band))}</span>
            <span>${escapeHtml(row.horizon.replaceAll("_", " "))}</span>
            ${row.owner ? `<span>${escapeHtml(row.owner)}</span>` : ""}
            <span>confidence ${Math.round(row.confidence * 100)}%</span>
          </div>
        </div>
        <span class="score-pill ${classForBand(row.band)}">${row.score}</span>
      </div>
      <ul class="drivers">${row.top_drivers.map((driver) => `<li>${escapeHtml(driver)}</li>`).join("")}</ul>
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
        <span>${row.signal_count} signals, average ${row.average_score}</span>
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
          ${escapeHtml(row.card_id)}
          <small>${escapeHtml(formatRiskType(row.risk_type))} - ${escapeHtml(row.entity_id)}</small>
        </div>
        <span class="band-pill ${classForBand(row.band)}">${formatBand(row.band)}</span>
      </div>
      <p>${escapeHtml(row.rationale)}</p>
      <strong>Human review: ${escapeHtml(row.recommended_human_review)}</strong>
      <div class="source-list">
        ${visibleSources.map((source) => `<span class="source-chip">${escapeHtml(source.domain)}: ${escapeHtml(source.record_id)}</span>`).join("")}
      </div>
    `;
    container.appendChild(item);
  });
}

function renderQualityIssues(rows) {
  const container = byId("qualityIssues");
  container.innerHTML = "";
  if (!rows.length) {
    container.innerHTML = `<div class="quality-row"><strong>No issues shown</strong><p>No top data quality issues were included in the static demo payload.</p></div>`;
    return;
  }
  rows.slice(0, 8).forEach((row) => {
    const item = document.createElement("div");
    item.className = "quality-row";
    item.innerHTML = `
      <strong>${escapeHtml(row.severity)} - ${escapeHtml(row.record_id)}</strong>
      <p>${escapeHtml(row.domain)}: ${escapeHtml(row.message)}</p>
    `;
    container.appendChild(item);
  });
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
  byId("storyTitle").textContent = "Demo data could not be loaded";
  byId("storyInterpretation").textContent = "Please rebuild the static payload with make vercel-demo.";
});
