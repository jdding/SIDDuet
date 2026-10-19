#!/usr/bin/env python3
"""Import a business count CSV through an explicit field and task mapping."""
from __future__ import annotations
import argparse,csv,hashlib,json
from collections import Counter
from pathlib import Path

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def main():
 ap=argparse.ArgumentParser(description=__doc__)
 for n in ['input','config','out-csv','out-json']:ap.add_argument('--'+n,type=Path,required=True)
 a=ap.parse_args()
 if a.out_csv.exists() or a.out_json.exists():raise ValueError('use fresh output paths')
 cfg=json.loads(a.config.read_text());fields=cfg['fields'];roles=cfg['role_values'];dataset=str(cfg['dataset']).strip()
 if not dataset or set(fields)!={'item_id','role','label','count'}:raise ValueError('declare a dataset and item_id/role/label/count fields')
 if not roles or not set(roles.values())<={'search','rec'}:raise ValueError('role_values must map explicitly to search or rec')
 totals=Counter();source_rows=0
 with a.input.open(encoding='utf-8',newline='') as f:
  reader=csv.DictReader(f)
  if not set(fields.values())<=set(reader.fieldnames or []):raise ValueError('configured fields are absent from CSV header')
  for number,row in enumerate(reader,start=2):
   item=row[fields['item_id']].strip();label=row[fields['label']].strip();role=roles.get(row[fields['role']])
   try:count=int(row[fields['count']])
   except (ValueError,TypeError):raise ValueError('count must be a positive integer on row '+str(number))
   if not item or not label or role is None or count<=0:raise ValueError('invalid item, label, task or count on row '+str(number))
   totals[(dataset,item,role,label)]+=count;source_rows+=1
 if not totals:raise ValueError('input is empty')
 a.out_csv.parent.mkdir(parents=True,exist_ok=True)
 with a.out_csv.open('w',encoding='utf-8',newline='') as f:
  w=csv.writer(f);w.writerow(['dataset','item_id','role','label','count'])
  for key,count in sorted(totals.items()):w.writerow([*key,count])
 report={'schema':'sr_sid_rolemap.count_import.v1','status':'pass','dataset':dataset,'source_rows':source_rows,'aggregated_rows':len(totals),'roles_seen':sorted({k[2] for k in totals}),'input_sha256':digest(a.input),'config_sha256':digest(a.config),'output_sha256':digest(a.out_csv),'boundary':'Field conversion preserves declared counts. The producer must define the contextual labels and observation unit; this importer does not infer task or label meaning.'}
 a.out_json.parent.mkdir(parents=True,exist_ok=True);a.out_json.write_text(json.dumps(report,indent=2)+'\n');print('PASS_ROLE_COUNTS_IMPORT')
if __name__=='__main__':main()
