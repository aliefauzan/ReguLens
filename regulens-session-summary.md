# ReguLens — Session Summary

## 1. Project Overview

**Project:** ReguLens  
**Hackathon:** All Things Agentic Hackathon  
**Track:** Collaborative Partner  
**Concept name:** Evolving Knowledge Engine  
**Tagline:** *Bukan sekadar membaca regulasi. Agent ini mendeteksi kontradiksi, memperbarui knowledge graph, dan menyelamatkan bisnis dari kesalahan compliance.*

ReguLens is an autonomous regulatory intelligence system for micro/small exporters. The core idea is not simply to build a regulatory Q&A chatbot, but a system that:

- Ingests regulatory information from multiple formats.
- Extracts regulatory clauses into structured entities.
- Stores those clauses in a compliance knowledge graph.
- Detects conflicts, changes, superseding rules, and gaps.
- Mutates compliance state when new information arrives.
- Records state changes as an audit trail.
- Propagates regulatory changes to affected products/markets.
- Answers user questions using scoped retrieval, evidence, and confidence.

The original concept explicitly focuses on fragmented sources such as official PDFs, screenshots, exported chat content, public posts, and articles, with the central differentiator being evolving knowledge and contradiction detection.

---

# 2. Original Problem

## Target Problem

Small exporters often have to comply with multiple jurisdictions at the same time. Relevant information may be scattered across:

- Government PDFs
- Regulatory documents
- Public announcements
- Export association updates
- Screenshots
- Exported WhatsApp/chat files
- Articles
- Social media posts

The challenge is not merely finding information. The challenge is determining:

> **Which requirement is currently applicable to my product and destination, and did anything change or conflict with what I already knew?**

### Example

An Indonesian food/herbal exporter may face:

```text
Indonesia / BPOM
Sodium Benzoate <= 0.10%

EU
Sodium Benzoate <= 0.05%
```

A product containing 0.08% may be compliant in Indonesia but not compliant for the EU destination.

---

# 3. Core Persona

## Primary Persona — Small Exporter / SME Owner

Example persona from the original concept:

**Ibu Sari**
- 34 years old
- Owns a small herbal/food business
- Wants to export powdered drinks to UAE and Europe
- Does not have a large internal compliance/legal team

### Typical Questions

- Can I export this product to Germany?
- What requirements apply to my product?
- Did the regulation change recently?
- Why is my product now considered risky?
- Which requirement is causing the problem?
- What should I fix before shipment?

---

# 4. Important Product Positioning

The initial framing was:

> **“ReguLens detects contradictions between regulations.”**

The stronger positioning developed during brainstorming was:

> **“ReguLens maintains a living compliance twin of your product. When regulations change, it traces the change through a compliance graph, identifies what is affected, and tells you what needs attention.”**

This shifts the product from a document-analysis tool into a **regulatory impact engine**.

### Three strong concepts identified

1. **Regulatory Impact Engine**
   - Detects a regulatory change.
   - Determines what products, markets, requirements, and risks are affected.

2. **Regulatory Git / Time Machine**
   - Treats regulatory evolution like version history.
   - Shows before/after requirement changes.
   - Lets users see when a product transitioned from compliant to at-risk.

3. **Compliance Twin**
   - Maintains a structured representation of the user's product, ingredients, packaging, destination, and compliance requirements.
   - Continuously compares the product state against changing regulatory knowledge.

### Recommended combination

**Compliance Twin + Regulatory Git + Impact Propagation**

---

# 5. Main User Use Cases

## Use Case A — Entering a New Market

User has a product and wants to export it to a new destination.

Example input:

```text
Product:
Herbal Drink Powder

Ingredients:
Ginger
Turmeric
Honey Powder
Sodium Benzoate

Origin:
Indonesia

Destination:
Germany
```

ReguLens returns a compliance readiness view such as:

```text
GERMANY / EU

Compliance Readiness
━━━━━━━━━━━━━━━━━━ 74%

✓ Ingredient documentation
✓ Packaging requirements
⚠ Preservative limit
✕ Label requirement
⚠ Certification
```

---

## Use Case B — Regulation Changed

User already exports to Germany. A new regulatory document is ingested.

ReguLens detects:

```text
BEFORE
Sodium Benzoate <= 0.10%

AFTER
Sodium Benzoate <= 0.05%
```

Then checks the actual product:

```text
Current product:
0.08%

New requirement:
0.05%

Result:
NON-COMPLIANT

Risk:
HIGH
```

This is one of the strongest demo scenarios.

---

## Use Case C — Cross-Jurisdiction Conflict

User asks why a product acceptable in Indonesia is not acceptable in Germany.

ReguLens explains:

```text
Indonesia
Maximum = 0.10%

EU
Maximum = 0.05%

Your product
= 0.08%

Indonesia: COMPLIANT
EU: NOT COMPLIANT
```

The key is that the system explicitly shows the underlying source clauses and conflict.

---

## Use Case D — Messy / Low-Authority Source

User uploads a public announcement, article, screenshot, or exported chat file.

Example:

```text
Kementerian update:

Untuk produk minuman yang akan masuk EU,
batas penggunaan sodium benzoate sekarang
lebih rendah dari sebelumnya.

Katanya mulai berlaku tahun ini.
```

ReguLens should extract the potential information but **not treat it as equally authoritative as an official regulation**.

Example state:

```text
Possible Clause

Substance: Sodium Benzoate
Limit: Unknown
Jurisdiction: EU
Effective Date: Uncertain
Authority: Low / Unverified
Status: Needs Review
```

---

## Use Case E — Pre-Export Compliance Check

User asks:

> “Can I export my Herbal Drink Powder with 0.08% sodium benzoate to Germany?”

Expected response:

```text
EXPORT READINESS — GERMANY

NOT READY

3 issues detected

1. ✕ Product labeling
2. ✕ Ingredient limit
3. ⚠ Certification

Most critical:
Ingredient limit

Confidence: 93%

Sources:
[Clause A]
[Clause B]
```

---

## Use Case F — Monitoring Multiple Clients / Products

Secondary possible user: export consultant or compliance specialist.

Example portfolio:

```text
Client A — Herbal Powder → Germany
Client B — Coffee → UAE
Client C — Cosmetics → Singapore
```

ReguLens could notify:

```text
3 CLIENTS AFFECTED

🔴 Client A
EU ingredient regulation

🟠 Client C
Singapore labeling update

🟡 Client B
Documentation change
```

---

# 6. What ReguLens Should NOT Be

Not primarily:

- A generic chatbot.
- A generic document Q&A tool.
- A consumer app.
- A domestic-only compliance assistant.
- A simple PDF summarizer.

The strongest value appears when:

> **A business depends on multiple regulatory jurisdictions and needs to understand how changing rules affect an actual product.**

---

# 7. User Journey

```text
I HAVE A PRODUCT
        ↓
I WANT TO EXPORT
        ↓
SELECT MARKET
        ↓
REGULENS ANALYZES
        ↓
 ┌──────────────┐
 │ COMPLIANT    │
 └──────────────┘
        OR
 ┌──────────────┐
 │ PROBLEMS     │
 └──────────────┘
        ↓
WHAT CHANGED?
        ↓
WHY IS IT A PROBLEM?
        ↓
WHAT SHOULD I FIX?
        ↓
EXPORT READY
```

Continuous monitoring loop:

```text
REGULENS MONITORS
        ↓
REGULATION CHANGES
        ↓
RECONCILIATION
        ↓
IMPACT ANALYSIS
        ↓
ALERT USER
        ↓
“YOUR PRODUCT IS NOW AT RISK”
```

The second loop is especially important because it demonstrates agentic behavior: the system notices a relevant state change rather than only waiting for a question.

---

# 8. Main Input Types

## A. Product Input

Recommended MVP form:

```text
Product Name:
Herbal Drink Powder

Ingredients:
Ginger, Turmeric, Honey, Sodium Benzoate 0.08%

Export To:
Germany
```

Optional product fields:

```text
SKU
Origin Country
Packaging
Production volume
Current Markets
```

---

## B. Regulatory Document Input

Example:

```text
Upload:
EU_Food_Additives_Regulation.pdf

Source:
European Commission

Source Type:
Official Regulation

Applicable Market:
European Union

Effective Date:
1 January 2026
```

Supported ingestion forms from the original design:

- PDF
- TXT/JSON exported chat
- Public URL/article
- Screenshot/other messy input formats

---

## C. Natural Language Query Input

Examples:

```text
Can I export my Herbal Drink Powder with 0.08% sodium benzoate to Germany?
```

```text
Why is my product now at risk?
```

```text
What changed in the EU regulation?
```

```text
Which requirements do I need to fix before exporting?
```

---

# 9. System Design

## High-Level Architecture

```text
                         ┌───────────────────────┐
                         │       USER            │
                         │ Exporter / SME        │
                         └───────────┬───────────┘
                                     │
                                     ▼
                         ┌───────────────────────┐
                         │  Next.js Web App      │
                         │                       │
                         │ • Upload              │
                         │ • Compliance Twin     │
                         │ • Risk Dashboard      │
                         │ • Regulatory Timeline │
                         │ • Query               │
                         └───────────┬───────────┘
                                     │ HTTPS
                                     ▼
                    ┌─────────────────────────────────┐
                    │       Cloud Run API             │
                    │          FastAPI                │
                    │                                 │
                    │ /upload /products /query        │
                    │ /requirements /events          │
                    └───────┬───────────┬─────────────┘
                            │           │
             ┌──────────────┘           └──────────────┐
             ▼                                         ▼
   ┌───────────────────┐                    ┌──────────────────┐
   │   Cloud Storage   │                    │    Firestore     │
   │                   │                    │                  │
   │ PDFs              │                    │ Products         │
   │ Screenshots       │                    │ Clauses          │
   │ TXT/JSON          │                    │ Requirements     │
   │ Raw documents     │                    │ Conflicts        │
   └─────────┬─────────┘                    │ Events           │
             │                              │ Compliance state │
             ▼                              └────────┬─────────┘
      ┌─────────────┐                                │
      │   Pub/Sub   │                                │
      └──────┬──────┘                                │
             ▼                                        │
   ┌───────────────────────┐                          │
   │ Extraction Worker     │                          │
   │ Cloud Run Job         │                          │
   │ Gemma + Gemini        │                          │
   └───────────┬───────────┘                          │
               │                                      │
               ▼                                      │
      ┌──────────────────────┐                        │
      │ Reconciliation Agent │◄───────────────────────┘
      │ Guardrail            │
      │ Vector retrieval     │
      │ Gemini judge         │
      └──────────┬───────────┘
                 │
        ┌────────┴─────────┐
        ▼                  ▼
┌───────────────┐  ┌──────────────────┐
│ Impact Engine  │  │ Query Agent      │
│               │  │                  │
│ What changed? │  │ What do I need?  │
│ What breaks?  │  │ Why?             │
│ What is risky?│  │ Sources?         │
└───────┬───────┘  └─────────┬────────┘
        │                    │
        └──────────┬─────────┘
                   ▼
             Firestore Events
                   │
                   ▼
          Regulatory Timeline
```

---

# 10. Recommended Technology Stack

| Layer | Technology | Responsibility |
|---|---|---|
| Frontend | Next.js + TypeScript | Main web application |
| UI | React | Interactive dashboard/components |
| UI Styling | Tailwind / shadcn | Visual system |
| Backend | Python + FastAPI | API and backend services |
| Agent framework | Google ADK | Agent orchestration/tool use |
| Main AI | Gemini via Vertex AI | Extraction, reasoning, reconciliation, Q&A |
| Secondary AI | Gemma | Pre-summarization for long documents |
| Storage | Google Cloud Storage | Raw uploaded files |
| Database | Firestore | Compliance state and knowledge graph |
| Messaging | Pub/Sub | Async processing |
| Compute | Cloud Run | API + agents/services |
| Batch | Cloud Run Jobs | Long/expensive extraction jobs |
| Embeddings | Vertex AI Embeddings | Clause similarity/search |
| Auth | Firebase Auth (optional) | Login |
| Logging | Cloud Logging | Runtime/log observability |
| Monitoring | Cloud Monitoring | System health |
| CI/CD | Cloud Build or GitHub Actions | Build/deploy |
| Containers | Docker | Packaging/deployment |

The original proposal already identifies Cloud Run, Firestore, Cloud Storage, Pub/Sub, Vertex AI, Google ADK, and Gemma as the major infrastructure/AI components.

---

# 11. Agent Architecture

Recommended agent hierarchy:

```text
ReguLens Root Agent
│
├── Extraction Agent
│
├── Reconciliation Agent
│     ├── Guardrail Tool
│     ├── Similarity Search Tool
│     └── Conflict Tool
│
├── Impact Agent
│     ├── Requirement Tool
│     └── Risk Tool
│
└── Query Agent
      ├── Retrieval Tool
      ├── Graph Tool
      └── Evidence Tool
```

Important principle:

> **LLMs reason over the regulatory graph, but deterministic systems control what gets changed in the graph.**

Do not use a raw LLM call as the sole authority for database mutations.

---

# 12. Agent 1 — Extraction Agent

### Responsibility

Turn messy documents into structured regulatory clauses.

### Flow

```text
PDF / Image / Text
        ↓
Text extraction
        ↓
Gemma pre-summary (long docs)
        ↓
Gemini extraction
        ↓
Structured Clause
```

### Example output

```json
{
  "substance": "sodium benzoate",
  "limit": 0.05,
  "unit": "%",
  "product_type": "food product",
  "jurisdiction": "EU",
  "effective_date": "2026-01-01",
  "source": "EU Regulation XYZ",
  "confidence": 0.94
}
```

---

# 13. Gemma's Role

For long regulatory documents:

```text
200-page PDF
      ↓
Gemma
      ↓
Relevant regulatory sections
      ↓
Gemini
      ↓
Precise extraction
```

Gemma is not a decorative bonus model. Its role is to reduce context burden before deep extraction.

---

# 14. Agent 2 — Reconciliation Agent

### Responsibility

Determine whether a new clause:

- Conflicts with existing information.
- Supersedes an old rule.
- Introduces a new requirement.
- Creates a gap.
- Is ambiguous and should be reviewed.

### Flow

```text
New Clause
    ↓
Generate Embedding
    ↓
Retrieve Similar Clauses
    ↓
Deterministic Guardrail
    ↓
 ┌───────────────────┐
 │ no match?         │ → New Requirement
 └───────────────────┘

If comparable:
    ↓
Gemini Judge
    ↓
Conflict / Supersede / Gap / Needs Review
```

---

# 15. Guardrail Engine

Guardrails are deterministic code, not LLM guesses.

Example checks:

```text
substance_match?
product_type_match?
dimension_match?
unit compatibility?
measurement basis compatibility?
```

Only when the structured checks pass should the candidate be sent to Gemini for semantic reconciliation.

Example pseudo-logic:

```python
def comparable(a, b):
    if a.substance != b.substance:
        return False
    if a.product_type != b.product_type:
        return False
    if a.unit != b.unit:
        return False
    return True
```

Architectural principle:

> **Deterministic code protects probabilistic reasoning.**

---

# 16. Agent 3 — Impact Engine

This is a recommended expansion beyond the original v2 concept.

### Responsibility

Trace regulatory changes into business consequences.

```text
Regulation
    ↓
Clause
    ↓
Requirement
    ↓
Product
    ↓
Destination
    ↓
Risk
```

Example:

```text
EU Regulation Changed
        ↓
Sodium Benzoate limit changed
        ↓
Requirement updated
        ↓
Herbal Drink Powder affected
        ↓
Germany affected
        ↓
HIGH RISK
```

This turns ReguLens into a regulatory **impact engine**, not only a contradiction detector.

---

# 17. Agent 4 — Query Agent

### Responsibility

Answer natural language questions using evidence from the knowledge graph.

Flow:

```text
User Question
      ↓
Intent extraction
      ↓
Top-k Vector Search
      ↓
2-hop Graph Traversal
      ↓
Relevant Clauses
      ↓
Requirements
      ↓
Conflicts
      ↓
Gemini
      ↓
Answer + Evidence + Confidence
```

The query agent should not answer from generic model knowledge when the question is about the user's compliance state.

---

# 18. Data Model

## `documents`

Stores original documents and ingestion metadata.

```json
{
  "id": "doc_001",
  "filename": "bpom_2026_labeling.pdf",
  "source_type": "pdf",
  "storage_url": "gs://...",
  "uploaded_at": "...",
  "status": "extracted"
}
```

## `clauses`

Stores extracted regulatory knowledge.

```json
{
  "id": "clause_001",
  "document_id": "doc_001",
  "text": "Batas maksimum ...",
  "substance": "sodium benzoate",
  "limit": "0.1%",
  "jurisdiction": "Indonesia - BPOM",
  "effective_date": "2026-01-01",
  "confidence": 0.92,
  "status": "active"
}
```

## `products`

Recommended extension for the Compliance Twin.

```json
{
  "id": "prod_001",
  "name": "Herbal Drink Powder",
  "ingredients": [
    "ginger",
    "turmeric",
    "sodium benzoate"
  ],
  "origin": "Indonesia"
}
```

## `markets`

```json
{
  "id": "market_de",
  "country": "Germany",
  "region": "EU"
}
```

## `requirements`

```json
{
  "id": "req_001",
  "product_id": "prod_001",
  "market_id": "market_de",
  "substance": "sodium benzoate",
  "limit": 0.05,
  "unit": "%",
  "status": "conflicted"
}
```

## `conflicts`

```json
{
  "id": "conf_001",
  "clause_a": "clause_bpom",
  "clause_b": "clause_eu",
  "type": "limit_mismatch",
  "severity": "high",
  "status": "open"
}
```

## `graph_events`

Immutable audit trail of state changes.

```json
{
  "event_type": "requirement_changed",
  "entity_id": "req_001",
  "before": {
    "limit": 0.10
  },
  "after": {
    "limit": 0.05
  },
  "triggered_by": "reconciliation_agent",
  "timestamp": "..."
}
```

## `query_logs`

Stores user questions, answers, evidence, and retrieval scope.

---

# 19. Confidence Model

Avoid relying on an LLM's self-reported confidence alone.

Recommended composite score:

```text
Confidence
   │
   ├── Parse / OCR Quality       30%
   ├── Self-Consistency           40%
   └── Source Authority Tier      30%
```

Formula:

```text
confidence_final =
0.3 * parse_quality
+ 0.4 * self_consistency
+ 0.3 * authority_tier_score
```

Authority tiers can be:

```text
official government regulation > professional/industry article > broadcast/social source
```

Low confidence should produce `needs_review`, not an automatic `conflict` state.

---

# 20. State Management

## Document State

```text
uploaded
   ↓
extracting
   ↓
extracted
   ↓
reconciled
```

## Clause State

```text
active
superseded
conflicted
needs_review
```

## Conflict State

```text
open
resolved
```

Every state transition should write to `graph_events`.

---

# 21. Failure Handling

## Extraction Failure

- Retry with exponential backoff.
- If repeatedly failing, mark as `needs_review`.

## Reconciliation Failure

- Do not blindly write conflict state.
- Keep clause active or mark as `needs_review` depending on the situation.

## Low-Confidence Reconciliation

- Do not auto-label as conflict.
- Flag for review.

## Query Failure

- Fall back to the strongest available clauses.
- Clearly indicate reduced confidence.

---

# 22. Why Pub/Sub

Avoid making the upload HTTP request perform every expensive operation synchronously.

### Better flow

```text
Upload
  ↓
Cloud Storage
  ↓
Pub/Sub Event
  ↓
Worker
  ↓
Extraction
  ↓
Reconciliation
  ↓
Firestore
```

Frontend can show:

```text
✓ Uploaded
✓ Extracting
● Reconciling
○ Updating compliance
```

This also supports retry and decoupling.

---

# 23. Why Firestore

Firestore is used as the compliance state/knowledge layer rather than as a conventional relational schema.

It stores:

- Entities
- Current state
- Relationships
- Conflict state
- Audit events
- Query logs

The important concept is not simply “database,” but **evolving state**.

---

# 24. Recommended UI Concepts

## A. Compliance Readiness

```text
GERMANY / EU

━━━━━━━━━━━━━━━━━━ 78%

✓ Ingredients
✓ Packaging
⚠ Preservative Limit
✕ Label
⚠ Certification
```

## B. Regulatory Alert

```text
⚠ REGULATORY CHANGE

EU Food Regulation

Sodium Benzoate
0.10% → 0.05%

Your product is affected.

Confidence: 94%

[Investigate]
```

## C. Regulatory Git / Timeline

```text
2025 ────────●──────── 2026
              ↑
          Aug 18, 2026

BEFORE
0.10%

AFTER
0.05%

Affected:
Herbal Drink Powder
```

## D. Impact View

```text
EU Regulation Changed
        ↓
Requirement Changed
        ↓
Product Affected
        ↓
Germany Shipment
        ↓
🔴 HIGH RISK
```

## E. Compliance Twin

```text
HERBAL DRINK POWDER

Ingredients
• Ginger
• Turmeric
• Honey Powder
• Sodium Benzoate 0.08%

Packaging
• 250g plastic pouch

Origin
• Indonesia

Destination
• Germany
```

---

# 25. Recommended End-to-End Demo

The strongest demo should focus on **one product, one market, one regulatory change**.

### Demo sequence

```text
1. Add Product
      ↓
2. Select Germany
      ↓
3. Show current compliance baseline
      ↓
4. Upload new EU regulation PDF
      ↓
5. Extraction agent processes it
      ↓
6. Guardrail checks candidate clauses
      ↓
7. Reconciliation agent confirms conflict/change
      ↓
8. Knowledge graph mutates
      ↓
9. Impact engine traces affected product
      ↓
10. Dashboard changes state
      ↓
11. Timeline shows BEFORE → AFTER
      ↓
12. User asks “Why is my product at risk?”
      ↓
13. Query Agent returns evidence + confidence
```

### Example final screen

```text
REGULATORY CHANGE DETECTED

EU — Food Additives

Sodium Benzoate

OLD LIMIT        NEW LIMIT
0.10%      →     0.05%

Your product
0.08%

STATUS
🔴 NON-COMPLIANT

AFFECTED MARKET
Germany

CONFIDENCE
94%

WHY?
The destination requirement is stricter
than the current formulation.

SOURCES
[EU Regulation]
[Existing Product Requirement]
```

---

# 26. Most Important Product Principle

The product should not feel like:

```text
User asks question
      ↓
AI answers
```

It should feel like:

```text
Regulations change
      ↓
ReguLens notices
      ↓
ReguLens reconciles
      ↓
ReguLens updates its knowledge
      ↓
ReguLens identifies affected products
      ↓
ReguLens alerts the user
      ↓
User decides what to do
```

That is the strongest expression of **agentic + evolving knowledge** behavior.

---

# 27. Final Recommended Product Definition

> **ReguLens is a living regulatory intelligence and impact engine for small exporters. It maintains a compliance twin of each product, ingests regulatory sources, detects contradictions and changes, updates a structured knowledge graph, traces the impact of those changes across products and markets, and proactively alerts users when their compliance status is affected.**

### One-line pitch

> **“ReguLens tells exporters not only what the regulations say, but what changed, what it breaks, and what they need to fix.”**

---

# 28. MVP Scope

Keep the first implementation focused on:

```text
UPLOAD
  ↓
EXTRACTION
  ↓
GUARDRAIL
  ↓
RECONCILIATION
  ↓
KNOWLEDGE GRAPH UPDATE
  ↓
IMPACT ANALYSIS
  ↓
DIFF / TIMELINE
  ↓
QUERY
```

### Defer until the core works

- Full authentication system
- Complex WhatsApp API integration
- Large multi-tenant administration
- Huge numbers of agents
- Excessive dashboard widgets
- Overly broad regulatory coverage
- Unverifiable simulated “messy” sources

Focus effort on proving the contradiction/change → state mutation → impact propagation loop.

---

# 29. Architectural Takeaway

The strongest architecture principle from this session is:

> **Use deterministic engineering to constrain probabilistic AI, use the knowledge graph as the persistent source of compliance state, and use agents to reason about how that state evolves.**

The technical system is therefore not just:

```text
PDF → LLM → Answer
```

It is:

```text
Source
  ↓
Extraction
  ↓
Structured Clause
  ↓
Deterministic Guardrail
  ↓
Reconciliation
  ↓
Knowledge Graph Mutation
  ↓
Audit Event
  ↓
Impact Propagation
  ↓
User Alert / Query
```

That is the core ReguLens system discussed in this session.
