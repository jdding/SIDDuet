const PYODIDE_BASE = "https://cdn.jsdelivr.net/pyodide/v314.0.7/full/";
const FILES = [
  "demo/browser_example.py",
  "scripts/materialize_role_label_counts.py",
  "scripts/build_role_topology.py",
  "scripts/admit_sid_family.py",
  "scripts/evaluate_collision_diagnostic.py",
  "scripts/adapt_method_scores.py",
  "scripts/evaluate_fixed_candidates.py",
  "docs/TOPOLOGY_PROFILE_V2_CONTRACT.md",
  "samples/synthetic_role_events.csv",
  "samples/synthetic_sid_map.csv",
  "samples/synthetic_method_scores.csv",
];

let runtime;

async function initialize(base) {
  postMessage({type: "progress", message: "Loading Python in your browser…"});
  importScripts(PYODIDE_BASE + "pyodide.js");
  const python = await loadPyodide({indexURL: PYODIDE_BASE});
  const response = await fetch(new URL("PACKAGE_MANIFEST.json", base));
  if (!response.ok) throw new Error("The resource manifest is unavailable.");
  const manifest = await response.json();
  const hashes = new Map(manifest.files.map(row => [row.path, row.sha256]));

  postMessage({type: "progress", message: "Checking the example source and fixtures…"});
  for (const path of FILES) {
    const resource = await fetch(new URL(path, base));
    if (!resource.ok) throw new Error("Could not load " + path);
    const bytes = new Uint8Array(await resource.arrayBuffer());
    const digest = new Uint8Array(await crypto.subtle.digest("SHA-256", bytes));
    const actual = Array.from(digest, byte => byte.toString(16).padStart(2, "0")).join("");
    if (hashes.get(path) !== actual) throw new Error("Source integrity check failed: " + path);
    const target = "/rolemap/" + path;
    python.FS.mkdirTree(target.slice(0, target.lastIndexOf("/")));
    python.FS.writeFile(target, bytes);
  }
  return python;
}

onmessage = async event => {
  try {
    const base = new URL("../", self.location.href);
    runtime ??= initialize(base);
    const python = await runtime;
    postMessage({type: "progress", message: "Running counts, topology, code groups and scores…"});
    const result = await python.runPythonAsync(`
import json, runpy
example = runpy.run_path('/rolemap/demo/browser_example.py')
json.dumps(example['run_example']())
`);
    postMessage({type: "result", result: JSON.parse(result)});
  } catch (error) {
    runtime = undefined;
    postMessage({type: "error", message: String(error.message || error)});
  }
};
