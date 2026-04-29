# Prompt Management — How We Govern LLM Usage

The fundamental problem: 5 team members using the same LLM on the same input will get different results. Prompts are probabilistic. Without governance, our SES produces non-reproducible artifacts.

---

## The System

### 1. Centralized Prompt Storage

Every prompt lives in `/prompts/*.txt` — never inline in code.

```
prompts/
├── transcript_parser.txt      # Parses .vtt meeting transcripts → structured JSON
├── priority_classifier.txt    # Classifies action items into P0/P1/P2
├── req_extractor.txt          # Synthesizes formal requirements from meeting data
├── session_extraction.txt     # Extracts coach session summaries
└── briefing_generator.txt     # Generates meeting briefing documents
```

Why not inline? Because inline prompts are invisible. Nobody can review what you put in a string literal buried in line 47 of your agent. Centralized storage means every prompt is visible, diffable, and reviewable.

### 2. Version Control via Hash Pinning

Every prompt file has a SHA-256 content hash. When an agent runs, it loads the prompt through the `PromptRegistry`, which:

1. Computes the hash of the current file content
2. Checks if this hash matches the **active version** in the registry
3. If it's a new hash (someone changed the file), it registers it as `pending_review`
4. The agent always uses the **pinned active version**, not whatever's on disk

This means: if you edit `transcript_parser.txt`, your change doesn't take effect until it's reviewed and activated. The old version keeps running.

**Current registry state:**

| Prompt | Active Hash | Author | Versions |
|--------|-------------|--------|----------|
| transcript_parser | v3277a42a | Ashritha | 2 |
| priority_classifier | v5677a0b9 | Ashritha | 1 |
| req_extractor | vb8b387c7 | Ashritha | 1 |
| session_extraction | v763d8a27 | Ashritha | 1 |
| briefing_generator | ve304cdc6 | Ashritha | 1 |

### 3. Peer Review Workflow

```
Author edits prompt → registers new version (status: pending_review)
                            ↓
                 Reviewer examines diff
                            ↓
              approve / reject / request_changes
                            ↓
              If approved → can be activated
                            ↓
              Activation writes to prompts/ dir and pins as active
```

The review is stored in `prompt_reviews` table: who reviewed, what action, comment, timestamp.

### 4. Performance Tracking Per Version

Every time an agent uses a prompt, the registry records:
- Run count
- Average tokens consumed
- Average quality score
- Correction rate (how often a human overrode the output)

This answers: "Did the new version of transcript_parser actually improve things, or just cost more tokens?"

### 5. A/B Testing

When two prompt versions both seem good, run them both on the same input and compare:

```
Same meeting transcript → Version A → Output A (score: 0.82)
Same meeting transcript → Version B → Output B (score: 0.91)
Winner: B
```

A/B results accumulate in `ab_tests` table with input hashes, scores, and winner.

---

## Team Conventions (Enforced)

These are stored in the `team_conventions` table and represent agreed-upon practices:

| # | Convention | Enforced By |
|---|-----------|-------------|
| 1 | All prompts in /prompts/ as .txt, never inline | Auto-scan on startup |
| 2 | Every prompt change requires peer review | Review workflow |
| 3 | temperature=0 for deterministic tasks | BaseAgent default |
| 4 | Every artifact carries provenance metadata | MetricsCollector |
| 5 | Human-in-the-loop for P0 items and ADRs | Pipeline config |
| 6 | Golden test cases for every prompt | Regression agent |
| 7 | Offline-first, LLM as upgrade | BaseAgent fallback |
| 8 | Deposit outputs to SharedMemory wiki | Pipeline executor |
| 9 | Cross-pipeline events, not function calls | EventBus |
| 10 | Weekly measurement dashboard review | Manual practice |

---

## Why This Matters

Without prompt governance:
- Team member A uses a prompt they found on Reddit. Team member B writes their own. Neither knows what the other is doing.
- A "small tweak" to a prompt breaks 40% of outputs. Nobody notices for a week.
- Measurement is meaningless because you can't compare runs across different prompt versions.

With prompt governance:
- Everyone uses the same pinned version. Outputs are reproducible.
- Changes are reviewed before activation. Regressions are caught.
- Performance is tracked per version. "Better" has a number.

---

## Where It Lives

- **Prompt files:** `/prompts/*.txt`
- **Registry DB:** `memory/prompt_registry.db`
  - `prompt_versions` — all versions with hashes, authors, status
  - `prompt_reviews` — review history
  - `prompt_metrics` — usage stats per version
  - `ab_tests` — A/B comparison results
  - `team_conventions` — enforced practices
- **Code:** `pipeline/prompt_registry.py`
- **Integration:** `agents/base.py` → `load_prompt()` reads from registry
