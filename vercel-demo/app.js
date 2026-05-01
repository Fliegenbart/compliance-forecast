const bandOrder = ["clear", "watch", "advisory", "storm", "severe_storm"];
let forecast = null;
let activeStoryId = null;
let activeForecastId = "today";
let forecastHorizons = [];

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
  const generatedAt = new Date(data.meta.generated_at).toLocaleString("de-DE", {
    day: "numeric",
    month: "numeric",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
  const asOfDate = new Date(`${data.meta.as_of_date}T00:00:00`).toLocaleDateString("de-DE");
  const briefing = buildWeatherBriefing(data);

  setText("modelVersion", data.meta.model_version);
  setText("generatedAt", generatedAt);
  setText("asOfDate", asOfDate);
  setText("sourceRecordCount", `${recordCount} synthetisch`);
  setText("briefingEyebrow", `HEUTE · ${asOfDate}`);
  setText("weatherStatus", briefing.status);
  setText("weatherBriefing", briefing.prose);
  setText("weatherWatchline", briefing.watchline);
  setText(
    "briefingFootnote",
    `Stand ${generatedAt} · ${recordCount} synthetische Records · Datenreife ${data.summary.data_readiness_score}%`,
  );
  byId("weatherGlyph").innerHTML = weatherGlyph(briefing.state);
}

function buildWeatherBriefing(data) {
  const topRisk = data.top_risks[0] || {};
  const topBand = topRisk.band || "clear";
  const state = weatherStateFromBand(topBand);
  const topArea = topRisk.process || topRisk.department || "dem Qualitätssystem";
  const topDepartment = topRisk.department || "bereichsübergreifend";
  const severeCount = data.risk_band_counts.severe_storm || 0;
  const stormCount = data.risk_band_counts.storm || 0;
  const watchCount = data.risk_band_counts.watch || 0;
  const advisoryCount = data.risk_band_counts.advisory || 0;
  const observedAreas = new Set(
    data.heatmap
      .filter((row) => row.max_score >= 50)
      .map((row) => `${row.department}/${row.process}`),
  );
  const furtherAreas = Math.max(observedAreas.size - 1, 0);
  const recurrence = data.top_risks.filter((row) => row.risk_type === "deviation_recurrence").length;
  const capa = data.top_risks.find((row) => row.risk_type === "capa_failure");
  const training = data.top_risks.find((row) => row.risk_type === "training_drift");
  const capaPhrase = capa ? `eine CAPA unter Druck (${capa.entity_id})` : "CAPA-Signale ohne dominierenden Einzelpunkt";
  const trainingPhrase = training ? `Training-Drift um ${training.entity_id.split("|").pop()}` : "keine führende Training-Drift im Top-Signal";

  const templates = {
    clear: {
      status: "Klare Lage",
      prose: `Die regelbasierte Sicht zeigt heute keine dominierende Sturmfront. ${topDepartment} bleibt sichtbar, aber ohne akuten Spitzenwert. Backlog und Evidenz sollten weiter im QA-Rhythmus geprüft werden.`,
    },
    watch: {
      status: `Beobachten in ${topArea}`,
      prose: `Die Lage ist noch kontrolliert, aber nicht leer. ${watchCount} Beobachtungssignale deuten auf Themen hin, die im nächsten QA-Termin bewusst priorisiert werden sollten.`,
    },
    building: {
      status: `Aufziehend über ${topArea}`,
      prose: `${recurrence} Wiederholungs-Signale, ${capaPhrase} und ${trainingPhrase} verdichten sich zu einer aufziehenden Wetterlage. Das ist kein GMP-Befund, sondern ein Hinweis für fokussierte QA-Prüfung.`,
    },
    storm: {
      status: `Sturm über ${topArea}`,
      prose: `${stormCount} Sturm-Signale und ${recurrence} Wiederholungs-Signale zeigen eine klare Verdichtung. ${capaPhrase}; ${trainingPhrase}. QA sollte die Quellenlage priorisiert ansehen.`,
    },
    "severe-storm": {
      status: `Schwerer Sturm über ${topArea}`,
      prose: `${severeCount} schwere Sturm-Signale, ${recurrence} Wiederholungs-Signale und ${capaPhrase} prägen die heutige Lage. Besonders ${topDepartment} sollte anhand der Quell-IDs menschlich geprüft werden.`,
    },
  };

  return {
    state,
    status: templates[state].status,
    prose: templates[state].prose,
    watchline: `${furtherAreas} weitere Bereiche unter Beobachtung`,
  };
}

function weatherStateFromBand(band) {
  if (band === "severe_storm") return "severe-storm";
  if (band === "storm") return "storm";
  if (band === "advisory") return "building";
  if (band === "watch") return "watch";
  return "clear";
}

function weatherGlyph(state) {
  const glyphs = {
    clear: `<svg viewBox="0 0 80 80" role="img" aria-label="Klar"><circle cx="40" cy="40" r="15"/><path d="M40 8v10M40 62v10M8 40h10M62 40h10M17.4 17.4l7.1 7.1M55.5 55.5l7.1 7.1M62.6 17.4l-7.1 7.1M24.5 55.5l-7.1 7.1"/></svg>`,
    watch: `<svg viewBox="0 0 80 80" role="img" aria-label="Beobachten"><path d="M23 53h32a13 13 0 0 0 0-26 18 18 0 0 0-34-5 15 15 0 0 0 2 31Z"/><path d="M24 64h34"/></svg>`,
    building: `<svg viewBox="0 0 80 80" role="img" aria-label="Aufziehend"><path d="M20 52h35a14 14 0 0 0 1-28 19 19 0 0 0-36-4 16 16 0 0 0 0 32Z"/><path d="M22 64h36M30 70h20"/></svg>`,
    storm: `<svg viewBox="0 0 80 80" role="img" aria-label="Sturm"><path d="M20 48h35a13 13 0 0 0 0-26 19 19 0 0 0-35-4 15 15 0 0 0 0 30Z"/><path d="m40 48-8 15h11l-6 12 18-20H44l7-7"/></svg>`,
    "severe-storm": `<svg viewBox="0 0 80 80" role="img" aria-label="Schwerer Sturm"><path d="M19 46h36a14 14 0 0 0 0-28 20 20 0 0 0-36-4 16 16 0 0 0 0 32Z"/><path d="m40 46-9 17h12l-6 13 20-22H45l8-8"/><path d="M24 63h-8M62 64h-8"/></svg>`,
  };
  return glyphs[state] || glyphs.clear;
}

function buildForecastStrip(data) {
  const severe = data.top_risks.filter((row) => row.band === "severe_storm");
  const storm = data.top_risks.filter((row) => row.band === "storm" || row.band === "severe_storm");
  const recurrence = data.top_risks.filter((row) => row.risk_type === "deviation_recurrence");
  const accelerated = recurrence.filter((row) =>
    row.top_drivers.some((driver) =>
      driver.includes("department backlog acceleration") ||
      driver.includes("same process recurrence") ||
      driver.includes("same equipment recurrence"),
    ),
  );
  const capas = data.top_risks.filter((row) => row.risk_type === "capa_failure");
  const training = data.top_risks.filter((row) => row.risk_type === "training_drift");
  const todayTop = severe[0] || storm[0] || data.top_risks[0] || {};
  const plusOneTop = accelerated[0] || recurrence[0] || todayTop;
  const plusThreeTop = capas.find((row) => row.entity_id === "CAPA-014") || capas[0] || todayTop;
  const plusSevenTop = training.find((row) => String(row.entity_id).includes("SOP-023")) || training[0] || todayTop;
  const observed = new Set(data.heatmap.filter((row) => row.max_score >= 50).map((row) => row.department));

  return [
    {
      id: "today",
      label: "Heute",
      state: weatherStateFromBand(todayTop.band || "severe_storm"),
      status: formatBand(todayTop.band || "severe_storm"),
      area: todayTop.process || todayTop.department || "Packaging",
      trigger: `${Math.max(severe.length, 1)} Sturm-Signale`,
      filter: (row) => row.band === "severe_storm",
    },
    {
      id: "plus1",
      label: "+1 Tag",
      state: "storm",
      status: "Sturm",
      area: plusOneTop.process || plusOneTop.department || "Packaging",
      trigger: `+${Math.min(Math.max(accelerated.length, 2), 9)} seit Mo`,
      filter: (row) =>
        row.risk_type === "deviation_recurrence" &&
        row.top_drivers.some((driver) => driver.includes("recurrence") || driver.includes("acceleration")),
    },
    {
      id: "plus3",
      label: "+3 Tage",
      state: "building",
      status: "Aufziehend",
      area: plusThreeTop.entity_id ? `${plusThreeTop.entity_id} Frist` : "CAPA-Frist",
      trigger: plusThreeTop.entity_id === "CAPA-014" ? "Packaging-CAPA" : `${Math.max(capas.length, 1)} CAPA-Fristen`,
      filter: (row) => row.risk_type === "capa_failure",
    },
    {
      id: "plus7",
      label: "+7 Tage",
      state: training.length ? "watch" : "building",
      status: "Wetterumschwung",
      area: plusSevenTop.entity_id && String(plusSevenTop.entity_id).includes("SOP-023") ? "SOP-023 Revision" : plusSevenTop.process || "Training",
      trigger: training.length ? `Training-Coverage ${Math.max(38, 100 - training.length * 7)}%` : `${observed.size} Bereiche`,
      filter: (row) => row.risk_type === "training_drift",
    },
  ];
}

function renderForecastStrip(data) {
  forecastHorizons = buildForecastStrip(data);
  const container = byId("forecastStrip");
  container.innerHTML = "";
  forecastHorizons.forEach((item) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "forecast-cell";
    button.dataset.forecastId = item.id;
    button.setAttribute("aria-pressed", String(item.id === activeForecastId));
    button.innerHTML = `
      <span class="forecast-label">${escapeHtml(item.label)}</span>
      <span class="forecast-glyph">${weatherGlyph(item.state)}</span>
      <strong>${escapeHtml(item.status)}</strong>
      <span>${escapeHtml(item.area)}</span>
      <em>${escapeHtml(item.trigger)}</em>
    `;
    button.addEventListener("click", () => selectForecast(item.id));
    container.appendChild(button);
  });
  updateForecastActiveState();
}

function selectForecast(forecastId) {
  activeForecastId = forecastId;
  updateForecastActiveState();
  renderPriorityList();
}

function updateForecastActiveState() {
  document.querySelectorAll(".forecast-cell").forEach((button) => {
    const isActive = button.dataset.forecastId === activeForecastId;
    button.classList.toggle("active", isActive);
    button.setAttribute("aria-pressed", String(isActive));
  });
}

function renderPriorityList() {
  const active = forecastHorizons.find((item) => item.id === activeForecastId) || forecastHorizons[0];
  const story = forecast.demo_stories.find((item) => item.id === activeStoryId) || forecast.demo_stories[0];
  const storyIds = new Set(story?.risk_entity_ids || []);
  const horizonRows = active ? forecast.top_risks.filter(active.filter) : [];
  const storyRows = forecast.top_risks.filter((row) => storyIds.has(row.entity_id));
  const rows = horizonRows.length ? horizonRows : storyRows.length ? storyRows : forecast.top_risks;
  setText("priorityScope", active ? active.label : "Heute");
  renderTopRisks(rows);
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
  const cards = forecast.evidence_cards.filter((row) => cardIds.has(row.card_id));
  renderPriorityList();
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
  generateMockSignals(rows)
    .sort((left, right) => right.escalationVelocity - left.escalationVelocity)
    .slice(0, 6)
    .forEach((signal, index) => {
    const item = document.createElement("article");
    item.className = `risk-row trend-${signal.pattern}`;
    item.innerHTML = `
      <div class="risk-rank">${String(index + 1).padStart(2, "0")}</div>
      <div class="risk-body">
        <div class="risk-card-head">
          <div class="trend-indicator">
            <span class="trend-arrow" aria-hidden="true">${escapeHtml(signal.trendIcon)}</span>
            <strong>${escapeHtml(signal.trendLabel)}</strong>
          </div>
          ${sparklineSvg(signal.sparkline)}
        </div>

        <div class="risk-title-block">
          <h4>${escapeHtml(signal.headline)}</h4>
          <p>${escapeHtml(signal.entity_id)} · ${escapeHtml(signal.department || "Bereichsübergreifend")}${signal.process ? ` · ${escapeHtml(signal.process)}` : ""}</p>
        </div>

        <div class="why-now">
          <span>Warum jetzt?</span>
          <ul>${signal.whyNow.map((reason) => `<li>${escapeHtml(reason)}</li>`).join("")}</ul>
        </div>

        <div class="risk-actions" aria-label="Beratende Aktionen">
          <button type="button">An QA übergeben</button>
          <button type="button">Heute beobachten</button>
          <button type="button">Bekannt markieren</button>
        </div>

        <details class="risk-details">
          <summary>Regel-Treiber anzeigen</summary>
          <div class="risk-meta">
            <span>${escapeHtml(formatBand(signal.band))}</span>
            <span>${escapeHtml(formatHorizon(signal.horizon))}</span>
            ${signal.owner ? `<span>${escapeHtml(signal.owner)}</span>` : ""}
            <span>Konfidenz ${Math.round(signal.confidence * 100)}%</span>
            <span>Score ${signal.score}</span>
          </div>
          <ul class="drivers">${signal.top_drivers.map((driver) => `<li>${escapeHtml(translateDriver(driver))}</li>`).join("")}</ul>
        </details>
      </div>
    `;
    container.appendChild(item);
  });
}

function generateMockSignals(rows) {
  const patterns = [
    {
      pattern: "strong-escalating",
      trendIcon: "↗",
      trendLabel: "Eskaliert seit 3 Tagen",
      sparkline: [2, 3, 3, 4, 6, 7, 9, 12, 15, 19, 25, 34, 47, 64],
      escalationVelocity: 62,
      why: (row) => [
        `${row.process || row.department || "Bereich"} zieht innerhalb von 72 Stunden deutlich an`,
        "2 ähnliche Abweichungen seit Montag",
      ],
    },
    {
      pattern: "stable-high",
      trendIcon: "→",
      trendLabel: "Stabil hoch",
      sparkline: [52, 54, 53, 55, 54, 56, 55, 55, 56, 54, 55, 56, 55, 56],
      escalationVelocity: 10,
      why: (row) => [
        `${formatBand(row.band)} bleibt ohne Entlastung sichtbar`,
        `${row.owner || "Owner"} hält mehrere offene Signale`,
      ],
    },
    {
      pattern: "first-visible",
      trendIcon: "↑",
      trendLabel: "Erstmals sichtbar",
      sparkline: [0, 0, 0, 0, 0, 1, 1, 2, 4, 7, 12, 20, 31, 45],
      escalationVelocity: 45,
      why: (row) => [
        "Neues Cluster überschreitet heute die Beobachtungsschwelle",
        `${row.entity_id} taucht erstmals in der Priorisierung auf`,
      ],
    },
    {
      pattern: "softening",
      trendIcon: "↘",
      trendLabel: "Leicht nachlassend",
      sparkline: [68, 66, 64, 63, 61, 59, 58, 55, 52, 50, 48, 46, 45, 43],
      escalationVelocity: -25,
      why: () => [
        "Signal bleibt relevant, verliert aber an Dichte",
        "Heute beobachten statt sofort eskalieren",
      ],
    },
    {
      pattern: "oscillating",
      trendIcon: "↕",
      trendLabel: "Oszillierend",
      sparkline: [20, 35, 22, 41, 28, 45, 31, 48, 34, 44, 36, 52, 39, 55],
      escalationVelocity: 18,
      why: (row) => [
        `${row.department || "Bereich"} zeigt wiederkehrende Ausschläge`,
        "Dichte schwankt, verschwindet aber nicht",
      ],
    },
    {
      pattern: "new-list",
      trendIcon: "●",
      trendLabel: "Neu auf der Liste",
      sparkline: [0, 0, 0, 0, 0, 0, 1, 1, 2, 3, 5, 9, 15, 22],
      escalationVelocity: 32,
      why: (row) => [
        `${formatRiskType(row.risk_type)} wurde neu priorisiert`,
        "Frühes Signal mit noch begrenzter Evidenz",
      ],
    },
  ];

  return rows.map((row, index) => {
    const template = patterns[index % patterns.length];
    return {
      ...row,
      pattern: template.pattern,
      trendIcon: template.trendIcon,
      trendLabel: template.trendLabel,
      sparkline: template.sparkline,
      escalationVelocity: template.escalationVelocity,
      whyNow: template.why(row),
      headline: `${formatRiskType(row.risk_type)} in ${row.process || row.department || row.entity_id}`,
    };
  });
}

function sparklineSvg(values) {
  const width = 92;
  const height = 28;
  const max = Math.max(...values, 1);
  const min = Math.min(...values, 0);
  const range = Math.max(max - min, 1);
  const points = values
    .map((value, index) => {
      const x = (index / (values.length - 1)) * width;
      const y = height - ((value - min) / range) * (height - 4) - 2;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
  const [endX, endY] = points.split(" ").at(-1).split(",");
  return `
    <svg class="sparkline" viewBox="0 0 ${width} ${height}" aria-label="Signaldichte der letzten 14 Tage" role="img">
      <polyline points="${points}" />
      <circle cx="${endX}" cy="${endY}" r="3.2" />
    </svg>
  `;
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
  const response = await fetch("./data/forecast.json?v=forecast-strip-1", { cache: "no-store" });
  forecast = await response.json();
  renderMetrics(forecast);
  renderForecastStrip(forecast);
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
