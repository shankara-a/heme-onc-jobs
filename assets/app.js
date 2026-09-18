/* Heme/Onc Jobs — single-page app over data/jobs.json */
(() => {
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));

  const TYPE_LABEL = { academic: "Academic", community: "Community", industry: "Industry", government: "Government/VA", locums: "Locums", unknown: "Unclassified" };
  const TYPE_ORDER = ["academic", "community", "industry", "government", "locums", "unknown"];
  const SUB_LABEL = {
    malignant_heme: "Malignant heme", classical_heme: "Classical heme", bmt_cell_therapy: "BMT / cell therapy",
    solid_tumor: "Solid tumor", breast: "Breast", gi: "GI", thoracic: "Thoracic", gu: "GU", gyn: "Gyn",
    head_neck: "Head & neck", neuro_onc: "Neuro-onc", sarcoma: "Sarcoma", melanoma_skin: "Melanoma", phase1_drug_dev: "Phase 1 / drug dev",
    pediatric: "Pediatric", palliative: "Palliative", general: "General heme/onc",
  };
  const BENEFIT_LABEL = {
    sign_on_bonus: "Sign-on bonus", relocation: "Relocation", loan_repayment: "Loan repayment", cme: "CME",
    malpractice: "Malpractice / tail", retirement: "Retirement plan", pto: "PTO", health_insurance: "Health insurance",
    partnership_track: "Partnership track", productivity_bonus: "wRVU / productivity bonus", visa_sponsorship: "Visa sponsorship",
    retention_bonus: "Retention bonus / stipend", equity: "Equity", housing: "Housing assistance", no_call: "Light / no call",
    four_day_week: "4-day week", research_support: "Research start-up", disability_life: "Disability / life",
  };
  const STATES = { AL:"Alabama",AK:"Alaska",AZ:"Arizona",AR:"Arkansas",CA:"California",CO:"Colorado",CT:"Connecticut",DE:"Delaware",DC:"District of Columbia",FL:"Florida",GA:"Georgia",HI:"Hawaii",ID:"Idaho",IL:"Illinois",IN:"Indiana",IA:"Iowa",KS:"Kansas",KY:"Kentucky",LA:"Louisiana",ME:"Maine",MD:"Maryland",MA:"Massachusetts",MI:"Michigan",MN:"Minnesota",MS:"Mississippi",MO:"Missouri",MT:"Montana",NE:"Nebraska",NV:"Nevada",NH:"New Hampshire",NJ:"New Jersey",NM:"New Mexico",NY:"New York",NC:"North Carolina",ND:"North Dakota",OH:"Ohio",OK:"Oklahoma",OR:"Oregon",PA:"Pennsylvania",RI:"Rhode Island",SC:"South Carolina",SD:"South Dakota",TN:"Tennessee",TX:"Texas",UT:"Utah",VT:"Vermont",VA:"Virginia",WA:"Washington",WV:"West Virginia",WI:"Wisconsin",WY:"Wyoming",PR:"Puerto Rico" };

  const state = {
    jobs: [], filtered: [], shown: 40,
    f: { state: "CA", types: new Set(TYPE_ORDER), sub: "", source: "", q: "", salary: false, md: true, effort: false, fresh: false, sort: "posted" },
    map: null, markers: null, charts: {},
  };

  // ---------- helpers ----------
  const fmt$ = (n) => n == null ? "" : n >= 1e6 ? "$" + (n / 1e6).toFixed(2).replace(/\.?0+$/, "") + "M" : "$" + Math.round(n / 1000) + "k";
  const fmtDate = (s) => s ? new Date(s + "T00:00:00").toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" }) : "";
  const daysAgo = (s) => s ? Math.floor((Date.now() - new Date(s + "T00:00:00")) / 864e5) : null;
  const cssVar = (n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
  const typeColor = (t) => cssVar(`--t-${TYPE_LABEL[t] ? t : "unknown"}`);
  const salaryMid = (j) => j.salary && j.salary.min ? (j.salary.max ? (j.salary.min + j.salary.max) / 2 : j.salary.min) : null;
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  function salaryText(j) {
    const s = j.salary || {};
    if (!s.disclosed || !s.min) return null;
    if (s.max && s.max !== s.min) return `${fmt$(s.min)} – ${fmt$(s.max)}`;
    return /or above|\+|minimum|from/i.test(s.text || "") ? `${fmt$(s.min)}+` : fmt$(s.min);
  }

  // ---------- filtering ----------
  function applyFilters() {
    const f = state.f, q = f.q.trim().toLowerCase();
    let out = state.jobs.filter((j) => {
      if (f.state && j.location.state !== f.state && !(f.state === "REMOTE" && j.remote)) return false;
      if (!f.types.has(j.job_type)) return false;
      if (f.sub && !(j.subspecialties || []).includes(f.sub)) return false;
      if (f.source && j.source_name !== f.source) return false;
      if (f.salary && !(j.salary && j.salary.disclosed && j.salary.min)) return false;
      if (f.md && j.md_required !== true) return false;
      if (f.effort && j.effort.clinical == null && j.effort.research == null) return false;
      if (f.fresh) { const d = daysAgo(j.posted_date || j.first_seen); if (d == null || d > 7) return false; }
      if (q) {
        const hay = `${j.title} ${j.employer} ${j.location.text} ${j.location.city} ${j.location.state} ${(j.subspecialties||[]).join(" ")} ${j.description}`.toLowerCase();
        if (!q.split(/\s+/).every((w) => hay.includes(w))) return false;
      }
      return true;
    });
    const sorters = {
      posted: (a, b) => (b.posted_date || b.first_seen || "").localeCompare(a.posted_date || a.first_seen || ""),
      salary: (a, b) => (salaryMid(b) || -1) - (salaryMid(a) || -1),
      salary_asc: (a, b) => (salaryMid(a) || Infinity) - (salaryMid(b) || Infinity),  // undisclosed still last
      clinical: (a, b) => ((b.effort.research ?? (b.effort.clinical != null ? 100 - b.effort.clinical : -1)) - (a.effort.research ?? (a.effort.clinical != null ? 100 - a.effort.clinical : -1))),
      employer: (a, b) => (a.employer || "").localeCompare(b.employer || ""),
    };
    out.sort(sorters[f.sort] || sorters.posted);
    state.filtered = out;
    state.shown = 40;
    renderStats(); renderJobs();
    if ($("#tab-map").classList.contains("active")) renderMap();
    if ($("#tab-insights").classList.contains("active")) renderCharts();
  }

  // ---------- stats ----------
  function renderStats() {
    const js = state.filtered;
    const withSal = js.filter((j) => salaryMid(j));
    const mids = withSal.map(salaryMid).sort((a, b) => a - b);
    const median = mids.length ? mids[Math.floor(mids.length / 2)] : null;
    const effort = js.filter((j) => j.effort.clinical != null || j.effort.research != null).length;
    const fresh = js.filter((j) => { const d = daysAgo(j.posted_date || j.first_seen); return d != null && d <= 7; }).length;
    const byType = TYPE_ORDER.map((t) => [t, js.filter((j) => j.job_type === t).length]).filter(([, n]) => n);
    const pct = js.length ? Math.round(100 * withSal.length / js.length) : 0;
    $("#stats").innerHTML = [
      [js.length, `postings · ${state.f.state ? (STATES[state.f.state] || state.f.state) : "all states"}`, ""],
      [withSal.length, `with salary (${pct}%)`, ""],
      [median ? fmt$(median) : "—", "median posted", "midpoint of disclosed ranges"],
      [effort, "state a time split", "clinical / research / admin"],
      [fresh, "new this week", "posted or first seen ≤ 7 days"],
      [byType.map(([t, n]) => `<span class="sw sw-${t}" title="${TYPE_LABEL[t]}"></span>${n}`).join(""), "by type", byType.map(([t, n]) => `${TYPE_LABEL[t]} ${n}`).join(" · ")],
    ].map(([v, l, tip]) => `<span class="stat" title="${tip}"><span class="v">${v}</span><span class="l">${l}</span></span>`).join("");
  }

  // ---------- job cards ----------
  function renderJobs() {
    const list = $("#job-list"), tpl = $("#job-card-tpl");
    list.innerHTML = "";
    $("#jobs-count").textContent = `${state.filtered.length} job${state.filtered.length === 1 ? "" : "s"}`;
    if (!state.filtered.length) {
      list.innerHTML = `<div class="empty">No postings match. Try clearing the state filter or unchecking "MD/DO required".</div>`;
      $("#more-btn").classList.add("hidden"); return;
    }
    const frag = document.createDocumentFragment();
    state.filtered.slice(0, state.shown).forEach((j) => frag.appendChild(card(j, tpl)));
    list.appendChild(frag);
    $("#more-btn").classList.toggle("hidden", state.shown >= state.filtered.length);
  }

  function card(j, tpl) {
    const el = tpl.content.firstElementChild.cloneNode(true);
    el.querySelector(".type-dot").style.background = typeColor(j.job_type);
    const a = el.querySelector(".job-title a"); a.textContent = j.title; a.href = j.url;
    el.querySelector(".employer").textContent = j.employer || "—";
    const loc = [j.location.city, j.location.state].filter(Boolean).join(", ") || j.location.text || "";
    el.querySelector(".loc").textContent = (j.remote ? "Remote · " : "") + loc;
    const d = daysAgo(j.posted_date || j.first_seen);
    el.querySelector(".posted").textContent = d == null ? "" : d === 0 ? "Today" : d === 1 ? "Yesterday" : d < 30 ? `${d} d ago` : fmtDate(j.posted_date || j.first_seen);

    const tags = [`<span class="tag type">${TYPE_LABEL[j.job_type]}</span>`];
    if (j.rank && j.rank !== "leadership") tags.push(`<span class="tag">${j.rank.replace("_", " ")}</span>`);
    if (j.rank === "leadership") tags.push(`<span class="tag">Leadership</span>`);
    (j.subspecialties || []).slice(0, 4).forEach((s) => tags.push(`<span class="tag">${SUB_LABEL[s] || s}</span>`));
    (j.benefits || []).filter((b) => ["sign_on_bonus", "loan_repayment", "partnership_track", "visa_sponsorship", "research_support", "four_day_week"].includes(b)).forEach((b) => tags.push(`<span class="tag">${BENEFIT_LABEL[b]}</span>`));
    if (j.md_required === true) tags.push(`<span class="tag">MD/DO</span>`);
    if (j.enriched_by === "llm") tags.push(`<span class="tag ai" title="Fields extracted by Claude">AI-read</span>`);
    tags.push(`<span class="tag">${esc(j.source_name)}</span>`);
    el.querySelector(".job-tags").innerHTML = tags.join("");

    const sal = el.querySelector(".salary"), st = salaryText(j);
    if (st) {
      sal.innerHTML = esc(st) + (j.salary.annualized_from ? `<small>annualized from ${j.salary.annualized_from}ly rate</small>` : j.salary.max ? `<small>posted base range</small>` : `<small>posted base</small>`);
    } else { sal.textContent = j.salary && j.salary.text ? j.salary.text.slice(0, 40) : "Salary not posted"; sal.classList.add("none"); }

    const e = j.effort || {};
    const effEl = el.querySelector(".effort");
    if (e.clinical != null || e.research != null) {
      const c = e.clinical ?? (e.research != null ? 100 - e.research : 0);
      const parts = [["c", c], ["r", e.research], ["a", e.admin], ["t", e.teaching]].filter(([, v]) => v);
      effEl.innerHTML = `${c}% clinical${e.research ? ` · ${e.research}% research` : ""}${e.admin ? ` · ${e.admin}% admin` : ""}${e.teaching ? ` · ${e.teaching}% teaching` : ""}
        <div class="effort-bar">${parts.map(([k, v]) => `<span class="${k}" style="width:${v}%"></span>`).join("")}</div>`;
    } else if (e.protected_time) { effEl.textContent = "Protected time mentioned"; }
    else effEl.textContent = "";

    // detail
    el.querySelector(".d-effort").textContent = e.text || (e.protected_time ? "Posting mentions protected time but no percentage." : "Not stated.");
    const bl = (j.benefits || []).map((b) => {
      const amt = j.benefit_amounts && j.benefit_amounts[b];
      return (BENEFIT_LABEL[b] || b) + (amt ? ` (${fmt$(amt)})` : "");
    });
    if (j.benefits_llm && j.benefits_llm.length) bl.push(...j.benefits_llm.filter((x) => !bl.some((y) => y.toLowerCase().includes(x.toLowerCase().slice(0, 8)))));
    el.querySelector(".d-benefits").textContent = bl.length ? bl.join(" · ") : "None mentioned.";
    el.querySelector(".d-req").textContent = [j.education_text, j.md_note, j.employment_type, j.call_schedule ? "Call: " + j.call_schedule : null, j.closing_date ? "Closes " + fmtDate(j.closing_date) : null].filter(Boolean).join(" · ") || "—";
    el.querySelector(".d-sources").innerHTML = [`<a href="${esc(j.url)}" target="_blank" rel="noopener">${esc(j.source_name)}</a>`]
      .concat((j.also_listed || []).map((s) => `<a href="${esc(s.url)}" target="_blank" rel="noopener">${esc(s.source_name)}</a>`)).join(" · ");
    el.querySelector(".d-summary").textContent = j.summary || "";
    el.querySelector(".d-desc").textContent = j.description || "";

    const btn = el.querySelector(".expand"), det = el.querySelector(".job-detail");
    btn.addEventListener("click", () => { const open = det.classList.toggle("hidden"); btn.setAttribute("aria-expanded", String(!open)); });
    return el;
  }

  // ---------- map ----------
  function renderMap() {
    if (!window.L) return;
    if (!state.map) {
      state.map = L.map("map", { scrollWheelZoom: false }).setView([37.5, -119.5], 6);
      L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
        attribution: "&copy; <a href=\"https://www.openstreetmap.org/copyright\">OpenStreetMap</a> contributors", maxZoom: 12,
      }).addTo(state.map);
      state.markers = L.layerGroup().addTo(state.map);
    }
    state.markers.clearLayers();
    const groups = new Map();
    state.filtered.forEach((j) => {
      if (j.location.lat == null) return;
      const key = `${j.location.lat},${j.location.lon}`;
      if (!groups.has(key)) groups.set(key, { lat: j.location.lat, lon: j.location.lon, jobs: [], label: j.location.geo_precision === "city" ? `${j.location.city}, ${j.location.state}` : `${STATES[j.location.state] || j.location.state} (city unknown)` });
      groups.get(key).jobs.push(j);
    });
    const bounds = [];
    groups.forEach((g) => {
      const n = g.jobs.length;
      const counts = {}; g.jobs.forEach((j) => counts[j.job_type] = (counts[j.job_type] || 0) + 1);
      const top = Object.entries(counts).sort((a, b) => b[1] - a[1])[0][0];
      const m = L.circleMarker([g.lat, g.lon], { radius: 6 + 4 * Math.sqrt(n), color: "#fff", weight: 2, fillColor: typeColor(top), fillOpacity: .8 });
      m.bindPopup(`<strong>${esc(g.label)}</strong> · ${n} posting${n > 1 ? "s" : ""}` +
        g.jobs.slice(0, 8).map((j) => `<div class="popup-job"><div class="t"><a href="${esc(j.url)}" target="_blank" rel="noopener">${esc(j.title)}</a></div><div class="m">${esc(j.employer || "")} · ${TYPE_LABEL[j.job_type]}${salaryText(j) ? " · " + salaryText(j) : ""}</div></div>`).join("") +
        (n > 8 ? `<div class="m">…and ${n - 8} more (filter the list to see them)</div>` : ""), { maxWidth: 360 });
      m.addTo(state.markers); bounds.push([g.lat, g.lon]);
    });
    if (bounds.length) state.map.fitBounds(bounds, { padding: [30, 30], maxZoom: 8 });
    setTimeout(() => state.map.invalidateSize(), 50);
  }

  // ---------- charts ----------
  function chartDefaults() {
    Chart.defaults.color = cssVar("--text-2");
    Chart.defaults.borderColor = cssVar("--grid");
    Chart.defaults.font.family = getComputedStyle(document.body).fontFamily;
    Chart.defaults.font.size = 12;
  }
  function kill(id) { if (state.charts[id]) { state.charts[id].destroy(); delete state.charts[id]; } }
  const median = (arr) => { if (!arr.length) return null; const s = [...arr].sort((a, b) => a - b); return s[Math.floor(s.length / 2)]; };

  const f2ok = (j) => { const f = state.f; return f.types.has(j.job_type) && (!f.md || j.md_required === true) && (!f.sub || (j.subspecialties || []).includes(f.sub)) && (!f.source || j.source_name === f.source) && (!f.salary || salaryMid(j)); };

  function renderCharts() {
    if (!window.Chart) return;
    chartDefaults();
    const js = state.filtered;

    // Salary box plot: one box per group (job type / subspecialty / state), one value per posting
    const measure = state.salaryMeasure || "mid", grouping = state.salaryGroup || "type";
    const pick = (j) => measure === "mid" ? salaryMid(j) : measure === "min" ? j.salary.min : (j.salary.max || j.salary.min);
    const withSalary = js.filter((j) => salaryMid(j));
    const MAX_GROUPS = 8;
    let groups; // [{key, label, color, vals}]
    if (grouping === "type") {
      groups = TYPE_ORDER.map((t) => ({ key: t, label: TYPE_LABEL[t], color: typeColor(t), vals: withSalary.filter((j) => j.job_type === t).map(pick) }));
    } else if (grouping === "sub") {
      const bySub = {};
      withSalary.forEach((j) => (j.subspecialties || []).forEach((s) => (bySub[s] = bySub[s] || []).push(pick(j))));
      groups = Object.entries(bySub).map(([k, vals]) => ({ key: k, label: SUB_LABEL[k] || k, color: cssVar("--accent"), vals }));
    } else {
      const pool = state.jobs.filter((j) => salaryMid(j) && f2ok(j));
      const byState = {};
      pool.forEach((j) => { const st = j.location.state; if (st) (byState[st] = byState[st] || []).push(pick(j)); });
      groups = Object.entries(byState).map(([k, vals]) => ({ key: k, label: STATES[k] || k, color: k === state.f.state ? cssVar("--accent") : cssVar("--text-3"), vals }));
    }
    groups = groups.filter((g) => g.vals.length >= 2).sort((a, b) => b.vals.length - a.vals.length).slice(0, MAX_GROUPS);
    if (grouping !== "type") groups.sort((a, b) => median(b.vals) - median(a.vals));
    const rows = groups.map((g) => {
      const vals = [...g.vals].sort((a, b) => a - b);
      const q = (p) => vals[Math.min(vals.length - 1, Math.floor(p * (vals.length - 1)))];
      return { t: g.key, label: g.label, color: g.color, n: vals.length, vals, min: vals[0], q1: q(.25), med: q(.5), q3: q(.75), max: vals[vals.length - 1] };
    });
    $("#salary-title").textContent = grouping === "type" ? "Posted base salary by job type" : grouping === "sub" ? "Posted base salary by subspecialty" : "Posted base salary by state";
    $("#salary-sub").textContent = grouping === "sub"
      ? ` — top ${MAX_GROUPS} tags by count, sorted by median; a posting tagged with several subspecialties counts in each`
      : grouping === "state"
      ? ` — top ${MAX_GROUPS} states by count under the other filters (state filter ignored), sorted by median`
      : " — box = middle 50% of postings, line = median, whiskers = 1.5×IQR, dots = individual postings";
    kill("salary");
    const hasBox = window.ChartBoxPlot && window.ChartBoxPlot.BoxPlotController;
    if (hasBox && rows.length) {
      Chart.register(ChartBoxPlot.BoxPlotController, ChartBoxPlot.BoxAndWiskers);
      const surface = cssVar("--surface");
      const alignStats = { id: "alignStats", afterLayout: (chart) => {
        const el = $("#table-salary"), a = chart.chartArea;
        if (!el || !a) return;
        el.style.paddingLeft = a.left + "px";
        el.style.paddingRight = (chart.width - a.right) + "px";
      } };
      state.charts.salary = new Chart($("#chart-salary"), {
        type: "boxplot",
        plugins: [alignStats],
        data: {
          labels: rows.map((r) => `${r.label} (n=${r.n})`),
          datasets: [{
            data: rows.map((r) => r.vals),
            backgroundColor: rows.map((r) => r.color + "33"),
            borderColor: rows.map((r) => r.color),
            borderWidth: 2,
            medianColor: rows.map((r) => r.color),
            outlierBackgroundColor: rows.map((r) => r.color),
            outlierBorderColor: surface,
            outlierRadius: 4,
            itemRadius: 3,
            itemStyle: "circle",
            itemBackgroundColor: rows.map((r) => r.color + "99"),
            itemBorderColor: surface,
            maxBarThickness: 90,
          }],
        },
        options: {
          responsive: true, maintainAspectRatio: false,
          plugins: {
            legend: { display: false },
            tooltip: { callbacks: {
              label: (c) => {
                const r = rows[c.dataIndex];
                return [`n = ${r.n}`, `Max ${fmt$(r.max)}`, `Q3 ${fmt$(r.q3)}`, `Median ${fmt$(r.med)}`, `Q1 ${fmt$(r.q1)}`, `Min ${fmt$(r.min)}`];
              },
            } },
          },
          scales: {
            y: { beginAtZero: false, ticks: { callback: (v) => fmt$(v) }, grid: { color: cssVar("--grid") },
                 title: { display: true, text: measure === "mid" ? "Midpoint of posted range" : measure === "min" ? "Low end of posted range" : "High end of posted range", color: cssVar("--text-3") } },
            x: { grid: { display: false } },
          },
        },
      });
    } else if (rows.length) {
      // Fallback if the boxplot plugin failed to load: median bars.
      state.charts.salary = new Chart($("#chart-salary"), {
        type: "bar",
        data: { labels: rows.map((r) => `${r.label} (n=${r.n})`), datasets: [{ data: rows.map((r) => r.med), backgroundColor: rows.map((r) => r.color), maxBarThickness: 24, borderRadius: { topLeft: 4, topRight: 4 }, borderSkipped: "start" }] },
        options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { y: { beginAtZero: true, ticks: { callback: (v) => fmt$(v) } }, x: { grid: { display: false } } } },
      });
    }
    const statsEl = $("#table-salary");
    statsEl.style.gridTemplateColumns = `repeat(${Math.max(rows.length, 1)}, minmax(0, 1fr))`;
    statsEl.classList.toggle("many", rows.length > 5);
    statsEl.innerHTML = rows.length
      ? rows.map((r) => `<div class="box-stat">
          <div class="h"><span class="sw" style="background:${r.color}"></span>${esc(r.label)}<span class="n">n = ${r.n}</span></div>
          <dl>
            <dt>Max</dt><dd data-l="Max">${fmt$(r.max)}</dd>
            <dt>Q3</dt><dd data-l="Q3">${fmt$(r.q3)}</dd>
            <dt class="med">Median</dt><dd class="med" data-l="Med">${fmt$(r.med)}</dd>
            <dt>Q1</dt><dd data-l="Q1">${fmt$(r.q1)}</dd>
            <dt>Min</dt><dd data-l="Min">${fmt$(r.min)}</dd>
            <dt>IQR</dt><dd data-l="IQR">${fmt$(r.q3 - r.q1)}</dd>
          </dl></div>`).join("")
      : `<div class="empty-note">Fewer than 2 postings with a disclosed salary in this view — widen the filters.</div>`;

    // By state (ignore the state filter so the chart stays useful)
    const f2 = { ...state.f, state: "" };
    const all = state.jobs.filter((j) => f2.types.has(j.job_type) && (!f2.md || j.md_required === true) && (!f2.sub || (j.subspecialties || []).includes(f2.sub)) && (!f2.source || j.source_name === f2.source));
    const byState = {}; all.forEach((j) => { const s = j.location.state || "??"; byState[s] = (byState[s] || 0) + 1; });
    const top = Object.entries(byState).sort((a, b) => b[1] - a[1]).slice(0, 12);
    kill("state");
    state.charts.state = new Chart($("#chart-state"), {
      type: "bar",
      data: { labels: top.map(([s]) => STATES[s] || s), datasets: [{ data: top.map(([, n]) => n), backgroundColor: top.map(([s]) => s === state.f.state ? cssVar("--accent") : cssVar("--text-3")), maxBarThickness: 18, borderRadius: { topRight: 4, bottomRight: 4 }, borderSkipped: "start" }] },
      options: { indexAxis: "y", responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { x: { beginAtZero: true, grid: { color: cssVar("--grid") }, ticks: { precision: 0 } }, y: { grid: { display: false } } } },
    });

    // Effort histogram
    const buckets = [["≤50%", 0, 50], ["51–70%", 51, 70], ["71–80%", 71, 80], ["81–90%", 81, 90], ["91–100%", 91, 100]];
    const eff = js.map((j) => j.effort.clinical ?? (j.effort.research != null ? 100 - j.effort.research : null)).filter((v) => v != null);
    kill("effort");
    state.charts.effort = new Chart($("#chart-effort"), {
      type: "bar",
      data: { labels: buckets.map((b) => b[0]), datasets: [{ label: "Postings", data: buckets.map(([, lo, hi]) => eff.filter((v) => v >= lo && v <= hi).length), backgroundColor: cssVar("--accent"), maxBarThickness: 24, borderRadius: { topLeft: 4, topRight: 4 }, borderSkipped: "start" }] },
      options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false }, title: { display: true, text: eff.length ? `Clinical share of time — ${eff.length} postings state a split` : "No postings in this view state a split", align: "start", color: cssVar("--text-2"), font: { weight: "normal" } } },
        scales: { y: { beginAtZero: true, ticks: { precision: 0 }, grid: { color: cssVar("--grid") } }, x: { grid: { display: false } } } },
    });

    // Benefits share
    const bc = {}; js.forEach((j) => (j.benefits || []).forEach((b) => bc[b] = (bc[b] || 0) + 1));
    const bt = Object.entries(bc).sort((a, b) => b[1] - a[1]).slice(0, 10);
    kill("benefits");
    state.charts.benefits = new Chart($("#chart-benefits"), {
      type: "bar",
      data: { labels: bt.map(([b]) => BENEFIT_LABEL[b] || b), datasets: [{ data: bt.map(([, n]) => js.length ? Math.round(100 * n / js.length) : 0), backgroundColor: cssVar("--t-industry"), maxBarThickness: 18, borderRadius: { topRight: 4, bottomRight: 4 }, borderSkipped: "start" }] },
      options: { indexAxis: "y", responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false }, tooltip: { callbacks: { label: (c) => `${c.raw}% of postings` } } }, scales: { x: { beginAtZero: true, max: 100, ticks: { callback: (v) => v + "%" }, grid: { color: cssVar("--grid") } }, y: { grid: { display: false } } } },
    });
  }

  // ---------- CSV ----------
  function downloadCSV() {
    const cols = ["title", "employer", "job_type", "city", "state", "remote", "salary_min", "salary_max", "salary_text", "clinical_pct", "research_pct", "admin_pct", "teaching_pct", "effort_text", "md_required", "benefits", "subspecialties", "posted_date", "closing_date", "source", "url"];
    const rows = state.filtered.map((j) => [j.title, j.employer, j.job_type, j.location.city, j.location.state, j.remote, j.salary.min, j.salary.max, j.salary.text, j.effort.clinical, j.effort.research, j.effort.admin, j.effort.teaching, j.effort.text, j.md_required, (j.benefits || []).join("; "), (j.subspecialties || []).join("; "), j.posted_date, j.closing_date, j.source_name, j.url]);
    const csv = [cols, ...rows].map((r) => r.map((v) => `"${String(v ?? "").replace(/"/g, '""')}"`).join(",")).join("\n");
    const a = document.createElement("a"); a.href = URL.createObjectURL(new Blob([csv], { type: "text/csv" })); a.download = "heme_onc_jobs.csv"; a.click();
  }

  // ---------- theme ----------
  const isDark = () => document.documentElement.dataset.theme === "dark" || (!document.documentElement.dataset.theme && matchMedia("(prefers-color-scheme: dark)").matches);
  function setTheme(t) {
    document.documentElement.dataset.theme = t;
    try { localStorage.setItem("hoj.theme", t); } catch (e) { /* private mode */ }
    if (state.map) renderMap();
    if ($("#tab-insights").classList.contains("active")) renderCharts();
  }

  // ---------- wiring ----------
  function populateSelects() {
    const st = $("#f-state");
    const counts = {}; state.jobs.forEach((j) => { if (j.location.state) counts[j.location.state] = (counts[j.location.state] || 0) + 1; });
    Object.keys(counts).sort((a, b) => (STATES[a] || a).localeCompare(STATES[b] || b)).forEach((s) => st.insertAdjacentHTML("beforeend", `<option value="${s}">${STATES[s] || s} (${counts[s]})</option>`));
    st.insertAdjacentHTML("beforeend", `<option value="REMOTE">Remote</option>`);
    st.value = counts[state.f.state] ? state.f.state : "";
    state.f.state = st.value;
    const subs = {}; state.jobs.forEach((j) => (j.subspecialties || []).forEach((s) => subs[s] = (subs[s] || 0) + 1));
    Object.entries(subs).sort((a, b) => b[1] - a[1]).forEach(([s, n]) => $("#f-sub").insertAdjacentHTML("beforeend", `<option value="${s}">${SUB_LABEL[s] || s} (${n})</option>`));
    const srcs = {}; state.jobs.forEach((j) => srcs[j.source_name] = (srcs[j.source_name] || 0) + 1);
    Object.entries(srcs).sort((a, b) => b[1] - a[1]).forEach(([s, n]) => $("#f-source").insertAdjacentHTML("beforeend", `<option value="${esc(s)}">${esc(s)} (${n})</option>`));
    $("#source-list").innerHTML = Object.entries(srcs).map(([s, n]) => `<li><strong>${esc(s)}</strong> — ${n} current postings</li>`).join("");
  }

  function wire() {
    $("#f-state").addEventListener("change", (e) => { state.f.state = e.target.value; applyFilters(); });
    $("#f-sub").addEventListener("change", (e) => { state.f.sub = e.target.value; applyFilters(); });
    $("#f-source").addEventListener("change", (e) => { state.f.source = e.target.value; applyFilters(); });
    $("#f-sort").addEventListener("change", (e) => { state.f.sort = e.target.value; applyFilters(); });
    let t; $("#f-q").addEventListener("input", (e) => { clearTimeout(t); t = setTimeout(() => { state.f.q = e.target.value; applyFilters(); }, 180); });
    [["#f-salary", "salary"], ["#f-md", "md"], ["#f-effort", "effort"], ["#f-new", "fresh"]].forEach(([s, k]) => $(s).addEventListener("change", (e) => { state.f[k] = e.target.checked; applyFilters(); }));
    $$("#f-type .chip").forEach((c) => c.addEventListener("click", () => {
      const v = c.dataset.v; c.classList.toggle("on");
      if (c.classList.contains("on")) state.f.types.add(v); else state.f.types.delete(v);
      applyFilters();
    }));
    $("#f-reset").addEventListener("click", () => {
      state.f = { state: "", types: new Set(TYPE_ORDER), sub: "", source: "", q: "", salary: false, md: false, effort: false, fresh: false, sort: "posted" };
      $("#f-state").value = ""; $("#f-sub").value = ""; $("#f-source").value = ""; $("#f-q").value = ""; $("#f-sort").value = "posted";
      ["#f-salary", "#f-md", "#f-effort", "#f-new"].forEach((s) => $(s).checked = false);
      $$("#f-type .chip").forEach((c) => c.classList.add("on"));
      applyFilters();
    });
    $("#more-btn").addEventListener("click", () => { state.shown += 40; renderJobs(); });
    $("#dl-csv").addEventListener("click", downloadCSV);
    $$("#salary-group .seg-btn").forEach((b) => b.addEventListener("click", () => {
      $$("#salary-group .seg-btn").forEach((x) => { x.classList.toggle("on", x === b); x.setAttribute("aria-checked", String(x === b)); });
      state.salaryGroup = b.dataset.v; renderCharts();
    }));
    $$("#salary-measure .seg-btn").forEach((b) => b.addEventListener("click", () => {
      $$("#salary-measure .seg-btn").forEach((x) => { x.classList.toggle("on", x === b); x.setAttribute("aria-checked", String(x === b)); });
      state.salaryMeasure = b.dataset.v; renderCharts();
    }));
    $$(".tab").forEach((b) => b.addEventListener("click", () => {
      $$(".tab").forEach((x) => x.classList.toggle("active", x === b));
      $$(".panel").forEach((p) => p.classList.toggle("active", p.id === "tab-" + b.dataset.tab));
      $("#filters").classList.toggle("hidden", b.dataset.tab === "about");
      $("#stats").classList.toggle("hidden", b.dataset.tab === "about");
      if (b.dataset.tab === "map") renderMap();
      if (b.dataset.tab === "insights") renderCharts();
    }));
    $("#theme-toggle").addEventListener("click", () => setTheme(isDark() ? "light" : "dark"));
    try { const t = localStorage.getItem("hoj.theme"); if (t) document.documentElement.dataset.theme = t; } catch (e) { /* ignore */ }
  }

  async function init() {
    wire();
    const head = $(".sticky-head");
    if (head) addEventListener("scroll", () => head.classList.toggle("stuck", head.getBoundingClientRect().top <= 0 && scrollY > 40), { passive: true });
    try {
      const r = await fetch("data/jobs.json", { cache: "no-cache" });
      const d = await r.json();
      state.jobs = d.jobs || [];
      const when = d.generated_at ? new Date(d.generated_at) : null;
      $("#updated-badge").textContent = when ? `${state.jobs.length} postings · updated ${when.toLocaleDateString(undefined, { month: "short", day: "numeric" })}` : `${state.jobs.length} postings`;
    } catch (e) {
      $("#updated-badge").textContent = "Could not load data/jobs.json";
      $("#job-list").innerHTML = `<div class="empty">No data yet. Run <code>python -m scraper.run</code> (or wait for the GitHub Action) to generate <code>data/jobs.json</code>.</div>`;
      return;
    }
    populateSelects();
    applyFilters();
  }
  document.addEventListener("DOMContentLoaded", init);
})();
