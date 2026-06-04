# eParts LLM-Based Layer 3 — POC Implementation

Reference-implementation scaffolding for the **LLM track** described in
`../LLM_Based_ML_Implementation_Plan.docx`. The goal of this folder is a
runnable proof-of-concept of Layer 3's LLM variant — retrieval-grounded
structured extraction with schema-enforced output, closed-vocabulary
post-validation, and provenance recording — so the team can evaluate it
head-to-head against the statistical baseline (`development_memo.docx`).

This is the L0–L1 + extraction-core slice from the plan. Retrieval, the
confidence ensemble, and Layer 4 fusion are scaffolded but stubbed; they
will be filled in as the plan's L2 → L7 milestones progress.

> **AI-generated code reminder.** Per the team's QA plan (see
> `eParts_Quality_Plan_v2.md` and the 2026-05-28 studio notes), code in
> this folder is AI-generated and must be reviewed by at least two
> people — including the author — before being treated as production
> intent.

---

## Choosing a local model

The POC runs against a local LLM via [Ollama](https://ollama.com/). The
model is selected by **one line** in `config/model.yaml`, so it is cheap
to A/B different sizes during the feasibility study.

| Tier | Model | Disk / RAM (Q4_K_M) | Strong points | Weak points |
|---|---|---|---|---|
| **Default** | `qwen2.5:7b-instruct` | ~4.7 GB | Best structured-JSON adherence at this size; reliably respects JSON-schema constraints; terse outputs; strong on HVAC-style technical text | Hedges on ambiguous cases; ~32K context window |
| Strongest reasoning per GB | `phi4` (14B) | ~9 GB | Excellent reasoning for size; great at category disambiguation; precise | 16K context; can be brittle on very noisy customer prose |
| Most ecosystem | `llama3.1:8b-instruct` | ~4.9 GB | 128K context; broadest tooling support; predictable | Slightly weaker than Qwen at strict JSON output; more verbose |
| Step-up (16 GB+ VRAM) | `qwen2.5:14b-instruct` | ~9 GB | Clear quality jump on tail and ambiguous queries; near-frontier for size | Noticeably slower; longer time-to-first-token |
| Rapid iteration | `llama3.2:3b-instruct` | ~2 GB | Sub-second per query; great for unit-test loops | Accuracy drops on hard cases; less reliable on closed-vocabulary |

For the artifact-collection POC the meeting called for, `qwen2.5:7b` is
the best default: it has the highest "did the model honor the JSON
schema and the closed-vocabulary constraint" rate among models that fit
comfortably on a laptop without a GPU.

---

## Quick start

### 1. Install Ollama and pull a model

Download Ollama from <https://ollama.com/download> (Windows installer),
then in PowerShell:

```powershell
ollama pull qwen2.5:7b-instruct
ollama serve     # usually starts automatically after install
```

### 2. Install Python deps

```powershell
cd "LLM Based Implementation"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 3. Run the demo

```powershell
python scripts/run_example.py                  # against the local Ollama model
python scripts/run_example.py --mock           # canned-response mode; no Ollama needed
python scripts/run_example.py --scenario 3     # run a specific scenario from the fixtures
```

Each scenario from the development memo (Scenarios 1–4) is encoded in
`data/fixtures/scenarios.json` and runs end-to-end against the local
model: retrieval (stub) → grounding pack → schema-constrained LLM call
→ closed-vocabulary post-validation → provenance record.

### 4. Run the tests

```powershell
pytest -q
```

The unit tests use `MockLLMClient` and require no model.

---

## Project structure

```
LLM Based Implementation/
├── README.md                        # this file
├── requirements.txt
├── config/
│   └── model.yaml                   # backend + model + sampling params
├── llm_layer3/                      # the library
│   ├── __init__.py
│   ├── schemas.py                   # Pydantic models for grounding + prediction + provenance
│   ├── llm_client.py                # Abstract LLMClient + Ollama + Mock + (Azure stub)
│   ├── prompt.py                    # System prompt + user-prompt renderer
│   ├── grounding.py                 # Retrieval stub + grounding-pack builder + fixture loader
│   └── extract.py                   # The end-to-end extract() entry point
├── data/fixtures/
│   ├── catalog.json                 # Tiny synthetic HVAC catalog (Damper Actuator / Temp Sensor / Thermostat)
│   ├── product_type_attributes.json # PT → list of in-scope attribute names (mirrors ePARTS PTA schema)
│   ├── canonical_values.json        # Attribute → allowed values + usage counts (the 2A vocabulary)
│   └── scenarios.json               # The four scenarios from development_memo.docx
├── scripts/
│   └── run_example.py               # Demo driver — exercises the full pipeline
└── tests/
    ├── conftest.py
    └── test_extract.py              # Mocked-LLM unit tests
```

---

## What is and isn't implemented yet

Mapping to the plan's milestones:

| Plan ID | Status |
|---|---|
| L0 Retrieval substrate (FAISS / Azure AI Search) | **Stub** — keyword-overlap retrieval over the fixture catalog. Real FAISS index lives in the stat track and will be wired in. |
| L0 LLMClient abstraction (Azure + local parity) | **Done (local)**; Azure client is a one-method stub. |
| L1 Grounding pack + JSON schema | **Done** — deterministic builder, schema-enforced output. |
| L1 Closed-vocabulary post-validation (2A guardrail) | **Done** — out-of-vocab values demoted to `insufficient_evidence`. |
| L2 LLM extraction service | **Done (single primary pass)**. Self-consistency sampling is a TODO in `llm_client.py`. |
| L3 Confidence ensemble + per-PT calibrator | **Not started** — placeholder in `extract.py`; needs val-split data. |
| L4 Layer 4 fusion / thresholds / caps | **Not in this folder** — preserved unchanged from stat track. |
| L5–L7 Eval / online feedback / hardening | **Not started**. |

---

## Swapping the backend

`config/model.yaml`:

```yaml
backend: ollama                       # ollama | azure_openai (stub) | mock
model: qwen2.5:7b-instruct            # any ollama model
host: http://localhost:11434
options:
  temperature: 0.0                    # primary pass is deterministic per the plan
  num_ctx: 8192
```

To run on a different local model, `ollama pull <name>` and change `model`.
To run on Azure OpenAI later, swap `backend: azure_openai` and provide
deployment + key via env vars (see `llm_client.py:AzureOpenAIClient` —
currently a `NotImplementedError` stub).

---

## Provenance (per the studio critique)

Every prediction produced by `extract()` carries an immutable
`Provenance` record:

- `model` — `ollama/<name>` or `azure_openai/<deployment>`
- `model_options` — temperature, seed, num_ctx, eval timing
- `prompt_hash` — sha256 prefix of (system + user prompt)
- `grounding_hash` — sha256 prefix of the serialized grounding pack
- `timestamp` — UTC, ISO-8601
- `samples_used` — 1 for the primary pass; >1 once self-consistency is enabled

This is the "agent provenance" defense the May 1 critique asked for and
is what the plan's §6.2 requires.
