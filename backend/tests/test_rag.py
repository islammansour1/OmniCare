"""RAG tests: chunking, retrieval, exclusions, unsupported queries, ingestion."""
from __future__ import annotations

from fakes import FakeEmbedder
from app.rag import RagPipeline
from app.rag.chunking import chunk_policy

POLICY = """# OmniCare General Insurance Policy 2026

## Section 1 — Home Water Damage Coverage

Water damage caused by sudden pipe bursts is covered up to $25,000 with a $500 deductible. Gradual leaks or flood damage are strictly excluded.

## Section 2 — Personal Property Protection

Electronics, furniture, and jewelry are covered up to $10,000 total. Single items exceeding $2,500 require individual appraisal receipts.
"""


def test_chunking_two_sections():
    chunks = chunk_policy(POLICY)
    assert len(chunks) == 2
    assert chunks[0].id == "sec1"
    assert chunks[1].id == "sec2"
    assert "Home Water Damage" in chunks[0].section
    assert "Personal Property" in chunks[1].section


def test_chunking_stable_ids():
    c1 = chunk_policy(POLICY)
    c2 = chunk_policy(POLICY)
    assert [c.id for c in c1] == [c.id for c in c2] == ["sec1", "sec2"]


def _pipeline(tmp_path):
    from pathlib import Path

    policy = Path(__file__).resolve().parents[2] / "sample_policy.md"
    return RagPipeline(
        embedder=FakeEmbedder(),
        chroma_dir=tmp_path / "chroma",
        policy_file=policy,
    )


def test_ingest_and_retrieve_covered(tmp_path):
    p = _pipeline(tmp_path)
    p.ingest()
    sources = p.retrieve("Does my policy cover burst pipes?")
    assert sources, "expected at least one source"
    assert sources[0]["id"] == "sec1"


def test_ingestion_idempotent(tmp_path):
    p = _pipeline(tmp_path)
    assert p.ingest() == 2
    assert p.ingest() == 2  # no duplicate chunks


def test_retrieve_exclusion(tmp_path):
    p = _pipeline(tmp_path)
    p.ingest()
    sources = p.retrieve("Is flood damage covered?")
    assert any(s["id"] == "sec1" for s in sources)


def test_unsupported_query_grounding(tmp_path):
    from fakes import FakeLanguageModel

    p = _pipeline(tmp_path)
    p.ingest()
    sources = p.retrieve("Does my policy cover earthquake damage?")
    analysis = FakeLanguageModel().analyze_policy("Does my policy cover earthquake damage?", sources, [])
    # The system must say it cannot establish coverage, with no citations.
    assert analysis["verdict"] == "unsupported"
    assert analysis["cited_ids"] == []


def test_citations_reference_real_text(tmp_path):
    p = _pipeline(tmp_path)
    p.ingest()
    sources = p.retrieve("Does my policy cover electronics?")
    assert sources
    assert "Electronics" in sources[0]["text"]
