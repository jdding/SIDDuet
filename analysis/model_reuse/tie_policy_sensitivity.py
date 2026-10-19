from pathlib import Path
import csv,json,math,time
import argparse
ap=argparse.ArgumentParser(description="Compare prior candidate-ID tie breaking with expected exact-tie metrics on the same exported scores.")
for n in ['scores','units','inference','out']:ap.add_argument('--'+n,type=Path,required=True)
cfg=ap.parse_args();t0=time.monotonic()
if cfg.out.exists():raise ValueError('output already exists')
covered=set()
with cfg.units.open(newline='') as f:
 for r in csv.DictReader(f):
  if int(r['covered']):covered.add(r['unit_id'])
agg={role:{s:{'requests':0,'old_ndcg_sum':0.,'new_ndcg_sum':0.,'old_hit_sum':0.,'new_hit_sum':0.,'tied_requests':0} for s in ['all','covered']} for role in ['search','rec']}
def flush(rows):
 if not rows:return
 target=[r for r in rows if r['is_target']=='1'];assert len(target)==1;t=target[0];ts=float(t['score']);tid=t['candidate_id'];higher=sum(float(r['score'])>ts for r in rows);tied=[r for r in rows if float(r['score'])==ts]
 rank=higher+sum(r['candidate_id']<tid for r in tied)+1;old=1/math.log2(rank+1) if rank<=10 else 0.
 ranks=range(higher+1,higher+len(tied)+1);new=sum(1/math.log2(k+1) for k in ranks if k<=10)/len(tied);newhit=sum(k<=10 for k in ranks)/len(tied)
 for s in ['all']+(['covered'] if t['unit_id'] in covered else []):
  a=agg[t['role']][s];a['requests']+=1;a['old_ndcg_sum']+=old;a['new_ndcg_sum']+=new;a['old_hit_sum']+=int(rank<=10);a['new_hit_sum']+=newhit;a['tied_requests']+=len(tied)>1
with cfg.scores.open(newline='') as f:
 group=[];key=None
 for row in csv.DictReader(f):
  if row['unit_id']!=key:flush(group);group=[];key=row['unit_id']
  group.append(row)
 flush(group)
expected=json.loads(cfg.inference.read_text())
for role,sub in agg.items():
 for name,a in sub.items():
  for x in ['old_ndcg','new_ndcg','old_hit','new_hit']:a[x+'10']=a.pop(x+'_sum')/a['requests']
  assert abs(a['new_ndcg10']-expected['roles'][role]['covered_ndcg10' if name=='covered' else 'ndcg10'])<1e-12
report={'status':'PASS_TIE_POLICY_SENSITIVITY','old_policy':'sort by score, then lexicographic candidate ID (v2)','new_policy':'expected gain uniformly within exact score ties (v3)','study_primary':'v3','roles':agg,'coverage_difference_direction_same_under_both_policies':all((x['covered']['old_ndcg10']<x['all']['old_ndcg10'])==(x['covered']['new_ndcg10']<x['all']['new_ndcg10']) for x in agg.values()),'historical_frozen_reports_recomputed':False,'method_or_weights_changed':False,'seconds':time.monotonic()-t0,'boundary':'Descriptive metric sensitivity on the same actual predictions. Candidate-ID ordering is arbitrary; old IDs are not semantic ground truth.'}
cfg.out.parent.mkdir(parents=True,exist_ok=True)
cfg.out.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
