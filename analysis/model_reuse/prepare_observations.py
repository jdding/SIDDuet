#!/usr/bin/env python3
"""Build RoleMap inputs from a locally held provider-processed UniSAR dataset."""
from __future__ import annotations
import argparse,csv,hashlib,json,pickle,time
from collections import Counter,defaultdict
from pathlib import Path

DATASET='kuaisar_unisar_processed'
def digest(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for c in iter(lambda:f.read(1<<20),b''): h.update(c)
 return h.hexdigest()
def load(p):
 with p.open('rb') as f:return pickle.load(f)
def main():
 ap=argparse.ArgumentParser(description=__doc__)
 ap.add_argument('--processed-root',type=Path,required=True)
 ap.add_argument('--out',type=Path,required=True)
 ap.add_argument('--users',type=int,default=1024)
 ap.add_argument('--seed',default='rolemap-external-20261019-v1')
 a=ap.parse_args();a.out.mkdir(parents=True,exist_ok=False);start=time.monotonic()
 root=a.processed_root
 # Input pickles must come from a trusted, locally held provider release.
 users=load(root/'vocab/user_vocab.pkl');items=load(root/'vocab/item_vocab_np.pkl');sessions=load(root/'vocab/src_session_vocab_np.pkl')
 labels=items['second_level_category_id'];nitems=len(labels)
 selected=sorted((int(u) for u in users if int(u)>0),key=lambda u:hashlib.sha256((a.seed+':user:'+str(u)).encode()).hexdigest())[:a.users]
 counts=defaultdict(Counter);stats=Counter()
 for u in selected:
  ud=users[u]
  stats['rec_history_appearances_total']+=len(ud['rec_his'])
  stats['rec_history_missing_item_or_category']+=sum(not (0<int(v)<nitems and int(labels[int(v)])>0) for v in ud['rec_his'])
  seq=[(float(t),i,int(v)) for i,(v,t) in enumerate(zip(ud['rec_his'],ud['rec_his_ts'])) if 0<int(v)<nitems and int(labels[int(v)])>0]
  seq.sort()
  for (_,_,item),(_,_,nxt) in zip(seq,seq[1:]):counts[(item,'rec')][str(int(labels[nxt]))]+=1;stats['rec_transitions']+=1
  seen=set()
  for sid in ud['src_session_his']:
   sid=int(sid)
   if sid<=0 or sid>=len(sessions['pos_items']) or sid in seen:continue
   seen.add(sid)
   pos=[int(v) for v in sessions['pos_items'][sid] if 0<int(v)<nitems and int(labels[int(v)])>0]
   if not pos:continue
   c=Counter(str(int(labels[v])) for v in pos);label=min(c,key=lambda k:(-c[k],k))
   for item in pos:counts[(item,'search')][label]+=1;stats['search_item_appearances']+=1
   stats['search_sessions']+=1
 search_items={i for i,role in counts if role=='search'};rec_items={i for i,role in counts if role=='rec'}
 common=sorted(search_items&rec_items)
 stats.update(search_items=len(search_items),rec_items=len(rec_items),search_only_items=len(search_items-rec_items),rec_only_items=len(rec_items-search_items))
 with (a.out/'role_label_counts.csv').open('w',newline='') as f:
  w=csv.writer(f);w.writerow(['dataset','item_id','role','label','count'])
  for item in sorted(search_items|rec_items):
   for role in ['search','rec']:
    for lab,n in sorted(counts[(item,role)].items()):w.writerow([DATASET,item,role,lab,n])
 with (a.out/'platform_counts.csv').open('w',newline='') as f:
  w=csv.writer(f);w.writerow(['catalog_item','service','context_category','observations'])
  for item in sorted(search_items|rec_items):
   for role in ['search','rec']:
    for lab,n in sorted(counts[(item,role)].items()):w.writerow([item,'query' if role=='search' else 'feed',lab,n])
 (a.out/'selected_users.json').write_text(json.dumps(selected)+'\n')
 with (a.out/'catalog_path_map.csv').open('w',newline='') as f:
  w=csv.writer(f);w.writerow(['dataset','item_id','sid'])
  for item in common:w.writerow([DATASET,item,json.dumps(['category1:'+str(int(items['first_level_category_id'][item])),'category2:'+str(int(labels[item]))])])
 provenance={str(p.relative_to(root)):digest(p) for p in [root/'vocab/user_vocab.pkl',root/'vocab/item_vocab_np.pkl',root/'vocab/src_session_vocab_np.pkl']}
 report={'status':'PASS_INPUT_CONVERSION','dataset':DATASET,'preprocessing_profile':'unisar_processed_positive_context_v1','sample_rule':'First requested users by SHA256(seed:user:processed_user_id), independent of topology or predictions.','sampling_seed':a.seed,'users_available':len(users)-1,'users_selected':len(selected),'common_items':len(common),'observations':dict(stats),'source_sha256':provenance,'converter_sha256':digest(Path(__file__)),'catalog_map_sha256':digest(a.out/'catalog_path_map.csv'),'map_semantics':'Illustrative provider category path, not a learned SID or an independent tokenizer.','counts_sha256':digest(a.out/'role_label_counts.csv'),'selected_users_sha256':digest(a.out/'selected_users.json'),'seconds':time.monotonic()-start,'limits':['Processed ID namespace; no asserted raw-ID bridge to the original RoleMap reference.','Positive histories and at most five clicked items per processed search session, not complete exposure logs.','Descriptive observations include the stored history; not a train-only predictor or a prospective utility test.','Same KuaiSAR provider, new input view; not a third independent dataset.','User/item rows remain local; this report is aggregate.']}
 (a.out/'PREPARATION.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:report[k] for k in ['status','users_selected','common_items','seconds']}),flush=True)
if __name__=='__main__':main()
