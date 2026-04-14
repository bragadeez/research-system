# 🔬 Autonomous Research AI

> A multi-agent AI system that takes any research question and produces a fully cited, fact-checked research report — automatically. Zero cost, no GPU required.

[![Python](https://img.shields.io/badge/Python-3.10+-blue)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-green)](LICENSE)

---

## What does it do?

You type a question like *"What are the latest advances in mRNA cancer vaccines?"* and the system:

1. **Plans** the research — breaks it into focused sub-tasks
2. **Searches** the web, arXiv, Semantic Scholar, and Wikipedia automatically
3. **Extracts** factual claims from every source using an AI model
4. **Ranks** sources by credibility, topic relevance, and source type
5. **Writes** a structured Markdown report with inline citations
6. **Fact-checks** the report and gives it a confidence score

The whole process takes **3–8 minutes** depending on topic complexity. You get a Word document and Markdown you can download.

---

## Quick Start (5 minutes)

### Step 1 — Get a free Gemini API key

Go to **https://aistudio.google.com/app/apikey** → Create API key → Copy it.

Free tier limits: 1,500 requests/day for Gemini 2.0 Flash, 500/day for 2.5 Flash. Plenty for research.

### Step 2 — Install Ollama (for local AI extraction)

| OS | Command |
|---|---|
| **Linux** | `curl -fsSL https://ollama.com/install.sh \| sh` |
| **macOS** | Download from https://ollama.com/download → drag to Applications |
| **Windows** | Download `.exe` from https://ollama.com/download → run it |

Then pull a GLM model. Pick based on your hardware:

```bash
# Option A — Cloud model (zero RAM, free Ollama account needed)
ollama signin
ollama pull glm-5:cloud    # 744B params, runs on Ollama's servers

# Option B — Local 9B model (~8GB RAM)
ollama pull glm4

# Option C — Local 30B model, best local quality (~18GB RAM)
ollama pull glm-4.7-flash
```

### Step 3 — Configure

```bash
cd research-ai-v2
cp .env.example .env
```

Open `.env` and set:
```
GEMINI_API_KEY=AIzaSy...your_key_here
OLLAMA_MODEL=glm4          # or glm-5:cloud or glm-4.7-flash
```

### Step 4 — Install Python dependencies

```bash
python3 -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### Step 5 — Run

```bash
chmod +x run.sh    # Linux/macOS only
./run.sh
```

Open **http://localhost:8501** in your browser. Type a topic, click **Start Research**.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Streamlit UI (port 8501)                    │
│        Search bar · Suggestion cards · Live progress card           │
│        Report viewer · LLM evaluation panel · Word/MD download      │
└─────────────────────────┬───────────────────────────────────────────┘
                          │  HTTP / REST
┌─────────────────────────▼───────────────────────────────────────────┐
│                      FastAPI Backend (port 8000)                     │
│          POST /api/research · GET /api/export/{id}/docx             │
│          WebSocket /ws/{id} · POST /api/research/{id}/continue      │
└─────────────────────────┬───────────────────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────────────────┐
│                    Research Pipeline (orchestrator)                  │
│                                                                      │
│  Planner → Search → Source Ranker → Extractor → Aggregator          │
│     ↓         ↓           ↓             ↓            ↓              │
│  Gemini    DDG +       Intent       Ollama GLM    Semantic          │
│  2.5 Flash arXiv +    scoring       (batched)     clustering        │
│            S2 + Wiki               + heuristic    + contradiction   │
│               ↓                       fallback     detection        │
│           ChromaDB ──────────────────────────────────────────────── │
│           (vector store)                                             │
│               ↓                                                      │
│         Synthesiser → Critic Agent                                   │
│         Gemini 2.5   Gemini 2.5                                      │
│         (RAG report) (fact-check + confidence score)                 │
│                            ↓                                         │
│                    SQLite (history + reports)                        │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Agent-by-agent breakdown

### 🧠 Planner Agent (`agents/planner_agent.py`)
Uses **Gemini 2.5 Flash** with structured JSON output to decompose your query into 3–5 focused sub-tasks, each tagged with:
- A specific search query (not just "research X" — actual keyword queries)
- Source type: `academic`, `web`, `news`, `documentation`, etc.
- Priority, difficulty, expected evidence types

This is the most critical agent — bad planning cascades into bad searches.

### 🔍 Search Agent (`agents/search_agent.py`)
Routes each sub-task to the right tool based on its `source_type`:

| Source type | Tool used |
|---|---|
| `web`, `news`, `blog` | DuckDuckGo (`ddgs` library, no key needed) |
| `academic` | arXiv SDK + Semantic Scholar REST API (free, no key) |
| Both | Wikipedia as supplemental context |

Web results are scraped using a 3-tier extractor: trafilatura → readability → BeautifulSoup. Domain diversity is enforced (max 3 URLs per domain).

### 📊 Source Ranker (`core/source_ranker.py`)
Each source gets a `final_score` from:
- **Topic alignment** (embedding similarity between source and research plan)
- **Credibility** (intent-prior matrix: `.edu`/`.gov`/`arxiv.org` score higher for technical research)
- **Query match** (capped keyword density, not inflated by repetition)
- **Content length** (rewards substantive articles)

The intent-prior matrix adjusts weights based on research type — market analysis trusts news more than academic papers, technical research is the opposite.

### 🔬 Extraction Agent (`agents/extraction_agent.py`)
**The most time-sensitive agent.** Key optimisations:

**Speed fix (v2):** Instead of 1 Ollama call per paragraph (600 calls = 30 min), the agent now:
1. Groups paragraphs into batches of 6
2. Sends one Ollama call per batch (→ ~100 calls total)
3. Processes all sources **concurrently** with a semaphore(4)
4. Result: **~3–6 minutes** instead of 35+ minutes

**LLM vs heuristic:** If Ollama is available, uses GLM for evidence extraction (understands negation, context, passive voice). If Ollama is offline, falls back to the heuristic keyword-matching approach automatically.

Each extracted piece of evidence gets:
- `category`: result / method / metric / limitation / comparison / trend / definition / conclusion
- `confidence`: composite score based on source quality + claim specificity
- `keywords`: signal terms for aggregation

### 🔗 Evidence Aggregator (`core/evidence_aggregator.py`)
Groups similar claims from different sources into clusters using:
- **Batch embedding similarity** (BAAI/bge-small-en-v1.5 — better than all-MiniLM for scientific text)
- **O(n) matrix clustering** (fixed from the original O(n²) approach)
- **Contradiction detection** (flags when a cluster mixes positive and limiting statements)

Each cluster becomes a `ResearchFinding` with a merged confidence score that rewards multi-source agreement.

### 📝 Synthesis Agent (`agents/synthesis_agent.py`)
Uses **Gemini 2.5 Flash** to write a structured Markdown report. The prompt includes:
- Top findings grouped by section
- All available citation URLs
- Contradictions to acknowledge
- The original thesis and audience

The report follows: Executive Summary → Section analysis → Key Findings → Limitations → Conclusion → References.

### ✅ Critic Agent (`agents/critic_agent.py`)
A second **Gemini 2.5 Flash** call that independently reviews the report. It:
1. Extracts 4–6 key factual claims
2. Checks each against the evidence pool
3. Assigns: `supported` / `unsupported` / `uncertain`
4. Computes an overall **confidence score** (0–100%)
5. Decides if another search iteration is needed

If confidence < 65% and iterations remain, the pipeline automatically runs a targeted follow-up search.

---

## Project structure

```
research-ai-v2/
│
├── config.py                   # All settings, loaded from .env
├── main.py                     # CLI entry point
├── requirements.txt
├── run.sh                      # One-command launcher
├── .env.example                # Template for environment variables
│
├── models/                     # Pydantic data models
│   ├── research_plan.py        # ResearchPlan, SubTopicPlan, etc.
│   ├── source.py               # RawSource, RankedSource
│   ├── extraction.py           # ExtractedEvidence, EvidenceCategory
│   ├── finding.py              # ResearchFinding
│   ├── critique.py             # CritiqueResult, FactCheckResult
│   └── state.py                # ResearchState (pipeline state object)
│
├── agents/                     # The 5 AI agents
│   ├── planner_agent.py        # Gemini → structured research plan
│   ├── search_agent.py         # DDG + arXiv + S2 + Wikipedia
│   ├── extraction_agent.py     # Ollama GLM (batched) + heuristic fallback
│   ├── synthesis_agent.py      # Gemini → Markdown report
│   └── critic_agent.py         # Gemini → fact-check + confidence
│
├── core/                       # Shared infrastructure
│   ├── llm_client.py           # GeminiClient + OllamaClient
│   ├── source_ranker.py        # Intent-aware source scoring
│   ├── evidence_aggregator.py  # Semantic clustering + finding builder
│   └── vector_store.py         # ChromaDB wrapper (BAAI/bge embeddings)
│
├── tools/                      # Low-level utilities
│   ├── search_tools.py         # DDG, arXiv, Semantic Scholar, Wikipedia
│   ├── scraper.py              # httpx + trafilatura + readability + BS4
│   └── normalizer.py           # Text cleaning (keeps Greek/math chars)
│
├── orchestrator/
│   └── pipeline.py             # Full pipeline with retry loop
│
├── db/
│   └── database.py             # SQLite: sessions, reports, progress log
│
├── api/
│   └── server.py               # FastAPI: REST + WebSocket + exports
│
└── frontend/
    └── app.py                  # Streamlit UI
```

---

## Configuration reference

All settings live in `.env` (copy from `.env.example`):

| Variable | Default | Description |
|---|---|---|
| `GEMINI_API_KEY` | *(required)* | Free key from aistudio.google.com |
| `GEMINI_MODEL` | `gemini-2.5-flash` | Main model for planning/synthesis/critique |
| `OLLAMA_MODEL` | `glm4` | Extraction model (`glm4`, `glm-5:cloud`, `glm-4.7-flash`) |
| `OLLAMA_ENABLED` | `true` | Set `false` to force heuristic extraction |
| `MAX_RAW_SOURCES` | `60` | Cap on total sources per pipeline run |
| `MAX_ITERATIONS` | `2` | Max retry loops if confidence is low |
| `CONFIDENCE_THRESHOLD` | `0.65` | Below this → retry with follow-up searches |
| `EMBEDDING_MODEL` | `BAAI/bge-small-en-v1.5` | Sentence transformer for RAG + clustering |
| `EVIDENCE_STORE_PATH` | `./data/evidence_store` | ChromaDB on-disk location |

---

## What each model does

| Model | Used for | Why |
|---|---|---|
| **Gemini 2.5 Flash** | Planning, Synthesis, Critique | Best reasoning quality for complex structured tasks |
| **GLM (Ollama)** | Evidence extraction | High-volume batched calls — local = zero cost |
| **BAAI/bge-small-en-v1.5** | Embeddings | Outperforms MiniLM on scientific text (BEIR benchmark) |

---

## UI guide

### Research tab
- **Suggestion cards** — click any topic to prefill the search box
- **Start Research** — runs the full pipeline
- **Continue Research** — adds another search iteration to the latest complete session
- **Progress card** — shows the current pipeline stage with animated indicator
- **▶ Show live log** — expands to show every agent's real-time messages
- **Download buttons** — Markdown (`.md`) and Word (`.docx`) after completion
- **LLM Evaluation** — expandable panel showing fact-checks with supported/unsupported/uncertain verdicts

### History tab
- View all past sessions with confidence scores
- Re-run any session for a new iteration
- Delete sessions you no longer need

### Report Viewer tab
- Browse completed reports
- **How it was evaluated** section explains the confidence score methodology
- Fact checks table with summary statistics (supported / unsupported / uncertain counts)
- Download as Markdown or Word from this tab

---

## Performance guide

| Scenario | Expected time | Tips |
|---|---|---|
| Simple factual topic | 3–5 min | Default settings work well |
| Complex technical topic | 6–10 min | Normal |
| Medical / scientific deep research | 8–15 min | Increase `MAX_RAW_SOURCES=80` |
| Very slow extraction | Reduce to `MAX_RAW_SOURCES=30` | Or set `OLLAMA_ENABLED=false` for heuristic mode |
| Low confidence score | Click "Continue Research" | Runs targeted follow-up searches |

**Speed tip:** If you have a fast machine and want better quality, set `PARA_BATCH_SIZE=4` in `agents/extraction_agent.py` (more calls, more granular extraction).

---

## CLI usage

```bash
source venv/bin/activate

# Research a topic, print results, save to report.md
python main.py

# Edit main.py line 12 to change the topic:
topic = "Your research question here"
```

---

## Troubleshooting

**`ModuleNotFoundError`** after install:
```bash
pip install -r requirements.txt --upgrade
```

**Ollama not found / model not available:**
```bash
ollama serve          # start Ollama server
ollama pull glm4      # pull the model
ollama list           # verify it appears
```

**`glm-5:cloud` auth error:**
```bash
ollama signin         # creates free account
ollama pull glm-5:cloud
```

**ChromaDB error on first run:**
```bash
rm -rf data/evidence_store/
# Re-run — it recreates automatically
```

**Port already in use:**
```bash
lsof -ti:8000 | xargs kill     # Linux/macOS
# Or change API_PORT=8001 in .env
```

**Low confidence score (< 60%):**
- Click **Continue Research** to run more targeted follow-up searches
- The system automatically uses the critic's suggested follow-up queries

**Word (.docx) download missing:**
```bash
pip install python-docx
```

---

## Tech stack (all free)

| Layer | Technology |
|---|---|
| LLM planning/synthesis | Google Gemini 2.5 Flash (free tier) |
| LLM extraction | Ollama GLM (local) or GLM-5:cloud |
| Web search | DuckDuckGo — no API key |
| Academic search | arXiv + Semantic Scholar — no API key |
| Knowledge | Wikipedia — no API key |
| Scraping | httpx + trafilatura + readability-lxml |
| Vector DB | ChromaDB (local, on-disk) |
| Embeddings | sentence-transformers BAAI/bge-small-en-v1.5 |
| Backend | FastAPI + WebSocket |
| Frontend | Streamlit |
| Persistence | SQLite |
| Word export | python-docx |

---

## License

MIT — free to use, modify, and deploy for any purpose.