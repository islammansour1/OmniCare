"""Opt-in hosted retrieval/assessment/clarification check, with isolated storage.

Run against the demo policy only. This sends synthetic dialogue and that policy
through the configured hosted model and embeddings. Outputs include actual
questions and selected source terms for human review of conversational quality.
"""
import argparse
import json
import logging
import sys
import tempfile
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / '.env')
sys.path.insert(0, str(ROOT / 'backend'))
logging.disable(logging.CRITICAL)

from app.agent.graph import run_agent
from app.agent.llm import get_language_model
from app.claims import ClaimsStore
from app.db import Database
from app.deps import Deps
from app.rag import RagPipeline

parser = argparse.ArgumentParser()
parser.add_argument('--scenario', choices=['water', 'vague', 'unknown', 'repair'], default='water')
parser.add_argument('--initial-only', action='store_true')
args = parser.parse_args()
scenario = args.scenario
messages = {
    'water': ['My floor is all flooded up and it ruined my flooring',
              'Kitchen', 'The pipe burst while I was standing there'],
    'vague': ['My floor is messed up and needs fixing'],
    'repair': ['Ok I need to fix the floor then', 'Yes, please start a claim'],
    'unknown': ['My floor is flooded and damaged', "I do not know what caused it",
                "I cannot tell where it came from and have no other details"],
}[scenario]
if args.initial_only:
    messages = messages[:1]
rows = []
with tempfile.TemporaryDirectory(prefix='omnicare-clarify-') as temp:
    directory = Path(temp)
    (directory / 'claims.json').write_text('[]')
    lm = get_language_model()
    rag = RagPipeline(chroma_dir=directory / 'chroma', policy_file=ROOT / 'sample_policy.md')
    deps = Deps(lm=lm, rag=rag, db=Database(directory / 'db.sqlite'),
                claims=ClaimsStore(directory / 'claims.json'))
    if scenario == 'repair':
        # Replay the user's already-completed coverage exchange, then test the
        # exact next-step request against real retrieval and model decisions.
        deps.db.record_turn('synthetic-dialogue', 'yes it a sudden pipe broke and ruined my flooring', {
            'response': 'Your policy covers water damage from sudden pipe bursts up to $25,000, subject to a $500 deductible.',
            'message_type': 'coverage_answer', 'data': {'verdict': 'covered'}, 'sources': [],
        }, None, '')
    analyze, review, compose, retrieve = lm.analyze_policy, lm.review_evidence, lm.compose_clarification, rag.retrieve
    offer = lm.compose_claim_offer
    stages, analyses = [], []

    def tracked_retrieve(query):
        stages.append({'stage': 'retrieve', 'query': query})
        return retrieve(query)

    def tracked_analyze(*args):
        stages.append({'stage': 'assess'})
        result = analyze(*args)
        analyses.append(result)
        return result

    def tracked_review(*args):
        stages.append({'stage': 'review'})
        return review(*args)

    def tracked_compose(*args, **kwargs):
        stages.append({'stage': 'clarify'})
        return compose(*args, **kwargs)

    def tracked_offer(*args):
        stages.append({'stage': 'offer_claim'})
        return offer(*args)

    lm.compose_claim_offer = tracked_offer
    rag.retrieve, lm.analyze_policy = tracked_retrieve, tracked_analyze
    lm.review_evidence, lm.compose_clarification = tracked_review, tracked_compose
    for message in messages:
        stages.clear()
        analyses.clear()
        result = run_agent('synthetic-dialogue', message, history=deps.db.get_history('synthetic-dialogue'), deps=deps)
        deps.db.record_turn('synthetic-dialogue', message, result, None, '')
        row = {'message': message, 'type': result['message_type'], 'response': result['response'],
               'stages': list(stages), 'policy_context': analyses[-1].get('policy_context'),
               'policy_terms': analyses[-1].get('clarification_terms', []),
               'plan': analyses[-1].get('clarification_plan'),
               'claim_requested': analyses[-1].get('claim_requested', False),
               'claim_offer': result['data'].get('claim_offer', False),
               'confirm_required': result['data'].get('confirm_required', False)}
        rows.append(row)
        print(json.dumps(row), flush=True)
        stage_names = [s['stage'] for s in stages]
        assert stage_names.index('retrieve') < stage_names.index('assess')
        if row['claim_offer']:
            assert 'offer_claim' in stage_names
        elif result['message_type'] == 'clarification':
            assert stage_names.index('review') < stage_names.index('clarify')
            assert all(t['quote'] in result['response'] for t in row['policy_terms'])

    assert rows[0]['type'] == 'clarification'
    if args.initial_only:
        assert rows[0]['policy_terms']
        assert not rows[0]['claim_requested']
        assert 'your claim' not in rows[0]['response'].casefold()
    elif scenario == 'water':
        assert rows[0]['policy_terms'], 'A known policy subject should yield source-backed operative terms'
        assert rows[1]['type'] == 'clarification', 'A location alone does not resolve the incident'
        assert rows[1]['plan']['approach'] == 'observation', 'Partial replies should advance the question'
        assert rows[2]['type'] == 'coverage_answer'
        assert analyses[-1]['verdict'] == 'covered'
    elif scenario == 'repair':
        assert rows[0]['claim_offer'] or rows[0]['type'] == 'claim_draft'
        assert rows[1]['type'] == 'claim_draft'
        assert rows[1]['confirm_required'] is True
        assert deps.claims.list_claims() == []
    elif scenario == 'vague':
        assert rows[0]['policy_context'] == 'unresolved'
        assert rows[0]['policy_terms'] == []
    else:
        assert rows[-1]['type'] == 'coverage_answer'
        assert analyses[-1]['verdict'] == 'uncertain'
    suffix = '_initial' if args.initial_only else ''
    report_path = ROOT / f'backend/eval/clarification_{scenario}{suffix}_live.json'
    report_path.write_text(json.dumps(rows, indent=2))
