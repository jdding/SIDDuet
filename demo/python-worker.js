const PYODIDE_BASE = "https://cdn.jsdelivr.net/pyodide/v314.0.7/full/";
const FILES = [
  "demo/browser_example.py",
  "scripts/materialize_role_label_counts.py",
  "scripts/build_role_topology.py",
  "scripts/sid_map_io.py",
  "scripts/admit_sid_family.py",
  "scripts/evaluate_collision_diagnostic.py",
  "scripts/adapt_method_scores.py",
  "scripts/evaluate_fixed_candidates.py",
  "scripts/verify_table2.py",
  "docs/TOPOLOGY_PROFILE_V2_CONTRACT.md",
  "samples/synthetic_role_events.csv",
  "samples/synthetic_sid_map.csv",
  "samples/synthetic_prediction_coverage_scores.csv",
  "reports/diagnostics_mc1999_20261020/TABLE2_NULL_MEANS.json",
  "reports/diagnostics_mc1999_20261020/MC1999_RESULTS.json",
  "reports/model_reuse/RESULTS.json",
  "analysis/reuse_validation/results/two_window_sensitivity/TWO_WINDOW_SENSITIVITY.json",
  "reports/cohort_sensitivity/RESULTS.json",
];

let runtime;

async function initialize(base) {
  postMessage({type: "progress", message: "Loading Python in your browser…"});
  const {loadPyodide} = await import(PYODIDE_BASE + "pyodide.mjs");
  const python = await loadPyodide({indexURL: PYODIDE_BASE});
  const response = await fetch(new URL("PACKAGE_MANIFEST.json", base));
  if (!response.ok) throw new Error("The resource manifest is unavailable.");
  const manifest = await response.json();
  const hashes = new Map(manifest.files.map(row => [row.path, row.sha256]));

  postMessage({type: "progress", message: `Verifying SHA-256 hashes for ${FILES.length} release files…`});
  for (const path of FILES) {
    const resource = await fetch(new URL(path, base));
    if (!resource.ok) throw new Error("Could not load " + path);
    const bytes = new Uint8Array(await resource.arrayBuffer());
    const digest = new Uint8Array(await crypto.subtle.digest("SHA-256", bytes));
    const actual = Array.from(digest, byte => byte.toString(16).padStart(2, "0")).join("");
    if (hashes.get(path) !== actual) throw new Error("Source integrity check failed: " + path);
    const target = "/sidduet/" + path;
    python.FS.mkdirTree(target.slice(0, target.lastIndexOf("/")));
    python.FS.writeFile(target, bytes);
  }
  return python;
}

self.onmessage = async event => {
  try {
    const base = new URL("../", self.location.href);
    runtime ??= initialize(base);
    const python = await runtime;
    postMessage({type: "progress", message: "Running shared-code calibration, Table 2 verification, coverage and pooling…"});
    const result = await python.runPythonAsync(`
import json, runpy
example = runpy.run_path('/sidduet/demo/browser_example.py')
json.dumps(example['run_example']())
`);
    postMessage({type: "result", result: JSON.parse(result)});
  } catch (error) {
    runtime = undefined;
    postMessage({type: "error", message: String(error.message || error)});
  }
};
