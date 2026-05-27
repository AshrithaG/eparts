# eParts Services — ML Confidence Scoring System
## Technical Proposal & Data Requirements

**Prepared by:** MSE Studio Team
**Date:** March 2026
**Version:** 1.0

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [What the System Does — Plain Language Overview](#2-what-the-system-does)
3. [System Architecture](#3-system-architecture)
4. [Technical Design with Key Formulas](#4-technical-design)
5. [Data Requirements from eParts](#5-data-requirements)
6. [Proposed Next Steps](#6-next-steps)

---

## 1. Executive Summary

We are building an automated pipeline that reads incoming product specification requests (emails, PDFs, CSV files) and maps them to the correct attributes in your product database — with a **confidence score** attached to every result.

- **High confidence** → the system processes the request automatically, no human needed.
- **Low confidence** → the system flags the request for a human reviewer.

This means your team only spends time on the hard or ambiguous cases, while routine requests are handled instantly. The system also learns and improves over time based on your team's feedback.

To build this system, we need two things from eParts:
1. **The model design** — described in this document.
2. **Training data** — specific examples described in Section 5.

---

## 2. What the System Does — Plain Language Overview

Think of the system as a well-trained new employee who has studied your entire product catalog. When a customer sends in a request, the employee does the following:

1. **Reads** the email, PDF, or CSV and pulls out the relevant text.
2. **Recognizes** known patterns — part numbers, voltage ratings, manufacturer names — from experience.
3. **Compares** unfamiliar descriptions against everything they have learned to find the closest match.
4. **Rates their own confidence**: "I'm 92% sure this is a 10K-3 thermistor, strap-on mount" vs. "I'm only 45% sure — please check."
5. **Learns from corrections**: When a reviewer says "you were wrong," the system updates its understanding so it does not make the same mistake again.

> **Key concept — Confidence Score:**
> Every output the system produces comes with a number between 0 and 1 (or equivalently 0%–100%). A score of 0.90 means the system is 90% confident in its answer. You define the threshold: for example, scores above 0.85 go straight to the database, scores below 0.85 go to a human reviewer. These thresholds can be adjusted at any time.

---

## 3. System Architecture

The pipeline has four layers, each with a clear responsibility:

```
┌─────────────────────────────────────────────────────────┐
│  INPUT SOURCES                                          │
│  Email body text │ PDF extracted text │ CSV rows        │
└────────────────────────────┬────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────┐
│  LAYER 1 — Text Extraction (no ML needed)               │
│  • CSV  → parse columns directly                        │
│  • PDF  → extract text (+ OCR for scanned documents)    │
│  • Email → extract body, strip signatures/headers       │
│  • Normalize units: "kΩ" → "kohm", "°F" noted, etc.    │
└────────────────────────────┬────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────┐
│  LAYER 2 — Rule Engine  (fast, high-confidence cases)   │
│  • Match part numbers against your product catalog      │
│  • Match numeric values + units (voltage, current, etc.)│
│  • Match manufacturer names from your Manufacturers list│
│  → Exact match → confidence = 1.0 (done)                │
│  → Partial match → confidence = 0.65–0.85               │
│  → No match → pass to Layer 3                           │
└────────────────────────────┬────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────┐
│  LAYER 3 — Semantic Similarity Matching (ML core)       │
│  • Convert text to a numeric vector (explained below)   │
│  • Compare against vectors of known correct examples    │
│  • Closer match → higher confidence score               │
└────────────────────────────┬────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────┐
│  LAYER 4 — Decision & Feedback Loop                     │
│  • Combine rule confidence + similarity confidence      │
│  • Score ≥ 0.85 → auto-process                          │
│  • 0.50 ≤ Score < 0.85 → human review queue            │
│  • Score < 0.50 → return to sender / flag as unclear    │
│  • Human decisions are fed back to improve the model    │
└─────────────────────────────────────────────────────────┘
```

---

## 4. Technical Design

This section contains the mathematical details for those interested. Each formula is followed by a plain-language explanation — **you do not need to understand the formulas to use or evaluate this system.**

---

### 4.1 Text-to-Vector Conversion

> **Plain language:** Computers cannot directly compare words or sentences. We first convert text into a list of numbers — a "vector" — that captures the meaning of the text. Two sentences with similar meanings will produce similar vectors, and two unrelated sentences will produce very different vectors. This is the foundation of how the system finds the "closest match."

We use **TF-IDF weighted word embeddings** to convert a sentence into a single vector. This approach weights important technical words (e.g., "thermistor", "actuator") more heavily than common words (e.g., "the", "is").

**Formula — Weighted Sentence Vector:**

```
v(sentence) = Σ [ tfidf(word_i) × embed(word_i) ] / Σ tfidf(word_i)

Where:
  embed(word)  = the pre-trained numeric vector for that word
                 (a list of ~100 numbers representing its meaning)
  tfidf(word)  = TF(word) × IDF(word)
  TF(word)     = how often this word appears in this sentence
  IDF(word)    = log( total sentences / sentences containing this word )
                 → rare technical terms get a high IDF weight
                 → common words like "the" get a near-zero IDF weight
```

> **Why TF-IDF weighting instead of simple averaging?**
> If we simply average all word vectors equally, the word "the" (which appears in almost every sentence) would pull the result toward a meaningless average. TF-IDF ensures that distinctive technical terms — the words that actually matter for product identification — dominate the vector.

---

### 4.2 Similarity Measurement

> **Plain language:** Once we have numeric vectors for both the new input and each known correct example, we measure how "close" they are. We use **cosine similarity**, which measures the angle between two vectors. An angle of 0° means they point in the same direction (identical meaning), and an angle of 90° means completely unrelated. This is more reliable than measuring straight-line distance in high-dimensional spaces.

**Formula — Cosine Similarity:**

```
similarity(A, B) = (A · B) / (‖A‖ × ‖B‖)

Result range: −1 to +1
  → Rescaled to [0, 1]:  sim = (cosine + 1) / 2

Interpretation:
  sim = 1.0  →  identical meaning
  sim = 0.7  →  closely related
  sim = 0.5  →  weakly related
  sim = 0.0  →  unrelated
```

---

### 4.3 Reference Region — The "High-Score Zone"

> **Plain language:** We take all the confirmed correct examples from your historical data and compute their average vector — the **centroid**. This centroid is the "center of gravity" of what good, correct product descriptions look like. When a new input arrives, we measure how far its vector is from this center. The further away it is, the less confident we are.

**Formula — Centroid of Reference Examples:**

```
μ = (1/N) × Σ v(sentence_i)     for all N confirmed-correct training sentences
```

To measure how far a new input `q` deviates from the reference region, we use **Mahalanobis distance**, which accounts for the shape of the reference distribution (not just the distance from the center):

**Formula — Mahalanobis Distance:**

```
D(q) = √[ (q − μ)ᵀ × Σ⁻¹ × (q − μ) ]

Where:
  q   = vector of the new incoming sentence
  μ   = centroid of all reference (correct) examples
  Σ   = covariance matrix of reference examples
        (describes the "shape" and spread of the reference cluster)
```

> **Why not just use straight-line (Euclidean) distance?**
> Imagine the reference examples form an elongated ellipse rather than a perfect circle. A point that is technically far from the center but still inside the ellipse should score well. Mahalanobis distance accounts for this shape; Euclidean distance does not. In practical terms, this makes the scoring fairer for product categories that have naturally wider variation.

**Formula — Embedding-based Confidence Score:**

```
conf_embed = exp( −D(q)² / (2σ²) )

Where:
  σ is a tuning parameter controlling how quickly confidence drops
    with distance. It is calibrated on a validation set.

Result: conf_embed is always between 0 and 1.
  D(q) = 0  →  conf_embed = 1.0  (perfect match to reference center)
  D(q) large  →  conf_embed → 0.0  (very different from known examples)
```

---

### 4.4 k-Nearest Neighbors Scoring (Simpler Alternative)

> **Plain language:** Instead of computing a full region, a simpler approach is to find the *k* most similar confirmed-correct examples and average their similarity scores. Think of it as asking: "What do the 5 most similar cases in our history look like, and how similar are they?" This is more interpretable and easier to debug.

**Formula — k-NN Confidence Score:**

```
conf_knn(q) = (1/k) × Σᵢ₌₁ᵏ sim(q, vᵢ)

Where vᵢ are the k reference vectors most similar to q.
Recommended starting value: k = 5
```

---

### 4.5 Final Combined Confidence Score

The rule engine (Layer 2) and the semantic matcher (Layer 3) each produce a confidence value. We combine them:

**Formula — Combined Score:**

```
conf_final = α × conf_rule + (1 − α) × conf_embed

Where:
  conf_rule  = confidence from pattern/rule matching (0 to 1)
  conf_embed = confidence from semantic similarity   (0 to 1)
  α          = weight parameter, initially set to 0.7
               (rule matching is given more trust when available)

Special cases:
  If conf_rule = 0   (no rule matched)  → conf_final = conf_embed
  If conf_rule = 1.0 (exact part match) → conf_final = 1.0 directly
```

**Decision thresholds (adjustable):**

```
conf_final ≥ 0.85  →  Auto-process, write to database
0.50 ≤ conf_final < 0.85  →  Send to human review queue
conf_final < 0.50  →  Flag as "unable to process", notify sender
```

---

### 4.6 Incremental Learning — How the System Improves Over Time

> **Plain language:** Each time a human reviewer approves or corrects an output, the system updates its reference center. Adding a confirmed correct example slightly shifts the center toward it; a human correction for a wrong high-confidence prediction pushes the center away from that mistake. Over thousands of reviews, the system becomes progressively more accurate.

**Formula — Online Update When a New Correct Sample is Confirmed:**

```
μ_new = (N × μ_old + v_new) / (N + 1)
N_new = N + 1
```

> This is simply a running average — no full retraining needed. It is fast and can happen automatically after every human review.

**Formula — Correction When the Model Was Confidently Wrong:**

```
μ_corrected = μ_old − λ × (v_wrong − μ_old)

Where:
  v_wrong = vector of the incorrectly high-scored input
  λ       = learning rate (recommended: 0.01)
            → small value ensures one bad case does not
               overly distort the model
```

---

### 4.7 How Much Training Data Do We Need? (PAC Learning Bound)

> **Plain language:** There is a mathematical framework (called PAC learning — "Probably Approximately Correct") that gives a lower bound on how many training examples are needed to achieve a target accuracy. The formula below estimates this. In practice, we recommend collecting more data than the theoretical minimum to account for real-world noise and edge cases.

**Formula — Sample Size Lower Bound:**

```
m ≥ (1/ε²) × ln(|H| / δ)

Where:
  ε   = acceptable error rate (e.g., 0.10 = allow up to 10% mistakes)
  δ   = confidence level   (e.g., 0.05 = 95% statistical confidence)
  |H| = number of attribute categories in your system (approx. 200
        based on the Attributes.csv you provided)

Example calculation:
  ε = 0.10,  δ = 0.05,  |H| = 200

  m ≥ (1/0.01) × ln(200/0.05)
    ≥ 100 × ln(4000)
    ≥ 100 × 8.29
    ≥ 830 total training samples

  → Per attribute category: 830 / 200 ≈ 4–5 minimum samples
  → Practical engineering recommendation: 20–50 samples per category
```

> This means the theoretical minimum is around 830 labeled input-output pairs. However, to achieve robust real-world performance, especially for rare product categories, we recommend targeting **200 examples in the first phase** and expanding from there.

---

## 5. Data Requirements from eParts

This section describes exactly what we need from your side, with concrete examples of the format. We have organized requests by priority.

> **Important note for non-technical readers:**
> The CSV files you have already provided (Attributes, Manufacturers, Product_attribute_values, etc.) give us the **correct answers** — they tell us what the right attribute mappings look like. What we are still missing is the **raw input side** — the original customer-facing text (emails, PDFs, order forms) that was *used to produce* those correct answers. Without input-output pairs, the model cannot learn to go from question to answer.

---

### Priority 1 — Blocking (cannot train without these)

#### P1-A: Input–Output Paired Samples

**What we need:** Examples where a raw customer input (as-received text) is paired with the correct structured output that a human has already verified.

**Minimum quantity:** 200 pairs to start. More is always better.

**Requested format:**

```
Sample #001
-----------
Source type   : Email
Raw input text: "Hi, we need 3 units of Belimo LM24-3-T actuator.
                 Specs: 24VAC, spring return, 5Nm torque, 0-10V
                 control input signal."

Verified correct output:
  Manufacturer    : Belimo                  (Manufacturer_ID = 18)
  Product_ID      : [your internal ID]
  Attribute mappings:
    INPUT_VOLTAGE   (Attribute_ID = 13) → "24VAC"
    ACTION          (Attribute_ID = 48) → "SPRING RETURN"
    INPUT_SIGNAL    (Attribute_ID = 51) → "0-10V"
  Confidence label: HIGH   (human confirmed, ready to auto-process)

Sample #002
-----------
Source type   : PDF (extracted text)
Raw input text: "Sensor type: 10K-3 thermistor, strap-on installation,
                 temperature range −40 to 250°F"

Verified correct output:
  ProductType_ID  : 44
  Attribute mappings:
    ELEMENT         (Attribute_ID = 42) → "10K-3 THERMISTOR"
    MOUNTING        (Attribute_ID = 66) → "STRAP-ON"
    TEMPERATURE RANGE (Attribute_ID = 6) → "-40 TO 250°F"
  Confidence label: HIGH

Sample #003  (example of a low-confidence / ambiguous case)
-----------
Source type   : Email
Raw input text: "We need a Johnson Controls T-6000, 24V for a room."

Issue noted   : "T-6000" prefix overlaps with both thermostat and
                temperature sensor product lines. Context insufficient
                to determine which.
Correct action: Flag for human review — do NOT auto-process.
Confidence label: LOW
```

> **Where to source these samples:** Any past email threads, support tickets, or order entries where a staff member manually looked up a product and entered it into the system. Even informal records or spreadsheets used by your team would work. We do not need the full email chain — just the key text that describes the product, and what it was ultimately mapped to.

---

#### P1-B: Products Master Table

**What we need:** A table linking each Product_ID to its name, description, part number, and manufacturer. This is the reference library the system searches against.

**Why this is critical:** Currently we have attribute value mappings (e.g., Product 294 has ELEMENT = "3K THERMISTOR"), but we do not know the product's name or readable description. Without this, the system cannot match a text description to a specific product.

**Requested format:**

```
Product_ID | Part_Number | Product_Name                  | Description (free text)                                   | Manufacturer_ID | Category_ID
---------- | ----------- | ----------------------------- | --------------------------------------------------------- | --------------- | -----------
4521       | LM24-3-T    | Belimo Spring Return Actuator | Spring return actuator, 24V AC/DC, 5Nm torque,            | 18              | 61
           |             |                               | 0-10V control signal, for HVAC damper applications.       |                 |
4522       | LM24-SR     | Belimo Spring Return Actuator | Spring return actuator, 24V AC/DC, 10Nm torque,           | 18              | 61
           |             |                               | on/off control, 90° rotation.                             |                 |
```

> The description text does not need to be polished prose — technical spec sheet language, catalog copy, or even concatenated attribute values are all acceptable.

---

### Priority 2 — Highly Recommended

#### P2-A: Valid Values per Attribute

**What we need:** For each attribute in your system, the complete list of all valid/accepted values.

**Why:** Without this, the model might predict a value that does not exist in your database (e.g., predicting "WALL-MOUNTED" when the only valid option is "WALL-MOUNT"). Knowing the full valid-value list also lets us build a constrained output — the model picks from real options only.

**Requested format:**

```
Attribute_ID | Attribute_Name      | All Valid Values
------------ | ------------------- | -------------------------------------------------------
16           | OUTPUT_SIGNAL       | RESISTANCE, 0-10V, 4-20mA, 0-5V, DIGITAL, PWM
66           | MOUNTING_LOCATION   | STRAP-ON, DUCT, WALL, IMMERSION, AVERAGING, WELL
42           | ELEMENT             | 3K THERMISTOR, 10K-3 THERMISTOR, 100K THERMISTOR,
             |                     | 100 OHM PLATINUM RTD, 1000 OHM PLATINUM RTD
6            | TEMPERATURE_RANGE   | [numeric range — min/max values or accepted formats]
```

> If some attributes accept free-form numeric values (like temperature or voltage), please indicate the expected unit and format (e.g., "−40 to 250°F" or "24VAC / 120VAC / 240VAC").

---

#### P2-B: Historical Error / Edge Case Records

**What we need:** Cases where the system (or a human reviewer) initially made a wrong call — especially cases that might seem correct at first glance but are actually wrong.

**Why:** To learn when to be less confident, the model must see examples of plausible-but-wrong inputs. Without these, it will tend to be overconfident on ambiguous cases.

**Requested format:**

```
Error Case #001
---------------
Input text       : "Johnson Controls T-6000, 24V, room temperature"
Initial wrong call: Category = "Thermostat"   (incorrectly classified)
Correct answer   : Category = "Temperature Sensor"
Reason for confusion: T-6000 part number prefix also appears in
                      thermostat product line. Only context clarifies.
Confidence that should be assigned: LOW (flag for review)

Error Case #002
---------------
Input text       : "10k sensor, 2-wire, duct"
Initial wrong call: ELEMENT = "10K-3 THERMISTOR", confidence HIGH
Correct answer   : Cannot determine — "10k" is ambiguous (could be
                   10K-2, 10K-3, or 10K Type II). Need clarification.
Correct action   : Flag as LOW confidence, request more info.
```

> **Minimum quantity:** 50 error cases would be a meaningful starting point. These are invaluable — they directly teach the model to recognize the boundaries of its own knowledge.

---

### Priority 3 — Helpful Additions

#### P3-A: Standard Customer Submission Templates

If customers typically submit requests using a standard form or template (e.g., a structured Excel sheet, a web form, or a recurring email format), sharing that template allows us to write targeted parsing rules — significantly improving the rule engine's coverage and accuracy.

**Example of what to share:**
> "Most of our HVAC contractor clients use this order form: [attached Excel template]"
> "Distributors typically send spec sheets with this header format: Part No. / Description / Qty / Notes"

---

#### P3-B: Request Volume Distribution by Product Category

A rough breakdown of how many requests per week/month fall into each product category (sensors, actuators, valves, relays, etc.).

**Why:** This tells us where to focus training data collection efforts. If 60% of requests are temperature sensors but our training data is only 20% temperature sensors, the model will underperform on your most common case.

---

### Summary Table

```
┌────────────┬─────────────────────────────────────┬──────────────────────────────┐
│  Priority  │  Data Type                          │  Minimum Quantity            │
├────────────┼─────────────────────────────────────┼──────────────────────────────┤
│  P1 (Must) │  Input–Output Paired Samples        │  200 labeled examples        │
│  P1 (Must) │  Products Master Table (with desc.) │  Full catalog                │
├────────────┼─────────────────────────────────────┼──────────────────────────────┤
│  P2        │  Valid Values per Attribute          │  All active attributes       │
│  P2        │  Historical Error / Edge Cases      │  50+ cases                   │
├────────────┼─────────────────────────────────────┼──────────────────────────────┤
│  P3        │  Customer Submission Templates       │  All standard formats used   │
│  P3        │  Request Volume by Product Category  │  Rough statistics sufficient │
└────────────┴─────────────────────────────────────┴──────────────────────────────┘
```

> **A note on data privacy:** We understand that customer emails and order records may contain sensitive information. For the purposes of model training, it is sufficient to share **anonymized or redacted versions** — customer names, contact details, and pricing can be removed. We only need the product specification text and the corresponding correct attribute mappings.

---

## 6. Proposed Next Steps

| Step | Action | Owner |
|------|--------|-------|
| 1 | eParts confirms which P1 data is available and in what format | eParts |
| 2 | eParts shares P1-A samples (200 input-output pairs) | eParts |
| 3 | eParts shares P1-B Products master table | eParts |
| 4 | Team builds and tests rule engine on provided data | Studio Team |
| 5 | Team trains and evaluates similarity model | Studio Team |
| 6 | First demo with confidence scoring on real inputs | Both |
| 7 | Human feedback loop activated; model begins improving | Both |

---

*Document prepared by MSE Studio 2026 — eParts Services Project Team*
*For questions about this document, please contact the project team.*
