# Feedback on the Data Delivery — for eParts Team

*Draft response to the data package delivered on 2026-04-16. Organized point-by-point against the files you sent.*

---

Hi team,

Thanks for the quick turnaround on the data package. We've loaded all five files and done an initial pass. Below is a per-file review — **what works well**, **what's insufficient for model training**, and **concrete asks** where we need a bit more.

---

## 1A_Product_Attribute_Pairs.csv

**What works well**
- Scale is outstanding: **1,938,426 rows covering 134,117 distinct products and 348 attributes.** That is far beyond the 200-pair minimum we asked for.
- The structured numeric fields (`DigitalValue`, `Unit_Suffix`, `RangeLow`, `RangeHigh`) are a **bonus we did not ask for but will use heavily**. They let our rule engine handle numeric attributes (voltage, temperature, flow, pressure) with full confidence without re-parsing them out of free text.
- `Short_Description` is populated on 99.8% of rows, `Extended_Description` on 78.1% — plenty of training text per product.

**What's insufficient**
- You noted "The description columns are what our product team wrote after reviewing spec sheets — treat these as the 'input text.'" We understand, but this is worth flagging: these descriptions are **internally curated clean text**, not what real customer requests actually look like. Real emails, PDFs, and order forms contain typos, inconsistent units ("24VAC" vs "24 V AC" vs "24 vac"), signatures, greetings, and missing fields.
  - **Impact on us:** We can train the similarity model on this data, but when we deploy, the confidence scores will be **overconfident** because the model has never seen noisy input. The high-confidence threshold (≥ 0.85) will need to be recalibrated post-deployment.
- **~29% of active attributes have no rows here.** Your Data Dictionary lists 487 active attributes; this file covers 348. The missing 139 either have zero products using them, or were filtered out during export. Either way, the model cannot learn to predict them.
- A long tail of attributes has **fewer than 5 rows** (e.g., `HOLDING FORCE`, `LATCH TYPE`, `APERTURE SIZE [W x H]`). Our theoretical minimum is 4–5 per attribute, but the practical recommendation is 20–50. These rare attributes will have weak predictions.

**Concrete asks**
1. A short list of 30–50 **real, anonymized customer inputs** — email snippets, PDF-extracted text, or order-form entries — paired with the attribute mappings your team eventually assigned. These do not need to be clean; the messier the better for calibration.
2. Confirmation on whether the **139 missing attributes** are (a) unused, (b) filtered out, or (c) something we should request separately.

---

## 1A_Product_Document_Links.csv

**What works well**
- This was **not in our original data request, and it is extremely useful.** 516,005 document links covering 178,194 products (339K PDFs + 177K images) gives us the original spec-sheet source material our team referenced.
- Clear `ImageFile` flag (1 = image, 0 = PDF) makes the OCR pipeline routing straightforward.
- Join key (`Product_ID`) matches cleanly against 1A and 1B.

**What's insufficient**
- Nothing blocking. One minor note: in the absence of real customer input (see 1A above), we plan to **OCR a sample of these PDFs and use the extracted text as a proxy** for noisy customer input. This is a second-best approach — real customer text would still be preferable.

**Concrete asks**
- None. This is a bonus deliverable we are grateful for.

---

## 1B_Product_Master.csv

**What works well**
- 198,147 rows, matching the "198,465 active products" figure in the Data Dictionary almost exactly. Full catalog delivered as promised.
- `Product_ID`, `Product_Number`, `Manufacturer_ID/Name`, `ProductType_ID/Name`, `Category_ID` are **100% populated**. No orphaned joins expected on the enforced FKs.
- `Short_Description` populated on 99.9% of rows — this will be our primary similarity-search text.

**What's insufficient**
- The **`Product_Name` column is empty on 198,141 of 198,147 rows (only 6 non-empty values, 0.003%).** This looks like either an export issue or a field your business doesn't maintain.
  - We can substitute `Short_Description` as a display name, but the concatenated spec-string format (e.g., `"Strap-On Temperature Sensor | 3K Thermistor | Resistance Output | ..."`) is not ideal for UI where the reviewer sees "the closest match is product X."
- `Full_Description` is only 1.5% populated and `Extended_Description_Post` only 3.9%. `Extended_Description_Pre` at 84.2% is good.

**Concrete asks**
1. Confirm: is `Product_Name` **deliberately unmaintained** in your PIMS, or was it dropped from the export? If the latter, please re-export with that column.
2. If `Product_Name` is genuinely unmaintained, that's fine — we just need the confirmation so we document it as a design constraint.

---

## 1C. Staging Schema

Understood — you'd like to sync on PIMS first before sending this. **No blocker on our side for now.** Once you have a clearer picture of what slice of PIMS is relevant, we can take another look. The sooner the better, since the staging schema determines how real-time requests will be ingested.

---

## 2A_Values_Per_Attribute.csv

**What works well**
- 9,918 rows covering 346 attributes — aligned with 1A's attribute coverage, which is consistent.
- **The `Usage_Count` column is a bonus we didn't ask for but will use directly.** We'll weight predictions with it as a frequency prior, so rare values get treated more conservatively. This noticeably helps cold-start performance.
- Median of 7 valid values per attribute is very workable for constrained output (the model picks from the real allowed list only).

**What's insufficient**
- **4.8% of rows have an empty `Value` field.** We'd like to confirm the semantics: does an empty value mean "this attribute has explicitly been recorded as unknown/unset for some products," or is it a data-quality artifact to be filtered?
- For numeric/range attributes (temperature, flow rate, pressure), the file gives individual discrete values that have actually appeared in production. We don't have a declaration of the **accepted unit format / expected range** for each such attribute. This is not blocking, but having it would let our rule engine validate input more strictly.

**Concrete asks**
1. Clarify the meaning of **empty `Value` rows**.
2. If easy: for numeric attributes, a short note on expected units and acceptable ranges (e.g., "TEMPERATURE_RANGE is always in °F or °C; acceptable range −100 to 600").

---

## 2B_Apparent_Correction_Cases.csv

This is the file where we have the most significant concern. We want to flag it clearly so we can course-correct together.

**What works well**
- We appreciate the transparency: you called out that "there's no formal error-tracking system, so this is the best proxy." We agree it's the right intent.

**What's insufficient — the data doesn't give us what the proposal was asking for**

We looked at this file closely. Here's what we found:

| Finding | Value |
|---|---|
| Total rows | 746,845 |
| **Distinct `EO_ID` values** | **6** |
| **Distinct `EO_Reason` values** | **6** |
| Distinct `Product_ID` values | 25,203 |
| Products with more than one EO event | **291** (not "many thousands") |

The six `EO_Reason` values are:

| EO_Reason | Row count | What it looks like to us |
|---|---:|---|
| `test` | 433,249 (58%) | Bulk test operation |
| `changing vendor` | 144,340 (19%) | Vendor swap — a business operation, not a model error |
| `Flipping Air Products Vendor` | 144,340 (19%) | Same as above |
| `HW - MORE DISABLE` | 14,706 (2%) | De-activation |
| `HW - POWER METERS - DISABLE` | 10,205 (1%) | De-activation |
| `ONICON - AMAZON PROJECT` | 5 | Project tag |

**Two issues:**

1. **`Edit_Count` is not per-product.** The median and the mode are both 2,685, which is the size of the `EO_ID = 1` batch. In other words, `Edit_Count` appears to be "how many products this Edit Order touched," not "how many times this specific product has been re-edited." The filter suggested in the readme ("Edit_Count > 1 were re-edited") does not actually isolate products with repeated edits — only 291 products genuinely have more than one EO event.

2. **None of the `EO_Reason` values correspond to semantic corrections.** A "correction" in the sense we need it means: *the initial attribute value or category assignment was wrong, and a human reviewer later fixed it.* The reasons here are vendor swaps, de-activations, and test operations — all legitimate business activity, but none of it teaches the model to recognize ambiguous or misleading inputs.

**Why this matters for the model**

The purpose of the error cases (P2-B in our proposal) was specifically to teach the model **when to be less confident**. Without this, the model will be overconfident on ambiguous inputs — which is the exact failure mode we designed the confidence score to prevent.

**Concrete asks**

We don't think a full re-export will help here — the underlying data doesn't contain what we need. Instead, we'd like to propose a lightweight manual process:

1. **Could your product team hand-pick 50–100 cases** where they remember (or can find in Slack / email / notes) an attribute or category that was initially entered one way and later corrected? The format can be very simple:

   ```
   Product_ID: ______
   Input text (what the team was working from): ______
   Initial (wrong) mapping: Attribute = ______, Value = ______
   Corrected mapping:       Attribute = ______, Value = ______
   Why it was confusing (one sentence): ______
   ```

2. Alternatively, **pointers to 2–3 known "tricky" product families** where human review catches things the catalog rules miss (e.g., part-number prefix overlaps, thermistor-type ambiguity, duct-vs-wall mount confusion). We can work from there to construct synthetic edge cases.

Even 50 hand-selected cases are worth more than 700,000 rows of edit-order events.

---

## Summary: what we're ready to do vs. what we'd like to request

**Ready to start now, using what you've sent:**
- Build the rule engine (Layer 2) against 1A + 2A
- Build the similarity / confidence model (Layer 3) against 1A
- Use 1A_Product_Document_Links to drive an OCR-based end-to-end test

**Asks, in priority order:**
1. **Highest priority — 50–100 hand-picked correction cases** (see 2B section above).
2. **Medium priority — 30–50 real customer input samples** (emails, PDFs, order-form extracts), anonymized.
3. **Confirmation** on: (a) whether `Product_Name` is intentionally unmaintained in 1B; (b) the meaning of empty `Value` rows in 2A; (c) whether the 139 missing attributes in 1A are unused or were filtered.
4. **Lower priority — P3 items from the original proposal**: standard customer submission templates (P3-A), and a rough request-volume breakdown by product category (P3-B). These are not blocking but will help us tune the rule engine and prioritize training data.
5. **Sometime later — 1C staging schema** once your PIMS side is ready.

Let us know which of these are feasible and we can refine the ask further.

Thanks again — the scale and structure of 1A, 1B, 2A, and the bonus document links are a strong starting point.

Best,
MSE Studio Team
