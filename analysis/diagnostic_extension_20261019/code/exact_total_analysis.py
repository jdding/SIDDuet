#!/usr/bin/env python3
"""Post-primary exact-total paired-regrouping robustness."""
from __future__ import annotations
import argparse, csv, hashlib, importlib.util, json, math, os, platform, resource, sys, time
from pathlib import Path
import numpy as np

POPULATION_SHA='67a40d4aea4d81f5bddbbfb8ae4dc28d30c5da00e904bb25c7f1764bfa6e780a'
PRIMARY_SHA='cf4e6390265b72b8d8f5a0c401002ac9f86eb117cdd51ec51531416a8cc3a5f6'
REPS=199

def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(4*1024*1024),b''):h.update(block)
    return h.hexdigest()

def write_json(path,value):
    Path(path).parent.mkdir(parents=True,exist_ok=True)
    with Path(path).open('x') as f:json.dump(value,f,indent=2,sort_keys=True,allow_nan=False);f.write('\n')

def load_population(path):
    if sha(path)!=POPULATION_SHA:raise ValueError('frozen population helper hash mismatch')
    spec=importlib.util.spec_from_file_location('frozen_population_helpers',str(path))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    if module.REPS!=REPS:raise ValueError('helper draw count mismatch')
    return module

def exact_classes(s,r):
    n=np.asarray(s,dtype=np.int64)+np.asarray(r,dtype=np.int64)
    order=np.argsort(n,kind='stable')
    splits=np.flatnonzero(np.diff(n[order]))+1
    classes=np.split(order,splits)
    variable=[idx for idx in classes if len(np.unique(s[idx]))>1]
    return classes,{'exact_total_classes':len(classes),'singleton_classes':sum(len(x)==1 for x in classes),
        'singleton_class_items':sum(len(x) for x in classes if len(x)==1),
        'multiple_slot_classes':sum(len(x)>=2 for x in classes),
        'multiple_slot_items':sum(len(x) for x in classes if len(x)>=2),
        'nontrivial_paired_value_classes':len(variable),'nontrivial_paired_value_items':sum(map(len,variable)),
        'nontrivial_paired_value_item_fraction':sum(map(len,variable))/len(s),
        'definition':'Nontrivial classes contain at least two different paired (S,R) values at exactly the same total; identity permutations and identical-pair exchanges are retained.'}

def exact_permutation_indices(classes,n,rng):
    perm=np.arange(n,dtype=np.int64)
    for idx in classes:perm[idx]=rng.permutation(idx)
    return perm

def equal_nested(left,right,tol=1e-14,path='root'):
    if isinstance(left,dict):
        if not isinstance(right,dict) or set(left)!=set(right):raise ValueError('observed dictionary mismatch at '+path)
        for k in left:equal_nested(left[k],right[k],tol,path+'/'+k)
    elif isinstance(left,(list,tuple)):
        if len(left)!=len(right):raise ValueError('observed list length mismatch at '+path)
        for i,(a,b) in enumerate(zip(left,right)):equal_nested(a,b,tol,path+'/'+str(i))
    elif isinstance(left,float) or isinstance(right,float):
        if left is None or right is None or not math.isclose(left,right,rel_tol=0,abs_tol=tol):raise ValueError('observed float mismatch at '+path)
    elif left!=right:raise ValueError('observed value mismatch at '+path)

def check_permutation(s,r,perm,classes,group_states):
    n=s+r
    if len(np.unique(perm))!=len(s) or not np.array_equal(n[perm],n):
        raise ValueError('paired permutation failed exact per-slot total/global multiset check')
    if np.any(s[perm]<1) or np.any(r[perm]<1):raise ValueError('positive-support selection not retained')
    for state in group_states:
        actual=np.bincount(state['groups'],weights=n[perm],minlength=len(state['sizes']))
        if not np.array_equal(actual,state['observed']['events']):raise ValueError('combined group total changed')

def evaluate_mapping_views(s,r,perm,states,h):
    # One immutable pair permutation is explicitly shared by every mapping view.
    ss,rr=s[perm],r[perm]
    return {family:h.group_stats(ss,rr,state['groups'],state['sizes']) for family,state in states.items()}

def run(args,helpers):
    if args.out.exists() or args.restricted_out.exists():raise ValueError('fresh distinct output directories required')
    paths=[args.out.resolve(),args.restricted_out.resolve()]
    if paths[0]==paths[1] or paths[0] in paths[1].parents or paths[1] in paths[0].parents:
        raise ValueError('outputs must be distinct and non-nested')
    bindings={'exact_total_code_sha256':sha(__file__),'exact_total_plan_sha256':sha(args.plan),
        'population_code_sha256':sha(args.population_code),'original_primary_results_sha256':sha(args.primary_results),
        'inputs_manifest_sha256':sha(args.inputs)}
    if args.acceptance_receipt:
        gate=json.loads(args.acceptance_receipt.read_text())
        if gate.get('decision')!='ACCEPT_RUN' or any(gate.get(k)!=v for k,v in bindings.items()):
            raise ValueError('supplied receipt must bind the declared inputs and code')
    if sha(args.primary_results)!=PRIMARY_SHA:raise ValueError('frozen primary result identity mismatch')
    args.out.mkdir(parents=True);args.restricted_out.mkdir(parents=True)
    try:
        return run_accepted(args,helpers,bindings)
    except Exception as exc:
        write_json(args.out/'FAILURE_RECEIPT.json',{'status':'FAILED_STOP_NO_FALLBACK','exception_type':type(exc).__name__,
            'exception_message':str(exc),'command_argv':sys.argv,'bindings':bindings,'no_training_or_model_calls':True})
        raise

def run_accepted(args,h,bindings):
    start=time.perf_counter();primary=json.loads(args.primary_results.read_text())
    originals={(x['dataset'],x['mapping_family']):x for x in primary['results']}
    data,assets=h.read_inputs(args.inputs)
    all_records=[];all_draws={};additional=[];partial={}
    for di,dataset in enumerate(h.DATASETS):
        d=data[dataset];s,r=d['s'],d['r'];states={}
        classes,mobility=exact_classes(s,r)
        for family in h.FAMILIES:
            m=d[family];stats=h.group_stats(s,r,m['groups'],m['sizes']);masks=h.strata(m['sizes'],stats)
            observed=h.describe(stats,m['sizes'],masks);original=originals[(dataset,family)]
            equal_nested(observed,original['observed'])
            admission=h.check_admission(args.admissions,dataset,family,m['sizes'],len(s))
            if admission['sha256']!=original['existing_admission_check']['sha256']:
                raise ValueError('admission source changed from the original primary analysis')
            additional.append(admission)
            states[family]={'groups':m['groups'],'sizes':m['sizes'],'sids':m['sids'],'observed':stats,'masks':masks,
                'description':observed,'null':h.empty_null(masks),'group_jsd':np.empty((REPS,len(m['sizes'])),dtype=float),
                'original':original,'admission':admission}
        rng=np.random.Generator(np.random.PCG64(20263018+di));draw_hashes=[]
        changed_slots=[];dataset_start=time.perf_counter()
        for b in range(REPS):
            if time.perf_counter()-start>300:
                write_json(args.out/'PARTIAL_NULL_AGGREGATES.json',all_draws|{dataset:{f:state['null'] for f,state in states.items()}})
                raise TimeoutError('fixed five-minute CPU cap reached; no draw reduction or fallback')
            perm=exact_permutation_indices(classes,len(s),rng)
            check_permutation(s,r,perm,classes,list(states.values()))
            draw_hashes.append(hashlib.sha256(perm.tobytes()).hexdigest())
            changed_slots.append(int(np.count_nonzero((s[perm]!=s)|(r[perm]!=r))))
            draw_views=evaluate_mapping_views(s,r,perm,states,h)
            for family,state in states.items():
                st=draw_views[family]
                h.add_null(state['null'],st,state['sizes'],state['masks'])
                state['group_jsd'][b]=st['jsd']
        for family,state in states.items():
            original=state['original'];observed=state['description'];summary=h.summarize_null(state['null'],observed)
            obs=observed['all_collision_groups']['means']['equal_group_jsd']
            null_values=state['null']['all_collision_groups']['equal_group_jsd']
            record={'dataset':dataset,'mapping_family':family,'analysis_stage':'post-primary robustness',
                'items':original['items'],'sid_groups':original['sid_groups'],'singleton_groups':original['singleton_groups'],
                'collision_groups':original['collision_groups'],'collision_items':original['collision_items'],
                'existing_admission_check':state['admission'],'observed_matches_original_primary':True,'observed':observed,
                'exact_total_mobility':mobility,
                'control_B_exact':{'draws':REPS,'seed':20263018+di,'dataset_draws_shared_across_families':True,
                    'permutation_checks':REPS,'exact_slot_and_combined_group_totals_preserved':True,
                    'separate_group_task_totals_preserved':False,'positive_support_selection_preserved':True,
                    'stratum_membership':'fixed from observed groups','dataset_elapsed_seconds':time.perf_counter()-dataset_start,
                    'changed_paired_value_slots':{'min':min(changed_slots),'mean':float(np.mean(changed_slots)),'max':max(changed_slots)},
                    'draw_permutation_sha256':draw_hashes,'summaries':summary},
                'primary_supplementary_two_sided_p':h.empirical_p(obs,null_values),
                'primary_supplementary_null_constant':len(set(null_values))==1,
                'original_B_primary_equal_group':original['control_B']['summaries']['all_collision_groups']['equal_group_jsd']}
            path=args.restricted_out/(dataset+'_'+family+'_exact_total_groups.csv')
            sizes=state['sizes'];js=state['group_jsd'];coll=sizes>=2
            means=js[:,coll].mean(axis=0);limits=np.percentile(js[:,coll],[2.5,97.5],axis=0)
            columns=['dataset','mapping_family','restricted_sid_group','members','search_observations','rec_observations','observed_jsd','observed_argmax_disjoint','B_exact_mean_jsd','B_exact_q025_jsd','B_exact_q975_jsd']
            with path.open('x',newline='') as f:
                writer=csv.DictWriter(f,fieldnames=columns);writer.writeheader();j=0
                for g,n in enumerate(sizes):
                    row=dict(zip(columns,[dataset,family,state['sids'][g],int(n),int(state['observed']['search'][g]),int(state['observed']['rec'][g]),float(state['observed']['jsd'][g]),bool(state['observed']['disjoint'][g]),None,None,None]))
                    if n>=2:
                        row.update(dict(zip(columns[-3:],[float(means[j]),float(limits[0,j]),float(limits[1,j])])));j+=1
                    writer.writerow(row)
            record['restricted_group_table']={'basename':path.name,'rows':len(sizes),'sha256':sha(path)}
            all_records.append(record);all_draws[dataset+'/'+family]=state['null']
        print(json.dumps({'phase':'dataset_complete','dataset':dataset,'elapsed_seconds':time.perf_counter()-start}),flush=True)
    adjusted=h.bh([x['primary_supplementary_two_sided_p'] for x in all_records]);harmonic=sum(1/k for k in range(1,7))
    for record,bh in zip(all_records,adjusted):
        record['primary_supplementary_BH_adjusted_p_across_six']=bh
        record['primary_supplementary_BY_adjusted_p_dependency_sensitivity']=min(1,bh*harmonic)
    for asset in assets:
        if sha(asset['path'])!=asset['sha256']:raise ValueError('scientific input changed during execution')
    for admission in additional:
        if sha(admission['path'])!=admission['sha256']:raise ValueError('admission input changed during execution')
    paths={'exact_total_code_sha256':__file__,'exact_total_plan_sha256':args.plan,'population_code_sha256':args.population_code,
        'original_primary_results_sha256':args.primary_results,'inputs_manifest_sha256':args.inputs}
    if any(sha(path)!=bindings[k] for k,path in paths.items()):raise ValueError('code/plan/primary identity changed during execution')
    result={'schema':'sr_sid_rolemap.exact_total_paired_regrouping.v1','status':'COMPLETE_VALIDITY_CHECKS_PASSED',
        'analysis_stage':'post-primary robustness; explicitly designed after original primary outcomes were inspected',
        'profile_id':h.PROFILE,'draws':REPS,'results':all_records,'bindings':bindings,
        'reference_definition':'paired (S,R) permutations within exact integer S+R classes, identical dataset draws across families',
        'conditioning':'exact positive per-item totals and group combined totals are retained; separate group S/R totals are not retained',
        'exchangeability_boundary':'Count pairs within equal-total classes provide a reference, not randomized actual SID assignments; semantic, temporal and role-exposure confounding remain.',
        'claim_boundary':'A robustness check of descriptive count-allocation heterogeneity, not semantic compatibility, harmfulness, causal effect or heldout utility; two related references are not independent replication.',
        'inference':'Six supplementary equal-group comparisons, finite two-sided empirical p, BH six plus BY(H6) sensitivity; minimum p .01; not the original outcome-blind primary family.',
        'inputs':assets,'inputs_rehashed_after':True,'admissions_rehashed_after':True,'command_argv':sys.argv,
        'python':sys.version,'numpy':np.__version__,'platform':platform.platform(),'elapsed_seconds':time.perf_counter()-start,
        'maxrss_native':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,'maxrss_unit':'bytes on macOS; KiB on Linux',
        'runtime_actor':'local installed CPython + NumPy, CPU only, no external API or paid compute','no_training_or_model_calls':True,
        'launcher_policy':'Standalone local CPU randomization analysis with dedicated complete receipt; no model/training launcher invoked.'}
    write_json(args.out/'EXACT_TOTAL_RESULTS.json',result);write_json(args.out/'NULL_AGGREGATE_DRAWS.json',all_draws)
    outputs=[args.out/'EXACT_TOTAL_RESULTS.json',args.out/'NULL_AGGREGATE_DRAWS.json']+sorted(args.restricted_out.glob('*.csv'))
    write_json(args.out/'EXECUTION_RECEIPT.json',{'status':result['status'],'command_argv':sys.argv,'bindings':bindings,
        'gate_receipt_sha256':sha(args.acceptance_receipt) if args.acceptance_receipt else None,'inputs_checked_before_after':assets,'admission_inputs_checked_before_after':additional,
        'output_files':[{'path':str(p),'bytes':p.stat().st_size,'sha256':sha(p)} for p in outputs],
        'runtime_actor':result['runtime_actor'],'launcher_policy':result['launcher_policy'],'python':sys.version,'numpy':np.__version__,
        'blas_thread_env':{k:os.environ.get(k) for k in ['OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','VECLIB_MAXIMUM_THREADS']},
        'elapsed_seconds':time.perf_counter()-start,'maxrss_native':result['maxrss_native'],'maxrss_unit':result['maxrss_unit'],
        'no_training_or_model_calls':True})
    print(json.dumps({'status':result['status'],'elapsed_seconds':result['elapsed_seconds'],'results_sha256':sha(args.out/'EXACT_TOTAL_RESULTS.json')}),flush=True)

def test(args,h):
    checks=[]
    def ok(name,val):
        if not bool(val):raise AssertionError(name)
        checks.append(name)
    s=np.array([1,2,1,2,3,1,4,2]);r=np.array([2,1,2,1,1,3,1,5]);group=np.array([0,0,1,1,2,2,3,3]);sizes=np.full(4,2)
    classes,mobility=exact_classes(s,r);base=h.group_stats(s,r,group,sizes);state={'groups':group,'sizes':sizes,'observed':base}
    rng=np.random.Generator(np.random.PCG64(101));allperms=[];vals=[]
    for i in range(REPS):
        perm=exact_permutation_indices(classes,len(s),rng);check_permutation(s,r,perm,classes,[state]);allperms.append(perm)
        vals.append(h.group_stats(s[perm],r[perm],group,sizes)['jsd'].mean())
    ok('199_exact_slot_total_multiset_positivity_and_group_total_checks',len(allperms)==REPS)
    ok('exact_total_class_count',mobility['exact_total_classes']==4)
    ok('singleton_class_accounting',mobility['singleton_classes']==2 and mobility['singleton_class_items']==2)
    ok('nontrivial_pair_class_accounting',mobility['nontrivial_paired_value_classes']==2 and mobility['nontrivial_paired_value_items']==6)
    ok('exact_total_conditioning_not_separate_task_totals',any(not np.array_equal(np.bincount(group,weights=s[p]),base['search']) for p in allperms))
    second=np.tile(np.arange(4),2)
    maps={'first':state,'second':{'groups':second,'sizes':sizes}}
    oneperm=allperms[5];views=evaluate_mapping_views(s,r,oneperm,maps,h)
    reference={}
    for name,view in maps.items():
        independent=[]
        for g in range(4):
            members=oneperm[view['groups']==g]
            independent.append(h.independent_js(s[members].tolist(),r[members].tolist()))
        reference[name]=independent
    ok('same_dataset_draw_shared_across_mapping_views_independent_JS',all(np.allclose(views[name]['jsd'],reference[name],rtol=0,atol=1e-14) for name in maps))
    # Exact 4-slot permutation enumeration: two (1,3) and two (3,1) pairs, two groups of 2.
    a=np.array([1,1,3,3]);b=4-a;gp=np.array([0,0,1,1]);sz=np.array([2,2]);enum=[]
    for perm in __import__('itertools').permutations(range(4)):
        perm=np.array(perm);one=[]
        for g in range(2):
            idx=perm[gp==g];one.append(h.independent_js(a[idx].tolist(),b[idx].tolist()))
        enum.append(sum(one)/2)
    target=float(np.mean(enum));cl,_=exact_classes(a,b);rng=np.random.Generator(np.random.PCG64(55));sim=[]
    for _ in range(30000):
        p=exact_permutation_indices(cl,4,rng);sim.append(float(h.group_stats(a[p],b[p],gp,sz)['jsd'].mean()))
    ok('exact_small_permutation_mean_matches_independent_enumeration',abs(np.mean(sim)-target)<6*np.std(sim)/math.sqrt(len(sim)))
    low=h.group_stats(a,b,gp,sz)['jsd'].mean();high=h.group_stats(a,b,np.tile(np.array([0,1]),2),sz)['jsd'].mean()
    ok('controlled_negative_effect_direction',low<target)
    ok('controlled_positive_effect_direction',high>target)
    a=np.array([1,1,1,1]);b=np.array([1,2,3,4]);cl,_=exact_classes(a,b);p=exact_permutation_indices(cl,4,rng)
    ok('unique_total_degenerate_identity',np.array_equal(p,np.arange(4)))
    a=np.array([1,1,1,1]);b=np.array([2,2,2,2]);cl,mo=exact_classes(a,b);p=exact_permutation_indices(cl,4,rng)
    ok('identical_pairs_retain_null_degeneracy',np.array_equal(a[p],a) and mo['nontrivial_paired_value_items']==0)
    ok('constant_null_p_one',h.empirical_p(.1,[.1]*REPS)==1)
    ok('zero_width_null_interval',np.array_equal(np.percentile([.1]*REPS,[2.5,97.5]),np.array([.1,.1])))
    a=np.array([1,1,9,1,4]);b=np.array([1,1,1,9,7]);gp=np.array([0,0,1,1,2]);sz=np.array([2,2,1]);st=h.group_stats(a,b,gp,sz);masks=h.strata(sz,st)
    ok('singleton_excluded',masks['all_collision_groups'].tolist()==[True,True,False])
    ok('all_equal_argmax_sets_overlap',not st['disjoint'][0] and st['argmax_overlap_count'][0]==2)
    reorder=np.array([4,2,0,3,1]);st2=h.group_stats(a[reorder],b[reorder],gp[reorder],sz)
    ok('observed_input_ID_reordering_invariant',all(np.array_equal(st[k],st2[k]) for k in st))
    frozen=h.describe(st,sz,masks);equal_nested(frozen,h.describe(st2,sz,h.strata(sz,st2)))
    ok('observed_helper_summaries_identical',True)
    empty=np.zeros(3,dtype=bool);ok('empty_stratum_null',all(x is None for x in h.means(st['jsd'],st['disjoint'],sz,st['events'],empty).values()))
    ok('empirical_extreme_p_floor',h.empirical_p(2,[.1]*REPS)==.01)
    ok('BH_BY_six_fixed',np.allclose(h.bh([.01]*6),[.01]*6) and math.isclose(.01*sum(1/k for k in range(1,7)),.0245))
    result={'status':'PASS','fabricated_data_only':True,'checks':checks,'count':len(checks),
        'independent_exact_permutation_mean_jsd':target,'synthetic_MC_mean_jsd':float(np.mean(sim)),
        'code_sha256':sha(__file__),'population_code_sha256':sha(args.population_code),'numpy':np.__version__,'python':sys.version}
    if args.out:write_json(args.out/'TESTS.json',result)
    print(json.dumps({'status':'PASS','checks':len(checks)}))

def benchmark(args,h):
    start=time.perf_counter();rng=np.random.Generator(np.random.PCG64(341));n=100000
    s=rng.integers(1,1000,n);r=rng.integers(1,1000,n);classes,mobility=exact_classes(s,r)
    groups=np.arange(n)//10;sizes=np.full(n//10,10);states=[{'groups':groups,'sizes':sizes,'observed':h.group_stats(s,r,groups,sizes)} for _ in range(3)]
    for _ in range(REPS):
        perm=exact_permutation_indices(classes,n,rng);check_permutation(s,r,perm,classes,states)
        for state in states:h.group_stats(s[perm],r[perm],state['groups'],state['sizes'])
    result={'fabricated_data_only':True,'items':n,'maps':3,'draws':REPS,'exact_total_classes':len(classes),'elapsed_seconds':time.perf_counter()-start,
        'code_sha256':sha(__file__),'population_code_sha256':sha(args.population_code),'maxrss_native':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        'python':sys.version,'numpy':np.__version__,'estimate_boundary':'Actual exact-total multiplicities and I/O affect timing; no real data computed.'}
    if args.out:write_json(args.out/'BENCHMARK.json',result)
    print(json.dumps(result))

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--population-code',type=Path,required=True);subs=p.add_subparsers(dest='mode',required=True)
    q=subs.add_parser('test');q.add_argument('--out',type=Path)
    q=subs.add_parser('benchmark');q.add_argument('--out',type=Path)
    q=subs.add_parser('run')
    for name in ['inputs','admissions','primary-results','plan','out','restricted-out']:q.add_argument('--'+name,type=Path,required=True)
    q.add_argument('--acceptance-receipt',type=Path,help='Optional local provenance receipt')
    args=p.parse_args();helpers=load_population(args.population_code)
    if args.mode=='test':test(args,helpers)
    elif args.mode=='benchmark':benchmark(args,helpers)
    else:run(args,helpers)
if __name__=='__main__':main()
