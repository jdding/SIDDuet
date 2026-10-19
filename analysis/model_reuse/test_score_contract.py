"""Observable tie-policy checks through the released CLI, with no provider data."""
import csv,json,math,subprocess,sys,tempfile,unittest
from pathlib import Path
EVALUATOR=Path(__file__).resolve().parents[2]/'scripts/evaluate_fixed_candidates.py'
class ScoreContract(unittest.TestCase):
 def evaluate(self,scores,target=0,direction='higher_is_better',rename=False):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);p=root/'c.csv';rows=[]
   for i,s in enumerate(scores):
    rows.append({'method_id':'fixture','method_paradigm':'discriminative','score_direction':direction,'dataset':'fixture','unit_id':'unit','role':'rec','candidate_id':str(999-i if rename else i),'is_target':int(i==target),'score':s,'topology_cell':'low_rsd|low_rsi','rsd_bucket':'low','rsi_mag_bucket':'low','topology_profile_id':'sr_sid_rolemap.topology.value_median.v2','topology_sha256':'a'*64})
   if rename:rows.reverse()
   with p.open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=rows[0]);w.writeheader();w.writerows(rows)
   subprocess.run([sys.executable,str(EVALUATOR),'--candidates',str(p),'--out-csv',str(root/'o.csv'),'--out-json',str(root/'o.json')],check=True,capture_output=True)
   d=json.loads((root/'o.json').read_text());return next(v for v in d['aggregates'] if v['slice_type']=='all')
 def test_all_tied_candidate_renaming_is_invariant(self):
  a=self.evaluate([1.]*20);b=self.evaluate([1.]*20,rename=True)
  self.assertEqual(a,b);self.assertAlmostEqual(a['hit10'],.5,places=6)
  self.assertAlmostEqual(a['ndcg10'],sum(1/math.log2(k+1) for k in range(1,11))/20,places=6)
 def test_tie_block_crossing_cutoff(self):
  v=self.evaluate([1.]+[2.]*9+[1.]*2+[0.]*3)
  self.assertAlmostEqual(v['hit10'],1/3,places=6);self.assertAlmostEqual(v['ndcg10'],1/(3*math.log2(11)),places=6)
 def test_direction_invariance_without_ties(self):
  a=self.evaluate([2.,3.,1.]);b=self.evaluate([-2.,-3.,-1.],direction='lower_is_better')
  self.assertEqual(a['ndcg10'],b['ndcg10']);self.assertAlmostEqual(a['ndcg10'],1/math.log2(3),places=6)
if __name__=='__main__':unittest.main()
