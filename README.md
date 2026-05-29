# 🎓 ScholarNode AI

[![React](https://img.shields.io/badge/Frontend-React%20%2B%20Vite%20%2B%20TS-61DAFB?style=flat-square&logo=react)](https://react.dev)
[![FastAPI](https://img.shields.io/badge/Backend-FastAPI-009688?style=flat-square&logo=fastapi)](https://fastapi.tiangolo.com)
[![LangGraph](https://img.shields.io/badge/Orchestration-LangGraph-orange?style=flat-square)](https://github.com/langchain-ai/langgraph)
[![ChromaDB](https://img.shields.io/badge/Vector%20Store-ChromaDB-blue?style=flat-square)](https://www.trychroma.com)
[![Gemini](https://img.shields.io/badge/LLM-Google%20Gemini%203.5/3.1-4285F4?style=flat-square&logo=google)](https://ai.google.dev/)

> A premium, multi-agent AI research pipeline that transforms any query into a fully cited, structured, and fact-checked research report in minutes. Built for 100% free cloud operation using Google's Gemini models with automatic key rotation, fallback capability, and an interactive RAG chatbot interface.

ScholarNode AI features a gorgeous, responsive **React + Vite + TypeScript** dashboard, real-time progress visualization via WebSockets, SQLite database persistence, interactive architecture flowcharts, and flexible export/import options (Word, Markdown, and Session JSON).

---

## 🚀 Key Features

* **Multi-Agent LangGraph Core**: Orchestrates research flows (`Plan` ➔ `Search` ➔ `Rank` ➔ `Extract` ➔ `Aggregate` ➔ `Synthesize` ➔ `Critique`) using structured LangGraph state graphs with native retry loops on critique failures.
* **Dual-tier Gemini Pipeline**:
  * **High-Reasoning Tasks** (Planning, Synthesis, Critique): Handled by `gemini-3.5-flash` for state-of-the-art reasoning and schema compliance.
  * **High-Volume Tasks** (Evidence Extraction): Handled by `gemini-3.1-flash-lite` (500 RPD / 15 RPM) to absorb extensive page-scraping extraction batches in parallel.
* **Option B Quota Fallback**: If the strict daily limit (20 RPD) of `gemini-3.5-flash` is exhausted across your keys, the backend automatically falls back to `gemini-3.1-flash-lite` without crashing the active run.
* **API Key Rotator**: Thread-safely rotates between multiple API keys in `GEMINI_API_KEYS` to scale past single-key request limits.
* **Interactive RAG Chatbot (Chat with Report)**: Automatically chunk, embed (`BAAI/bge-small-en-v1.5`), and index completed reports into ChromaDB. Ask follow-up questions, view retrieved text snippets, and inspect source materials inside an overlay chat window.
* **Dual Research Modes**:
  * **Standard Mode**: Scours Tavily, DDG, arXiv, Semantic Scholar, and Wikipedia for a balanced blend of news, web documentation, and literature.
  * **Research Heavy Mode**: Queries academic databases exclusively (arXiv, PMC, Semantic Scholar, CORE, OpenAlex). Normalizes and ranks research papers using citation-per-year impact scores to generate standard academic literature reviews with numerical inline citations and APA bibliographies.
* **Persistent Sessions & JSON Portability**: Save any session as a JSON data file, and import it into another ScholarNode instance to review history, inspect evaluation metrics, and download Word/Markdown documents.

---

## 🛠️ System Architecture

```
┌───────────────────────────────────────────────────────────────────────────┐
│                        Vite + React UI (port 5173)                        │
│   Interactive Hero Search · Mode Toggle · Dynamic Flowchart Selector       │
│   WebSocket Progress Tracker · Report Viewer · LLM Evaluation Dashboard   │
│   Floating RAG Chat Assistant (Chat-with-Report) · Import / Export Panel  │
└─────────────────────────────────────┬─────────────────────────────────────┘
                                      │  HTTP / WebSockets
┌─────────────────────────────────────▼─────────────────────────────────────┐
│                       FastAPI Backend (port 8000)                         │
│   POST /api/research               · GET /api/export/{id}/{format}        │
│   POST /api/import                 · POST /api/research/{id}/chat         │
│   GET /api/sessions                · WebSocket /ws/{id}                   │
└─────────────────────────────────────┬─────────────────────────────────────┘
                                      │
┌─────────────────────────────────────▼─────────────────────────────────────┐
│                     Research Pipeline (Orchestrator)                      │
│                                                                           │
│   Planner  ➔  Searcher  ➔  Source Ranker  ➔  Extractor  ➔  Aggregator     │
│      │           │              │               │              │          │
│   Gemini 3.5  APIs/Web     bge-small-en-v1.5  Gemini 3.1     Semantic     │
│    (Planning)  Scrapers     (Cosine Rank)      (Batched)      Matrix      │
│                                                                Clustering │
│                                                                           │
│          Synthesizer (Structured Draft) ➔ Critic Agent (Fact Audit)       │
│             Gemini 3.5 / 3.1 Flash-Lite      Gemini 3.5 / 3.1 Auditor     │
│                                                   │ (Retry Loop)          │
│                                                   ▼                       │
│                                         SQLite (data/research.db)         │
│                                         ChromaDB (data/chroma)            │
└───────────────────────────────────────────────────────────────────────────┘
```

---

## 📦 Project Directory Layout

```
scholarnode-ai/
├── agents/                     # AI agents coordinating the research stages
│   ├── planner_agent.py        # Decomposes queries into structured subtopics
│   ├── search_agent.py         # Performs parallel web searches
│   ├── academic_search_agent.py# Queries PMC, arXiv, Semantic Scholar, OpenAlex, CORE
│   ├── extraction_agent.py     # Batches paragraphs for factual claim extraction
│   ├── synthesis_agent.py      # Drafts the final standard report with citations
│   ├── heavy_synthesis_agent.py# Synthesizes literature reviews & APA references
│   └── critic_agent.py         # Fact-checks and evaluates report confidence
├── api/
│   └── server.py               # FastAPI server (CORS, WebSocket relays, Word export)
├── core/
│   ├── llm_client.py           # GeminiClient (API rotation & fallback), Groq client (unused)
│   ├── source_ranker.py        # Intent-prior domain scoring & semantic ranking
│   ├── evidence_aggregator.py  # Clusters claims & highlights source contradictions
│   └── rag_engine.py           # Ingests reports to ChromaDB and handles semantic search QA
├── db/
│   └── database.py             # SQLite persistence layer (sessions, reports, chat logs)
├── data/
│   └── .gitkeep                # SQLite databases & Chroma vector store directory
├── exports/
│   └── .gitkeep                # Default directory for generated Word and Markdown files
├── models/                     # Shared Pydantic schemas representing graph state
│   ├── critique.py             # Fact-check, metric scoring, and audit models
│   ├── extraction.py           # Atomic fact-claims and batch schemas
│   ├── finding.py              # Consolidated evidence and contradiction schemas
│   ├── research_plan.py        # Search subtopics and queries
│   ├── source.py               # Scraped, raw, and ranked documents
│   └── state.py                # LangGraph StateGraph TypedDict schema
├── orchestrator/               # LangGraph state machine configurations
│   ├── pipeline.py             # Standard research pipeline graph
│   └── heavy_pipeline.py       # Academic research pipeline graph
├── tools/                      # Normalizers, crawlers, and scrapers
│   ├── normalizer.py           # Text cleaning, formatting, and domain normalizers
│   ├── scraper.py              # Scrapers using Trafilatura, BeautifulSoup, and Readability
│   └── search_tools.py         # Interfaces for DDG, PMC, Semantic Scholar, and OpenAlex
├── frontend/                   # React + Vite + TS Frontend Dashboard
│   ├── src/
│   │   ├── api/client.ts       # Frontend REST client & WebSocket connectors
│   │   ├── App.tsx             # Interactive dashboard (hero, logs, report, evaluator, chat)
│   │   ├── index.css           # Vanilla CSS custom design system (custom variables, transitions)
│   │   └── main.tsx            # React application entry point
│   ├── package.json            # NPM packages and scripts
│   └── vite.config.ts          # Vite compilation config
├── .env.example                # Configuration template
├── config.py                   # Configuration management via Pydantic Settings
├── Dockerfile                  # Containerization docker config
├── main.py                     # Command-line interface (CLI) research tool
└── requirements.txt            # Python dependencies
```

---

## ⚡ Quick Start

### 1. Configure the Environment
Clone the repository and copy the environment template:
```bash
cp .env.example .env
```

Open `.env` and insert your Gemini API Key(s):
```env
# Singular key
GEMINI_API_KEY=AIzaSy...your_gemini_key

# Optional: Multiple keys separated by commas for automatic rotation
GEMINI_API_KEYS=key1,key2,key3

# Optional Search API overrides (Tavily/Serper keys)
TAVILY_API_KEY=your_tavily_key
```

### 2. Set Up the Backend
Create a virtual environment (Python 3.10+ recommended) and install dependencies:
```bash
# Set up env
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install requirements
pip install -r requirements.txt
```

Launch the FastAPI backend server:
```bash
uvicorn api.server:app --host 0.0.0.0 --port 8000 --reload
```
You can verify the backend is online by navigating to `http://localhost:8000/health`.

### 3. Set Up the Frontend
Open a new terminal window, navigate to the frontend directory, install npm packages, and run Vite:
```bash
cd frontend
npm install
npm run dev
```
Open **http://localhost:5173** to access the ScholarNode AI dashboard.

---

## 🧬 Configuration Reference

Custom settings can be configured inside `.env`. Here are the primary tuning options:

| Variable | Default Value | Description |
|---|---|---|
| `GEMINI_HIGH_REASONING_MODEL` | `gemini-3.5-flash` | Used for Planning, Synthesis, and Critique steps. |
| `GEMINI_VOLUME_MODEL` | `gemini-3.1-flash-lite` | Used for high-volume claim extraction batches. |
| `MAX_SUBTOPICS` | `5` | Maximum research subtopics planned per query. |
| `MAX_ITERATIONS` | `2` | Maximum retry loops triggered by low critique scores. |
| `CONFIDENCE_THRESHOLD` | `0.65` | Minimum critique confidence required (runs retry if lower). |
| `HEAVY_PAPER_THRESHOLD` | `10` | Top-K papers retained after academic citation filtering. |
| `RAG_CHUNK_SIZE` | `800` | Token character chunking size for ChromaDB report indexing. |
| `RAG_TOP_K` | `5` | Retrieved context chunks passed to RAG chat assistant. |

---

## 📄 License
This project is licensed under the MIT License — free to use, modify, and distribute.
