#!/usr/bin/env bash
# ── Autonomous Research AI v2 ── launcher ──────────────────────────────────
set -e
cd "$(dirname "$0")"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'
RED='\033[0;31m'; BOLD='\033[1m'; RESET='\033[0m'

echo ""
echo -e "${CYAN}${BOLD}  🔬 Autonomous Research AI v2${RESET}"
echo -e "${CYAN}  ── Plan → Search → Extract → Synthesise → Critique ──${RESET}"
echo ""

# ── Check .env ─────────────────────────────────────────────────────────────
if [ ! -f ".env" ]; then
    echo -e "${YELLOW}⚠️  .env not found. Copying from .env.example...${RESET}"
    cp .env.example .env
    echo -e "${RED}❗ Edit .env and set GOOGLE_API_KEY before running.${RESET}"
    echo -e "   Get a free key: ${CYAN}https://aistudio.google.com/app/apikey${RESET}"
    exit 1
fi

source .env
if [[ "$GEMINI_API_KEY" == "your_gemini_api_key_here" || -z "$GEMINI_API_KEY" ]]; then
    echo -e "${RED}❗ GEMINI_API_KEY not set in .env${RESET}"
    exit 1
fi

# ── Virtualenv ─────────────────────────────────────────────────────────────
if [ ! -d "venv" ]; then
    echo -e "${GREEN}📦 Creating virtual environment...${RESET}"
    python3 -m venv venv
fi
source venv/bin/activate

# ── Install ─────────────────────────────────────────────────────────────────
if ! python -c "import fastapi" 2>/dev/null; then
    echo -e "${GREEN}📦 Installing dependencies...${RESET}"
    pip install -q --upgrade pip
    pip install -q -r requirements.txt
    echo -e "${GREEN}✅ Dependencies installed${RESET}"
fi

mkdir -p data exports

# ── Ollama check ────────────────────────────────────────────────────────────
if command -v ollama &>/dev/null; then
    MODEL="${OLLAMA_MODEL:-glm4}"
    echo -e "${GREEN}🦙 Ollama found. Checking model: ${MODEL}...${RESET}"
    if ollama list 2>/dev/null | grep -q "$MODEL"; then
        echo -e "${GREEN}   ✅ ${MODEL} is ready${RESET}"
    else
        echo -e "${YELLOW}   ⚠️  ${MODEL} not pulled yet. Run: ollama pull ${MODEL}${RESET}"
        echo -e "   For cloud: ollama signin && ollama pull glm-5:cloud"
    fi
else
    echo -e "${YELLOW}ℹ️  Ollama not found — heuristic extraction will be used.${RESET}"
    echo -e "   Install: ${CYAN}https://ollama.com/download${RESET}"
fi

API_PORT="${API_PORT:-8000}"
STREAMLIT_PORT="${STREAMLIT_PORT:-8501}"

echo ""
echo -e "${GREEN}🚀 Starting FastAPI backend on port ${API_PORT}...${RESET}"
uvicorn api.server:app \
    --host 0.0.0.0 \
    --port "$API_PORT" \
    --reload \
    --log-level warning &
API_PID=$!

sleep 2

echo -e "${GREEN}🎨 Starting Streamlit UI on port ${STREAMLIT_PORT}...${RESET}"
streamlit run frontend/app.py \
    --server.port "$STREAMLIT_PORT" \
    --server.address 0.0.0.0 \
    --server.headless true \
    --theme.base dark \
    --theme.primaryColor "#7c3aed" \
    --theme.backgroundColor "#0d1117" \
    --theme.secondaryBackgroundColor "#161b22" \
    --theme.textColor "#e6edf3" &
UI_PID=$!

echo ""
echo -e "${CYAN}${BOLD}  ✅ All services running!${RESET}"
echo ""
echo -e "  📡 API:       ${GREEN}http://localhost:${API_PORT}${RESET}"
echo -e "  🎨 UI:        ${GREEN}http://localhost:${STREAMLIT_PORT}${RESET}"
echo -e "  📖 API docs:  ${GREEN}http://localhost:${API_PORT}/docs${RESET}"
echo ""
echo -e "  CLI: ${YELLOW}python main.py${RESET}"
echo -e "  ${RED}Ctrl+C to stop all services${RESET}"
echo ""

trap "kill $API_PID $UI_PID 2>/dev/null; echo 'Stopped.'" SIGINT SIGTERM
wait $API_PID $UI_PID