# eParts Risk Register

**Total Risks:** 16  
**Critical:** 2 | **High:** 7 | **Medium:** 7

| # | Severity | Category | Title | Mitigation | Status |
|---|----------|----------|-------|------------|--------|
| 1 | **critical** | technical | Confidence threshold miscalibration | Refinement 1: Run prototype on >=200 labeled submissions, co | open |
| 2 | **critical** | schedule | Data access delay blocking ML development | Data received ~Feb 22; team started basic model tests. Conti | mitigating |
| 3 | **high** | technical | Insufficient training data (<200 labeled examples) | Secure labeled data from eParts; augment with synthetic exam | open |
| 4 | **high** | technical | PIMS staging schema incompatibility (P1-C pending) | Refinement 4: Map P1-C columns to canonical schema; integrat | open |
| 5 | **high** | business | Catalog team capacity vs review volume | Measure actual review volume in prototype; adjust threshold  | open |
| 6 | **high** | technical | Drift detection metrics and baselines undefined | Define baseline metrics before prototype; SES measurement sy | open |
| 7 | **high** | measurement | Measurement validity for AI effectiveness | SES measurement system tracks tokens, cost, latency, human r | open |
| 8 | **high** | technical | Model selection uncertainty | ADR-1 hybrid approach with clear trigger conditions for swit | open |
| 9 | **high** | dependency | Integration dependency on Jake (PIMS schema) | Refinement 4 scheduled; team-owned buffer table as fallback | open |
| 10 | **medium** | technical | Alpha weighting sensitivity in hybrid scoring | Refinement 3: Sweep alpha 0.3-0.9; measure ECE, precision, c | open |
| 11 | **medium** | technical | Attribute correlation invalidates per-attribute routing | Refinement 2: Pairwise mutual information analysis on labele | open |
| 12 | **medium** | ux | Human review interface design not decided | Refinement 5: Present 30 sample items to Brian/Dewey; measur | open |
| 13 | **medium** | scope | Scope creep risk | Strict phase scoping; architecture designed for category ext | open |
| 14 | **medium** | technical | Azure tool constraints | Single App Service deployment chosen to minimize Azure opera | open |
| 15 | **medium** | schedule | Capstone timeline constraint | Architecture favors simplicity (single App Service, internal | open |
| 16 | **medium** | process | Knowledge loss from manual processes | Agentic SE system auto-captures decisions, action items, and | mitigating |

---
_Auto-generated from risk_register.db_