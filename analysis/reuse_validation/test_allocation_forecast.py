"""Synthetic tests only: no provider, native mapping, or audit files are opened."""
import argparse
import copy
import csv
import json
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
import allocation_forecast as a


def row(name, role, items, split='train', user=None, start=0):
    return dict(request_hash=name, user_hash=user or name, role=role, split=split,
                timestamp_start=start, timestamp_end=start + .1,
                exposed_item_ids=items, clicked_item_ids=[])


def fixture():
    return a.Mapping('gensar_shared2', {'a': 'g1', 'b': 'g1', 'c': 'g2', 'd': 'g2', 'z': 'single'})


class AllocationTests(unittest.TestCase):
    def test_request_group_and_member_weights(self):
        m = fixture()
        e = a.encode([row('x', 'search', ['a', 'b', 'c', 'z'])], m)
        np.testing.assert_allclose(e['weights'], [.25, .25, .5])
        self.assertEqual(e['weights'].sum(), 1.)
        counts, totals = a.count_training(e, m)
        self.assertAlmostEqual(counts.sum(), 1.)
        self.assertAlmostEqual(totals.sum(), 1.)
        self.assertEqual(e['coverage']['search']['collision_member_appearances'], 3)

    def test_duplicate_exposures_read_deduplicates(self):
        with tempfile.TemporaryDirectory() as t:
            p = Path(t) / 'train.jsonl'
            p.write_text(json.dumps(row('x', 'search', ['b', 'a', 'a'])) + '\n')
            self.assertEqual(a.read_requests(p, 'train')[0]['exposed_item_ids'], ['a', 'b'])

    def test_uniform_zero_and_one_role_normalization(self):
        m = fixture()
        zero = np.zeros(len(m.items))
        for alpha in a.GRID:
            p = a.categorical(zero, m, alpha)
            np.testing.assert_allclose(p, m.uniform)
            counts = np.asarray([9., 1., 0., 0., 0.])
            q = a.categorical(counts, m, alpha)
            a.verify_probabilities(np.vstack([p, q]), m)
            self.assertEqual(q[m.item_index['c']], .5)
            self.assertEqual(q[m.item_index['z']], 1.)

    def test_loss_exact_and_macro_equal_roles(self):
        m = fixture()
        rs = [row('s', 'search', ['a', 'b', 'c'])]
        rs += [row('r' + str(i), 'rec', ['a']) for i in range(3)]
        e = a.encode(rs, m)
        p = np.vstack([m.uniform, m.uniform])
        losses = a.request_losses(e, p)
        np.testing.assert_allclose(losses, math.log(2))
        sm = a.summarize_losses(np.asarray([4., 1., 1., 1.]), e)
        self.assertEqual(sm['macro'], 2.5)

    def test_no_collision_control(self):
        m = a.Mapping('unique', {'a': '1', 'b': '2'})
        r = a.fit_view([row('x', 'search', ['a'])], [], m)
        self.assertEqual(r['status'], 'NO_COLLISION_CONTROL')
        self.assertEqual(r['train_coverage']['search']['singleton_only_requests'], 1)
        self.assertNotIn('blind_probabilities', r)

    def test_validation_selects_without_test(self):
        m = fixture()
        train = [row('s' + str(i), 'search', ['a']) for i in range(5)]
        train += [row('r' + str(i), 'rec', ['b']) for i in range(5)]
        validation = [row('vs', 'search', ['a'], 'validation'), row('vr', 'rec', ['b'], 'validation')]
        result = a.fit_view(train, validation, m)
        self.assertNotEqual(result['selected_aware']['kind'], 'fallback')
        self.assertLess(result['selected_aware']['validation']['macro'], result['selected_blind']['validation']['macro'])
        self.assertEqual(len(result['validation_candidates']), 21)
        # Heldout outcomes are not an argument and cannot change selection.
        again = a.fit_view(train, validation, m)
        self.assertEqual(result['selected_aware'], again['selected_aware'])

    def test_role_swap_invariance(self):
        m = fixture()
        tr = [row('1', 'search', ['a']), row('2', 'search', ['a', 'c']), row('3', 'rec', ['b'])]
        va = [row('4', 'search', ['a']), row('5', 'rec', ['b', 'd'])]
        original = a.fit_view(tr, va, m)
        def swap(rows):
            other = copy.deepcopy(rows)
            for r in other:
                r['role'] = 'rec' if r['role'] == 'search' else 'search'
            return other
        mirrored = a.fit_view(swap(tr), swap(va), m)
        self.assertEqual(original['selected_blind']['kind'], mirrored['selected_blind']['kind'])
        self.assertAlmostEqual(original['selected_aware']['validation']['macro'], mirrored['selected_aware']['validation']['macro'])
        np.testing.assert_allclose(np.asarray(original['aware_probabilities'])[::-1], mirrored['aware_probabilities'])

    def test_deterministic_ties(self):
        val = dict(search=1., rec=1., macro=1.)
        blind = [dict(kind='balanced', alpha=.1, validation=val), dict(kind='pooled', alpha=100., validation=val), dict(kind='pooled', alpha=.1, validation=val)]
        self.assertEqual(a.choose(blind)['alpha'], .1)
        self.assertEqual(a.choose(blind)['kind'], 'pooled')
        aware = [dict(kind='separate', alpha=.1, validation=val), dict(kind='shrinkage', beta=.1, validation=val), dict(kind='shrinkage', beta=1000., validation=val)]
        self.assertEqual(a.choose(aware, True)['beta'], 1000.)
        aware.append(dict(kind='fallback', validation=val))
        self.assertEqual(a.choose(aware, True)['kind'], 'fallback')

    def test_user_cluster_preserves_roles_and_dependence(self):
        rows = [row('1', 'search', ['a'], user='u1'), row('2', 'rec', ['a'], user='u1'),
                row('3', 'search', ['a'], user='u2'), row('4', 'rec', ['a'], user='u2')]
        # Both roles' differences cancel within every sampled user.
        b = np.array([3., 1., 5., 1.])
        x = np.array([1., 3., 1., 5.])
        boot = a.cluster_bootstrap(rows, b, x, draws=300)
        self.assertEqual(boot['intervals']['macro'], [0., 0.])
        self.assertEqual(boot['users'], 2)
        self.assertEqual(boot, a.cluster_bootstrap(rows, b, x, draws=300))
        duplicated = rows + rows
        boot2 = a.cluster_bootstrap(duplicated, np.r_[b, b], np.r_[x, x], draws=300)
        self.assertEqual(boot, boot2)

    def test_common_window_whole_request(self):
        rows = [row('s0', 'search', [], start=0), row('s1', 'search', [], start=5),
                row('s2', 'search', [], start=8), row('r0', 'rec', [], start=3), row('r1', 'rec', [], start=6)]
        selected, receipt = a.common_window(rows)
        self.assertEqual(receipt['common_range'], [3., 6.1])
        self.assertEqual({r['request_hash'] for r in selected}, {'s1', 'r0', 'r1'})

    def test_missing_role_validation_fails_closed(self):
        m = fixture()
        with self.assertRaisesRegex(ValueError, 'Both roles'):
            a.fit_view([row('tr', 'rec', ['a'])], [row('va', 'search', ['b'])], m)

    def test_split_validation_and_phase_separation(self):
        with tempfile.TemporaryDirectory() as t:
            t = Path(t)
            data, out = t / 'data', t / 'fitted'
            data.mkdir()
            train = [row('ts', 'search', ['a'], start=0), row('tr', 'rec', ['b'], start=0)]
            validation = [row('vs', 'search', ['a'], split='validation', user='v1', start=2),
                          row('vr', 'rec', ['b'], split='validation', user='v2', start=2)]
            for name, rows in [('train', train), ('validation', validation)]:
                (data / (name + '.jsonl')).write_text(''.join(json.dumps(r) + '\n' for r in rows))
            # Poison files: fit must not try to parse or hash either file.
            (data / 'test.jsonl').write_text('THIS IS NOT JSON')
            (data / 'audit.jsonl').write_text('THIS IS NOT JSON')
            protocol = t / 'PROTOCOL.md'
            protocol.write_text('Synthetic protocol only')
            csv_path = t / 'map.csv'
            with open(csv_path, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(['item_id', 'sid'])
                writer.writerows([['a', '[1]'], ['b', '[1]']])
            maps = t / 'maps.json'
            maps.write_text(json.dumps(dict(maps=[dict(name='gensar_shared2', path=str(csv_path))])))
            args = argparse.Namespace(input=str(data), out=str(out), maps_manifest=str(maps),
                                      protocol=str(protocol), manifest=None, common_window=False,
                                      fitted=None, evaluation_split='audit')
            original_open = open
            def guarded(file, *aa, **kw):
                if Path(file).name in ('test.jsonl', 'audit.jsonl'):
                    raise AssertionError('Fit attempted heldout access')
                return original_open(file, *aa, **kw)
            with patch('builtins.open', side_effect=guarded):
                a.fit(args)
            fitted = out / 'restricted/FITTED.json'
            args.fitted = str(fitted)
            receipt = json.loads((out / 'FIT_RECEIPT.json').read_text())
            self.assertFalse(receipt['test_accessed'])
            audit = [row('as', 'search', ['a'], split='audit', user='a1', start=2),
                     row('ar', 'rec', ['b'], split='audit', user='a2', start=2)]
            (data / 'audit.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in audit))
            args.out = str(t / 'audit_results')
            a.evaluate(args)
            result = json.loads((Path(args.out) / 'RESULTS.json').read_text())
            self.assertEqual(result['evaluation_split'], 'audit')
            self.assertTrue(result['results'][0]['primary'])
            self.assertEqual(result['results'][0]['bootstrap']['draws'], 2000)
            # Audit tuning user overlap fails even with distinct request hashes.
            audit[0]['user_hash'] = 'v1'
            (data / 'audit.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in audit))
            with self.assertRaisesRegex(ValueError, 'users overlap'):
                a.evaluate(args)
            # Any bound source mutation rejects before parsing heldout outcomes.
            protocol.write_text('Mutated protocol')
            with self.assertRaisesRegex(ValueError, 'binding mismatch'):
                a.evaluate(args)


if __name__ == '__main__':
    unittest.main(verbosity=2)
