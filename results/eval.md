# Evaluation

Deals by outcome: accepted 12, rejected_output 0.

Model: `us.anthropic.claude-sonnet-4-6`. Labels come from the dataset spec, not from the model.

## Change detection

| Match rule | TP | FP | FN | Precision | Recall | F1 |
|---|---|---|---|---|---|---|
| deal + clause type | 32 | 1 | 0 | 32/33 (0.970) | 32/32 (1.000) | 64/65 (0.985) |
| deal + clause type + change kind | 32 | 1 | 0 | 32/33 (0.970) | 32/32 (1.000) | 64/65 (0.985) |

## Per clause type

| Clause type | TP | FP | FN | Precision | Recall | F1 |
|---|---|---|---|---|---|---|
| payment_terms | 8 | 0 | 0 | 8/8 (1.000) | 8/8 (1.000) | 16/16 (1.000) |
| price_discount | 4 | 0 | 0 | 4/4 (1.000) | 4/4 (1.000) | 8/8 (1.000) |
| liability_cap | 6 | 0 | 0 | 6/6 (1.000) | 6/6 (1.000) | 12/12 (1.000) |
| auto_renewal | 5 | 0 | 0 | 5/5 (1.000) | 5/5 (1.000) | 10/10 (1.000) |
| termination | 2 | 0 | 0 | 2/2 (1.000) | 2/2 (1.000) | 4/4 (1.000) |
| sla | 2 | 0 | 0 | 2/2 (1.000) | 2/2 (1.000) | 4/4 (1.000) |
| data_processing | 4 | 0 | 0 | 4/4 (1.000) | 4/4 (1.000) | 8/8 (1.000) |
| confidentiality | 0 | 1 | 0 | 0/1 (0.000) | 0/0 (n/a) | 0/1 (0.000) |
| governing_law | 1 | 0 | 0 | 1/1 (1.000) | 1/1 (1.000) | 2/2 (1.000) |

## Direction

Correct on matched changes: 32/32. Baseline, always answering buyer-favorable on the same matched set: 30/32.

| Label \ predicted | buyer-favorable | seller-favorable | neutral |
|---|---|---|---|
| buyer-favorable | 30 | 0 | 0 |
| seller-favorable | 0 | 1 | 0 |
| neutral | 0 | 0 | 1 |

## Grounding

Excerpts found in the right document: 52/56. An empty excerpt where one is expected counts as not found.

## False positives

- D04 `confidentiality` removed neutral: The Confidentiality clause was moved but its substance is unchanged. Sent: "" Signed: ""

## False negatives

None.
