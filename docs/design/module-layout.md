# Module layout

- **Status:** current
- **Date:** 2026-08-11
- **Supersedes:** [`module-layout-2026-08-09-superseded.md`](module-layout-2026-08-09-superseded.md) (45 modules → 22 files)

A directory listing says *where things live*. It cannot say *who calls whom*, *what
flows*, or *what each file protects*. So the mechanisms come first — the trees below
are an index into them.

## The four mechanisms

Every file in this document exists to serve one of these. A file that serves none of
them does not get created.

**1. Provenance.** A `Source` object is minted in exactly one place — inside
`workers/search.py`, after bytes have actually arrived from the network. A citation
can only point at a `Source`. `engine/citations.py` raises if a draft carries a marker
with no matching `Source`.

> A fabricated citation is not "unlikely" — it is unrepresentable. This is the
> mechanism the whole project exists for.

**2. Independent verification.** The model that *writes* a claim and the model that
*checks* it are separate calls. The checker sees only the pair `(one claim, one
excerpt)` — not the original question, not the rest of the draft.

> It cannot defend its own writing, because it does not know whose writing it is
> reading.

**3. Retrieved content is data, never instruction.** `tools/clean.py` runs on every
byte that comes off the wire, before any of it reaches a prompt.

> A page saying "ignore previous instructions and…" does not steer the agent. This is
> a security boundary, so it is its own file: greppable, separately tested.

**4. Budget: check before, charge after.** Before each model call, ask whether the
worst-case estimate still fits. After the call, deduct the real token count the
provider reported.

> Why the two ends differ: only the provider knows the true token count (so charging
> must happen after), but charging alone lets a single huge call overshoot without
> limit (so checking must happen before).
>
> Consequence: running out of budget is a **normal exit** — a partial report with
> stated gaps — not a crash.

## One run, with real data

```
"What are the transparency rules in the EU AI Act?"
   │
   ▼  lead/planner.py ─────────────────────────────── 1 model call
   [ Task("t1", "What must be disclosed for AI-generated content?"),
     Task("t2", "Which systems count as limited-risk?") ]
   │
   ▼  engine/loop.py ── t1 and t2 run in parallel, one worker each
   │
   │   ┌─ workers/search.py, on t1 ─────────────────────────────────┐
   │   │  tools/web.py    search(...)   → 5 URLs + snippets         │
   │   │  tools/web.py    fetch(url)    → 87 KB of raw bytes        │
   │   │  tools/clean.py  extract(...)  → 12 000 chars + title      │
   │   │  tools/clean.py  sanitize(...) → 11 800 chars, 2 instruc-  │
   │   │                                  tion-shaped lines defused │
   │   │  ══ Source(url, title, fingerprint, excerpt) IS MINTED ══  │
   │   │     here, and only here            ← mechanism 1           │
   │   │  lead/ask.py   "what do these 5 excerpts answer for t1?"   │
   │   │                                ──────────  1 model call    │
   │   │  → Evidence(task_id="t1", statements=3, sources=5)         │
   │   └────────────────────────────────────────────────────────────┘
   │
   ▼  engine/evidence.py ── merge + deduplicate by fingerprint
   10 sources → 7          ← two mirrors of one page count as ONE
   │                         (otherwise "corroborated by 2 independent
   │                          sources" is a lie)
   ▼  lead/assess.py ────────────────────────────────  1 model call
   sufficient? → no. missing "penalties for non-compliance" → 1 new task
   │
   ├─► budget left  → back into the loop, round 2
   └─► budget spent → carry on with what exists, shortfall recorded
   │                  in `gaps`                        ← mechanism 4
   ▼  lead/synthesizer.py ───────────────────────────  1 model call
   markdown draft, each sentence ending in [s<id>] — the id of a Source
   │
   ▼  workers/verify.py ─────────────  1 model call PER cited sentence
   for each (sentence, excerpt of s<id>): does the excerpt actually
   support this? no → the sentence is demoted to "unverified"
   │                                                   ← mechanism 2
   ▼  engine/citations.py ───────────────  0 model calls, pure rules
   [s9f2a1c8e] → [2] · render the source list ·
   RAISE if any marker has no Source          ← the gate for mechanism 1
   │
   ▼  storage.py
   report.md
```

Cost is readable straight off the diagram, which is the payoff of keeping every prompt
inside `lead/` and `workers/`:

| Step | Model calls |
|---|---|
| planner | 1 |
| search worker | 1 × tasks |
| assess | 1 × rounds |
| synthesizer | 1 |
| verify | 1 × cited sentences |
| **everything in `engine/`** | **0 — always** |

A 2-round run with 4 tasks and 12 cited sentences ≈ **21 calls**. Countable by eye, no
instrumentation needed.

## Source tree

```
src/research_agent/
│
├── models.py        # The 4 backbone schemas: Task, Source, Evidence, Result.
│                    #   Source.fingerprint = sha256(EXTRACTED text), not raw bytes
│                    #   → two mirrors of the same page deduplicate to one
├── config.py        # Settings + budget ceiling. Reads .env — the only place that does
│
├── engine/          ═══ DETERMINISTIC — zero prompts, tests run offline ═══
│   ├── loop.py      # mechanism: runs in ROUNDS, not a graph.
│   │                #   one round = independent tasks in parallel → collect → ask assess.
│   │                #   receives lead/workers/storage AS PARAMETERS → never imports them
│   ├── budget.py    # mechanism 4: ask before with an estimate, charge after with the
│   │                #   real token count the provider returned
│   ├── evidence.py  # mechanism: merge Evidence, deduplicate Sources by fingerprint
│   └── citations.py # mechanism 1 (the gate): [s3]→[2], render the source list,
│                    #   raise if a marker has no matching Source. This file is why
│                    #   a fabricated citation cannot exist
│
├── lead/            ═══ JUDGEMENT — every prompt lives here ═══
│   ├── ask.py       # mechanism: call model → validate against schema → on failure,
│   │                #   call again WITH the validation error itself. The 3 files
│   │                #   below all go through it
│   ├── planner.py   # question → list of Tasks
│   ├── assess.py    # evidence → (sufficient? gaps? next tasks?) in ONE call
│   ├── synthesizer.py # evidence → markdown draft carrying [s<id>] markers
│   └── prompts/     # versioned .md — a prompt change reviews as a diff, like code
│
├── workers/         ═══ THE WORK — uses both tools/ and lead/ ═══
│   ├── search.py    # search → fetch → clean → mint Source → ask model → Evidence.
│   │                #   CATCHES EVERY EXCEPTION, returns Evidence(limitations=[...]).
│   │                #   one worker dying must never cancel workers still running
│   └── verify.py    # mechanism 2: sees only (one claim, one excerpt). Nothing else
│
├── providers/       ═══ THE MODEL BOUNDARY — no model SDK outside here ═══
│   ├── base.py      # Protocol: prompt + schema in, JSON + token usage out
│   ├── fake.py      # deterministic scenarios → whole system testable with no API key
│   └── anthropic.py
│
├── tools/           ═══ THE EXTERNAL-I/O BOUNDARY — no httpx outside here ═══
│   ├── base.py      # Protocol: SearchTool, FetchTool
│   ├── fake.py      # canned SERPs + pages, INCLUDING one carrying an injection payload
│   ├── web.py       # search + fetch. Same file because they share one concern:
│   │                #   timeouts, per-domain rate limiting, robots.txt, User-Agent
│   └── clean.py     # mechanism 3: raw bytes → safe text. TWO steps, one responsibility:
│                    #   extract (strip nav/ads) → sanitize (neutralise instruction-shaped
│                    #   text). Runs on every byte off the wire, before any prompt sees it
│
├── storage.py       # ═══ THE DISK BOUNDARY ═══ one module: job directory,
│                    #   report.md (overwrite), evidence/*.json (write-only),
│                    #   trace.jsonl (append-only). Tests swap it for tmp_path
│
├── composition.py   # the ONLY file allowed to import every package.
│                    #   build(settings) → a fully wired Engine. Tests call this same
│                    #   function with fakes → one argument flips the system offline
└── cli.py           # parse arguments → call composition → print. Nothing else
```

## Who may import whom

```
cli.py
  └─► composition.py ────────── the only file that knows about everything
        ├─► engine/loop.py
        │     ├─► engine/{budget, evidence, citations}
        │     └─✗ does NOT import lead/ or workers/ — receives them as parameters
        ├─► workers/{search, verify} ─► tools/ (via Protocol) + lead/ask
        ├─► lead/*                   ─► providers/ (via Protocol)
        ├─► providers/{fake | anthropic}
        ├─► tools/{fake | web + clean}
        └─► storage.py

every package ─► models.py, config.py     (the base layer — never imports upward)
```

`composition.py` is what makes "engine never imports lead" enforceable rather than
merely intended: `loop.py` takes `plan`, `assess` and `synthesize` as arguments and
calls them without knowing where they live.

Note the rule this settles: **`workers/` may import `lead/`.** `verify.py` needs its
own prompt. The real constraint is *"`engine/` contains no prompts"*, not *"only
`lead/` contains prompts"*.

Four import rules, all machine-checkable with `import-linter`:

- no model SDK imported outside `providers/`
- no HTTP client imported outside `tools/`
- `engine/` never imports `lead/` or `workers/`
- nothing imports `composition.py` except `cli.py` and the tests

## `tests/` — offline, free, runs on every save

A test file is named after the invariant it proves, not after the source file it
covers.

```
tests/
├── conftest.py             # the wiring fixture: build(settings, FakeProvider, FakeTools, tmp_path).
│                           #   Every test starts from composition.py, same as production —
│                           #   so the wiring itself is under test, not bypassed
├── test_full_run.py        # WRITE THIS ONE FIRST. question → report.md, all fakes, no network.
│                           #   It fails loudest and earliest. Until it passes, nothing else matters
│
│   ── the four mechanisms. If any of these breaks, the product is broken ──
├── test_citations.py       # mechanism 1: a draft carrying a marker with no matching Source
│                           #   MUST raise. This single test is what makes a fabricated
│                           #   citation impossible rather than merely unlikely
├── test_verify.py          # mechanism 2: assert the verifier's prompt contains NEITHER the
│                           #   original question NOR the rest of the draft. Independence is
│                           #   a property of the prompt, so it is asserted on the prompt
├── test_clean.py           # mechanism 3: feed the injection page from tools/fake.py through
│                           #   clean(), assert the instruction-shaped text is neutralised
├── test_budget.py          # mechanism 4: exhaustion returns PARTIAL with non-empty gaps.
│                           #   Assert it never raises — running out is an exit, not an error
│
│   ── the rest ──
├── test_evidence.py        # two mirrors of one page → one Source. If this fails, "corroborated
│                           #   by 2 independent sources" is counting the same page twice
├── test_worker_failure.py  # one worker raises → the others still return their Evidence, and
│                           #   the result records what was lost in limitations
├── test_ask.py             # model returns malformed JSON → retried WITH the validation error
│                           #   in the prompt → second attempt validates
├── test_models.py          # round-trip Source → dict → Source; timezone survives
└── test_storage.py         # tmp_path: report overwrites, evidence is write-only,
                            #   trace appends and a truncated file still parses line by line
```

Two files are deliberately untested here: `providers/anthropic.py` and `tools/web.py`.
They *are* the outside world — a unit test of them tests a mock of reality. Their
coverage lives in `evals/`. Everything else in `src/` is reachable offline, which is
the whole return on having `providers/fake.py` and `tools/fake.py`.

The tree is flat on purpose. At 11 files, subdirectories cost a path and buy nothing.
Add `tests/engine/` the day a package needs a second test file of its own.

## `evals/` — costs money, run on demand

Siblings, never nested: `tests/` runs in a second and gates every change, `evals/`
takes minutes and costs money. Mixed together, the fast one quietly stops being run.

```
evals/
├── questions.yaml   # ~8 questions with known-good answers. At least two are special:
│                    #   – one CONTESTED (real sources genuinely disagree) — proves the
│                    #     system surfaces conflict instead of silently picking a side
│                    #   – one TRAP (a plausible, confidently-written page that is wrong)
│                    #     — proves verification does something a summariser wouldn't
├── run.py           # the ONLY code path that touches the real provider and the real web.
│                    #   Records the hash of every prompt .md alongside the score: a score
│                    #   without its prompt version cannot be compared to the next one
├── score.py         # the four numbers: coverage % · entailment % · fabricated count ·
│                    #   corroboration %
└── results/*.json   # one file per run, committed. The value is the trend, not any one run
```

One number in `score.py` is not a quality score — it is an alarm. **Fabricated
citations must be exactly 0.** If it is ever non-zero, that is not a prompt to tune:
`engine/citations.py` has a hole, and it is a code bug with a failing unit test waiting
to be written.

## Workspace on disk

The mechanism: **the audit trail must survive the process.** After the program exits,
someone with no access to the code can check every claim from two files.

```
~/.research-agent/jobs/<job-id>/
│
│   job-id = 2026-08-11T14-03-eu-ai-act-transparency
│   timestamp first so `ls` sorts chronologically, slug after so it is readable.
│   That is a mechanism, not cosmetics — it is how you find last Tuesday's run
│
├── job.json          # question, budget, status, timings. Written TWICE: once at start
│                     #   (status=running) and once at the end. A job.json still saying
│                     #   "running" is how you spot a crashed run
├── report.md         # the deliverable. Markdown because a human edits it
├── sources.json      # every Source that survived dedup: url, title, retrieved_at,
│                     #   fingerprint, excerpt. report.md's [n] markers index into THIS
│                     #   file — together, these two files ARE the audit trail
├── evidence/<task-id>.json   # raw worker output, write-only during a run. Kept so that
│                     #   when a report is wrong you can read exactly what the model saw
└── trace.jsonl       # append-only, one line per decision. Append-only is the point:
                      #   a run killed mid-flight still leaves a readable prefix
```

Markdown for anything a human edits, JSON for records, JSONL for append-only streams.
No database until one is needed.

## Repo root

```
research-agent/
├── src/research_agent/    # 22 files — the tree above
├── tests/                 # 11 files. Free. Runs on every save
├── evals/                 # Costs money. Runs on demand
├── scratch/               # local playground — gitignored, so it exists on one machine
│                          #   only. Never imported by src/, never shipped in the wheel.
│                          #   Anything worth keeping gets moved into src/ or docs/
├── docs/design/           # this file + the superseded 2026-08-09 draft
├── pyproject.toml         # deps, pytest config, and the four import contracts
├── .env.example           # every variable the app reads, with dummy values
└── .gitignore
```

## Deferred, and the trigger to bring each back

Nothing here was cut because it is wrong — only because nothing needs it yet. A file is
created the day real code requires it; a directory the day a second file belongs in it.

| Deferred | Bring it back when |
|---|---|
| `task_graph.py` (DAG + `depends_on`) | task B's *question* depends on task A's *answer*. Until then, rounds are enough and `depends_on` is ceremony |
| `registry.py` | a fourth worker exists. With two, a `dict` in `composition.py` **is** the registry |
| `dispatcher.py` | never — semaphore + timeout are ~15 lines inside `loop.py` |
| `retry.py` | the first 429. This one arrives early |
| `job_state.py` + checkpoint/resume | a run gets long enough that losing progress costs real money |
| `modes.py`, `intent.py`, the approval gate | there is **real cost data** to tune them against. Knock-on: `Result` needs only `final`/`partial`, no `declined` |
| `source_classifier.py` | the report needs source-quality labels. It is a domain lookup table, ~40 lines |
| `context_builder.py` | evidence outgrows the model's context window |
| `claim_extractor.py` | folded into `verify.py` — the synthesizer emits its own markers, so claims never need re-extracting |
| `conflict.py`, `confidence.py` | the synthesizer is observed swallowing genuine disagreement between sources |
| `exceptions.py`, `trace.py`, `router.py` | folded into `models.py`, `storage.py`, `config.py` respectively |
| `policy.py` (consent gate) | dropped with attachments — it existed mainly to gate uploading user files to an external API |
| splitting `storage.py` into four | it passes ~200 lines |
| RAG: attachments, embeddings, file_loader, chunker, rag_worker | v2. This is a second product — "answer from my files" shares no machinery with "research the web" |
| `job_index`, `compaction`, `rewrite`, `follow-up`, `revisions/` | there are more than ~50 jobs on disk |
| `cli/render.py` | progress display needs to be more than `print()` |

## Open decisions

Each should be settled before the code that depends on it is written.

1. **ADR-0003 — search API + HTTP client + extraction library.** Required before the
   third vertical slice (real web). These three constrain each other, so they are one
   decision, not three.
2. **`robots.txt`, User-Agent identity, per-domain rate limits** — the contract for
   `tools/web.py`. Not currently written down anywhere.
3. **Cache key vs dedup key.** Proposal: cache key = `sha256(canonical URL + raw
   bytes)`; dedup key = `sha256(extracted text, whitespace-normalised)`. Two hashes,
   two jobs — hashing raw bytes can never deduplicate mirrors.
4. **Concurrency.** Proposal: one global semaphore for model calls (reason: cost and
   provider rate limits) and a separate per-domain semaphore for fetches (reason:
   politeness). One shared semaphore is either too slow or too rude.
