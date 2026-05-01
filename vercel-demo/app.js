const bandOrder = ["clear", "watch", "advisory", "storm", "severe_storm"];
let outlook = null;
let activeStoryId = null;
let activeOutlookId = "today";
let outlookHorizons = [];

const storyCopy = {
  "packaging-priority": {
    label: "Packaging-Priorität",
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
    label: "Sterile Filling prüfen",
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
  clear: "Niedrig",
  watch: "Beobachten",
  advisory: "Erhöht",
  storm: "Hoch",
  severe_storm: "Kritisch",
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
  const briefing = buildPriorityBriefing(data);

  setText("modelVersion", data.meta.model_version);
  setText("generatedAt", generatedAt);
  setText("asOfDate", asOfDate);
  setText("sourceRecordCount", `${recordCount} synthetisch`);
  setText("briefingEyebrow", `HEUTE · ${asOfDate}`);
  setText("focusStatus", briefing.status);
  setText("focusBriefing", briefing.prose);
  setText("focusWatchline", briefing.watchline);
  setText(
    "briefingFootnote",
    `Stand ${generatedAt} · ${recordCount} synthetische Records · Datenreife ${data.summary.data_readiness_score}%`,
  );
  byId("focusReasons").innerHTML = briefing.reasons.map((reason) => `<li>${escapeHtml(reason)}</li>`).join("");
}

function buildPriorityBriefing(data) {
  const topRisk = data.top_risks[0] || {};
  const topBand = topRisk.band || "clear";
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
    clear: `Heute gibt es keinen dominierenden Spitzenwert. ${topDepartment} bleibt sichtbar, aber die regelbasierte Priorisierung zeigt keinen akuten Fokusbereich.`,
    watch: `${watchCount} Beobachtungssignale deuten auf Themen hin, die im nächsten QA-Termin bewusst priorisiert werden sollten.`,
    advisory: `${recurrence} Wiederholungs-Signale, ${capaPhrase} und ${trainingPhrase} machen ${topArea} heute zu einem erhöhten Review-Kandidaten.`,
    storm: `${stormCount} hohe Signale und ${recurrence} Wiederholungs-Signale zeigen eine klare Verdichtung. ${capaPhrase}; ${trainingPhrase}.`,
    severe_storm: `${severeCount} kritische Signale, ${recurrence} Wiederholungs-Signale und ${capaPhrase} prägen die heutige Priorisierung. Besonders ${topDepartment} sollte anhand der Quell-IDs menschlich geprüft werden.`,
  };

  return {
    status: `${formatBand(topBand)} · ${topArea}`,
    prose: templates[topBand] || templates.clear,
    reasons: [
      `${recurrence} Wiederholungs-Signale in den Top-Risiken`,
      capa ? `CAPA-Fokus: ${capa.entity_id}` : "Keine einzelne CAPA dominiert die Top-Signale",
      training ? `Training-/SOP-Fokus: ${training.entity_id.split("|").pop()}` : `${topDepartment} als führender Kontext`,
    ],
    watchline: `${furtherAreas} weitere Bereiche unter Beobachtung`,
  };
}

function buildOutlookStrip(data) {
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
      status: formatBand(todayTop.band || "severe_storm"),
      area: todayTop.process || todayTop.department || "Packaging",
      trigger: `${Math.max(severe.length, 1)} kritische Signale`,
      filter: (row) => row.band === "severe_storm",
    },
    {
      id: "plus1",
      label: "+1 Tag",
      status: "Hoch",
      area: plusOneTop.process || plusOneTop.department || "Packaging",
      trigger: `+${Math.min(Math.max(accelerated.length, 2), 9)} seit Mo`,
      filter: (row) =>
        row.risk_type === "deviation_recurrence" &&
        row.top_drivers.some((driver) => driver.includes("recurrence") || driver.includes("acceleration")),
    },
    {
      id: "plus3",
      label: "+3 Tage",
      status: "Erhöht",
      area: plusThreeTop.entity_id ? `${plusThreeTop.entity_id} Frist` : "CAPA-Frist",
      trigger: plusThreeTop.entity_id === "CAPA-014" ? "Packaging-CAPA" : `${Math.max(capas.length, 1)} CAPA-Fristen`,
      filter: (row) => row.risk_type === "capa_failure",
    },
    {
      id: "plus7",
      label: "+7 Tage",
      status: "Beobachten",
      area: plusSevenTop.entity_id && String(plusSevenTop.entity_id).includes("SOP-023") ? "SOP-023 Revision" : plusSevenTop.process || "Training",
      trigger: training.length ? `Training-Coverage ${Math.max(38, 100 - training.length * 7)}%` : `${observed.size} Bereiche`,
      filter: (row) => row.risk_type === "training_drift",
    },
  ];
}

function renderOutlookStrip(data) {
  outlookHorizons = buildOutlookStrip(data);
  const container = byId("outlookStrip");
  container.innerHTML = "";
  outlookHorizons.forEach((item) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "outlook-cell";
    button.dataset.outlookId = item.id;
    button.setAttribute("aria-pressed", String(item.id === activeOutlookId));
    button.innerHTML = `
      <span class="outlook-label">${escapeHtml(item.label)}</span>
      <span class="outlook-marker ${classForBand(item.status === "Hoch" ? "storm" : item.status === "Erhöht" ? "advisory" : item.status === "Kritisch" ? "severe_storm" : "watch")}"></span>
      <strong>${escapeHtml(item.status)}</strong>
      <span>${escapeHtml(item.area)}</span>
      <em>${escapeHtml(item.trigger)}</em>
    `;
    button.addEventListener("click", () => selectOutlook(item.id));
    container.appendChild(button);
  });
  updateOutlookActiveState();
}

function selectOutlook(outlookId) {
  activeOutlookId = outlookId;
  updateOutlookActiveState();
  renderPriorityList();
}

function updateOutlookActiveState() {
  document.querySelectorAll(".outlook-cell").forEach((button) => {
    const isActive = button.dataset.outlookId === activeOutlookId;
    button.classList.toggle("active", isActive);
    button.setAttribute("aria-pressed", String(isActive));
  });
}

function renderPriorityList() {
  const active = outlookHorizons.find((item) => item.id === activeOutlookId) || outlookHorizons[0];
  const story = outlook.demo_stories.find((item) => item.id === activeStoryId) || outlook.demo_stories[0];
  const storyIds = new Set(story?.risk_entity_ids || []);
  const horizonRows = active ? outlook.top_risks.filter(active.filter) : [];
  const storyRows = outlook.top_risks.filter((row) => storyIds.has(row.entity_id));
  const rows = horizonRows.length ? horizonRows : storyRows.length ? storyRows : outlook.top_risks;
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
  const story = outlook.demo_stories.find((item) => item.id === storyId) || outlook.demo_stories[0];
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
  const cards = outlook.evidence_cards.filter((row) => cardIds.has(row.card_id));
  renderPriorityList();
  renderEvidenceCards(cards.length ? cards : outlook.evidence_cards.slice(0, 8));
}

function renderBandCounts(data) {
  const container = byId("bandCounts");
  const total = bandOrder.reduce((sum, band) => sum + (data.risk_band_counts[band] || 0), 0) || 1;
  container.innerHTML = "";
  const segments = bandOrder
    .map((band) => {
      const count = data.risk_band_counts[band] || 0;
      const width = (count / total) * 100;
      return `<span class="band-stack-segment ${classForBand(band)}" style="width:${width}%"></span>`;
    })
    .join("");
  const labels = bandOrder
    .map((band) => {
      const count = data.risk_band_counts[band] || 0;
      return `<span><i class="${classForBand(band)}"></i>${formatBand(band)} <strong>${count}</strong></span>`;
    })
    .join("");
  container.innerHTML = `
    <div class="band-distribution" aria-label="Verteilung der Risikobänder">${segments}</div>
    <div class="band-distribution-labels">${labels}</div>
  `;
}

function priorityStatusMarkup(band) {
  return `
    <span class="priority-status ${classForBand(band)}">
      <span class="priority-status-marker" aria-hidden="true"></span>
      <span>${escapeHtml(formatBand(band))}</span>
    </span>
  `;
}

function heatmapBand(row) {
  return scoreBand(row.max_score);
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
    const band = heatmapBand(row);
    item.innerHTML = `
      <div>
        <strong>${escapeHtml(row.department)} / ${escapeHtml(row.process)}</strong>
        <span>${row.signal_count} Signale, Durchschnitt ${row.average_score}</span>
      </div>
      ${priorityStatusMarkup(band)}
    `;
    container.appendChild(item);
  });
}

function renderEvidenceCards(rows) {
  const container = byId("evidenceCards");
  container.innerHTML = "";
  buildEvidenceClusters(rows).forEach((cluster) => {
    const item = document.createElement("article");
    item.className = "evidence-row evidence-cluster";
    item.innerHTML = `
      <div class="evidence-topline">
        <div class="evidence-title">
          ${escapeHtml(cluster.title)}
          <small>${escapeHtml(cluster.subtitle)}</small>
        </div>
        ${priorityStatusMarkup(cluster.band)}
      </div>
      <div class="source-list evidence-chip-row">
        ${cluster.records.map((record) => recordChip(record)).join("")}
      </div>
      ${cluster.records.map((record) => recordDrawer(record)).join("")}
      <p>${escapeHtml(cluster.description)}</p>
      <strong>Menschliche Prüfung: ${escapeHtml(cluster.recommendation)}</strong>
    `;
    container.appendChild(item);
  });
}

function buildEvidenceClusters(rows) {
  const groups = new Map();
  rows.forEach((row) => {
    const key = `${row.risk_type}|${row.department || "bereichsübergreifend"}|${row.process || "prozessübergreifend"}`;
    const group = groups.get(key) || [];
    group.push(row);
    groups.set(key, group);
  });

  return Array.from(groups.values()).slice(0, 4).map((group, index) => {
    const first = group[0];
    const records = group
      .flatMap((row) =>
        row.source_records.map((source) => ({
          ...source,
          score: row.score,
          band: row.band,
          entityId: row.entity_id,
          owner: row.owner,
          drivers: row.top_drivers,
          riskType: row.risk_type,
          department: row.department,
          process: row.process,
        })),
      )
      .filter((record, recordIndex, all) => all.findIndex((item) => item.record_id === record.record_id) === recordIndex)
      .slice(0, 8);
    return {
      title: clusterTitle(first, records),
      subtitle: `${formatRiskType(first.risk_type)} · ${first.department || "bereichsübergreifend"}${first.process ? ` · ${first.process}` : ""}`,
      band: first.band,
      records,
      description: clusterDescription(first, records, index),
      recommendation: clusterRecommendation(first, records, index),
    };
  });
}

function clusterTitle(row, records) {
  if (row.risk_type === "deviation_recurrence") {
    return `Abweichungs-Cluster ${row.process || row.department || "QMS"} (${records[0]?.record_id || row.entity_id} ff.)`;
  }
  if (row.risk_type === "capa_failure") return `CAPA-Cluster ${row.process || row.department || "QMS"} (${records[0]?.record_id || row.entity_id} ff.)`;
  if (row.risk_type === "training_drift") return `Training-Drift ${row.process || row.department || "SOP"} (${records[0]?.record_id || row.entity_id} ff.)`;
  return `${formatRiskType(row.risk_type)} (${records[0]?.record_id || row.entity_id} ff.)`;
}

function clusterDescription(row, records, index) {
  const templates = [
    `Die Records liegen nicht isoliert nebeneinander, sondern bilden ein erkennbares Muster in ${row.process || row.department}. Auffällig ist die Nähe der Signale: mehrere Quellen zeigen denselben Bereich, aber nicht zwingend dieselbe Ursache. Das ist ein guter Kandidat für eine gebündelte QA-Sichtung statt Einzelbearbeitung.`,
    `Der Cluster verdichtet mehrere Signale zu einem gemeinsamen Prioritätsbild. Die Quell-IDs zeigen, wo die Analyse starten sollte; die Bewertung bleibt bewusst beratend und ersetzt keine fachliche GMP-Entscheidung.`,
    `Hier wirkt weniger der einzelne Record entscheidend als die Wiederholung im Kontext. ${records.length} Quellrecords zeigen genug Nähe, um den Bereich im Quality Council fokussiert anzusehen.`,
    `Das Signal ist vor allem als Lagebild relevant: gleicher Bereich, ähnliche Treiber, mehrere sichtbare Records. Für die Demo zählt diese Verdichtung stärker als das Alter eines einzelnen Backlog-Items.`,
    `Die Evidenz spricht für einen Review-Block statt für verstreute Einzeldiskussionen. Die Quellen sollten zusammen gelesen werden, damit Wiederholungen, CAPA-Bezug und Trainingseffekte nicht getrennt bewertet werden.`,
  ];
  return templates[index % templates.length];
}

function clusterRecommendation(row, records, index) {
  const templates = [
    `QA sollte die ${records.length} Quellrecords gemeinsam sichten und prüfen, ob ein gemeinsamer Review-Pfad sinnvoll ist.`,
    `Empfohlen ist eine kurze QA-Triage mit Blick auf Wiederholung, CAPA-Bezug und offene Trainings-/SOP-Effekte.`,
    `Der Cluster sollte im nächsten Quality-Rhythmus als zusammenhängendes Signal besprochen werden, nicht als vier unabhängige Einzelpunkte.`,
    `Owner und QA sollten die Quell-IDs nebeneinander legen und klären, ob eine bestehende Maßnahme noch ausreichend trägt.`,
    `Für die menschliche Prüfung bietet sich eine Cluster-Review-Notiz an: Quellen, Zeitraum, Owner-Belastung und offene Maßnahmen zusammenführen.`,
  ];
  return templates[index % templates.length];
}

function recordChip(record) {
  return `
    <details class="record-chip">
      <summary>${escapeHtml(record.record_id)}</summary>
      <div class="source-list">
        <span class="source-chip">${escapeHtml(domainLabels[record.domain] || record.domain)}</span>
        <span class="source-chip priority-source ${escapeHtml(classForBand(record.band))}">${escapeHtml(formatBand(record.band))}</span>
        ${record.owner ? `<span class="source-chip">${escapeHtml(record.owner)}</span>` : ""}
      </div>
    </details>
  `;
}

function recordDrawer(record) {
  return `
    <details class="record-drawer">
      <summary>Details zu ${escapeHtml(record.record_id)}</summary>
      <p>${escapeHtml(domainLabels[record.domain] || record.domain)} in ${escapeHtml(record.department || "bereichsübergreifend")}${record.process ? ` / ${escapeHtml(record.process)}` : ""}. Sichtbare Treiber: ${escapeHtml(record.drivers.slice(0, 2).map(translateDriver).join("; "))}.</p>
    </details>
  `;
}

function renderQualityIssues(rows) {
  const container = byId("qualityIssues");
  container.innerHTML = "";
  if (!rows.length) {
    container.innerHTML = `<div class="quality-row"><strong>Keine Top-Issues</strong><p>In der statischen Demo wurden keine priorisierten Datenqualitätsprobleme angezeigt.</p></div>`;
    return;
  }
  aggregateQualityIssues(rows).slice(0, 8).forEach((row) => {
    const item = document.createElement("div");
    item.className = row.records ? "quality-row quality-aggregate" : "quality-row";
    item.innerHTML = row.records ? qualityAggregateMarkup(row) : `
        <strong>${escapeHtml(translateSeverity(row.severity))} · ${escapeHtml(row.record_id)}</strong>
        <p>${escapeHtml(domainLabels[row.domain] || row.domain)}: ${escapeHtml(translateQualityMessage(row.message))}</p>
      `;
    container.appendChild(item);
  });
}

function aggregateQualityIssues(rows) {
  const groups = new Map();
  rows.forEach((row) => {
    const date = row.message.match(/\d{4}-\d{2}-\d{2}/)?.[0] || "ohne Datum";
    const issueType = row.message.replace(/\d{4}-\d{2}-\d{2}/g, "{date}");
    const key = `${row.domain}|${issueType}|${date}`;
    const group = groups.get(key) || {
      domain: row.domain,
      severity: row.severity,
      issueType,
      date,
      records: [],
    };
    group.records.push(row.record_id);
    groups.set(key, group);
  });
  return Array.from(groups.values()).map((group) => {
    if (group.records.length < 3) {
      return {
        domain: group.domain,
        record_id: group.records[0],
        severity: group.severity,
        message: group.issueType.replace("{date}", group.date),
      };
    }
    return group;
  });
}

function qualityAggregateMarkup(group) {
  const firstRecords = group.records.slice(0, 4).join(", ");
  const lastRecord = group.records.at(-1);
  const rangeText = group.records.length > 4 ? `${firstRecords} … ${lastRecord}` : firstRecords;
  return `
    <strong>${group.records.length} ${escapeHtml(qualityDomainPlural(group.domain))}</strong>
    <div>
      <p>Identischer Stichtag ${escapeHtml(group.date)} (${escapeHtml(rangeText)}). Signal: gemeinsame Quelle? Bulk-Upload-Logs prüfen.</p>
      <details class="quality-details">
        <summary>Records anzeigen</summary>
        <div class="source-list">${group.records.map((recordId) => `<span class="source-chip">${escapeHtml(recordId)}</span>`).join("")}</div>
      </details>
    </div>
  `;
}

function qualityDomainPlural(domain) {
  const labels = {
    deviations: "Abweichungs-Records",
    capas: "CAPA-Records",
    audit_findings: "Audit-Finding-Records",
    training_records: "Training-Records",
    change_controls: "Change-Control-Records",
    sops: "SOP-Records",
  };
  return labels[domain] || `${domain}-Records`;
}

function germanRationale(row) {
  const sourceIds = row.source_record_ids.slice(0, 8).join(", ");
  return `Basierend auf den verfügbaren synthetischen Daten zeigt dieses Element ein erhöhtes Risikosignal (${formatBand(row.band)}, Score ${row.score}). Die Anzeige ist für menschliche QA-Prüfung gedacht und ist keine GMP-Entscheidung. Sichtbare Treiber: ${row.top_drivers.slice(0, 2).map(translateDriver).join("; ")}. Quell-IDs: ${sourceIds}.`;
}

function germanReview(riskType) {
  if (riskType === "deviation_recurrence") return "QA sollte die Quellrecords gemeinsam lesen und prüfen, ob ein gebündelter Review-Pfad sinnvoll ist.";
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

async function loadRiskData() {
  const response = await fetch("./data/forecast.json?v=outlook-strip-1", { cache: "no-store" });
  outlook = await response.json();
  renderMetrics(outlook);
  renderOutlookStrip(outlook);
  renderStoryButtons(outlook);
  renderBandCounts(outlook);
  renderHeatmap(outlook.heatmap);
  renderQualityIssues(outlook.data_quality_issues);
  selectStory(activeStoryId || outlook.demo_stories[0].id);
}

loadRiskData().catch((error) => {
  console.error(error);
  byId("storyTitle").textContent = "Demo-Daten konnten nicht geladen werden";
  byId("storyInterpretation").textContent = "Bitte die statische Demo mit make vercel-demo neu erzeugen.";
});
