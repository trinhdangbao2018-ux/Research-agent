# Final module layout

- **Status:** final. This is the single source of truth for the layout.
- **Date:** 2026-09-20
- **Replaces:** `module-layout.md` (2026-08-11) and `module-layout-2026-08-09-superseded.md`.
  Same design, consolidated. Rationale and the annotated run walkthrough stay in
  `module-layout.md` until it is archived.

A file exists only if it serves one of the four mechanisms below, or is a boundary
(model, network, disk) or wiring.

## The four mechanisms

| # | Mechanism | Enforced by |
|---|---|---|
| 1 | **Provenance.** A `Source` is minted in exactly one place, `workers/search.py`, after bytes arrive. Citations can only point at a `Source`. | `engine/citations.py` raises on any marker with no matching `Source` |
| 2 | **Independent verification.** The checker sees only `(one claim, one excerpt)`, never the question or the rest of the draft. | `workers/verify.py`, asserted on the prompt in `test_verify.py` |
| 3 | **Retrieved content is data, never instruction.** Everything off the wire passes `extract` then `sanitize` before any prompt. Sanitizing is defence in depth. The main protection is that fetched text is only ever inserted as quoted data. | `tools/clean.py` |
| 4 | **Budget: check before, charge after.** Estimate before each call and charge the provider's real token count after it. Exhaustion is a normal exit (`Result.status="partial"` with `gaps`), never a crash. | `engine/budget.py` |

## Source tree (22 modules)

```
src/research_agent/
├── models.py          # Task, Source, Evidence, Result (frozen pydantic). Base layer
├── config.py          # Settings + budget ceiling. The only file that reads .env. Base layer
│
├── engine/            # DETERMINISTIC: zero prompts, tests run offline
│   ├── loop.py        # rounds, not a graph. Defines the Plan/Assess/Synthesize/Work
│   │                  #   Protocols and receives implementations as parameters
│   ├── budget.py      # mechanism 4
│   ├── evidence.py    # merge Evidence, dedup Sources by fingerprint
│   └── citations.py   # mechanism 1 gate: [s<id>] -> [n], render source list, raise on orphan
│
├── lead/              # JUDGEMENT: the prompts for planning, assessing, synthesizing
│   ├── ask.py         # model call -> validate -> retry WITH the validation error
│   ├── planner.py     # question -> Tasks
│   ├── assess.py      # evidence -> (sufficient?, gaps, next tasks) in one call
│   ├── synthesizer.py # evidence -> markdown carrying [s<id>] markers
│   └── prompts/*.md   # versioned prompts, reviewed as diffs
│
├── workers/           # THE WORK: may import tools/ and lead/
│   ├── search.py      # search -> fetch -> clean -> MINT Source -> ask -> Evidence.
│   │                  #   catches every exception, returns Evidence(limitations=[...])
│   └── verify.py      # mechanism 2. Owns its own prompt
│
├── providers/         # MODEL BOUNDARY: no model SDK imported outside here
│   ├── base.py        # Protocol: prompt + schema in, JSON + token usage out
│   ├── fake.py        # deterministic scenarios, so no API key is needed
│   └── anthropic.py
│
├── tools/             # EXTERNAL-I/O BOUNDARY: no HTTP client imported outside here
│   ├── base.py        # Protocols: SearchTool, FetchTool
│   ├── fake.py        # canned SERPs and pages, including one injection payload
│   ├── web.py         # search + fetch: timeouts, per-domain limits, robots.txt, User-Agent
│   └── clean.py       # mechanism 3: extract -> sanitize
│
├── storage.py         # DISK BOUNDARY: job dir, report.md, sources.json, evidence/, trace.jsonl
├── composition.py     # build(settings) -> wired Engine. The only file that imports every package
└── cli.py             # parse args -> composition -> print
```

Each package also has an `__init__.py` (not counted). Prompts stay outside `engine/`.
The rule is that `engine/` contains no prompts, not that only `lead/` does.

## Import rules

```
cli -> composition -> {engine, lead, workers, providers, tools, storage}
workers -> tools (via Protocol), lead/ask
lead    -> providers (via Protocol)
engine  -> engine only (receives lead/workers as parameters)
everything -> models, config   (never upward)
```

Enforced with `import-linter` contracts in `pyproject.toml`:

1. no model SDK outside `providers/`
2. no HTTP client outside `tools/`
3. `engine/` never imports `lead/` or `workers/`
4. only `cli.py` and `tests/` import `composition.py`

## Repo root

```
Research-agent/
├── src/research_agent/   # the tree above
├── tests/                # offline, free, runs on every save
├── evals/                # real provider + real web, costs money, on demand
├── scratch/              # gitignored playground, never imported, never shipped
├── docs/design/          # this file (+ ADRs as adr-NNNN-*.md)
├── pyproject.toml
├── .env.example
└── .gitignore
```

## `tests/`

Named after the invariant proved, not the file covered. Everything starts from
`composition.build(...)` with fakes, so the wiring is under test.

| File | Proves |
|---|---|
| `conftest.py` | wiring fixture: `build(settings, FakeProvider, FakeTools, tmp_path)` |
| `test_full_run.py` | **write first.** question -> `report.md`, no network |
| `test_citations.py` | orphan marker raises (mechanism 1) |
| `test_verify.py` | verifier prompt has neither the question nor the rest of the draft (2) |
| `test_clean.py` | injection page is neutralised, and is only ever passed as quoted data (3) |
| `test_budget.py` | exhaustion returns partial with non-empty gaps, never raises (4) |
| `test_evidence.py` | two mirrors of one page count as one Source |
| `test_worker_failure.py` | one worker raising does not cancel the others; loss recorded in `limitations` |
| `test_ask.py` | malformed JSON is retried with the validation error in the prompt |
| `test_models.py` | Source round-trips through dict; timezone survives; `partial` requires `gaps` |
| `test_storage.py` | report overwrites, evidence is write-only, truncated trace still parses line by line |

`providers/anthropic.py` and `tools/web.py` are deliberately not unit-tested. They are
covered by `evals/`.

## `evals/`

`questions.yaml` (~8 questions, including one contested and one trap), `run.py` (the only
code path touching the real provider and web; records prompt hashes), `score.py`
(coverage, entailment, fabricated count, corroboration), `results/*.json` (committed).
**Fabricated citations must be exactly 0.** A non-zero value means a hole in
`engine/citations.py`, not a prompt to tune.

## Workspace on disk

```
~/.research-agent/jobs/<YYYY-MM-DDTHH-MM>-<slug>/
├── job.json      # written twice (running -> final). A stale "running" means a crash
├── report.md     # the deliverable
├── sources.json  # every deduped Source. report.md's [n] markers index into it
├── evidence/<task-id>.json   # raw worker output, write-only
└── trace.jsonl   # append-only, one line per decision
```

## Deferred, with triggers

| Deferred | Bring back when |
|---|---|
| `task_graph.py` | a task's *question* depends on another task's *answer* |
| `registry.py` | a fourth worker exists |
| `retry.py` | the first 429 (expect this early) |
| checkpoint/resume | lost progress costs real money |
| `modes.py`, `intent.py`, approval gate | real cost data exists to tune against |
| `source_classifier.py` | the report needs source-quality labels |
| `context_builder.py` | evidence outgrows the context window |
| `conflict.py`, `confidence.py` | the synthesizer is seen swallowing disagreement |
| split `storage.py` | it passes ~200 lines |
| RAG / attachments | v2, a separate product |
| `job_index`, compaction, follow-ups | more than ~50 jobs on disk |
| `cli/render.py` | progress needs more than `print()` |

## Open decisions (settle before the dependent code)

1. **ADR-0003:** search API, HTTP client and extraction library, decided together, before
   the real-web slice.
2. **`tools/web.py` contract:** robots.txt, User-Agent identity, per-domain rate limits.
3. **Cache key vs dedup key:** cache = `sha256(canonical URL + raw bytes)`, dedup =
   `sha256(whitespace-normalised extracted text)`. Matches `models.fingerprint_of`.
4. **Concurrency:** one global semaphore for model calls, a separate per-domain one for
   fetches.
5. **Verify budgeting:** `verify` makes one call per cited sentence, so `budget.py` needs
   an estimate for it. Decide whether verification draws from the same budget or a
   reserved slice, so it can't be starved by research rounds.
