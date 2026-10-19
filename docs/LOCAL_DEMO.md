# Local runnable demo

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
