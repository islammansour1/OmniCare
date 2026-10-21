"""Opt-in hosted evidence-review and clarification-voice regression."""
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
stages=[]
with tempfile.TemporaryDirectory(prefix='omnicare-clarify-') as temp:
 p=Path(temp);(p/'claims.json').write_text('[]')
 lm=get_language_model()
 review=lm.review_evidence; compose=lm.compose_clarification
 def tracked_review(*args):
  stages.append('evidence_review'); return review(*args)
 def tracked_compose(*args):
  stages.append('clarification_composer'); return compose(*args)
 lm.review_evidence=tracked_review;lm.compose_clarification=tracked_compose
 deps=Deps(lm=lm,rag=RagPipeline(chroma_dir=p/'chroma',policy_file=ROOT/'sample_policy.md'),db=Database(p/'db.sqlite'),claims=ClaimsStore(p/'claims.json'))
 r=run_agent('test','I got a bad sink and now my floor is all messed up I need it fixed asap',deps=deps)
 report={'type':r['message_type'],'response':r['response'],'stages':stages}
 (ROOT/'backend/eval/clarification_voice_live.json').write_text(json.dumps(report,indent=2))
 print(json.dumps(report),flush=True)
 assert r['message_type']=='clarification'
 assert stages.index('evidence_review') < stages.index('clarification_composer')
