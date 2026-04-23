# eParts — Project Risk & Project Document

---

## Risk Management

### Risk 1: Blocked Development due to Tool Access (Cursor)

- **Condition:** The team currently lacks access to the Cursor tool required for development.
- **Consequence:** This blocks the team from utilizing specific AI-assisted coding workflows designated for the project.
- **Mitigation:**
  - Continue proactively scheduling troubleshooting calls with the client to resolve access.
  - **Interim Strategy:** Utilize the team's own LLMs and local tools to proceed with development without using proprietary client data until Cursor access is granted.

### Risk 2: Blocked Development due to Data Access

- **Condition:** The team is waiting on sample data (PDF spec sheets, database rows) and constraint metrics from the client.
- **Consequence:** Access delays could block the team from beginning essential OCR and ML model building.
- **Mitigation:**
  - **Request Schema Only:** If actual data is delayed, request the database schema immediately to allow the team to generate synthetic data.
  - **Representative Data:** Scrape the client's public website for representative parts data to create a minimally viable dataset for initial pipeline testing.
  - **Communication:** Shift communication from "we are blocked" to "we need this by date X to avoid impact Y," using leading indicators like yellow/red flags as deadlines approach.

### Risk 3: Technical Risk & ML Uncertainty

- **Condition:** The system relies on ML for attribute prediction. The team has three candidate models, including BERT and others, but has not yet determined which yields the best performance.
- **Consequence:** If the selected model yields low confidence, excessive records will route to human review.
- **Mitigation:**
  - **Experimentation:** Conduct experiments against all three ML candidates to quantitatively evaluate which meets the performance and resource usage baselines.
  - **Baseline Creation:** Since the client does not have a hard baseline, the team will establish one using the manual processing data and compare the experimental models against it.

### Risk 4: Overhead from Schema Volatility

- **Condition:** Although product schema changes are infrequent, they are a possibility.
- **Likelihood / Impact:** **Low Likelihood, High Impact.** While unlikely to happen often, a significant schema change could affect 30–40% of data.
- **Consequence:** Significant schema changes could force manual retraining.
- **Mitigation:** Move forward with the proposed "Semantic Matcher" approach (all-MiniLM model), which handles schema adjustments without manual retraining.

---

## Project Constraints

- **Azure Environment Lock-in:** The client is strictly locked into the Azure environment and relies on native integrations. The team must use Bicep (not Terraform) and avoid languages/tools that require the client to learn new non-Azure technologies.

---

## Strategic Planning & Project Management

### Change Management & Scope Control

*(Formerly Risk 3)*

- **Statement of Work (SOW):** The team will generate an official SOW to define the strict scope of the MVP (1–2 supplier formats, limited attributes).
- **Change Control Process:** To prevent scope creep, any request outside the SOW will not be rejected but met with a formal review — e.g., *"That is a great idea, let us scope the impact and return to you with a decision."*
- **Governance:** Adherence to the SES artifact lifecycle (Draft → Review → Approved → Baselined).

### Lifecycle & Milestones

- **Model:** Phase-by-phase iterative approach mapped to functional Vertical Slices.
- **Spring 2026 Roadmap:**
  - **Phase 1 & 2:** Lock SES, MVP scope, requirements, and architecture.
  - **Phase 3 & 4 (Vertical Slices):** Deliver functional slices.
    - **Vertical Slice 1:** End-to-end MVP using the defined SES.
    - **Vertical Slice 2:** Documentation, hand-off materials, and system hardening.
  - **Phase 5 & 6:** Hardening, critique, and wrap-up.

### Project Roles & Responsibilities

- **Team / Project Lead:** Rotates every mini-semester to ensure continuity while sharing leadership experience.
- **Architecture Lead:** Owns architecture decisions and ADRs.
- **Data / ML Lead:** Owns model behavior and confidence logic.
- **Engineering Lead:** Assigned to the member with the most experience in pipelines and integrations.
- **QA / Process Lead:**
  - **Expanded Scope:** Beyond software testing, this role monitors process metrics.
  - **Metrics:** Tracks code review quality, meaningful comments vs. rubber-stamping, cycle time, and rework frequency.

### Success Criteria

- **Product Metrics:** Percentage of records auto-accepted, prediction confidence distributions, data defect rates.
- **Human-in-the-Loop:** Specifically tracking the effectiveness of the HITL system (time saved vs. manual baseline).

### Resource & Task Planning

- **Human Allocation:** Distributed according to leadership roles.
- **AI Resource Allocation:** AI tools (Cursor) used for repetitive tasks and coding assistance.
- **Task Identification:** Derived from ETVX (Entry, Tasks, Verification, Exit) process models.
- **Progress Tracking:** QA Lead oversees backlog size, rework frequency, and cycle time per ingestion batch.
