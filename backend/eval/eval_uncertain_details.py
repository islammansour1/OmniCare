"""Opt-in hosted regression for useful policy details after an uncertain mixed account."""
import sys, tempfile, logging, json
from pathlib import Path
from dotenv import load_dotenv
ROOT=Path(__file__).resolve().parents[2]
load_dotenv(ROOT/'.env'); sys.path.insert(0,str(ROOT/'backend'))
logging.disable(logging.CRITICAL)
from app.agent.llm import get_language_model
from app.agent.graph import run_agent
from app.rag import RagPipeline
from app.claims import ClaimsStore
from app.db import Database
from app.deps import Deps
messages=['I got a bad sink and now my floor is all messed up I need it fixed asap',
          "I'm not really sure I think it was slow then all at once !"]
rows=[]
with tempfile.TemporaryDirectory(prefix='omnicare-dialogue-') as temp:
 p=Path(temp);(p/'claims.json').write_text('[]')
 deps=Deps(lm=get_language_model(),rag=RagPipeline(chroma_dir=p/'chroma',policy_file=ROOT/'sample_policy.md'),db=Database(p/'db.sqlite'),claims=ClaimsStore(p/'claims.json'))
 for i, message in enumerate(messages):
  try:
   r=run_agent('synthetic-conversation',message,history=deps.db.get_history('synthetic-conversation'),deps=deps)
   deps.db.record_turn('synthetic-conversation',message,r,None,'')
   row={'turn':i+1,'input':message,'type':r['message_type'],'response':r['response'],
        'verdict':r['data'].get('verdict'),'source_ids':[s['id'] for s in r['sources']]}
   rows.append(row); print(json.dumps(row),flush=True)
  except Exception as exc:
   rows.append({'turn':i+1,'error':type(exc).__name__});print(rows[-1],flush=True);break
 (ROOT/'backend/eval/uncertain_details_live.json').write_text(json.dumps(rows,indent=2))

last = rows[-1]
assert len(rows) == 2 and last['type'] == 'coverage_answer'
assert last['verdict'] == 'uncertain' and last['source_ids']
assert '?' not in last['response']
assert '25000' in last['response'].replace(',', '') and '500' in last['response']
