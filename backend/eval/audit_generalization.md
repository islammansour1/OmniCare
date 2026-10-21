# OmniCare RAG Evaluation Results

- Mode: hosted: gemini-flash-latest / gemini-embedding-001
- Golden cases: 8 (supported: 7, unsupported: 1)
- Top-K: 1
- Provider/validation errors: 0

## Metrics

| Metric | Value |
| --- | --- |
| Retrieval Recall@1 | 100.0% |
| Verdict accuracy | 100.0% |
| Citation validity | 100.0% |
| Unsupported-question handling | 100.0% |

## Per-case results

| id | query | expected | verdict | retrieved | cited | verdict_ok | citation_ok |
| --- | --- | --- | --- | --- | --- | --- | --- |
| transit_paraphrase | The rented lighting rig was struck while being delivered. Is this covered? | covered | covered | sec1,sec3,sec2,sec4 | sec1 | Y | Y |
| new_limit | What is the coverage limit for accidental impact to lighting equipment in transit? | covered | covered | sec1,sec2,sec3,sec4 | sec1 | Y | Y |
| new_exclusion | The rented lighting equipment was damaged after being left outside unattended. Is it covered? | excluded | excluded | sec1,sec3,sec2,sec4 | sec1 | Y | Y |
| nonfinancial_condition | Our rented speakers were stolen; we have not yet submitted a police report. Is coverage conditional? | conditional | conditional | sec2,sec3,sec1,sec4 | sec2 | Y | Y |
| misplacement | We misplaced the rented sound equipment. Is that covered? | excluded | excluded | sec2,sec3,sec1,sec4 | sec2 | Y | Y |
| permit_condition | Will you cover weather damage to rented projection screens if we still need to establish whether the organizer had a permit? | conditional | conditional | sec3,sec1,sec2,sec4 | sec3 | Y | Y |
| electrical_failure | The hired generator suffered an internal electrical fault. Is it covered? | covered | covered | sec4,sec1,sec3,sec2 | sec4 | Y | Y |
| unknown_category | Does this policy cover cancellation of a performer's flight? | unsupported | unsupported | sec2,sec3,sec4,sec1 | — | Y | Y |
