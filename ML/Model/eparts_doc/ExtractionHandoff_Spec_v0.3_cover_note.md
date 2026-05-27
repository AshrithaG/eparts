# Cover note — Extraction Handoff Spec v0.3

**To:** Extraction sub-team
**From:** ML team (eParts Capstone)
**Re:** Attached `ExtractionHandoff_Spec_v0.3.docx`
**Read time:** ~1 min. The attached spec takes ~10 min.

---

## What you're looking at

The attached `.docx` is the **technical contract** for the data shape
your team's Layer 1 extraction pipeline must produce as input to our
Layer 2 rule engine and Layer 3 semantic matcher. The doc covers:

* 5 supported `source_type` values (csv / email / pdf_text / pdf_ocr / image)
* The `ExtractedInput` dataclass / JSON schema your output must match
* What to retain vs strip from the text body
* Required unit normalization table
* Canonical structured-field keys
* Worked examples per channel

## Things to know that aren't in the doc

1. **Contract authority.** The doc's dataclass code is canonical, but
   the live source of truth is [`ML/Model/src/contracts.py`](../src/contracts.py)
   in our repo. If the two ever drift, the code wins.
2. **Shared latency budget.** Our V1 SLA is **p95 ≤ 200 ms** end-to-end
   per V1 Engineering Spec §1.2. That's your pipeline + ours combined.
   LLM-based extraction can burn this fast — design for batching or
   async if you go that route. Tell us your target per-request latency
   so we can sanity-check the joint budget.
3. **Implementation freedom.** Your team chooses the OCR engine, NER
   stack, LLM (if any), email parser, and PDF parser. We don't
   constrain those — only the output shape. Anything in the spec
   tagged "do not" (§3.3 in the doc) is non-negotiable; everything
   else is your call.
4. **Reference implementation.** We shipped a deterministic Layer 1
   prototype before the scope split. It lives at
   [`ML/Model/archive/m2_layer1_extraction/`](../archive/m2_layer1_extraction/)
   with tests. Useful as a sanity check on your output shape, or as a
   fallback path if the LLM/NER approach hits a wall.
5. **Contract freeze.** We'd like to **lock the schema by end of this
   sprint** (our M3a is shipped, M3b in flight). After freeze, schema
   changes require a joint design review. Reply by end of week if you
   need a change before freeze.
6. **Integration test.** Once your pipeline can produce one valid
   `ExtractedInput` per channel, please commit those 4–5 fixtures to
   our `tests/fixtures/extraction/` directory. We'll wire up a joint
   regression test as part of M7.

## Questions we'd appreciate answered in your first reply

1. Which OCR / NER / LLM stack are you planning? (Not a constraint —
   helps us anticipate failure modes and latency.)
2. Do you need access to `1B_Product_Master.csv` to validate
   extracted part numbers against the canonical catalog before
   emission? We can grant explicit read access.
3. How do you plan to handle: multi-page PDFs, emails with
   attachments, non-English inputs (rare but possible)?
4. Any anticipated need for a third confidence signal? V1's fusion
   is locked at 2 inputs (rule + embedding), but we want to capture
   V2 backlog items now.

## Pointers

* Repo: `ML/Model/` in the main eParts repo
* Type contract: `src/contracts.py` (canonical) — `ExtractedInput` dataclass
* Unit canonicalization table: `config/unit_aliases.yaml`
* Architecture diagram: `eparts_doc/Architecture_Diagram.md`
* Channel: #eparts-ml (Slack)

Thanks — looking forward to working together on this. — ML team
