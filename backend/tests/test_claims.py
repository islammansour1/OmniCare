"""Claims tool + validation + persistence + idempotency tests.

All tests use isolated temp stores. The module-level tool functions
(``get_claim_status`` / ``submit_claim``) are patched to a fresh store so the
real sample claims file is never mutated.
"""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from app.claims import (
    ClaimNotFoundError,
    ClaimsStore,
    InvalidClaimError,
    SubmitClaimInput,
    get_claim_status,
    submit_claim,
)

SAMPLE = Path(__file__).resolve().parent.parent / "data" / "mock_claims.json"


@pytest.fixture(autouse=True)
def fresh_store(tmp_path, monkeypatch):
    import app.claims.store as store_module
    import app.claims.tools as tools_module

    claims_file = tmp_path / "claims.json"
    shutil.copy(SAMPLE, claims_file)
    st = ClaimsStore(claims_file)
    monkeypatch.setattr(tools_module, "claims_store", st)
    monkeypatch.setattr(store_module, "claims_store", st)
    return st


def test_get_claim_status_known():
    created = submit_claim("POL-1092", "Water Damage", 3500.0, "Pipe burst in kitchen", owner_id="u1")
    claim = get_claim_status(created["claim_id"], "u1")
    assert claim["policy_number"] == "POL-1092"
    assert claim["status"] == "Submitted"
    assert claim["amount"] == 3500.0


def test_get_claim_status_hidden_from_other_owner():
    created = submit_claim("POL-1092", "Water Damage", 3500.0, "Pipe burst in kitchen", owner_id="u1")
    with pytest.raises(ClaimNotFoundError):
        get_claim_status(created["claim_id"], "u2")


def test_get_claim_status_unknown():
    with pytest.raises(ClaimNotFoundError):
        get_claim_status("CLM-9999", "u1")


def test_get_claim_status_invalid_identifier():
    with pytest.raises(InvalidClaimError):
        get_claim_status("..//", "u1")


def test_submit_claim_valid():
    claim = submit_claim("POL-1092", "Water Damage", 3500.0, "Pipe burst in kitchen", owner_id="u1")
    assert claim["claim_id"].startswith("CLM-")
    assert claim["status"] == "Submitted"
    assert claim["amount"] == 3500.0
    assert claim["owner_id"] == "u1"


def test_validation_rejects_negative_amount():
    with pytest.raises(Exception):
        submit_claim("POL-1092", "Water Damage", -10.0, "desc", owner_id="u1")


def test_validation_rejects_non_numeric_amount():
    with pytest.raises(Exception):
        SubmitClaimInput(
            policy_number="POL-1092", claim_type="Water Damage", amount="abc", description="desc"
        )


def test_validation_rejects_zero_amount():
    with pytest.raises(Exception):
        submit_claim("POL-1092", "Water Damage", 0, "desc", owner_id="u1")


def test_validation_rejects_missing_description():
    with pytest.raises(Exception):
        SubmitClaimInput(
            policy_number="POL-1092", claim_type="Water Damage", amount=100.0, description="  "
        )


def test_validation_rejects_bad_policy_number():
    with pytest.raises(Exception):
        SubmitClaimInput(
            policy_number="!!", claim_type="Water Damage", amount=100.0, description="desc"
        )


def test_original_records_preserved(tmp_path):
    claims_file = tmp_path / "claims.json"
    shutil.copy(SAMPLE, claims_file)
    store = ClaimsStore(claims_file)
    claim = store.submit_claim("POL-1092", "Water Damage", 100.0, "new claim desc", owner_id="u1")
    claims = store.list_claims()
    assert len(claims) == 1
    assert claims[0]["claim_id"] == claim["claim_id"]
    assert claims[0]["owner_id"] == "u1"
    assert claims[0]["status"] == "Submitted"


def test_idempotent_submission_same_id(tmp_path):
    claims_file = tmp_path / "claims.json"
    shutil.copy(SAMPLE, claims_file)
    store = ClaimsStore(claims_file)
    a = store.submit_claim("POL-1092", "Water Damage", 3500.0, "burst pipe", owner_id="u1")
    b = store.submit_claim("POL-1092", "Water Damage", 3500.0, "burst pipe", owner_id="u1")
    assert a["claim_id"] == b["claim_id"]
    assert len(store.list_claims()) == 1  # only one claim


def test_different_inputs_different_ids(tmp_path):
    claims_file = tmp_path / "claims.json"
    shutil.copy(SAMPLE, claims_file)
    store = ClaimsStore(claims_file)
    a = store.submit_claim("POL-1092", "Water Damage", 3500.0, "burst pipe", owner_id="u1")
    b = store.submit_claim("POL-1092", "Water Damage", 3600.0, "burst pipe", owner_id="u1")
    assert a["claim_id"] != b["claim_id"]


def test_idempotency_key_stable():
    k1 = ClaimsStore.idempotency_key("POL-1092", "Water Damage", 3500.0, "desc", "u1")
    k2 = ClaimsStore.idempotency_key("POL-1092", "Water Damage", 3500.0, "desc", "u1")
    k3 = ClaimsStore.idempotency_key("POL-1092", "Water Damage", 3500.0, "other", "u1")
    assert k1 == k2
    assert k1 != k3
