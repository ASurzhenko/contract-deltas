# contract-deltas

A small prototype of one idea: **document templates that learn from how deals actually close.**

A company writes a standard proposal once and sends it hundreds of times. The other side pushes back on the same
clauses again and again, and each push is negotiated by hand. Nobody sees the pattern.

This repo closes that loop on a small scale. For every deal it compares the **sent** version with the
**signed** version, extracts the changes **per clause** with Claude on Amazon Bedrock, links them to the **deal
outcome** (won or lost, amount, days to close), aggregates by clause type, and proposes template edits that cite
the deals behind them. A human decides. The system only proposes.

## Read this first: what this is not

- **The data is synthetic.** 12 invented deals with fictional parties and amounts.
- **The patterns are planted on purpose.** I designed which clauses change and which deals win, so the pipeline has
  something to find. Finding them proves the pipeline works, not that real contracts behave this way.
- **n = 12.** Win rates over 4 to 8 deals are anecdotes, not statistics. The report shows counts, never p-values.
- **One author wrote the documents, the labels and the prompt rubric.** The labels are independent of the model
  (they come from the dataset spec, not from a model run). They are not independent of me.
- Real contracts are longer, messier and ambiguous. Expect lower accuracy there.
- For the 5 lost deals, `signed.md` is the last negotiated version, which the customer did not sign.

## Run it

```
python -m venv .venv
.venv/Scripts/activate            # Linux/macOS: source .venv/bin/activate
pip install -r requirements-dev.txt
pytest                            # offline, no network, no AWS credentials needed
python -m contract_deltas run     # served from the committed raw cache: no AWS call, no credentials
```

The committed `results/raw/` holds the real model responses, so a fresh clone reproduces every report without
touching AWS. The run prints `calls made: 0`.

To call the model yourself you need AWS credentials in the default credential chain (for example `aws configure`)
and access to a Claude model in `us-east-1`:

```
python -m contract_deltas check                      # one tiny call, tests access
python -m contract_deltas run --refresh              # call the model again for every deal
python -m contract_deltas run --refresh-rejected     # redo only deals the model could not answer
python -m contract_deltas run --source labels        # aggregate the hand labels only, no model call
python -m contract_deltas run --model-id <id>        # another model or inference profile
```

Credentials are never read from files in this repo. The default model is `us.anthropic.claude-sonnet-4-6`.

## What it does

| Step | What happens |
|---|---|
| Data | `data/deals/<id>/sent.md` and `signed.md`, `data/deals.csv`, hand labels in `data/labels/`. Generated from one spec by `scripts/generate_dataset.py`; a test regenerates the files and compares bytes |
| Extract | One Bedrock Converse call per deal. The model must answer through a forced tool call whose input schema is the single source of truth, `temperature` 0. Output is validated against the same schema; invalid output is retried with the error shown to the model (at most 3 calls per deal) |
| Evaluate | Predicted changes are matched to hand labels on (deal, clause type). Precision, recall, F1, change-kind strictness, direction accuracy against a same-set baseline, and a check that every quoted excerpt really appears in the document |
| Aggregate | Per clause type: how often it changed, direction, win rate with and without the change, mean days to close |
| Suggest | Four plain rules (R1 to R4, thresholds in `contract_deltas/config.py`) turn the aggregates into template edits, each citing deal ids. No model is involved in this step |

Cosmetic edits are part of the test: `signed.md` also changes `thirty (30) days` to `30 days`, `shall` to `will`,
the effective date, the signatories, and in two deals the order of two clauses. None of these are labelled
changes, so a model that reports them loses precision. `confidentiality` and `warranty` never change in any deal.

## Results

The first run is commit `df9ef24` (`results: first Bedrock run (raw + eval + report)`). It used one system prompt,
written before the run and not edited afterwards. The numbers below are copied verbatim from
[`results/headline.md`](results/headline.md) and a test checks that they match.

<!-- headline:start -->
- Model: `us.anthropic.claude-sonnet-4-6`
- Deals: 12 (accepted 12, rejected_output 0)
- Change detection, match on deal and clause type: precision 32/33 (0.970), recall 32/32 (1.000), F1 64/65 (0.985) (TP 32, FP 1, FN 0)
- Strict, change kind must also match: F1 64/65 (0.985) (TP 32, FP 1, FN 0)
- Direction on matched changes: 32/32 correct; always answering buyer-favorable on the same set: 30/32
- Excerpts found in the documents: 52/56
- Model calls stored in the raw cache: 12
- Tokens: input 25942, output 3882, total 29824
<!-- headline:end -->

- Full breakdown, every false positive and false negative: [`results/eval.md`](results/eval.md)
- Aggregation and suggested template edits from the model's output, with a comparison to the same rules run on the
  hand labels: [`results/report.md`](results/report.md)
- The same report from the hand labels alone: [`results/report.labels.md`](results/report.labels.md)

How to read them:

- The one false positive is a clause that was only moved to a different position. The model read the move as a
  removal. That is a real model error, and it is left in the numbers.
- Direction is hard to score on this data: nearly every planted change favors the buyer, so always answering
  "buyer-favorable" is a strong baseline. The headline shows that baseline next to the model on the same set of
  matched changes.
- "Excerpts found" is a strict substring check after ignoring case, whitespace, markdown marks and quote style. A
  few misses are near-quotes where the model dropped a phrase at the end. They are not invented text.
- The suggestions from predictions and from labels are compared in `report.md`, so you can see whether an
  extraction error would flip a rule.

### Cost

Token totals in the block above are summed from the usage stored with every raw response. At a list price of USD 3
per million input tokens and USD 15 per million output tokens, that is about USD 0.14. If the `us.` inference profile
is billed at a roughly 10 percent higher regional rate (USD 3.30 and 16.50), it is about USD 0.15. This is an
estimate from third-party price lists (checked 2026-10-22), not from the AWS pricing page, whose rate table
could not be read.
The account ran on credits, so nothing was charged.

### Reproducibility

`temperature` 0 does not make a model bit-for-bit deterministic. What makes the **reports** reproducible is the raw
cache: responses are stored per deal under a key built from the exact request (model, prompt, schema, documents,
retry rules), and reports contain no timestamps. A rerun on an equal key makes no call and rewrites the same bytes.
`results/runs.jsonl` records one line per batch of real calls, which is how the number of prompt iterations can be
counted: here, one distinct system prompt.

## Why Bedrock

Contract text is the first thing a customer's legal team asks about. AWS states that with Amazon Bedrock "your
content is not used to improve the base models and is not shared with any model providers"
([Bedrock FAQs](https://aws.amazon.com/bedrock/faqs/)). I rely on that statement and claim nothing beyond it. This
repo makes no claim about certifications, and the `us.` inference profile can serve a request from more than one US
region, so I do not claim the text stays in one region.

## Failure handling

- A model that cannot produce a valid answer within the retry budget is an outcome, `rejected_output`. It is scored
  as all labels missed and counted at the top of `eval.md`.
- An infrastructure failure (access denied, throttling, expired credentials, timeouts) is a different outcome and
  never becomes a number: the run stops with a non-zero exit, writes no cache file for that deal, and leaves the
  previous reports untouched. A rerun resumes from the cache.
- Error text that leaves the process is scrubbed of ARNs and account ids, and only the error class and code are printed.

## Layout

```
contract_deltas/   package: config, schema, prompts, bedrock (the only boto3 import), extract, evaluate,
                   aggregate, suggest, report, data, io_utils, CLI
data/              synthetic deals and hand labels
scripts/           dataset generator
results/           raw model responses, run log, reports
tests/             offline tests (Stubber-backed Bedrock client, one captured real response)
DECISIONS.md       the choices made and what each cost
```

## License

MIT
