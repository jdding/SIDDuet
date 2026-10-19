#!/usr/bin/env python3
"""Check exact checkpoint reconstruction, tamper failure and path confinement."""

from pathlib import Path
import sys, tempfile, json, hashlib, unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from assemble_checkpoint import assemble


class AssemblyTest(unittest.TestCase):
    def fixture(self, p):
        payload = [b"first\x00tensor", b"second\xfftensor"]
        parts = []
        for i, b in enumerate(payload):
            f = p / f"part-{i}"
            f.write_bytes(b)
            parts.append({"path": f.name, "bytes": len(b), "sha256": hashlib.sha256(b).hexdigest()})
        allbytes = b"".join(payload)
        m = {
            "schema": "sr_sid_rolemap.checkpoint_parts.v1",
            "bytes": len(allbytes),
            "sha256": hashlib.sha256(allbytes).hexdigest(),
            "parts": parts,
        }
        f = p / "manifest.json"
        f.write_text(json.dumps(m))
        return f, m, allbytes

    def test_exact_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            manifest, _, expected = self.fixture(p)
            out = p / "out.pt"
            assemble(manifest, out)
            self.assertEqual(out.read_bytes(), expected)
            with self.assertRaises(ValueError):
                assemble(manifest, out)

    def test_tamper_does_not_leave_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            manifest, _, _ = self.fixture(p)
            (p / "part-1").write_bytes(b"changed")
            out = p / "out.pt"
            with self.assertRaises(ValueError):
                assemble(manifest, out)
            self.assertFalse(out.exists())
            self.assertFalse((p / "out.pt.partial").exists())

    def test_path_escape(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            manifest, m, _ = self.fixture(p)
            m["parts"][0]["path"] = "../escape"
            manifest.write_text(json.dumps(m))
            with self.assertRaisesRegex(ValueError, "escapes"):
                assemble(manifest, p / "out.pt")


if __name__ == "__main__":
    unittest.main()
