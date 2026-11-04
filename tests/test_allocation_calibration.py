"""Fabricated, isolated CLI tests for generic paired-count calibration."""
import csv
import hashlib
import json
import math
from pathlib import Path
import runpy
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/calibrate_task_allocation.py"
METRICS = ("equal_group_jsd", "item_weighted_jsd", "observation_weighted_jsd",
           "equal_group_disjoint", "item_weighted_disjoint", "observation_weighted_disjoint")


def independent_metrics(pairs, groups):
    values = []
    for members in groups:
        if len(members) < 2:
            continue
        s, r = zip(*(pairs[i] for i in members))
        ps, pr = [v / sum(s) for v in s], [v / sum(r) for v in r]
        js = sum(v * math.log2(v / ((a + b) / 2)) / 2
                 for a, b in zip(ps, pr) for v in (a, b))
        overlap = any(a == max(s) and b == max(r) for a, b in zip(s, r))
        values.append((js, float(not overlap), len(members), sum(s) + sum(r)))
    if not values:
        return dict.fromkeys(METRICS)
    js, dis, n, events = zip(*values)
    weighted = lambda vals, weights: sum(v * w for v, w in zip(vals, weights)) / sum(weights)
    return dict(zip(METRICS, (sum(js) / len(js), weighted(js, n), weighted(js, events),
                             sum(dis) / len(dis), weighted(dis, n), weighted(dis, events))))


class AllocationCalibration(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.counts = self.base / "counts.csv"
        self.mapping = self.base / "map.csv"
        self.dataset = "any dataset/中文"
        self.pairs = [(9, 1), (1, 9), (5, 5), (5, 5), (2, 3), (3, 2)]
        self.ids = ["private-" + str(i) for i in range(len(self.pairs))]
        self.count_rows = [[self.dataset, item, role, "label", count]
                           for item, pair in zip(self.ids, self.pairs)
                           for role, count in zip(("search", "rec"), pair)]
        self.map_rows = [[self.dataset, item, "group" + str(i // 2)]
                         for i, item in enumerate(self.ids)]
        self.write(self.counts, ["dataset", "item_id", "role", "label", "count"], self.count_rows)
        self.write(self.mapping, ["dataset", "item_id", "sid"], self.map_rows)

    def write(self, path, header, rows):
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(header)
            writer.writerows(rows)

    def command(self, maps=None, draws=19, suffix="", extra=()):
        output, flat = self.base / ("result" + suffix + ".json"), self.base / ("result" + suffix + ".csv")
        args = [sys.executable, "-I", "-B", str(SCRIPT), "--role-counts", str(self.counts),
                "--draws", str(draws), "--seed", "20261104", "--out-json", str(output),
                "--out-csv", str(flat)]
        for name, path in maps or [("view with space 中文", self.mapping)]:
            args += ["--sid-map", name + "=" + str(path)]
        return args + list(extra), output, flat

    def success(self, **kwargs):
        args, output, flat = self.command(**kwargs)
        process = subprocess.run(args, cwd=self.base, text=True, capture_output=True)
        self.assertEqual(process.returncode, 0, process.stderr)
        with flat.open(newline="") as handle:
            rows = list(csv.DictReader(handle))
        return json.loads(output.read_text()), rows

    def failure(self, **kwargs):
        args, output, flat = self.command(**kwargs)
        process = subprocess.run(args, cwd=self.base, text=True, capture_output=True)
        self.assertNotEqual(process.returncode, 0)
        self.assertFalse(output.exists())
        self.assertFalse(flat.exists())
        return process

    def test_analytic_six_metrics_and_aggregate_only_provenance(self):
        result, rows = self.success()
        record = result["results"][0]
        expected = independent_metrics(self.pairs, [[0, 1], [2, 3], [4, 5]])
        for key, value in expected.items():
            self.assertAlmostEqual(record["observed"][key], value, places=14)
        self.assertEqual(len(rows), 2)
        self.assertEqual(result["inputs"]["role_counts"]["sha256"], hashlib.sha256(self.counts.read_bytes()).hexdigest())
        self.assertEqual(result["runtime"]["numpy"], np.__version__)
        self.assertEqual(len(result["implementation"]), 3)
        self.assertTrue(result["inputs_rehashed_after"])
        for private in self.ids + [row[2] for row in self.map_rows]:
            self.assertNotIn('"' + private + '"', json.dumps(result))
        self.assertEqual(record["counts"]["collision_groups"], 3)
        for row in rows:
            self.assertAlmostEqual(float(row["observed_equal_group_jsd"]), expected["equal_group_jsd"], places=14)

    def test_tied_leader_sets_overlap_even_when_first_leaders_differ(self):
        self.pairs = [(4, 1), (4, 4), (1, 4)]
        rows = [[self.dataset, str(i), role, "x", count] for i, pair in enumerate(self.pairs)
                for role, count in zip(("search", "rec"), pair)]
        self.write(self.counts, ["dataset", "item_id", "role", "label", "count"], rows)
        self.write(self.mapping, ["dataset", "item_id", "sid"], [[self.dataset, str(i), "same"] for i in range(3)])
        result, _ = self.success()
        self.assertEqual(result["results"][0]["observed"]["equal_group_disjoint"], 0)

    def test_aggregation_exclusion_unused_and_exact_dataset_keys(self):
        rows = self.count_rows + [[self.dataset, "only-search", "search", "a", 4],
                                 [self.dataset, "zero", "search", "a", 0],
                                 [self.dataset, "zero", "rec", "a", 3]]
        # Replace one row by two labels and repeated rows without changing support.
        rows = rows[1:] + [[self.dataset, self.ids[0], "search", "b", 4],
                          [self.dataset, self.ids[0], "search", "b", 2],
                          [self.dataset, self.ids[0], "search", "c", 3]]
        self.write(self.counts, ["dataset", "item_id", "role", "label", "count"], rows)
        self.write(self.mapping, ["dataset", "item_id", "sid"], self.map_rows + [["other", self.ids[0], "extra"]])
        result, _ = self.success()
        self.assertEqual(result["cohorts"][0]["common_items"], 6)
        self.assertEqual(result["cohorts"][0]["excluded_items"], 2)
        self.assertEqual(result["map_coverage"][0]["unused_rows"], 1)
        expected = independent_metrics(self.pairs, [[0, 1], [2, 3], [4, 5]])
        for metric in METRICS:
            self.assertAlmostEqual(result["results"][0]["observed"][metric], expected[metric], places=14)
        self.write(self.mapping, ["dataset", "item_id", "sid"], self.map_rows[1:] + [["other", self.ids[0], "extra"]])
        self.failure(suffix="missing")

    def test_singletons_structural_controls_and_degenerate_references(self):
        # Distinct totals force exact-total reference to be the identity.
        pairs = [(1, 1), (1, 2), (1, 3)]
        self.write(self.counts, ["dataset", "item_id", "role", "label", "count"],
                   [["new", str(i), role, "x", count] for i, pair in enumerate(pairs)
                    for role, count in zip(("search", "rec"), pair)])
        self.write(self.mapping, ["dataset", "item_id", "sid"], [["new", str(i), "a" if i < 2 else "b"] for i in range(3)])
        singleton = self.base / "singleton.csv"
        self.write(singleton, ["dataset", "item_id", "sid"], [["new", str(i), str(i)] for i in range(3)])
        result, _ = self.success(maps=[("collision", self.mapping), ("control", singleton)])
        collision, control = result["results"]
        self.assertEqual(collision["counts"]["collision_items"], 2)
        self.assertEqual(collision["references"]["exact_total"]["primary_p"], 1)
        self.assertEqual(control["status"], "STRUCTURAL_NONCOLLISION_CONTROL")
        self.assertTrue(all(v is None for v in control["observed"].values()))
        for ref in control["references"].values():
            self.assertIsNone(ref["primary_p"])
            self.assertIsNone(ref["primary_bh_q"])
            self.assertIsNone(ref["metrics"]["equal_group_jsd"]["mean"])
        self.assertTrue(all(family["size"] == 1 for family in result["multiplicity_families"]))
        only_control, _ = self.success(maps=[("control", singleton)], suffix="control-only")
        self.assertTrue(all(family["size"] == 0 for family in only_control["multiplicity_families"]))

    def test_row_order_map_order_and_identical_views_share_draws(self):
        first, _ = self.success(maps=[("z", self.mapping), ("a", self.mapping)])
        self.write(self.counts, ["dataset", "item_id", "role", "label", "count"], list(reversed(self.count_rows)))
        self.write(self.mapping, ["dataset", "item_id", "sid"], list(reversed(self.map_rows)))
        second, _ = self.success(maps=[("a", self.mapping), ("z", self.mapping)], suffix="reverse")
        self.assertEqual(first["results"], second["results"])
        self.assertEqual(first["results"][0]["references"], first["results"][1]["references"])
        one, _ = self.success(maps=[("a", self.mapping)], suffix="one")
        for ref in ("band", "exact_total"):
            self.assertEqual(first["results"][0]["references"][ref]["metrics"], one["results"][0]["references"][ref]["metrics"])

    def test_multiple_arbitrary_datasets(self):
        self.write(self.counts, ["dataset", "item_id", "role", "label", "count"],
                   self.count_rows + [["second:cohort", *row[1:]] for row in self.count_rows])
        self.write(self.mapping, ["dataset", "item_id", "sid"],
                   self.map_rows + [["second:cohort", *row[1:]] for row in self.map_rows])
        result, _ = self.success()
        self.assertEqual(len(result["results"]), 2)
        self.assertTrue(all(f["size"] == 2 for f in result["multiplicity_families"]))

    def test_reference_means_ranges_p_and_adjustment_against_independent_calculations(self):
        # Unequal groups and singleton pool members detect frozen observation-volume weights.
        pairs = [(9, 1), (1, 8), (3, 5), (7, 1), (4, 5), (1, 10), (11, 1)]
        groups = [[0, 1], [2, 3, 4], [5], [6]]
        self.write(self.counts, ["dataset", "item_id", "role", "label", "count"],
                   [[self.dataset, str(i), role, "x", count] for i, pair in enumerate(pairs)
                    for role, count in zip(("search", "rec"), pair)])
        self.write(self.mapping, ["dataset", "item_id", "sid"],
                   [[self.dataset, str(i), str(g)] for g, members in enumerate(groups) for i in members])
        result, _ = self.success(draws=31, maps=[("a", self.mapping), ("b", self.mapping)])
        observed = independent_metrics(pairs, groups)
        for reference in ("band", "exact_total"):
            material = json.dumps(["sidduet.count_reference.v1", 20261104, self.dataset, reference],
                                  ensure_ascii=False, separators=(",", ":")).encode()
            stream = int.from_bytes(hashlib.sha256(material).digest(), "big")
            rng = np.random.Generator(np.random.PCG64(stream))
            keys = [(s + r).bit_length() - 1 if reference == "band" else s + r for s, r in pairs]
            simulations = []
            for _ in range(31):
                order = list(range(len(pairs)))
                for key in sorted(set(keys)):
                    slots = [i for i, value in enumerate(keys) if value == key]
                    for slot, source in zip(slots, rng.permutation(slots)):
                        order[slot] = int(source)
                simulations.append(independent_metrics([pairs[i] for i in order], groups))
            actual = result["results"][0]["references"][reference]
            for metric in METRICS:
                values = [sample[metric] for sample in simulations]
                self.assertAlmostEqual(actual["metrics"][metric]["mean"], sum(values) / len(values), places=14)
                expected_range = np.percentile(values, [2.5, 97.5])
                for a, e in zip(actual["metrics"][metric]["central_95pct"], expected_range):
                    self.assertAlmostEqual(a, e, places=14)
            # Independent arithmetic, inclusive ties; duplicate views give equal BH q=p, BY=min(1,1.5p).
            primary_values = [sample["equal_group_jsd"] for sample in simulations]
            obs = observed["equal_group_jsd"]
            # Avoid asserting a tail boundary when Python/NumPy differ by a final bit.
            greater = sum(value > obs or math.isclose(value, obs, abs_tol=1e-14) for value in primary_values)
            less = sum(value < obs or math.isclose(value, obs, abs_tol=1e-14) for value in primary_values)
            p = min(1, 2 * min((1 + greater) / 32, (1 + less) / 32))
            self.assertAlmostEqual(actual["primary_p"], p, places=14)
            self.assertAlmostEqual(actual["primary_bh_q"], p, places=14)
            self.assertAlmostEqual(actual["primary_by_q"], min(1, p * 1.5), places=14)

    def test_pair_band_exact_preservation_and_one_permutation_per_draw(self):
        namespace = runpy.run_path(str(SCRIPT))
        pop = namespace["POP"]
        real_permute, real_stats = pop.paired_permutation_indices, pop.group_stats
        self.assertEqual(pop.support_bands(np.array([1, 1, 1, 1, 1]),
                                          np.array([1, 2, 3, 6, 7])).tolist(), [1, 1, 2, 2, 3])
        calls, states = [], []
        def permutation(keys, rng):
            perm = real_permute(keys, rng)
            self.assertEqual(sorted(perm.tolist()), list(range(len(keys))))
            self.assertTrue(np.array_equal(keys, keys[perm]))
            calls.append(keys.copy())
            return perm
        def stats(s, r, groups, sizes):
            self.assertEqual(sorted(zip(map(int, s), map(int, r))), sorted(self.pairs))
            states.append((s.copy(), r.copy()))
            return real_stats(s, r, groups, sizes)
        args, _, _ = self.command(maps=[("one", self.mapping), ("two", self.mapping)], draws=7)
        with patch.object(pop, "paired_permutation_indices", side_effect=permutation), patch.object(pop, "group_stats", side_effect=stats), patch.object(sys, "argv", args[3:]):
            namespace["main"]()
        self.assertEqual(len(calls), 14)
        # Observed views then each shared permuted view, including singleton slots.
        for index in range(2, len(states), 2):
            self.assertTrue(np.array_equal(states[index][0], states[index + 1][0]))
            self.assertTrue(np.array_equal(states[index][1], states[index + 1][1]))
        band = [int(s + r).bit_length() - 1 for s, r in self.pairs]
        total = [s + r for s, r in self.pairs]
        self.assertEqual(calls[0].tolist(), band)
        self.assertEqual(calls[7].tolist(), total)

    def test_rejects_bad_counts_empty_cohorts_and_unsafe_sums(self):
        bad_rows = ([self.dataset, "x", "search", "x", "-1"],
                    [self.dataset, "x", "search", "x", "1.5"],
                    [self.dataset, "x", "search", "x", "NaN"],
                    [self.dataset, "x", "other", "x", "1"],
                    [self.dataset, "x", "search", "x", str(2**53)])
        for i, row in enumerate(bad_rows):
            self.write(self.counts, ["dataset", "item_id", "role", "label", "count"], self.count_rows + [row])
            self.failure(suffix=str(i))
        self.write(self.counts, ["dataset", "item_id", "role", "label", "count"], [["empty", "x", "search", "x", 1]])
        self.failure(suffix="empty")
        self.counts.write_text("dataset,item_id,role,label,count\nx,y,search,z,1,extra\n")
        self.failure(suffix="width")

    def test_rejects_duplicate_invalid_names_bad_maps_and_draws(self):
        for i, name in enumerate(("", " ", "a=b", "a\nb")):
            self.failure(maps=[(name, self.mapping)], suffix="name" + str(i))
        self.failure(maps=[("same", self.mapping), ("same", self.mapping)], suffix="duplicate")
        self.failure(draws=0, suffix="draws")
        for i, body in enumerate(("dataset,item_id,sid\nx,y,\n", "dataset,item_id,sid\nx,y,a\nx,y,a\n")):
            self.mapping.write_text(body)
            self.failure(suffix="map" + str(i))

    def test_existing_alias_and_input_outputs_never_overwritten(self):
        args, output, flat = self.command()
        output.write_text("sentinel")
        process = subprocess.run(args, cwd=self.base, capture_output=True)
        self.assertNotEqual(process.returncode, 0)
        self.assertEqual(output.read_text(), "sentinel")
        self.assertFalse(flat.exists())
        output.unlink()
        for extra in (("--out-csv", str(output)), ("--out-json", str(self.counts))):
            process = subprocess.run(args + list(extra), cwd=self.base, capture_output=True)
            self.assertNotEqual(process.returncode, 0)
            self.assertFalse(output.exists())
            self.assertFalse(flat.exists())
        flat.symlink_to(self.mapping)
        original_map = self.mapping.read_bytes()
        process = subprocess.run(args, cwd=self.base, capture_output=True)
        self.assertNotEqual(process.returncode, 0)
        self.assertFalse(output.exists())
        self.assertEqual(self.mapping.read_bytes(), original_map)


if __name__ == "__main__":
    unittest.main()
