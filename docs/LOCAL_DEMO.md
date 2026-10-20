# Runnable demos

## Online example

Open <https://jdding.github.io/SIDDuet/> and select **Run example**. The browser loads
a pinned Pyodide Python runtime and verifies the source/fixture hashes against the
package manifest. Six actual scripts rebuild counts and topology, join the map,
inspect within-code support and evaluate supplied candidate scores. Each execution
uses a fresh temporary filesystem directory. The page accepts no uploads and needs
no account, provider data, model download or hosted inference service.

The first load needs access to the jsDelivr runtime CDN. The optional local interface
below is available when that network dependency is unsuitable. The fixture demonstrates
software behavior; it does not reproduce the real dataset findings or run all command-line
rejection tests. Use the CLI quickstart for the full source and interface checks.

## Local interface


```sh
python3 -I scripts/serve_demo.py --port 8765
```

Open <http://127.0.0.1:8765> and select **Run synthetic workflow**. Python 3.10+ and the
standard library are sufficient. Each run copies the declared source assets to a fresh
temporary directory, executes the fixed synthetic command and removes the temporary files.
The page displays the eight-item topology, map coverage, fixed-candidate metrics and
interface checks. It accepts no uploads or custom commands and binds to loopback by default.
Stop it with Ctrl-C.

The demo checks software interfaces. Real-data results and replay instructions are in the
[result guide](../reports/README.md). This is a locally runnable interface, not a hosted model
service. No model weights or provider inputs are needed for it.
