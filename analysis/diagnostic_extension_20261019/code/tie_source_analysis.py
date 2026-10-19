#!/usr/bin/env python3
"""Decompose fixed v2 ties using their serialized keys and original label counts.

No threshold, weights, depth, model, or item membership is changed. Raw joined
IDs never enter aggregate outputs. See ANALYSIS_CONTRACT.md for interpretation.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import math
import platform
import resource
import sys
import tempfile
import time
from collections import Counter, defaultdict
from decimal import Decimal, ROUND_HALF_EVEN
from fractions import Fraction
from pathlib import Path

PROFILE = 'sr_sid_rolemap.topology.value_median.v2'
SCALE = 10**12
COMP = [('js','js_rank_key','js_twice_rank'),('neighbor','neighbor_rank_key','neighbor_twice_rank'),('top_label','top_label_rank_key','top_label_twice_rank')]
BINS = ['1','2-5','6-20','21-100','>100']
REGIMES = ['both1','search1_only','rec1_only','both>1']

def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(1<<20),b''): h.update(block)
    return h.hexdigest()

def q12(x):
    return int(Decimal(str(x)).quantize(Decimal('0.000000000001'),rounding=ROUND_HALF_EVEN)*SCALE)

def fsum(values):
    v=math.fsum(sorted(values))
    if not math.isfinite(v): raise ValueError('nonfinite count aggregate')
    return v

def median(values):
    v=sorted(values); n=len(v)
    if not n: raise ValueError('empty universe')
    return Fraction(v[n//2]) if n%2 else (Fraction(v[n//2-1])+Fraction(v[n//2]))/2

def frac_record(x): return {'numerator':x.numerator,'denominator':x.denominator}

def summary(values):
    c=Counter(values)
    return {'items':len(values),'unique_values':len(c),'max_value':max(c) if c else None,
            'at_max_items':c[max(c)] if c else 0,'most_frequent_value_items':max(c.values(),default=0)}

def cell_record(count, denominator):
    return {'items':count,'denominator':denominator,'fraction':count/denominator if denominator else None}

def read_topology(path):
    rows=[]; seen=set()
    with Path(path).open(newline='') as f:
        rd=csv.DictReader(f)
        required={'dataset','item_id','profile_id','js_binary64','rsi_binary64','rsd_numerator','rsd_denominator','rsi_split_key','rsd_at_median','rsi_at_median','search_support','rec_support','search_entropy','rec_entropy','rsd_bucket','rsi_mag_bucket'}|{x for _,k,r in COMP for x in (k,r)}
        if not rd.fieldnames or not required.issubset(rd.fieldnames) or len(rd.fieldnames)!=len(set(rd.fieldnames)): raise ValueError('invalid topology header')
        for raw in rd:
            item=(raw['dataset'],raw['item_id'])
            if raw['profile_id']!=PROFILE or item in seen: raise ValueError('wrong profile or duplicate item')
            seen.add(item)
            js=float.fromhex(raw['js_binary64']); rsi=float.fromhex(raw['rsi_binary64'])
            if not(0<=js<=1) or not(-1<=rsi<=1): raise ValueError('raw coordinate range')
            row={'dataset':item[0],'item_id':item[1],'raw':raw,'js':js,'rsi':rsi,
                 'keys':tuple(int(raw[k]) for _,k,_ in COMP),'ranks':tuple(int(raw[r]) for _,_,r in COMP),
                 'rsd':Fraction(int(raw['rsd_numerator']),int(raw['rsd_denominator'])),
                 'rsi_key':int(raw['rsi_split_key']),'rsd_median_flag':int(raw['rsd_at_median']),
                 'rsi_median_flag':int(raw['rsi_at_median'])}
            if q12(js)!=row['keys'][0] or q12(abs(rsi))!=row['rsi_key']: raise ValueError('raw/key mismatch')
            if any(k<0 or k>SCALE for k in row['keys']): raise ValueError('component key range')
            if sum((Fraction(2,120+r) for r in row['ranks']),Fraction())!=row['rsd']: raise ValueError('exact RRF mismatch')
            rows.append(row)
    if len({r['dataset'] for r in rows})!=1: raise ValueError('each topology must contain exactly one dataset')
    rows.sort(key=lambda r:r['item_id'])
    for j in range(3):
        freq=Counter(r['keys'][j] for r in rows); start=0; expected={}
        for key,n in sorted(freq.items(),reverse=True):
            expected[key]=2*start+n+1;start+=n
        if any(r['ranks'][j]!=expected[r['keys'][j]] for r in rows): raise ValueError('average rank mismatch')
    mr=median([r['rsd'] for r in rows]); mi=median([r['rsi_key'] for r in rows])
    for r in rows:
        raw=r['raw']
        if r['rsd_median_flag']!=int(r['rsd']==mr) or r['rsi_median_flag']!=int(r['rsi_key']==mi): raise ValueError('median flag mismatch')
        if raw['rsd_bucket']!=('high_rsd' if r['rsd']>mr else 'low_rsd') or raw['rsi_mag_bucket']!=('high_rsi' if r['rsi_key']>mi else 'low_rsi'): raise ValueError('bucket mismatch')
    return rows,mr,mi

def read_label_counts(path, rows):
    # Keep only frozen common-item IDs. Zero rows do not create a label.
    targets={(r['dataset'],r['item_id']) for r in rows}
    parts={key:{'search':defaultdict(list),'rec':defaultdict(list)} for key in targets}
    scanned=kept=zero=duplicates=0
    with Path(path).open(newline='') as f:
        rd=csv.DictReader(f)
        if not rd.fieldnames or not {'dataset','item_id','role','label','count'}.issubset(rd.fieldnames) or len(rd.fieldnames)!=len(set(rd.fieldnames)): raise ValueError('counts header')
        for r in rd:
            scanned+=1
            if None in r or any(r.get(k) is None for k in ('dataset','item_id','role','label','count')): raise ValueError('count row width')
            role=r['role'].strip().lower(); count=float(r['count'])
            if role not in ('search','rec') or not math.isfinite(count) or count<0 or not r['label']: raise ValueError('invalid count row')
            key=(r['dataset'],r['item_id'])
            if key not in targets: continue
            if count==0: zero+=1;continue
            kept+=1
            values=parts[key][role][r['label']]
            duplicates+=bool(values); values.append(count)
    records={}
    for key,roles in parts.items():
        values={role:{label:fsum(v) for label,v in sorted(labels.items())} for role,labels in roles.items()}
        if not values['search'] or not values['rec']: raise ValueError('frozen common item lacks positive label')
        records[key]=values
    return records,{'scanned_rows':scanned,'retained_positive_rows':kept,'retained_zero_rows':zero,'duplicate_positive_label_rows':duplicates}

def entropy(counts):
    total=math.fsum(counts[k] for k in sorted(counts))
    p={k:counts[k]/total for k in sorted(counts)}
    return -math.fsum(p[k]*math.log2(p[k]) for k in sorted(p) if p[k]>0)

def support_bin(x):
    # Labels 2-5 etc refer to integer observation totals; refuse fractional totals.
    if not x.is_integer() or x<1: raise ValueError('support strata require positive integer observation totals')
    return '1' if x==1 else '2-5' if x<=5 else '6-20' if x<=20 else '21-100' if x<=100 else '>100'

def annotate(rows, counts):
    checks=Counter()
    maxima=tuple(max(r['keys'][j] for r in rows) for j in range(3))
    for r in rows:
        v=counts[(r['dataset'],r['item_id'])]; s=v['search']; t=v['rec']
        ns,nr=len(s),len(t); ss=math.fsum(s[k] for k in sorted(s)); rr=math.fsum(t[k] for k in sorted(t))
        es,er=entropy(s),entropy(t)
        for field,value in [('search_support',ss),('rec_support',rr),('search_entropy',es),('rec_entropy',er)]:
            # Builder displays these at 12 significant figures; do not claim display=raw.
            if float(r['raw'][field])!=float(format(value,'.12g')): raise ValueError(f'{field} source/display mismatch')
            checks[field+'_display_matches_source']+=1
        rsi=(er-es)/max(es,er,1e-12)
        if rsi.hex()!=r['raw']['rsi_binary64']:
            # Signed zero has the same scientific value but a distinct representation.
            if rsi!=r['rsi']: raise ValueError('source entropy/raw RSI mismatch')
            checks['rsi_signed_zero_representation_difference']+=1
        checks['rsi_raw_matches_source_numeric']+=1
        disjoint=set(s).isdisjoint(t)
        regime='both1' if ns==nr==1 else 'search1_only' if ns==1 else 'rec1_only' if nr==1 else 'both>1'
        raw_equal=es==er; display_equal=float(r['raw']['search_entropy'])==float(r['raw']['rec_entropy'])
        distribution_equal=set(s)==set(t) and all(Fraction(s[k])*Fraction(rr)==Fraction(t[k])*Fraction(ss) for k in s)
        if (ns==1)!=(es==0) or (nr==1)!=(er==0): raise ValueError('single-label/zero entropy mismatch')
        if disjoint and r['js']!=1: raise ValueError('disjoint label set/raw JS endpoint mismatch')
        flags={
          'search_single_label':ns==1,'rec_single_label':nr==1,'both_single_label':ns==nr==1,
          'disjoint_label_sets':disjoint,'overlapping_label_sets':not disjoint,
          'search_entropy_zero':es==0,'rec_entropy_zero':er==0,'both_entropy_zero':es==er==0,
          'entropy_equal_raw_recomputed':raw_equal,'entropy_equal_display':display_equal,
          'source_normalized_distributions_equal_exact_crossproduct':distribution_equal,
          'equal_entropy_different_normalized_distribution':raw_equal and not distribution_equal,
          'entropy_display_equal_raw_different':display_equal and not raw_equal,
          'rsi_raw_zero':r['rsi']==0,'rsi_key_zero':r['rsi_key']==0,
          'rsi_abs_raw_one':abs(r['rsi'])==1,'rsi_key_one':r['rsi_key']==SCALE,
          'rsi_key_one_raw_below_one':r['rsi_key']==SCALE and abs(r['rsi'])<1,
          'js_raw_zero':r['js']==0,'js_key_zero':r['keys'][0]==0,
          'js_raw_one':r['js']==1,'js_key_one':r['keys'][0]==SCALE,
          'js_key_one_raw_below_one':r['keys'][0]==SCALE and r['js']<1,
          'top_label_mismatch':r['keys'][2]==SCALE,
          'all_component_keys_at_max':r['keys']==maxima,
          'js_key_at_dataset_max':r['keys'][0]==maxima[0],
          'neighbor_key_at_dataset_max':r['keys'][1]==maxima[1],
          'top_label_key_at_dataset_max':r['keys'][2]==maxima[2],
          'rsd_at_median':bool(r['rsd_median_flag']),'rsi_at_median':bool(r['rsi_median_flag']),
        }
        r.update(search_support=ss,rec_support=rr,search_labels=ns,rec_labels=nr,
                 overlap_labels=len(set(s)&set(t)),search_entropy_recomputed=es,rec_entropy_recomputed=er,
                 support_bin=support_bin(min(ss,rr)),regime=regime,overlap='empty' if disjoint else 'nonempty',flags=flags)
    return dict(checks)

def cohort_summary(rows):
    n=len(rows)
    return {'items':n,
      'components':{name:summary([r['keys'][j] for r in rows]) for j,(name,_,_) in enumerate(COMP)},
      'indicators':{flag:cell_record(sum(r['flags'][flag] for r in rows),n) for flag in rows[0]['flags']} if rows else {},
      'label_regimes':{key:cell_record(sum(r['regime']==key for r in rows),n) for key in REGIMES},
      'label_overlap':{key:cell_record(sum(r['overlap']==key for r in rows),n) for key in ('empty','nonempty')},
      'support_bins':{key:cell_record(sum(r['support_bin']==key for r in rows),n) for key in BINS}}

def stratified(rows):
    out=[]
    for field,categories in [('support_bin',BINS),('regime',REGIMES),('overlap',['empty','nonempty'])]:
        for category in categories:
            selected=[r for r in rows if r[field]==category]
            out.append({'stratum_type':field,'stratum':category,**cohort_summary(selected)})
    # Joint denominator exposes whether apparent median associations are support-regime confounded.
    joint=[]
    for b in BINS:
        for regime in REGIMES:
            for overlap in ('empty','nonempty'):
                selected=[r for r in rows if r['support_bin']==b and r['regime']==regime and r['overlap']==overlap]
                joint.append({'support_bin':b,'regime':regime,'overlap':overlap,**cohort_summary(selected)})
    return {'marginal':out,'joint':joint}

def js_merge_table(rows):
    groups=defaultdict(list)
    for r in rows: groups[r['keys'][0]].append(r)
    table=[]
    for key,group in sorted(groups.items()):
        vals={r['js'] for r in group}; representations={r['raw']['js_binary64'] for r in group}
        # All unequal binary64 values are reported, without treating rounding gaps as true label changes.
        near_endpoint=key in (0,SCALE)
        table.append({'js_key':key,'items':len(group),'distinct_binary64_numeric_values':len(vals),
                      'distinct_hex_representations':len(representations),'raw_min_hex':min(vals).hex(),'raw_max_hex':max(vals).hex(),
                      'raw_spread':max(vals)-min(vals),'unequal_numeric_merge':len(vals)>1,
                      'signed_zero_only_merge':len(vals)==1 and len(representations)>1,
                      'endpoint_key':near_endpoint,
                      'raw_endpoint_items':sum(r['js'] in (0,1) for r in group),
                      'raw_nonendpoint_items':sum(r['js'] not in (0,1) for r in group),
                      'label_disjoint_items':sum(r['flags']['disjoint_label_sets'] for r in group),
                      'median_cohort_items':sum(r['rsd_median_flag'] for r in group)})
    return table

def triple_table(rows):
    c=Counter((r['keys'],r['ranks'],r['rsd'],bool(r['rsd_median_flag'])) for r in rows)
    return [{'js_key':k[0],'neighbor_key':k[1],'top_label_key':k[2],
             'js_twice_rank':rk[0],'neighbor_twice_rank':rk[1],'top_label_twice_rank':rk[2],
             'rsd_numerator':rsd.numerator,'rsd_denominator':rsd.denominator,
             'at_rsd_median':int(at),'items':n} for (k,rk,rsd,at),n in sorted(c.items())]

def rsd_tie_decomposition(rows):
    groups=defaultdict(list)
    for r in rows:groups[r['rsd']].append(r)
    table=[]
    for score,group in sorted(groups.items()):
        triples=Counter(r['keys'] for r in group)
        table.append({'rsd_numerator':score.numerator,'rsd_denominator':score.denominator,
                      'items':len(group),'distinct_component_key_triples':len(triples),
                      'same_triple_repeated_items':sum(n for n in triples.values() if n>1),
                      'same_triple_repeat_excess':sum(n-1 for n in triples.values()),
                      'different_triples_same_exact_rsd':len(triples)>1,
                      'at_rsd_median_items':sum(r['rsd_median_flag'] for r in group)})
    return table

def output_csv(path,records):
    records=list(records)
    if not records: return
    with Path(path).open('x',newline='') as f:
        wr=csv.DictWriter(f,fieldnames=list(records[0]));wr.writeheader();wr.writerows(records)

def analyze(topology, role_counts, output, restricted, expected=None):
    started=time.perf_counter()
    before={'topology':digest(topology),'role_counts':digest(role_counts)}
    if expected is not None and before!=expected: raise ValueError('input hash differs from declared manifest')
    rows,mr,mi=read_topology(topology)
    counts,source_stats=read_label_counts(role_counts,rows); checks=annotate(rows,counts); del counts
    dataset=rows[0]['dataset']; output=Path(output);restricted=Path(restricted)
    if output.exists() or restricted.exists(): raise ValueError('output directories must be fresh')
    output.mkdir(parents=True);restricted.mkdir(parents=True)
    merge=js_merge_table(rows); triples=triple_table(rows); rsd_ties=rsd_tie_decomposition(rows)
    cohorts={'all':rows,'rsd_median':[r for r in rows if r['rsd_median_flag']],
             'rsd_not_median':[r for r in rows if not r['rsd_median_flag']]}
    result={'dataset':dataset,'profile_id':PROFILE,'items':len(rows),
      'inputs':{key:{'sha256':value} for key,value in before.items()},
      'script_sha256':digest(__file__),'source_count_read':source_stats,
      'checks':{'exact_rrf_all_rows':len(rows),'average_ranks_all_rows':len(rows),'median_flags_all_rows':len(rows),**checks},
      'rsd_median':frac_record(mr),'rsi_key_median':frac_record(mi),
      'rsd_summary':{'unique_exact_fractions':len({r['rsd'] for r in rows}),'at_median_items':len(cohorts['rsd_median']),
                     'above_median_items':sum(r['rsd']>mr for r in rows),'below_median_items':sum(r['rsd']<mr for r in rows),
                     'median_is_max':mr==max(r['rsd'] for r in rows)},
      'js_raw_q12':{'unique_binary64_numeric_values':len({r['js'] for r in rows}),
                    'unique_hex_representations':len({r['raw']['js_binary64'] for r in rows}),
                    'unique_q12_keys':len(merge),'keys_merging_unequal_binary64':sum(r['unequal_numeric_merge'] for r in merge),
                    'items_in_unequal_binary64_merge_keys':sum(r['items'] for r in merge if r['unequal_numeric_merge']),
                    'endpoint_merge_keys':sum(r['unequal_numeric_merge'] and r['endpoint_key'] for r in merge),
                    'interior_merge_keys':sum(r['unequal_numeric_merge'] and not r['endpoint_key'] for r in merge),
                    'signed_zero_only_merge_keys':sum(r['signed_zero_only_merge'] for r in merge)},
      'cohorts':{key:cohort_summary(group) for key,group in cohorts.items()},
      'strata':{key:stratified(group) for key,group in cohorts.items()},
      'rsd_tie_decomposition':{'exact_rsd_values_with_multiple_key_triples':sum(r['different_triples_same_exact_rsd'] for r in rsd_ties),
                               'items_at_rsd_values_with_multiple_key_triples':sum(r['items'] for r in rsd_ties if r['different_triples_same_exact_rsd']),
                               'same_key_triple_repeat_excess':sum(r['same_triple_repeat_excess'] for r in rsd_ties),
                               'denominator_items':len(rows)},
      'component_triples':{key:{'unique_key_triples':len({r['keys'] for r in group}),
                               'unique_rank_triples':len({r['ranks'] for r in group})} for key,group in cohorts.items()},
      'semantics':{'js_raw':'serialized float.hex binary64; 12-significant-digit display never used as raw',
                   'entropy':'recomputed solely from same positive source-label counts, matched against 12g display; raw entropy was not serialized',
                   'component_keys':'fixed serialized Q12 values; never re-binned',
                   'binary64_merges':'unequal floating representations within fixed Q12; not evidence of distinct true semantics',
                   'equality':'raw binary64 JS equality and entropy equality do not imply equal label distributions; exact source crossproduct equality is reported separately',
                   'execution_surface':'independent local CPU diagnostic with dedicated command/script/input/output hashes; no axiomdesk_run training launcher, no model calls',
                   'support_bins':'integer min(search_support,rec_support); fixed 1,2-5,6-20,21-100,>100',
                   'scope':'associations in fixed common-item universe; not causal attribution, label-coarseness proof, preference or model effects'},
      'runtime':{'python':sys.version,'platform':platform.platform(),'elapsed_seconds':time.perf_counter()-started,'peak_rss_native_units':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                 'peak_rss_units':'bytes on macOS; kibibytes on Linux'}}
    output_csv(output/'js_raw_key_merges.csv',merge)
    output_csv(output/'component_triples.csv',triples)
    output_csv(output/'exact_rsd_tie_decomposition.csv',rsd_ties)
    if before!={'topology':digest(topology),'role_counts':digest(role_counts)}: raise ValueError('inputs changed during read')
    records=[]
    for r in rows:
        records.append({'dataset':dataset,'item_id':r['item_id'],'search_support':r['search_support'],'rec_support':r['rec_support'],
                        'search_positive_labels':r['search_labels'],'rec_positive_labels':r['rec_labels'],'label_intersection_size':r['overlap_labels'],
                        'search_entropy_recomputed_hex':r['search_entropy_recomputed'].hex(),'rec_entropy_recomputed_hex':r['rec_entropy_recomputed'].hex(),
                        'js_binary64':r['raw']['js_binary64'],'rsi_binary64':r['raw']['rsi_binary64'],
                        'support_bin':r['support_bin'],'label_regime':r['regime'],'label_overlap':r['overlap'],
                        'at_rsd_median':r['rsd_median_flag'],'at_rsi_median':r['rsi_median_flag']})
    output_csv(restricted/'item_label_diagnostics.csv',records)
    (output/'summary.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
    receipt={'status':'PASS','dataset':dataset,'items':len(rows),'summary_sha256':digest(output/'summary.json'),
             'aggregate_files':{p.name:digest(p) for p in sorted(output.iterdir()) if p.is_file()},
             'restricted_item_csv_sha256':digest(restricted/'item_label_diagnostics.csv'),'script_sha256':digest(__file__)}
    (output/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    return result

# Fabricated test writer independently defines source components, to test the
# analysis without importing or mutating the v2 builder.
def fixture_topology(path, counts):
    records=[]
    for item,roles in sorted(counts.items()):
        total={role:{label:fsum(v) if isinstance(v,list) else float(v) for label,v in labels.items() if (fsum(v) if isinstance(v,list) else v)>0} for role,labels in roles.items()}
        s,t=total['search'],total['rec']; ss=fsum(s.values());rr=fsum(t.values())
        p={k:v/ss for k,v in s.items()};q={k:v/rr for k,v in t.items()}
        if p==q:js=0.
        elif set(p).isdisjoint(q):js=1.
        else:
            terms=[]
            for k in sorted(set(p)|set(q)):
                a,b=p.get(k,0),q.get(k,0)
                if a:terms.append(.5*a*math.log2(2*a/(a+b)))
                if b:terms.append(.5*b*math.log2(2*b/(a+b)))
            js=min(1.,max(0.,math.fsum(terms)))
        st=[k for k,_ in sorted(s.items(),key=lambda v:(-v[1],v[0]))[:3]];rt=[k for k,_ in sorted(t.items(),key=lambda v:(-v[1],v[0]))[:3]]
        nd=1-len(set(st)&set(rt))/len(set(st)|set(rt));tm=float(st[0]!=rt[0]);es=entropy(s);er=entropy(t);rsi=(er-es)/max(es,er,1e-12)
        r={'dataset':'fabricated','item_id':item,'profile_id':PROFILE,'search_support':format(ss,'.12g'),'rec_support':format(rr,'.12g'),
           'search_entropy':format(es,'.12g'),'rec_entropy':format(er,'.12g'),'js_binary64':js.hex(),'rsi_binary64':rsi.hex(),'rsi_split_key':q12(abs(rsi))}
        for (_,key,_),value in zip(COMP,[js,nd,tm]):r[key]=q12(value)
        records.append(r)
    for _,key,rk in COMP:
        freq=Counter(r[key] for r in records);start=0;mp={}
        for value,n in sorted(freq.items(),reverse=True):mp[value]=2*start+n+1;start+=n
        for r in records:r[rk]=mp[r[key]]
    for r in records:
        rsd=sum((Fraction(2,120+r[rk]) for _,_,rk in COMP),Fraction());r['rsd_numerator']=rsd.numerator;r['rsd_denominator']=rsd.denominator
    med=median([Fraction(r['rsd_numerator'],r['rsd_denominator']) for r in records]);mi=median([r['rsi_split_key'] for r in records])
    for r in records:
        rsd=Fraction(r['rsd_numerator'],r['rsd_denominator']);r['rsd_at_median']=int(rsd==med);r['rsi_at_median']=int(r['rsi_split_key']==mi)
        r['rsd_bucket']='high_rsd' if rsd>med else 'low_rsd';r['rsi_mag_bucket']='high_rsi' if r['rsi_split_key']>mi else 'low_rsi'
    output_csv(path,records)

def self_test(out):
    root=Path(out)
    if root.exists():raise ValueError('test output must be fresh')
    root.mkdir(parents=True);checks=[]
    def check(name,condition):
        if not condition:raise AssertionError(name)
        checks.append(name)
    counts={
      'a':{'search':{'x':[1,2],'ignored':0},'rec':{'x':3}},
      'b':{'search':{'x':1},'rec':{'y':2}},
      'c':{'search':{'x':1},'rec':{'x':1,'y':1}},
      'd':{'search':{'x':1,'y':1},'rec':{'x':1,'y':1}},
      'e':{'search':{'x':2,'y':3},'rec':{'y':4,'z':1}},
      'f':{'search':{'x':21,'y':80},'rec':{'x':22,'y':80}},
      'g':{'search':{'x':3,'y':3},'rec':{'x':7}},
    }
    top=root/'top.csv';cnt=root/'counts.csv';fixture_topology(top,counts)
    input_rows=[]
    for item,roles in counts.items():
        for role,labels in roles.items():
            for label,value in labels.items():
                for v in value if isinstance(value,list) else [value]:input_rows.append({'dataset':'fabricated','item_id':item,'role':role,'label':label,'count':v})
    # Excluded IDs and zero labels cannot alter the frozen universe.
    input_rows += [{'dataset':'fabricated','item_id':'outside','role':'search','label':'foreign','count':99}]
    output_csv(cnt,input_rows)
    a=analyze(top,cnt,root/'aggregate',root/'restricted')
    check('all source supports/entropy and exact ranks/fractions accepted',a['checks']['exact_rrf_all_rows']==7)
    check('duplicate source label rows collapsed',a['source_count_read']['duplicate_positive_label_rows']==1)
    check('zero row excluded from label cardinality',a['cohorts']['all']['indicators']['both_single_label']['items']==2)
    check('single label both entropy zero',a['cohorts']['all']['indicators']['both_entropy_zero']['items']==2)
    check('disjoint source labels raw JS one',a['cohorts']['all']['indicators']['disjoint_label_sets']['items']==1)
    check('two endpoints absent from zero denominators',all(v['fraction'] is None for x in a['strata']['all']['joint'] if x['items']==0 for v in x['label_overlap'].values()))
    check('RSI absolute one from one zero entropy role',a['cohorts']['all']['indicators']['rsi_abs_raw_one']['items']==2)
    check('median cohort plus complement exhaustive',a['cohorts']['rsd_median']['items']+a['cohorts']['rsd_not_median']['items']==7)
    for b,example in zip(BINS,[1.,2.,6.,21.,101.]):check('fixed support bin '+b,support_bin(example)==b)
    try:support_bin(1.5);check('fractional support refused',False)
    except ValueError:check('fractional support refused',True)
    shuffled=root/'counts_reversed.csv';output_csv(shuffled,list(reversed(input_rows)))
    b=analyze(top,shuffled,root/'aggregate_reordered',root/'restricted_reordered')
    for key in ('cohorts','strata','component_triples','rsd_tie_decomposition','js_raw_q12','checks'):
        check('count order invariant '+key,a[key]==b[key])
    # Exercise genuine numerical merges, endpoint neighbors, and signed-zero representations.
    fabricated=[{'keys':(0,0,0),'js':0.,'raw':{'js_binary64':0.0.hex()},'flags':{'disjoint_label_sets':False},'rsd_median_flag':1},
                {'keys':(0,0,0),'js':-0.,'raw':{'js_binary64':(-0.0).hex()},'flags':{'disjoint_label_sets':False},'rsd_median_flag':0},
                {'keys':(SCALE,0,0),'js':1.,'raw':{'js_binary64':1.0.hex()},'flags':{'disjoint_label_sets':True},'rsd_median_flag':1},
                {'keys':(SCALE,0,0),'js':math.nextafter(1.,0.),'raw':{'js_binary64':math.nextafter(1.,0.).hex()},'flags':{'disjoint_label_sets':False},'rsd_median_flag':0}]
    m=js_merge_table(fabricated)
    check('signed zero representations distinguished',m[0]['signed_zero_only_merge'])
    check('endpoint-neighbor binary64 merge distinguished',m[1]['unequal_numeric_merge'] and m[1]['raw_nonendpoint_items']==1)
    check('endpoint-neighbor Q12 identical',q12(math.nextafter(1.,0.))==SCALE)
    probe=[{'keys':(1,2,3),'rsd':Fraction(1,7),'rsd_median_flag':1},{'keys':(1,2,3),'rsd':Fraction(1,7),'rsd_median_flag':1},{'keys':(4,5,6),'rsd':Fraction(1,7),'rsd_median_flag':1}]
    d=rsd_tie_decomposition(probe)[0]
    check('same-triple and cross-triple exact ties separated',d['distinct_component_key_triples']==2 and d['same_triple_repeat_excess']==1 and d['different_triples_same_exact_rsd'])
    check('equal entropy does not imply equal distribution',a['cohorts']['all']['indicators']['equal_entropy_different_normalized_distribution']['items']>=1)
    check('aggregate outputs no raw IDs',not any('item_id' in p.read_text() for p in (root/'aggregate').glob('*')))
    # Duplicate topology item, corrupt exact score, raw/key mismatch, and bad median flags fail closed.
    with top.open(newline='') as f:raw=list(csv.DictReader(f))
    for name,field,value in [('raw key','js_rank_key','42'),('exact RRF','rsd_numerator','1'),('median flag','rsd_at_median',str(1-int(raw[0]['rsd_at_median'])))]:
        bad=[dict(r) for r in raw];bad[0][field]=value;p=root/(name.replace(' ','_')+'.csv');output_csv(p,bad)
        try:read_topology(p);check('refuse '+name,False)
        except ValueError:check('refuse '+name,True)
    p=root/'duplicate.csv';output_csv(p,raw+[raw[0]])
    try:read_topology(p);check('refuse duplicate',False)
    except ValueError:check('refuse duplicate',True)
    benchmark_counts={str(i)+'_'+item:roles for i in range(100) for item,roles in counts.items()}
    bt=root/'benchmark_topology.csv';bc=root/'benchmark_counts.csv';fixture_topology(bt,benchmark_counts)
    benchmark_rows=[]
    for item,roles in benchmark_counts.items():
        for role,labels in roles.items():
            for label,value in labels.items():
                for v in value if isinstance(value,list) else [value]:benchmark_rows.append({'dataset':'fabricated','item_id':item,'role':role,'label':label,'count':v})
    output_csv(bc,benchmark_rows)
    bench=analyze(bt,bc,root/'benchmark_aggregate',root/'benchmark_restricted')
    check('fabricated 700-item benchmark',bench['items']==700)
    receipt={'status':'PASS','benchmark':{'items':700,'positive_count_rows':bench['source_count_read']['retained_positive_rows'],'elapsed_seconds':bench['runtime']['elapsed_seconds'],'peak_rss_native_units':bench['runtime']['peak_rss_native_units']},'assertions':len(checks),'checks':checks,'script_sha256':digest(__file__),'python':sys.version,
             'real_data_aggregated':False}
    (root/'RECEIPT.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(receipt))

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--topology',type=Path);p.add_argument('--role-counts',type=Path)
    p.add_argument('--out',type=Path);p.add_argument('--restricted-out',type=Path)
    p.add_argument('--self-test',type=Path);p.add_argument('--inputs',type=Path)
    a=p.parse_args()
    if a.self_test:
        if any([a.topology,a.role_counts,a.out,a.restricted_out,a.inputs]):p.error('self-test is exclusive')
        self_test(a.self_test);return
    if not all([a.topology,a.role_counts,a.out,a.restricted_out,a.inputs]):p.error('four analysis paths and --inputs manifest required')
    declared={Path(x['path']).resolve():x['sha256'] for x in json.loads(a.inputs.read_text())['assets']}
    expected={'topology':declared[a.topology.resolve()],'role_counts':declared[a.role_counts.resolve()]}
    r=analyze(a.topology,a.role_counts,a.out,a.restricted_out,expected)
    print(json.dumps({'status':'PASS','dataset':r['dataset'],'items':r['items'],'elapsed_seconds':r['runtime']['elapsed_seconds']}))
if __name__=='__main__':main()
