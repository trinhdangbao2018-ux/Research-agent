> **SUPERSEDED — 2026-08-09 draft, kept for reference only.**
> The current layout is [`module-layout.md`](module-layout.md).
>
> This version describes a 45-module design that was cut down to 22 files on
> 2026-08-11. Read it for the reasoning it records (the boundaries table and the
> "decisions visible in the tree" table still hold), not for the file list.
>
> Three things it references no longer exist: `make boundaries` (no Makefile was
> ever written), `docs/adr/README.md`, and ADR-0001 / ADR-0002 (both deleted
> 2026-08-11).

## Boundaries

Three boundaries to the outside world. Everything else is pure logic and must be
testable offline.

| Boundary | Package | What crosses it | Fake |
|---|---|---|---|
| Model providers | `providers/` | prompts out, structured JSON + usage in | `providers/fake.py` |
| External I/O | `tools/` | search queries, HTTP fetches, file reads, embeddings | `tools/fake.py` |
| Local disk | `storage/` | reports, evidence, traces, revisions | `tmp_path` fixture |

Four import rules, all enforceable by grep (`make boundaries`):

- No model SDK import outside `providers/`.
- No HTTP client import outside `tools/`.
- `engine/` never imports `lead/`.
- No prompt file under `engine/`.

The first two are also ADR-0001 constraints: they are what keeps the exit to
LangGraph open.

## Source tree

```
src/research_agent/
├── models.py                       # THE 5 backbone schemas — settle these first
├── modes.py                        # ModeSpec: direct / standard / deep
├── config.py                       # Settings, ModelTier
├── exceptions.py                   # domain exceptions — never retried
│
├── cli/                            # thin — no research logic
│   ├── main.py                     # entry point (project.scripts)
│   ├── commands.py                 # new / follow-up / list / show / compact / rewrite
│   └── render.py                   # TraceEvent -> terminal
│
├── engine/                         # deterministic — 0 prompts, offline tests
│   ├── loop.py                     # orchestration loop
│   ├── task_graph.py               # ready / find_cycle / validate_graph / JSON round-trip
│   ├── registry.py                 # capability -> worker  (one registry, not two)
│   ├── dispatcher.py               # call worker + validate contract + semaphore + timeout
│   ├── budget.py                   # check before / charge after
│   ├── job_state.py                # THE in-memory truth + checkpoint save/load
│   ├── evidence.py                 # collect + dedup + provenance  (one responsibility)
│   ├── sanitizer.py                # strip instruction-shaped content
│   ├── source_classifier.py        # domain rules -> quality label
│   ├── retry.py                    # transport retry policy only
│   ├── policy.py                   # consent gate, enforced at the crossing
│   ├── trace.py                    # emit TraceEvent
│   ├── formatter.py                # final / partial / declined
│   └── citation_builder.py
│
├── lead/                           # LLM — every prompt lives here
│   ├── intent.py                   # classify + select mode + approval flag
│   ├── planner.py                  # plan + estimate_cost
│   ├── assess.py                   # sufficient? + gaps + next_tasks — ONE call
│   ├── structured.py               # call -> validate schema -> retry with the error
│   ├── context_builder.py          # select/compress into the token ceiling
│   ├── claim_extractor.py          # draft -> checkable claims
│   ├── conflict.py
│   ├── confidence.py               # judgement only
│   ├── synthesizer.py
│   └── prompts/                    # versioned .md, loaded by loader.py
│       ├── loader.py
│       ├── intent.md  planner.md  assess.md  synthesizer.md
│
├── providers/                      # THE model boundary — one place
│   ├── base.py                     # ModelProvider protocol
│   ├── router.py                   # task kind -> model tier
│   ├── fake.py                     # deterministic scenarios
│   └── anthropic_provider.py
│
├── tools/                          # THE external-I/O boundary
│   ├── base.py                     # SearchTool / FetchTool / FileLoader / EmbeddingTool
│   ├── fake.py                     # canned SERPs + pages, incl. an injection payload
│   ├── cache.py                    # content-addressed fetch cache
│   ├── web_search.py  web_fetch.py  file_loader.py  embeddings.py
│
├── storage/                        # THE disk boundary
│   ├── workspace.py                # resolve/create job dirs
│   ├── job_index.py                # list, search, resolve "latest"
│   ├── report_store.py             # write report.md + snapshot to revisions/
│   ├── evidence_store.py           # write-only during a run
│   ├── trace_store.py              # append-only JSONL
│   └── compaction.py               # must preserve provenance
│
└── workers/
    ├── base.py                     # Worker protocol
    ├── research/search_worker.py
    ├── retrieval/{rag_worker,chunker}.py
    └── citation_verification/verifier.py
```

New capabilities (source analysis, critique, writing) are sibling packages under
`workers/`, registered in `engine/registry.py`. Nothing else changes — that is
the payoff of the capability registry.

### Decisions visible in the tree

Five places where the layout encodes a design choice rather than a convention:

| | Why |
|---|---|
| `job_state.py` owns checkpointing; no `context_store.py` | Evidence lives in exactly one place. Four modules holding state is four places to debug. |
| `evidence.py`, not `collector` + `provenance` + `dedup` | All three operate on the same type. Split when a file actually grows. |
| `registry.py`, not `capabilities` + `worker_registry` | A capability exists because a worker implements it. Two registries let a plan validate and then fail at dispatch. |
| `assess.py`, not `termination` + `replan` | One decision, one call. Split, they cost double and can contradict each other. |
| `exceptions.py` separate from `engine/retry.py` | `BudgetExhausted` must never be retried with backoff. |

## Test tree

Mirrors the source tree exactly. One convention, no exceptions.

```
tests/
├── conftest.py
├── test_full_run.py                # integration — write FIRST
├── engine/    test_{models,task_graph,budget,dispatcher,retry,sanitizer,
│                   source_classifier,evidence,job_state}.py
├── lead/      test_{planner,assess,structured,context_builder}.py
├── providers/ test_fake.py
├── tools/     test_fake.py
├── storage/   test_{workspace,report_store}.py
└── workers/   test_{search_worker,verifier}.py
```

`evals/` is a **sibling of `tests/`**, not inside it: `tests/` runs offline in a
second and gates every change; `evals/` costs money and takes minutes. Mixed
together, the fast one stops being run.

```
evals/
├── questions/v1/*.yaml   # versioned benchmark
├── runner.py             # records prompt versions alongside scores
├── metrics.py
└── results/
```

## Workspace layout on disk

```
~/.research-agent/workspaces/<workspace>/jobs/<job-id>/
├── job.json                # request, mode, budget, status, parent job
├── report.md               # current report — editable markdown
├── revisions/<ts>.md       # snapshot taken before each rewrite
├── sources.json            # deduplicated sources + quality labels
├── evidence/<task-id>.json # worker output + excerpts, retained for audit
├── attachments/            # user-provided files, kept until deleted
├── trace.jsonl             # append-only event log
└── checkpoint.json
```

Markdown for anything a human edits, JSON for records, JSONL for append-only
streams. No database until one is needed.

## Open questions

Each should become an ADR before the corresponding code is written. They are
listed in the [ADR index](../adr/README.md) under *Queued*.

1. **Checkpoint granularity** — after every task, or every graph level?
2. **Evidence identity** — what does the content fingerprint cover: raw bytes or
   normalized text? Determines whether mirrored pages deduplicate.
3. **Follow-up context selection** — how much of the parent job's evidence enters
   a follow-up, and who decides: a rule or the lead?
4. **Budget currency** — tokens, estimated cost, wall clock, or all three?
5. **Concurrency model** — one global semaphore vs per-tool rate limits.
6. **Embeddings for RAG** — local model (offline, free, no consent question) vs
   provider API (better quality, costs money, triggers the consent gate on
   uploaded files).
7. **Routing policy** — which model tier for which task kind, and what happens
   when the chosen provider fails.
