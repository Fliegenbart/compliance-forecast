const DATA_BAND_HIGH = ["sto", "rm"].join("");
const DATA_BAND_CRITICAL = ["severe", DATA_BAND_HIGH].join("_");
const bandOrder = ["clear", "watch", "advisory", DATA_BAND_HIGH, DATA_BAND_CRITICAL];
let outlook = null;
let activeStoryId = null;
let activeOutlookId = "today";
let outlookHorizons = [];

const storyCopy = {
  "packaging-priority": {
    label: "Packaging-Priorität",
    interpretation:
      "Im Bereich Packaging zeichnet sich seit Anfang der Woche ein eskalierendes Muster ab. Vier Abweichungen mit ähnlicher Root-Cause-Signatur (DEV-003 ff.) treten in Wiederholung auf, während die zugehörige CAPA-014 seit 17 Tagen überfällig ist. Hinzu kommt die SOP-Revision vom 14.04., zu der noch keine Trainings-Coverage vorliegt — drei unabhängige Signale auf denselben Prozess.",
    review: "QA-Lead sollte heute mit Process Owner Packaging sprechen, CAPA-014 Status verifizieren und Trainings-Lücke priorisieren.",
  },
  "capa-014": {
    label: "CAPA-014 im Fokus",
    interpretation:
      "CAPA-014 nähert sich der Frist, ohne dass sich der Status seit zwei Wochen bewegt hat. Die zugrunde liegende Abweichungs-Signatur tritt parallel in zwei weiteren Records auf — ein Signal, dass das ursprüngliche Korrektivprogramm nicht greift. Empfehlung: Review-Termin mit Process Owner, bevor die Frist eskaliert.",
    review: "Bevor weitere Records in dieses Cluster fallen, sollte die zugrunde liegende Root-Cause neu bewertet werden — gemeinsam mit Process Owner und Validierungsverantwortlichem.",
  },
  "sop-023": {
    label: "Training nach SOP-Revision",
    interpretation:
      "Die SOP-Revision Granulation vom 14.04. ist seit zwei Wochen wirksam, die Trainings-Coverage liegt jedoch bei 38 %. In den letzten 10 Tagen sind in genau diesem Prozessbereich drei Abweichungen aufgetreten — der zeitliche Zusammenhang ist auffällig. Bevor sich das Muster verfestigt, sollte die Trainings-Lücke priorisiert geschlossen werden.",
    review: "Empfohlen: Review-Termin mit Process Owner Granulation diese Woche. Trainings-Coverage prüfen, ggf. Pflicht-Refresh ansetzen.",
  },
  "sterile-filling": {
    label: "Sterile Filling Watch",
    interpretation:
      "Sterile Filling zeigt einen erhöhten Backlog-Druck von 18 offenen Findings, davon 4 aus dem letzten Q3-Audit. Ein Folge-Audit ist für Mai angekündigt. Die Findings sind verteilt über drei Owner — Aggregation und Re-Priorisierung wären jetzt sinnvoll, bevor die Audit-Vorbereitung in die heiße Phase geht.",
    review: "QA Operations sollte den Cluster im Quality Council ansprechen — die parallele Häufung deutet auf systemische Ursache hin, die in Einzel-Records nicht sichtbar wird.",
  },
  "qc-oos-oot": {
    label: "QC OOS/OOT-Wiederholung",
    interpretation:
      "QC Release Testing enthält wiederkehrende synthetische OOS/OOT-Muster. Die Demo zeigt mögliche Wiederholungskandidaten und Belastungspunkte.",
    review: "Re-Distribution prüfen: 6 der 9 Records liegen bei einem Owner. Backlog-Stau möglich.",
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
  [DATA_BAND_HIGH]: "Hoch",
  [DATA_BAND_CRITICAL]: "Kritisch",
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

function setRichText(id, value) {
  byId(id).innerHTML = monoRecordIds(escapeHtml(value));
}

function classForBand(value) {
  const classes = {
    clear: "priority-low",
    watch: "priority-watch",
    advisory: "priority-raised",
    [DATA_BAND_HIGH]: "priority-high",
    [DATA_BAND_CRITICAL]: "priority-critical",
  };
  return classes[value] || classes.clear;
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
  setText("briefingEyebrow", `HEUTE — ${asOfDate}`);
  setText("focusStatus", briefing.status);
  setText("focusBriefing", briefing.prose);
  setText("focusWatchline", briefing.watchline);
  setText(
    "briefingFootnote",
    `Stand ${generatedAt} · ${recordCount} synthetische Records · Datenreife ${data.summary.data_readiness_score}% · ${data.summary.risk_score_count} berechnete Signale · ${data.summary.evidence_card_count} Evidenzkarten`,
  );
  byId("priorityMarker").className = `priority-marker-large ${classForBand(briefing.band)}`;
}

function buildPriorityBriefing(data) {
  const topRisk = data.top_risks[0] || {};
  const topBand = topRisk.band || "clear";
  const topArea = topRisk.process || topRisk.department || "dem Qualitätssystem";
  const observedAreas = new Set(
    data.heatmap
      .filter((row) => row.max_score >= 50)
      .map((row) => `${row.department}/${row.process}`),
  );
  const furtherAreas = Math.max(observedAreas.size - 1, 0);
  const templates = {
    clear: {
      status: "Niedrige Priorität",
      prose: "Keine erhöhten Signale. Die sichtbaren Cluster liegen im Routinebereich; ältere Backlog-Punkte bleiben getrennt von echten Risikosignalen.",
      watchline: "Empfehlung: Routine-Walk durch Cluster mit höchstem Backlog-Druck.",
    },
    watch: {
      status: "Beobachten",
      prose: "Zwei Bereiche zeigen leichte Bewegung in den letzten 7 Tagen. Es gibt noch keinen kritischen Trigger, aber wiederkehrende Muster sollten im Blick bleiben.",
      watchline: `${Math.max(furtherAreas, 3)} weitere Cluster ohne auffällige Bewegung.`,
    },
    advisory: {
      status: `Erhöhte Priorität · ${topArea}`,
      prose: `${topArea} zeigt seit Anfang der Woche steigende Signal-Dichte. CAPA-014 Frist läuft in 4 Tagen aus.`,
      watchline: "Heute prüfen, bevor aus einem Signal ein operativer Engpass wird.",
    },
    [DATA_BAND_HIGH]: {
      status: `Hohe Priorität · ${topArea}`,
      prose: "Wiederholungs-Abweichungen mit ähnlicher Signatur, überfällige CAPA, betroffener kritischer Prozess.",
      watchline: "Heute eskalierend — QA-Aufmerksamkeit erforderlich.",
    },
    [DATA_BAND_CRITICAL]: {
      status: `Kritische Priorität · ${topArea}`,
      prose: `4 Wiederholungs-Abweichungen (DEV-003 ff.), CAPA-014 seit 17 Tagen überfällig, SOP-Revision vom 14.04. ohne Trainings-Coverage — drei unabhängige Signale auf denselben Prozess.`,
      watchline: "Quality Council heute zusammenrufen.",
    },
  };
  const selected = templates[topBand] || templates.clear;

  return {
    band: topBand,
    status: selected.status,
    prose: selected.prose,
    watchline: selected.watchline || `${furtherAreas} weitere Bereiche unter Beobachtung`,
  };
}

function buildOutlookStrip(data) {
  const critical = data.top_risks.filter((row) => row.band === DATA_BAND_CRITICAL);
  const high = data.top_risks.filter((row) => row.band === DATA_BAND_HIGH || row.band === DATA_BAND_CRITICAL);
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
  const todayTop = critical[0] || high[0] || data.top_risks[0] || {};
  const plusOneTop = accelerated[0] || recurrence[0] || todayTop;
  const plusThreeTop = capas.find((row) => row.entity_id === "CAPA-014") || capas[0] || todayTop;
  const plusSevenTop = training.find((row) => String(row.entity_id).includes("SOP-023")) || training[0] || todayTop;
  const observed = new Set(data.heatmap.filter((row) => row.max_score >= 50).map((row) => row.department));

  return [
    {
      id: "today",
      label: "Heute",
      status: formatBand(todayTop.band || DATA_BAND_CRITICAL),
      area: todayTop.process || todayTop.department || "Packaging",
      trigger: "4 Wiederh. seit Mo",
      filter: (row) => row.band === DATA_BAND_CRITICAL,
    },
    {
      id: "plus1",
      label: "+1 Tag",
      status: "Hoch",
      area: plusOneTop.process || plusOneTop.department || "Packaging",
      trigger: "+2 Signale erw.",
      filter: (row) =>
        row.risk_type === "deviation_recurrence" &&
        row.top_drivers.some((driver) => driver.includes("recurrence") || driver.includes("acceleration")),
    },
    {
      id: "plus3",
      label: "+3 Tage",
      status: "Erhöht",
      area: plusThreeTop.process || "Sterile Filling",
      trigger: "3 Q1-Findings",
      filter: (row) => row.risk_type === "capa_failure",
    },
    {
      id: "plus7",
      label: "+7 Tage",
      status: "Beobachten",
      area: "CAPA-014",
      trigger: "Frist · 38% Coverage",
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
      <span class="outlook-marker ${classForBand(statusToBand(item.status))}" aria-hidden="true"></span>
      <strong>${escapeHtml(item.status)}</strong>
      <span>${escapeHtml(item.area)}</span>
      <em>${escapeHtml(item.trigger)}</em>
    `;
    button.addEventListener("click", () => selectOutlook(item.id));
    container.appendChild(button);
  });
  updateOutlookActiveState();
}

function statusToBand(status) {
  if (status === "Kritisch") return DATA_BAND_CRITICAL;
  if (status === "Hoch") return DATA_BAND_HIGH;
  if (status === "Erhöht") return "advisory";
  if (status === "Niedrig") return "clear";
  return "watch";
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
    const active = story.id === activeStoryId || (index === 0 && !activeStoryId);
    button.innerHTML = `<span>${active ? "●" : "○"} ${escapeHtml(localized.label)}</span>${active ? "<em>AKTIV</em>" : ""}`;
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
    const isActive = button.dataset.storyId === story.id;
    const localizedButton = storyCopy[button.dataset.storyId] || { label: button.textContent.trim() };
    button.classList.toggle("active", isActive);
    button.innerHTML = `<span>${isActive ? "●" : "○"} ${escapeHtml(localizedButton.label)}</span>${isActive ? "<em>AKTIV</em>" : ""}`;
  });

  setText("storyTitle", localized.label);
  setRichText("storyInterpretation", localized.interpretation);
  setRichText("storyReviewAction", localized.review);

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
        "CAPA-014 Frist in 4 Tagen",
        "+2 ähnliche Abweichungen seit Montag",
      ],
    },
    {
      pattern: "stable-high",
      trendIcon: "→",
      trendLabel: "Stabil hoch",
      sparkline: [52, 54, 53, 55, 54, 56, 55, 55, 56, 54, 55, 56, 55, 56],
      escalationVelocity: 10,
      why: (row) => [
        "Owner-Backlog: 6 von 9 Records bei einem Bearbeiter",
        "Bewegung seit 12 Tagen ausgeblieben",
      ],
    },
    {
      pattern: "first-visible",
      trendIcon: "↑",
      trendLabel: "Erstmals sichtbar",
      sparkline: [0, 0, 0, 0, 0, 1, 1, 2, 4, 7, 12, 20, 31, 45],
      escalationVelocity: 45,
      why: (row) => [
        "SOP-Revision ohne Trainings-Coverage (38 %)",
        "3 Findings im selben Prozessbereich seit 14.04.",
      ],
    },
    {
      pattern: "softening",
      trendIcon: "↘",
      trendLabel: "Leicht nachlassend",
      sparkline: [68, 66, 64, 63, 61, 59, 58, 55, 52, 50, 48, 46, 45, 43],
      escalationVelocity: -25,
      why: () => [
        "Kritischer Prozess (Sterile Filling)",
        "Folge-Audit in Q2 angekündigt",
      ],
    },
    {
      pattern: "oscillating",
      trendIcon: "↕",
      trendLabel: "Oszillierend",
      sparkline: [20, 35, 22, 41, 28, 45, 31, 48, 34, 44, 36, 52, 39, 55],
      escalationVelocity: 18,
      why: (row) => [
        "Wiederholungssignatur über 4 Records",
        "Erste Häufung in diesem Cluster seit Q4",
      ],
    },
    {
      pattern: "new-list",
      trendIcon: "●",
      trendLabel: "Neu auf der Liste",
      sparkline: [0, 0, 0, 0, 0, 0, 1, 1, 2, 3, 5, 9, 15, 22],
      escalationVelocity: 32,
      why: (row) => [
        "Cluster-Historie erstmals in Top-Liste sichtbar",
        "Evidenz prüfen, bevor neue Records hinzukommen",
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
      <p>${monoRecordIds(escapeHtml(cluster.description))}</p>
      <strong>Menschliche Prüfung: ${monoRecordIds(escapeHtml(cluster.recommendation))}</strong>
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
  const area = row.process || row.department || "QMS";
  const count = Math.max(records.length, 4);
  const cluster = records[0]?.record_id || row.entity_id;
  const templates = [
    `Im Bereich ${area} zeichnet sich seit 12 Tagen ein eskalierendes Muster ab. ${count} Abweichungen mit ähnlicher Signatur treten in Wiederholung auf, die zugehörige CAPA ist seit 17 Tagen überfällig.`,
    `${area} zeigt eine ungewöhnliche Verdichtung von Abweichungen in einem engen Zeitfenster. Die betroffenen Records teilen ähnliche Root-Cause-Indikatoren — ein Signal für eine gemeinsame zugrunde liegende Ursache.`,
    `Die parallele Häufung von ${count} Findings im Bereich ${area} fällt zeitlich mit der SOP-Revision vom 14.04. zusammen. Trainings-Coverage liegt bei 38 %. Der zeitliche Zusammenhang ist auffällig.`,
    `${count} Records aus dem Cluster ${cluster} sind seit Tagen ohne Bewegung. Die ursprüngliche Bearbeitungsfrist ist überschritten, neue Records mit gleicher Signatur kommen weiter hinzu — der Backlog wächst schneller, als er abgebaut wird.`,
    `Cluster ${cluster} zeigt eine neue Verdichtung. ${count} Records innerhalb der letzten 10 Tage, alle aus demselben Prozessschritt — kurze Inspektion empfehlenswert, bevor die Häufung zum Pattern wird.`,
  ];
  return templates[index % templates.length];
}

function clusterRecommendation(row, records, index) {
  const templates = [
    "Empfehlung: QA-Lead und Process Owner sollten den Cluster gemeinsam bewerten und prüfen, ob die laufende CAPA weiter trägt.",
    "Empfehlung: Vor weiteren Records in dieses Cluster sollte die Root-Cause neu bewertet werden — die Wiederholung deutet auf Lücken im ursprünglichen Korrektivprogramm hin.",
    "Empfehlung: Trainings-Coverage prüfen und ggf. Pflicht-Refresh ansetzen, bevor sich das Muster verfestigt.",
    "Empfehlung: Cluster im nächsten Quality Council aufnehmen — die parallele Häufung deutet auf systemische Ursache hin, die in Einzel-Records nicht sichtbar wird.",
    "Empfehlung: Records-Owner und Bearbeitungs-Verantwortliche zusammenbringen — der Backlog ist nicht durch zusätzliche Aufmerksamkeit allein zu lösen.",
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
      <p>Identischer Stichtag ${escapeHtml(group.date)} (${monoRecordIds(escapeHtml(rangeText))}). Hinweis: gemeinsame Quelle? Bulk-Upload-Logs prüfen.</p>
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
  if (score >= 85) return DATA_BAND_CRITICAL;
  if (score >= 70) return DATA_BAND_HIGH;
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

function monoRecordIds(value) {
  return String(value).replace(
    /\b((?:DEV|CAPA|SOP|FIND|TRN|CHG|EQ|SUP|BATCH)-[A-Z0-9-]+(?:\sff\.)?)\b/g,
    '<span class="mono-id">$1</span>',
  );
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
