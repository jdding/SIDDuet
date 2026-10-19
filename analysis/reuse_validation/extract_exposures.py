#!/usr/bin/env python3
"""Export restricted chronological exposure requests; no model fitting or text reading."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import resource
import sys
import time
from collections import Counter
from pathlib import Path

UNIVERSE_SHA = 'a6f3202fd6b6ac09e1a154e8c6d42511bd663e2f381206739c0243113aeb33e9'
SOURCE_SHA = {
    ('search', 'train'): 'dbe68affa5ea64aad0744fa9c08ac9d8d58180564ab28c0625684eaa09534bdd',
    ('search', 'test'): '89dd99821e365341860d69f77bab36eeb8d8b692194e082e40a9ea6ea39ff243',
    ('recommendation', 'train'): '42b3679342c369c5df3802355a5fd0029dcedc5709a2248497ae1ac6fe56533d',
    ('recommendation', 'test'): '849d5cce5b2244a535568f72230cc98e4fabb23634b30c98365d8a64cdf0c5f0',
}
ROLES = ('search', 'recommendation')
CATALOG_SIZE = 1983938
VALIDATION_START = 1732700625.0
TEST_START = 1732706088.0
CPU_LIMIT_SECONDS = 20 * 60
MAX_RSS_BYTES = 3 * 1024 ** 3


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def check_hash(path, expected):
    actual = sha(path)
    if actual != expected:
        raise RuntimeError('SHA256 mismatch: ' + str(path))
    return actual


def stable_hash(*parts):
    return hashlib.sha256('\x1f'.join(map(str, parts)).encode()).hexdigest()


def valid_id(value):
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def timestamp(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        value = float(value)
    except (ValueError, TypeError):
        return None
    return value if math.isfinite(value) else None


def source_plan(phase):
    if phase == 'trainval':
        return [(role, 'train') for role in ROLES]
    if phase == 'test':
        return [(role, 'test') for role in ROLES]
    raise ValueError('Unknown phase')


def choose_split(provider, start, end):
    if start > end:
        return None
    if provider == 'test':
        return 'test' if start >= TEST_START else None
    if end < VALIDATION_START:
        return 'train'
    if start >= VALIDATION_START and end < TEST_START:
        return 'validation'
    return None


def validation_partition(user_hash):
    digest = hashlib.sha256(('rolemap-allocation-val-v1|' + user_hash).encode()).hexdigest()
    return 'validation' if int(digest[:16], 16) % 2 == 0 else 'audit'


def request_record(row, role, provider, source_row, universe, audit):
    """No output includes original user/session/request identifiers or raw text."""
    request_key = 'search_idx' if role == 'search' else 'request_idx'
    detail_key = 'search_result_details_with_idx' if role == 'search' else 'rec_result_details_with_idx'
    time_key = 'search_timestamp' if role == 'search' else 'request_timestamp'
    if any(not valid_id(row.get(k)) for k in ('user_idx', 'session_idx', request_key)):
        audit['excluded_invalid_identity'] += 1
        return None
    details = row.get(detail_key)
    if not isinstance(details, list) or not details:
        audit['excluded_missing_or_empty_details'] += 1
        return None
    if any(not isinstance(d, dict) or timestamp(d.get(time_key)) is None for d in details):
        audit['excluded_invalid_or_missing_detail_timestamp'] += 1
        return None
    times = [timestamp(d[time_key]) for d in details]
    start, end = min(times), max(times)
    split = choose_split(provider, start, end)
    if split is None:
        audit['excluded_nonchronological_provider_test' if provider == 'test'
              else 'excluded_later_or_boundary_crossing_interval'] += 1
        return None
    exposed, clicked = set(), set()
    appearances = common_appearances = 0
    for detail in details:
        item = detail.get('note_idx')
        if not valid_id(item):
            audit['excluded_invalid_item_appearances'] += 1
            continue
        if item >= CATALOG_SIZE:
            audit['excluded_outside_catalog_appearances'] += 1
            continue
        appearances += 1
        common_appearances += item in universe
        exposed.add(item)
        click = timestamp(detail.get('click'))
        if click is not None and click > 0:
            clicked.add(item)
    if not exposed:
        audit['excluded_no_valid_catalog_exposure'] += 1
        return None
    return {
        'schema': 'sr_sid_rolemap.exposure_request.v1',
        'request_hash': stable_hash('qilin-native-request-v1', role, provider, row[request_key]),
        'user_hash': stable_hash('p152-user', row['user_idx']),
        'session_hash': stable_hash('qilin-session-v1', row['user_idx'], row['session_idx']),
        'role': role, 'split': split, 'source_chronological_split': split, 'provider_split': provider, 'source_row': source_row,
        'timestamp_start': start, 'timestamp_end': end,
        'exposed_item_ids': sorted(exposed & universe),
        'clicked_item_ids': sorted(clicked & universe),
        'full_catalog_exposure_appearance_count': appearances,
        'full_catalog_exposed_item_count': len(exposed),
        'full_catalog_clicked_item_count': len(clicked),
        'common_exposure_appearance_count': common_appearances,
    }


def check_unique_native(row, role, seen):
    key_name = 'search_idx' if role == 'search' else 'request_idx'
    native = row.get(key_name)
    if valid_id(native):
        key = (role, native)
        if key in seen:
            raise RuntimeError('Duplicate native request identity; raw value withheld')
        seen.add(key)


def update_range(ranges, name, start, end):
    old = ranges.setdefault(name, {'min_start': start, 'max_end': end})
    old['min_start'] = min(old['min_start'], start)
    old['max_end'] = max(old['max_end'], end)


def write_json(path, value):
    with Path(path).open('x') as handle:
        json.dump(value, handle, indent=2, sort_keys=True)
        handle.write('\n')


def extract(args):
    import pyarrow
    import pyarrow.parquet as pq
    wall, cpu = time.monotonic(), time.process_time()
    if args.out.exists():
        raise RuntimeError('Output directory must not exist: ' + str(args.out))
    check_hash(args.universe, UNIVERSE_SHA)
    with args.universe.open() as handle:
        universe_rows = [int(row['item_id']) for row in csv.DictReader(handle)]
    universe = set(universe_rows)
    if len(universe) != 20540 or len(universe_rows) != len(universe):
        raise RuntimeError('Frozen common cohort must contain exactly 20540 unique item IDs')
    splits = ('train', 'validation', 'audit') if args.phase == 'trainval' else ('test',)
    # This plan is the sole source-opening loop: trainval never opens a test source.
    plan = source_plan(args.phase)
    sources = []
    for role, provider in plan:
        path = args.provider_root / (role + '_' + provider) / 'train-00000-of-00001.parquet'
        check_hash(path, SOURCE_SHA[(role, provider)])
        sources.append((role, provider, path))
    args.out.mkdir(parents=True)
    outputs = {split: args.out / (split + '.jsonl') for split in splits}
    handles = {split: path.open('x') for split, path in outputs.items()}
    seen_native, seen_hash, audits, source_ranges, out_ranges = set(), set(), {}, {}, {}
    counts = {split: {role: Counter() for role in ROLES} for split in splits}
    users = {split: {role: set() for role in ROLES} for split in splits}
    sessions = {split: {role: set() for role in ROLES} for split in splits}
    bindings = []
    try:
        for role, provider, path in sources:
            audit = Counter()
            column = 'search_result_details_with_idx' if role == 'search' else 'rec_result_details_with_idx'
            rkey = 'search_idx' if role == 'search' else 'request_idx'
            tkey = 'search_timestamp' if role == 'search' else 'request_timestamp'
            for batch in pq.ParquetFile(path).iter_batches(batch_size=2048, columns=['user_idx', 'session_idx', rkey, column]):
                if time.process_time() - cpu > CPU_LIMIT_SECONDS or resource.getrusage(resource.RUSAGE_SELF).ru_maxrss > MAX_RSS_BYTES:
                    raise RuntimeError('Extraction runtime budget exceeded')
                for row in batch.to_pylist():
                    source_row = audit['source_rows']
                    audit['source_rows'] += 1
                    check_unique_native(row, role, seen_native)
                    raw_times = [timestamp(d.get(tkey)) for d in (row.get(column) or []) if isinstance(d, dict)]
                    raw_times = [t for t in raw_times if t is not None]
                    if raw_times:
                        update_range(source_ranges, role, min(raw_times), max(raw_times))
                    record = request_record(row, role, provider, source_row, universe, audit)
                    if record is None:
                        continue
                    if record['request_hash'] in seen_hash:
                        raise RuntimeError('Duplicate hashed request identity')
                    seen_hash.add(record['request_hash'])
                    if record['source_chronological_split'] == 'validation':
                        record['split'] = validation_partition(record['user_hash'])
                    split = record['split']
                    if split not in handles:
                        raise RuntimeError('Phase attempted to export an unauthorized split')
                    count = counts[split][role]
                    count['all_catalog_exposed_requests'] += 1
                    count['common_exposed_requests'] += bool(record['exposed_item_ids'])
                    count['common_clicked_requests'] += bool(record['clicked_item_ids'])
                    count['full_catalog_exposure_appearances'] += record['full_catalog_exposure_appearance_count']
                    count['common_exposure_appearances'] += record['common_exposure_appearance_count']
                    count['common_distinct_exposures_summed_over_requests'] += len(record['exposed_item_ids'])
                    count['full_catalog_distinct_exposures_summed_over_requests'] += record['full_catalog_exposed_item_count']
                    count['requests_with_catalog_click'] += record['full_catalog_clicked_item_count'] > 0
                    users[split][role].add(record['user_hash'])
                    sessions[split][role].add(record['session_hash'])
                    update_range(out_ranges, split + '|' + role, record['timestamp_start'], record['timestamp_end'])
                    handles[split].write(json.dumps(record, sort_keys=True, separators=(',', ':')) + '\n')
            check_hash(path, SOURCE_SHA[(role, provider)])
            audits[role] = dict(audit)
            bindings.append({'path': str(path), 'sha256': SOURCE_SHA[(role, provider)], 'rows_seen': audit['source_rows']})
    finally:
        for handle in handles.values():
            handle.close()
    check_hash(args.universe, UNIVERSE_SHA)
    receipt = {
        'schema': 'sr_sid_rolemap.exposure_extraction.v1', 'status': 'COMPLETE_EXTRACTION', 'phase': args.phase,
        'code_sha256': sha(__file__), 'protocol_sha256': sha(args.protocol),
        'sources': bindings, 'universe': {'path': str(args.universe.resolve()), 'sha256': UNIVERSE_SHA, 'items': len(universe)},
        'source_audits': audits, 'source_timestamp_ranges': source_ranges, 'output_timestamp_ranges': out_ranges,
        'counts': {s: {r: dict(c) for r, c in roles.items()} for s, roles in counts.items()},
        'unique_users': {s: {r: len(v) for r, v in roles.items()} for s, roles in users.items()},
        'unique_user_sessions': {s: {r: len(v) for r, v in roles.items()} for s, roles in sessions.items()},
        'outputs': {s: {'path': str(p.resolve()), 'sha256': sha(p), 'bytes': p.stat().st_size} for s, p in outputs.items()},
        'validation_user_partition': {'source_interval': 'chronological validation', 'rule': "SHA256('rolemap-allocation-val-v1|' + user_hash), first 64 bits mod 2: 0=validation tuning, 1=audit", 'same_user_all_roles_jointly_partitioned': True, 'audit_must_not_be_read_during_model_fit': True},
        'temporal_boundaries': {'validation_start': VALIDATION_START, 'test_start': TEST_START,
            'request_rule': 'Use entire detail interval; reject missing/nonfinite detail times, boundary crossings, and provider-test start before test anchor'},
        'runtime': {'python': sys.executable, 'python_version': sys.version.split()[0], 'pyarrow_version': pyarrow.__version__,
            'wall_seconds': time.monotonic() - wall, 'cpu_seconds': time.process_time() - cpu,
            'max_rss_bytes_macos': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            'telemetry': 'Built-in wall/process-time/resource counters; extraction writes only the chosen output directory'},
        'scope': 'Restricted historical cohort; requests with zero common exposure retained; no fitting or model evaluation; no raw query/history/text fields read',
    }
    write_json(args.out / 'EXTRACTION_RECEIPT.json', receipt)
    print(json.dumps({'status': receipt['status'], 'phase': args.phase, 'receipt': str(args.out / 'EXTRACTION_RECEIPT.json'),
                      'receipt_sha256': sha(args.out / 'EXTRACTION_RECEIPT.json'), 'counts': receipt['counts'], 'runtime': receipt['runtime']}, sort_keys=True))


def self_test():
    checks = 0
    def row(t=VALIDATION_START - 1, items=(1, 1, 2, 5)):
        return {'user_idx': 1, 'session_idx': 2, 'search_idx': 3,
                'search_result_details_with_idx': [{'note_idx': i, 'click': int(i == 1), 'search_timestamp': t} for i in items]}
    a = Counter()
    r = request_record(row(), 'search', 'train', 0, {1, 2}, a)
    assert r['exposed_item_ids'] == [1, 2] and r['clicked_item_ids'] == [1]
    assert r['full_catalog_exposure_appearance_count'] == 4 and r['full_catalog_exposed_item_count'] == 3
    assert r['common_exposure_appearance_count'] == 3
    checks += 3
    assert choose_split('train', VALIDATION_START, TEST_START - 1) == 'validation'
    assert choose_split('train', VALIDATION_START - 1, VALIDATION_START) is None
    assert choose_split('train', TEST_START - 1, TEST_START) is None
    assert choose_split('test', TEST_START - 1, TEST_START + 1) is None
    assert choose_split('test', TEST_START, TEST_START + 1) == 'test'
    checks += 5
    x = row(); x['search_result_details_with_idx'][0]['search_timestamp'] = float('nan')
    assert request_record(x, 'search', 'train', 0, {1}, Counter()) is None
    x = row(); x['search_result_details_with_idx'] = None
    assert request_record(x, 'search', 'train', 0, {1}, Counter()) is None
    checks += 2
    x = row(items=(True, 1.5, '1', -1, 2)); a = Counter()
    y = request_record(x, 'search', 'train', 0, {2}, a)
    assert y['exposed_item_ids'] == [2] and a['excluded_invalid_item_appearances'] == 4
    x['user_idx'] = 1.5
    assert request_record(x, 'search', 'train', 0, {2}, Counter()) is None
    checks += 2
    x = row(items=(5,)); y = request_record(x, 'search', 'train', 0, {1}, Counter())
    assert y is not None and y['exposed_item_ids'] == []
    assert y['full_catalog_exposed_item_count'] == 1
    checks += 2
    seen = set(); check_unique_native(row(), 'search', seen)
    try:
        check_unique_native(row(), 'search', seen)
    except RuntimeError:
        checks += 1
    else:
        raise AssertionError('Duplicate native ID accepted')
    assert source_plan('trainval') == [('search', 'train'), ('recommendation', 'train')]
    assert source_plan('test') == [('search', 'test'), ('recommendation', 'test')]
    checks += 2
    assert not {'user_idx', 'session_idx', 'search_idx', 'query', 'recent_clicked_note_idxs'} & set(r)
    checks += 1
    user = stable_hash('p152-user', 123)
    expected_partition = 'validation' if int(hashlib.sha256(('rolemap-allocation-val-v1|' + user).encode()).hexdigest()[:16], 16) % 2 == 0 else 'audit'
    assert validation_partition(user) == expected_partition
    assert validation_partition(user) == validation_partition(user)
    assert r['source_chronological_split'] == 'train'
    checks += 3
    return {'status': 'PASS_SYNTHETIC_ONLY', 'checks': checks, 'provider_data_read': False, 'code_sha256': sha(__file__)}


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--provider-root', type=Path)
    parser.add_argument('--universe', type=Path, help='Original 20540-item cohort CSV, checked against the fixed SHA256')
    parser.add_argument('--protocol', type=Path, default=Path(__file__).resolve().parent / 'PROTOCOL.md')
    parser.add_argument('--out', type=Path)
    parser.add_argument('--phase', choices=('trainval', 'test'))
    parser.add_argument('--self-test', action='store_true')
    args = parser.parse_args()
    if args.self_test:
        print(json.dumps(self_test(), sort_keys=True))
    elif args.provider_root is None or args.out is None or args.phase is None or args.universe is None:
        parser.error('--provider-root, --universe, --out, and --phase are required for extraction')
    else:
        extract(args)


if __name__ == '__main__':
    main()
