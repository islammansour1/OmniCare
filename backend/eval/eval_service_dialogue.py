"""Opt-in hosted four-turn customer-service regression with isolated storage."""
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
messages=['My sink got bad and it distroyed my floor I need it covered by you',
          "no I just woke up today and I'm drowning",'yeah sudden','yeah the pipe just broken suddenly']
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
 (ROOT/'backend/eval/service_dialogue_live.json').write_text(json.dumps(rows,indent=2))

passed = (len(rows) == 4 and rows[0].get('type') == 'clarification'
          and sum(r.get('type') == 'clarification' for r in rows) <= 2
          and rows[-1].get('type') == 'claim_draft' and bool(rows[-1].get('source_ids'))
          and not any('error' in r for r in rows))
raise SystemExit(0 if passed else 1)
