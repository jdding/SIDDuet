const runButton = document.getElementById("run");
const status = document.getElementById("status");
const results = document.getElementById("results");
const worker = new Worker("demo/python-worker.js");
const fixed = value => Number(value).toFixed(4);
const percent = value => (100 * Number(value)).toFixed(2) + "%";

function addRow(id, values) {
  const row = document.createElement("tr");
  for (const value of values) {
    const cell = document.createElement("td");
    cell.textContent = value;
    row.append(cell);
  }
  document.getElementById(id).append(row);
}

function render(result) {
  for (const id of ["topology", "coverage", "metrics", "steps"]) {
    document.getElementById(id).replaceChildren();
  }
  for (const item of result.topology) {
    const cell = item.cell.split("|").map(part => part.startsWith("high") ? "H" : "L").join("");
    addRow("topology", [item.item, item.search_support, item.rec_support,
      fixed(item.rsd), fixed(item.rsi), cell]);
  }
  const coverage = result.coverage;
  addRow("coverage", [`${coverage.joined_items} / ${coverage.topology_items}`,
    percent(coverage.join_coverage), coverage.unique_sid_count]);
  for (const metric of result.metrics) {
    addRow("metrics", [metric.role === "rec" ? "Recommendation" : "Search",
      metric.units, fixed(metric.ndcg10), percent(metric.hit10)]);
  }
  for (const step of result.steps) {
    const item = document.createElement("li");
    item.textContent = step.script + " — " + step.output;
    document.getElementById("steps").append(item);
  }
  document.getElementById("runtime").textContent =
    `Python ${result.python} · ${result.steps.length} source scripts executed · fixture-only results`;
  results.hidden = false;
}

function finish(message, failed = false) {
  status.textContent = message;
  status.className = failed ? "error" : "";
  runButton.disabled = false;
  runButton.textContent = "Run example";
  results.removeAttribute("aria-busy");
}

worker.onmessage = event => {
  const response = event.data;
  if (response.type === "progress") status.textContent = response.message;
  if (response.type === "result") {
    render(response.result);
    finish("Complete. The tables show the result of this run.");
  }
  if (response.type === "error") finish(response.message, true);
};
worker.onerror = event => finish(event.message || "The Python runtime could not start.", true);

runButton.addEventListener("click", () => {
  runButton.disabled = true;
  runButton.textContent = "Running…";
  status.className = "";
  status.textContent = "Starting the example. The first run downloads the Python runtime.";
  results.setAttribute("aria-busy", "true");
  worker.postMessage({action: "run"});
});
