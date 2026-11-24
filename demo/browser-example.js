const runButton = document.getElementById("run");
const status = document.getElementById("status");
const results = document.getElementById("results");
const groupSelect = document.getElementById("group-select");
const tabs = Array.from(document.querySelectorAll("[data-tab]"));
const panels = Array.from(document.querySelectorAll("[data-panel]"));

const worker = new Worker("demo/python-worker.js", {type: "module"});
const fixed = (value, digits = 3) => Number(value).toFixed(digits);
const percent = value => (100 * Number(value)).toFixed(2) + "%";

let lastResult = null;

function addRow(id, values) {
  const row = document.createElement("tr");
  for (const value of values) {
    const cell = document.createElement("td");
    cell.textContent = value;
    row.append(cell);
  }
  document.getElementById(id).append(row);
}

function setActiveTab(name) {
  for (const btn of tabs) {
    const active = btn.dataset.tab === name;
    btn.classList.toggle("active", active);
    btn.setAttribute("aria-selected", active ? "true" : "false");
  }
  for (const panel of panels) {
    panel.hidden = panel.dataset.panel !== name;
  }
}

for (const btn of tabs) {
  btn.addEventListener("click", () => setActiveTab(btn.dataset.tab));
}

function renderMemberBars(group) {
  const container = document.getElementById("member-bars");
  container.replaceChildren();
  const note = document.getElementById("member-note");
  note.textContent =
    `${group.sid}: ${group.size} items · Allocation JSD = ${fixed(group.allocation_jsd, 3)} · ` +
    `Search leader ${group.search_leader} (${percent(group.search_leader_share)}) vs. ` +
    `Rec. leader ${group.rec_leader} (${percent(group.rec_leader_share)})`;

  for (const member of group.members) {
    const row = document.createElement("div");
    row.className = "bar-row";

    const label = document.createElement("div");
    label.className = "bar-label";
    const badges = [];
    if (member.is_search_leader) badges.push("S-leader");
    if (member.is_rec_leader) badges.push("R-leader");
    label.textContent = member.item + (badges.length ? ` (${badges.join(", ")})` : "");

    const tracks = document.createElement("div");
    tracks.className = "bar-tracks";

    for (const [cls, tag, share, count] of [
      ["search", "Search", member.search_share, member.search_count],
      ["rec", "Rec.", member.rec_share, member.rec_count],
    ]) {
      const line = document.createElement("div");
      line.className = "bar-line";
      const fill = document.createElement("span");
      fill.className = `bar-fill ${cls}`;
      fill.style.width = `${Math.max(2, share * 100).toFixed(1)}%`;
      const val = document.createElement("span");
      val.className = "bar-val";
      val.textContent = `${tag} ${percent(share)} (n=${count})`;
      line.append(fill, val);
      tracks.append(line);
    }

    row.append(label, tracks);
    container.append(row);
  }
}

if (groupSelect) {
  groupSelect.addEventListener("change", () => {
    if (!lastResult) return;
    const chosen = lastResult.workflow1.groups.find(g => g.sid === groupSelect.value);
    if (chosen) renderMemberBars(chosen);
  });
}

function render(result) {
  lastResult = result;
  for (const id of [
    "wf1-groups", "wf1-cal", "wf1-table2",
    "wf2-synth-metrics", "wf2-table3",
    "wf3-synth", "wf3-table4", "wf3-cohort", "steps",
  ]) {
    document.getElementById(id).replaceChildren();
  }

  // Workflow 1: Shared-code groups & count-matched calibration
  const wf1 = result.workflow1;
  groupSelect.replaceChildren();
  for (const g of wf1.groups) {
    addRow("wf1-groups", [
      g.sid,
      g.size,
      g.search_total,
      g.rec_total,
      fixed(g.allocation_jsd, 3),
      `${g.search_leader} (${percent(g.search_leader_share)})`,
      `${g.rec_leader} (${percent(g.rec_leader_share)})`,
      g.disjoint_leaders ? "Yes" : "No",
    ]);
    const opt = document.createElement("option");
    opt.value = g.sid;
    opt.textContent = `${g.sid} (${g.size} items, JSD ${fixed(g.allocation_jsd, 3)})`;
    groupSelect.append(opt);
  }
  if (wf1.groups.length) renderMemberBars(wf1.groups[0]);

  addRow("wf1-cal", [
    "Observed (synthetic 8-item fixture)",
    fixed(wf1.observed_mean_jsd, 3),
    percent(wf1.observed_disjoint_rate),
    `${wf1.collision_groups} groups`,
  ]);
  addRow("wf1-cal", [
    `Band-matched reference (${wf1.band_reference.draws} draws)`,
    fixed(wf1.band_reference.mean_jsd, 3),
    percent(wf1.band_reference.mean_disjoint_rate),
    `${wf1.band_reference.strata} log2 bands`,
  ]);
  addRow("wf1-cal", [
    `Exact-total reference (${wf1.exact_reference.draws} draws)`,
    fixed(wf1.exact_reference.mean_jsd, 3),
    percent(wf1.exact_reference.mean_disjoint_rate),
    `${wf1.exact_reference.strata} exact totals`,
  ]);

  const dsNames = {kuaisar: "KuaiSAR", qilin: "Qilin"};
  const mapNames = {"grid": "GRID", "rq-vae": "RQ-VAE", "resid-gaoq": "ReSID-GAOQ"};
  for (const row of result.table2) {
    addRow("wf1-table2", [
      dsNames[row.dataset] || row.dataset,
      mapNames[row.mapping] || row.mapping,
      Number(row.groups).toLocaleString("en-US"),
      row.observed_jsd,
      row.band_mean,
      row.exact_total_mean,
      row.disjoint_leaders,
    ]);
  }

  // Workflow 2: Prediction coverage & ranking
  for (const m of result.metrics) {
    addRow("wf2-synth-metrics", [
      m.role === "rec" ? "Recommendation" : "Search",
      `${m.covered_units} / ${m.units} (${percent(m.covered_units / m.units)})`,
      fixed(m.ndcg10),
      m.covered_ndcg10 === null ? "—" : fixed(m.covered_ndcg10),
    ]);
  }
  for (const row of result.table3) {
    addRow("wf2-table3", [
      row.task,
      `${row.covered_requests.toLocaleString("en-US")} / ${row.total_requests.toLocaleString("en-US")} (${fixed(row.paired_coverage_pct, 2)}%)`,
      fixed(row.full_ndcg10, 3),
      fixed(row.covered_ndcg10, 3),
      `[${fixed(row.diff_ci95[0], 3)}, ${fixed(row.diff_ci95[1], 3)}]`,
    ]);
  }

  // Workflow 3: Temporal pooling comparison
  const ps = result.pooling_synthetic;
  for (const [label, row] of [
    [`Pooled (α=${ps.pooled.alpha})`, ps.pooled],
    [`Separate (α=${ps.task_conditioned.alpha})`, ps.task_conditioned],
    [`Shrinkage (β=${ps.shrinkage.beta})`, ps.shrinkage],
  ]) {
    addRow("wf3-synth", [
      label,
      fixed(row.macro_loss),
      fixed(row.search_loss),
      fixed(row.rec_loss),
    ]);
  }

  const fmtCell = (delta, ci) => `${fixed(delta, 3)} [${fixed(ci[0], 3)}, ${fixed(ci[1], 3)}]`;
  for (const row of result.table4) {
    if (row.control) {
      addRow("wf3-table4", [row.view, "— (collision-free)", "— (collision-free)"]);
    } else {
      addRow("wf3-table4", [
        row.view,
        fmtCell(row.first_delta_mnats, row.first_ci_mnats),
        fmtCell(row.second_delta_mnats, row.second_ci_mnats),
      ]);
    }
  }
  for (const row of result.cohort_sensitivity) {
    addRow("wf3-cohort", [
      row.window,
      row.groups.toLocaleString("en-US"),
      row.scored_requests.toLocaleString("en-US"),
      fmtCell(row.delta_mnats, row.ci_mnats),
    ]);
  }

  for (const step of result.steps) {
    const item = document.createElement("li");
    item.textContent = step.script + " — " + step.output;
    document.getElementById("steps").append(item);
  }
  document.getElementById("runtime").textContent =
    `Python ${result.python} · SIDDuet ${result.version} · ${result.steps.length} release scripts executed with SHA-256 verification`;
  results.hidden = false;
}

function finish(message, failed = false) {
  status.textContent = message;
  status.className = failed ? "error" : "";
  runButton.disabled = false;
  runButton.textContent = "Run all three workflows";
  results.removeAttribute("aria-busy");
}

worker.onmessage = event => {
  const response = event.data;
  if (response.type === "progress") status.textContent = response.message;
  if (response.type === "result") {
    render(response.result);
    finish("Complete. Synthetic examples ran for all three workflows.");
  }
  if (response.type === "error") finish(response.message, true);
};
worker.onerror = event => finish(event.message || "The Python runtime could not start.", true);

runButton.addEventListener("click", () => {
  runButton.disabled = true;
  runButton.textContent = "Running…";
  status.className = "";
  results.setAttribute("aria-busy", "true");
  worker.postMessage({type: "run"});
});
