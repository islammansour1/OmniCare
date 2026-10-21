"""Opt-in hosted claim-workflow regression using isolated synthetic data."""
import sys, tempfile, logging, json
from pathlib import Path
from dotenv import load_dotenv
ROOT=Path(__file__).resolve().parents[2]
load_dotenv(ROOT/'.env')
sys.path.insert(0,str(ROOT/'backend'))
logging.disable(logging.CRITICAL)
from app.agent.llm import get_language_model
from app.agent.graph import run_agent
from app.rag import RagPipeline
from app.claims import ClaimsStore
from app.db import Database
from app.deps import Deps
cases=[
 ('sink','My sink has been leaking for a while and it distroyed my home I need it fixed by your money','excluded'),
 ('paraphrase','The plumbing has been seeping over several months and wrecked the flooring. Please pay for the repairs.','excluded'),
 ('sudden','A pipe suddenly burst this morning and damaged the kitchen. Help me file a claim.','claim_draft'),
 ('unknown','My home has water damage and I need to file a claim, but I do not know where the water came from.','uncertain'),
]
results=[]
with tempfile.TemporaryDirectory(prefix='omnicare-loop-live-') as tmp:
 p=Path(tmp); (p/'claims.json').write_text('[]')
 deps=Deps(lm=get_language_model(),rag=RagPipeline(chroma_dir=p/'chroma',policy_file=ROOT/'sample_policy.md'),db=Database(p/'db.sqlite'),claims=ClaimsStore(p/'claims.json'))
 for name,query,expected in cases:
  try:
   r=run_agent(name,query,deps=deps)
   actual=r.get('data',{}).get('verdict',r['message_type'])
   row=dict(case=name,expected=expected,actual=actual,passed=actual==expected,response=r['response'])
  except Exception as exc:
   row=dict(case=name,passed=False,error=type(exc).__name__)
  results.append(row); print(json.dumps(row),flush=True)
 (ROOT/'backend/eval/claim_workflow_live.json').write_text(json.dumps(results,indent=2))
raise SystemExit(0 if all(r['passed'] for r in results) else 1)
