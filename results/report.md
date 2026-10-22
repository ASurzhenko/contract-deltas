# Report from model predictions

n = 12 of 12 deals.

Win rates are counts of won deals. Rule thresholds: R1 more than half of deals changed and at least 3/4 buyer-favorable; R2 changed in at least 3 deals, unchanged in at least 3, win-rate gap at least +30 pp; R3 same counts and gap at most -30 pp or mean days at least +20; R4 clause added in at least 3 deals.

## Per clause type (n = 12 of 12 deals)

| Clause type | Changed | Kinds | Directions | Won with change | Won without | Mean days with | Mean days without | Mean amount with (USD) |
|---|---|---|---|---|---|---|---|---|
| payment_terms | 8/12 | modified 8 | buyer-favorable 8 | 4/8 | 3/4 | 68.6 | 59.2 | 62375.0 |
| price_discount | 4/12 | modified 4 | buyer-favorable 4 | 2/4 | 5/8 | 65.0 | 65.8 | 61500.0 |
| liability_cap | 6/12 | modified 6 | buyer-favorable 6 | 5/6 | 2/6 | 68.3 | 62.7 | 100166.7 |
| auto_renewal | 5/12 | removed 5 | buyer-favorable 5 | 1/5 | 6/7 | 83.6 | 52.6 | 70200.0 |
| termination | 2/12 | modified 2 | buyer-favorable 2 | 1/2 | 6/10 | 66.0 | 65.4 | 68500.0 |
| sla | 2/12 | modified 2 | buyer-favorable 1, seller-favorable 1 | 1/2 | 6/10 | 72.5 | 64.1 | 84000.0 |
| data_processing | 4/12 | added 4 | buyer-favorable 4 | 4/4 | 3/8 | 69.5 | 63.5 | 116000.0 |
| confidentiality | 1/12 | removed 1 | neutral 1 | 1/1 | 6/11 | 66.0 | 65.5 | 120000.0 |
| governing_law | 1/12 | modified 1 | neutral 1 | 0/1 | 7/11 | 77.0 | 64.5 | 47000.0 |
| warranty | 0/12 | - | - | 0/0 | 7/12 | n/a | 65.5 | n/a |

## Suggested template edits

Coincides with the outcomes below; this is a prototype signal on a handful of deals, not a causal claim.

- **R1 payment_terms** (deals: D01, D02, D03, D04, D05, D07, D09, D10): Common pushback: payment terms was changed in 8 of 12 deals, 8 of them in the buyer's favor. Consider moving the template default toward the signed value. Signed wording: D01: "Customer will pay each invoice within 60 days of the invoice date."; D02: "Customer will pay each invoice within 60 days of receipt of the invoice."; D03: "Customer will pay each invoice within 60 days of the date printed on the invoice.".
- **R2 liability_cap** (deals: D02, D04, D06, D08, D10, D12): A change to liability cap coincides with more wins: won 5/6 with it, 2/6 without. Consider pre-approving this concession for the sales team.
- **R3 auto_renewal** (deals: D03, D05, D08, D09, D10): A change to auto renewal coincides with slower or lost deals: won 1/5 with it, 6/7 without. Review this clause before it reaches the buyer; this flags a question, it is not a fix.
- **R2 data_processing** (deals: D02, D04, D08, D12): A change to data processing coincides with more wins: won 4/4 with it, 3/8 without. Consider pre-approving this concession for the sales team.
- **R4 data_processing** (deals: D02, D04, D08, D12): Buyers added a data processing clause in 4 deals. Consider adding it to the template.

## Rules on this source versus hand labels

| Rule | Clause type | This source | hand labels |
|---|---|---|---|
| R1 | payment_terms | fires | fires |
| R2 | data_processing | fires | fires |
| R2 | liability_cap | fires | fires |
| R3 | auto_renewal | fires | fires |
| R4 | data_processing | fires | fires |

The same rules fire on both sources.
