# 🎓 ScholarNode AI

> A premium, multi-agent AI research pipeline that transforms any query into a fully cited, structured, and fact-checked research report in minutes. Built for 100% free cloud operation using Google's Gemini models with automatic key rotation and fallback capability.

ScholarNode AI features a **React + Vite + TypeScript** dashboard, real-time progress visualization via WebSockets, SQLite database persistence, and flexible export/import options (Word, Markdown, and Session JSON).

---

## 🚀 Key Features

* **Dual-tier Gemini Pipeline**:
  * **High-Reasoning Tasks** (Planning, Synthesis, Critique): Handled by `gemini-3.5-flash` for high schema compliance and detailed reports.
  * **High-Volume Tasks** (Evidence Extraction): Handled by `gemini-3.1-flash-lite` (500 RPD / 15 RPM) to absorb extensive page-scraping extraction batches.
* **Option B Quota Fallback**: If the strict daily limit (20 RPD) of `gemini-3.5-flash` is exhausted across your keys, the backend automatically falls back to `gemini-3.1-flash-lite` without crashing the active run.
* **API Key Rotator**: Thread-safely rotates between multiple API keys in `GEMINI_API_KEYS` to scale past single-key request limits.
* **Multi-Source Scraping**: Searches and aggregates findings from DuckDuckGo, arXiv, Semantic Scholar, and Wikipedia.
* **Inline Citations & Quality Audits**: Merges claims across sources using embeddings, formats proper markdown citations, and fact-checks report claims with a Critique/Critic agent.
* **Persistent Sessions**: History and reports are saved to a local SQLite database that persists across restarts.
* **Session Import/Export**: Save any session as a JSON data file, and import it into another ScholarNode instance to review history, inspect evaluation metrics, and download Word/Markdown documents.

---

## 🛠️ Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                       Vite + React UI (port 5173)                   │
│        Hero Search · Suggestion Chips · WebSocket Progress Tracker  │
│        Report Viewer · LLM Evaluation Dashboard · Import / Export    │
└─────────────────────────┬───────────────────────────────────────────┘
                          │  HTTP / WebSockets
┌─────────────────────────▼───────────────────────────────────────────┐
│                      FastAPI Backend (port 8000)                     │
│          POST /api/research · GET /api/export/{id}/{format}         │
│          POST /api/import   · WebSocket /ws/{id}                    │
└─────────────────────────┬───────────────────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────────────────┐
│                    Research Pipeline (orchestrator)                  │
│                                                                      │
│  Planner → Search → Source Ranker → Extractor → Aggregator          │
│     ↓         ↓           ↓             ↓            ↓              │
│  Gemini    DDG, arXiv     Intent   Gemini 3.1 Lite  Semantic        │
│  3.5/3.1   S2, Wiki      scoring     (batched)      clustering      │
│                                                                     │
│                                                                     │
│         Synthesiser ──────────────────────────► Critic Agent        │
│         Gemini 3.5 / 3.1                        Gemini 3.5 / 3.1    │
│         (Structured draft)                      (Fact-checking)     │
│                            │                                        │
│                            ▼                                        │
│                    SQLite (data/research.db)                        │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 📦 Project Directory Layout

```
scholarnode-ai/
├── agents/                     # The AI agents coordinating stages
│   ├── planner_agent.py        # Decomposes queries into structured subtopics
│   ├── search_agent.py         # Performs parallel academic and web searches
│   ├── extraction_agent.py     # Batches paragraphs for factual claim extraction
│   ├── synthesis_agent.py      # Drafts the final report with citations
│   └── critic_agent.py         # Fact-checks and evaluates report confidence
├── api/
│   └── server.py               # FastAPI server (lifespan startup, CORS, DOCX generation)
├── core/
│   ├── llm_client.py           # GeminiClient (API rotation & fallback), Groq client (optional)
│   ├── source_ranker.py        # Intent-prior domain scoring & ranking
│   └── evidence_aggregator.py  # Cluster evidence evidence & contradictions using embeddings
├── db/
│   └── database.py             # SQLite persistence layer (sessions, reports, logs)
├── frontend/                   # React + Vite + TS Frontend
│   ├── src/
│   │   ├── api/client.ts       # Frontend REST client & WebSocket connectors
│   │   ├── App.tsx             # Interactive dashboard
│   │   ├── index.css           # Styling system
│   │   └── main.tsx            # React application entry point
│   ├── package.json
│   └── vite.config.ts
├── models/                     # Shared Pydantic data schemas
├── tools/                      # Utilities for normalisation, scraping, and searching
├── .env.example                # Configuration template
├── config.py                   # Pydantic Settings management
├── main.py                     # CLI researcher mode
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
GEMINI_API_KEYS=key1,key2

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

## 🧬 How to Export / Import Reports
To transfer a report generated on one system to another:
1. Open the report in the **Report Viewer** or **Research History** tab.
2. Click the **JSON Data** download button. A `.json` file containing the session, report contents, and full log logs will download.
3. On another system running ScholarNode AI, click the **Import Session** button (on the History tab) or **Import Report** button (on the Viewer tab) and select the `.json` file.
4. The report, evaluation logs, and full agent logs will be immediately populated and editable.

---

## 📄 License
This project is licensed under the MIT License — free to use, modify, and distribute.
