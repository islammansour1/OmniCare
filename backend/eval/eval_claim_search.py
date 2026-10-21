"""Opt-in hosted semantic claim-search smoke test using ONLY synthetic records."""
from __future__ import annotations
import json
import sys
import tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.agent.llm import get_language_model
from app.claims.store import ClaimsStore
from app.rag.embeddings import get_embedder


def main():
    records = [
        {'claim_id':'CLM-SYNTHA','owner_id':'synthetic-user','claim_type':'Equipment transit',
         'status':'Under Review','description':'Rented spotlights shattered when the delivery van collided.'},
        {'claim_id':'CLM-SYNTHB','owner_id':'synthetic-user','claim_type':'Mechanical malfunction',
         'status':'Approved','description':'An internal electrical fault stopped the rented generator.'},
        {'claim_id':'CLM-SYNTHC','owner_id':'different-user','claim_type':'Equipment transit',
         'status':'Under Review','description':'Spotlights broke during a van collision.'},
    ]
    cases = [
        ('Find my lighting equipment transport accident claim', ['CLM-SYNTHA']),
        ('Show the power supply failure claim that has been approved', ['CLM-SYNTHB']),
        ('Find my missing musical instrument claim', []),
    ]
    model, embedder = get_language_model(), get_embedder()
    results = []
    with tempfile.TemporaryDirectory(prefix='omnicare-claims-eval-') as temp:
        path = Path(temp)/'claims.json'
        path.write_text(json.dumps(records))
        store = ClaimsStore(path)
        for query, expected in cases:
            try:
                candidates = store.search(query, 'synthetic-user', embedder=embedder)
                actual = model.select_claims(query, candidates)
                result = {'query':query,'expected':expected,'actual':actual,
                          'passed':set(actual)==set(expected)}
            except Exception as exc:
                result = {'query':query,'passed':False,'error':type(exc).__name__}
            results.append(result)
            print(json.dumps(result), flush=True)
    Path(__file__).with_name('audit_claim_search.json').write_text(json.dumps(results,indent=2))
    return 0 if all(r['passed'] for r in results) else 1

if __name__ == '__main__':
    raise SystemExit(main())
