# OmniCare RAG Evaluation Results

- Mode: hosted: gemini-flash-latest / gemini-embedding-001
- Golden cases: 25 (supported: 19, unsupported: 6)
- Top-K: 1
- Provider/validation errors: 0

## Metrics

| Metric | Value |
| --- | --- |
| Retrieval Recall@1 | 94.7% |
| Verdict accuracy | 92.0% |
| Citation validity | 100.0% |
| Unsupported-question handling | 100.0% |

## Per-case results

| id | query | expected | verdict | retrieved | cited | verdict_ok | citation_ok |
| --- | --- | --- | --- | --- | --- | --- | --- |
| cov_water_burst | Does my policy cover burst pipes? | covered | covered | sec1,sec2 | sec1 | Y | Y |
| cov_water_burst_paraphrase | My pipes broke suddenly — am I covered? | covered | covered | sec1,sec2 | sec1 | Y | Y |
| excl_gradual_leak | Is a slow gradual leak covered? | excluded | excluded | sec1,sec2 | sec1 | Y | Y |
| excl_gradual_paraphrase | Water leaked slowly for months | excluded | excluded | sec1,sec2 | sec1 | Y | Y |
| excl_flood | Does my policy cover flood damage? | excluded | excluded | sec1,sec2 | sec1 | Y | Y |
| pp_laptop | Is my laptop covered? | covered | conditional | sec2,sec1 | sec2 | N | Y |
| pp_furniture | Is my furniture covered? | covered | covered | sec2,sec1 | sec2 | Y | Y |
| pp_electronics | Does my policy cover electronics? | covered | covered | sec2,sec1 | sec2 | Y | Y |
| pp_tv_paraphrase | My TV got ruined | uncertain | uncertain | sec1,sec2 | sec2 | Y | Y |
| cond_engagement_ring | Is my $5,000 engagement ring covered? | conditional | conditional | sec2,sec1 | sec2 | Y | Y |
| cond_diamond_necklace | I have a diamond necklace worth $3,000 — is it covered? | conditional | conditional | sec2,sec1 | sec2 | Y | Y |
| unsup_earthquake | Does my policy cover earthquakes? | unsupported | unsupported | sec1,sec2 | — | Y | Y |
| unsup_car | Is my car covered? | unsupported | unsupported | sec1,sec2 | — | Y | Y |
| unsup_fire | Is fire damage covered? | unsupported | unsupported | sec1,sec2 | — | Y | Y |
| unsup_mold | Does my policy cover mold? | unsupported | unsupported | sec1,sec2 | — | Y | Y |
| unsup_theft | Does my policy cover theft? | unsupported | unsupported | sec2,sec1 | — | Y | Y |
| mixed_flood_laptop | My laptop was damaged in a flood. Is it covered? | excluded | excluded | sec1,sec2 | sec1 | Y | Y |
| ambiguous_water | I have water damage. Am I covered? | uncertain | uncertain | sec1,sec2 | sec1 | Y | Y |
| unknown_laptop_cause | My laptop was destroyed, is it covered? | uncertain | conditional | sec2,sec1 | sec2 | N | Y |
| below_appraisal | Is my jewelry worth $2,000 covered? | covered | covered | sec2,sec1 | sec2 | Y | Y |
| at_appraisal | Is my jewelry worth $2,500 covered? | covered | covered | sec2,sec1 | sec2 | Y | Y |
| over_appraisal | Is my jewelry worth $2,501 covered? | conditional | conditional | sec2,sec1 | sec2 | Y | Y |
| negated_burst | The water damage was not caused by a pipe burst. Am I covered? | uncertain | uncertain | sec1,sec2 | sec1 | Y | Y |
| unmentioned_peril | Does my policy cover hurricanes? | unsupported | unsupported | sec1,sec2 | — | Y | Y |
| followup_deductible | What is the deductible for that? | covered | covered | sec1,sec2 | sec1 | Y | Y |
