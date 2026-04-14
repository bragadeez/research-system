"""api/server.py — FastAPI backend v2."""
from __future__ import annotations
import asyncio, io, json, os, re
from datetime import datetime
from typing import Dict, Optional

from fastapi import BackgroundTasks, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse, StreamingResponse
from pydantic import BaseModel

import db.database as db
from config import settings
from orchestrator.pipeline import pipeline

# ── python-docx: check once at startup ───────────────────────────────────────
try:
    from docx import Document as _DocxDocument
    from docx.shared import Pt, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    DOCX_AVAILABLE = True
except ImportError:
    DOCX_AVAILABLE = False

app = FastAPI(title="Autonomous Research AI", version="2.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


# ── WebSocket manager ─────────────────────────────────────────────────────────
class ConnectionManager:
    def __init__(self):
        self._ws: Dict[str, WebSocket] = {}
        self._queues: Dict[str, asyncio.Queue] = {}

    def make_queue(self, sid: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self._queues[sid] = q
        return q

    async def connect(self, sid: str, ws: WebSocket):
        await ws.accept()
        self._ws[sid] = ws

    def disconnect(self, sid: str):
        self._ws.pop(sid, None)

    async def send(self, sid: str, data: dict):
        q = self._queues.get(sid)
        if q:
            await q.put(data)
        ws = self._ws.get(sid)
        if ws:
            try:
                await ws.send_text(json.dumps(data, default=str))
            except Exception:
                self.disconnect(sid)

    async def close_queue(self, sid: str):
        q = self._queues.get(sid)
        if q:
            await q.put({"__done__": True})


manager = ConnectionManager()


class ResearchRequest(BaseModel):
    topic: str


# ── Background pipeline ───────────────────────────────────────────────────────
async def _run_pipeline(session_id: str, topic: str):
    async def callback(update: dict):
        db.log_progress(session_id, update.get("agent","system"),
                        update.get("message",""), update.get("data",{}))
        await manager.send(session_id, update)
    try:
        state = await pipeline.run(topic, session_id=session_id, progress_callback=callback)
        fact_checks = [fc.model_dump() for fc in state.critique.fact_checks] if state.critique else []
        db.save_report(session_id, state.report,
                       state.critique.critique if state.critique else "", fact_checks)
        db.update_session(session_id, "complete",
                          confidence=state.critique.confidence_score if state.critique else 0.0,
                          findings=len(state.findings),
                          sources=len(state.ranked_sources))
        await callback({"agent":"system","message":"🎉 Research complete!","data": state.to_summary()})
    except Exception as e:
        db.update_session(session_id, "error")
        db.log_progress(session_id, "system", f"❌ Fatal: {e}", {})
        await manager.send(session_id, {"agent":"system","message":f"❌ Fatal: {e}","data":{}})
    finally:
        await manager.close_queue(session_id)


# ── REST endpoints ────────────────────────────────────────────────────────────
@app.get("/health")
async def health():
    return {"status": "ok", "time": datetime.utcnow().isoformat(), "docx": DOCX_AVAILABLE}


@app.post("/api/research")
async def start_research(req: ResearchRequest, bg: BackgroundTasks):
    if not req.topic.strip():
        raise HTTPException(400, "Topic cannot be empty")
    sid = db.create_session(req.topic.strip())
    manager.make_queue(sid)
    bg.add_task(_run_pipeline, sid, req.topic.strip())
    return {"session_id": sid, "status": "running"}


@app.post("/api/research/{session_id}/continue")
async def continue_research(session_id: str, bg: BackgroundTasks):
    session = db.get_session(session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    db.update_session(session_id, "running")
    manager.make_queue(session_id)
    bg.add_task(_run_pipeline, session_id, session["topic"])
    return {"session_id": session_id, "status": "running"}


@app.get("/api/research/{session_id}")
async def get_research(session_id: str):
    session = db.get_session(session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    return {"session": session, "report": db.get_report(session_id),
            "progress": db.get_progress(session_id)}


@app.get("/api/sessions")
async def list_sessions(limit: int = 50):
    return {"sessions": db.list_sessions(limit)}


@app.delete("/api/sessions/{session_id}")
async def delete_session(session_id: str):
    if not db.get_session(session_id):
        raise HTTPException(404, "Session not found")
    db.delete_session(session_id)
    return {"deleted": session_id}


@app.get("/api/export/{session_id}/md")
async def export_markdown(session_id: str):
    session = db.get_session(session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    report = db.get_report(session_id)
    if not report:
        raise HTTPException(404, "Report not found")
    conf = session.get("confidence") or 0.0
    content = (f"# {session['topic']}\n\n"
               f"**Generated:** {session['created_at']}  |  **Confidence:** {conf:.0%}\n\n---\n\n"
               + report["content"])
    os.makedirs(settings.EXPORT_PATH, exist_ok=True)
    slug = re.sub(r"[^\w-]", "_", session["topic"][:40])
    with open(f"{settings.EXPORT_PATH}/{slug}_{session_id[:8]}.md", "w", encoding="utf-8") as f:
        f.write(content)
    return PlainTextResponse(content, media_type="text/markdown")


@app.get("/api/export/{session_id}/docx")
async def export_docx(session_id: str):
    if not DOCX_AVAILABLE:
        raise HTTPException(503,
            detail="python-docx not installed. Run: pip install python-docx && restart the server")

    session = db.get_session(session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    report = db.get_report(session_id)
    if not report:
        raise HTTPException(404, "Report not found")

    conf = session.get("confidence") or 0.0
    content = report["content"]
    topic = session["topic"]
    created = session["created_at"][:10]

    try:
        doc = _DocxDocument()

        # ── Document style ────────────────────────────────────────────────────
        normal = doc.styles["Normal"]
        normal.font.name = "Calibri"
        normal.font.size = Pt(11)

        # ── Title ─────────────────────────────────────────────────────────────
        title_para = doc.add_heading(topic, 0)
        if title_para.runs:
            title_para.runs[0].font.color.rgb = RGBColor(0x1A, 0x56, 0xDB)

        # ── Meta line ─────────────────────────────────────────────────────────
        meta = doc.add_paragraph()
        run = meta.add_run(f"Generated: {created}   |   Confidence Score: {conf:.0%}")
        run.font.color.rgb = RGBColor(0x6B, 0x72, 0x80)
        run.font.size = Pt(10)
        doc.add_paragraph()

        # ── Parse markdown → docx ─────────────────────────────────────────────
        for line in content.split("\n"):
            s = line.strip()
            if not s:
                continue
            if s.startswith("## "):
                doc.add_heading(s[3:], level=1)
            elif s.startswith("### "):
                doc.add_heading(s[4:], level=2)
            elif s.startswith("#### "):
                doc.add_heading(s[5:], level=3)
            elif s.startswith(("- ", "* ")):
                doc.add_paragraph(s[2:], style="List Bullet")
            elif s.startswith("---"):
                pass  # skip horizontal rules
            else:
                # Handle inline **bold**
                p = doc.add_paragraph()
                parts = re.split(r"\*\*(.+?)\*\*", s)
                for idx, part in enumerate(parts):
                    if part:
                        r = p.add_run(part)
                        if idx % 2 == 1:
                            r.bold = True

        # ── Fact checks table ─────────────────────────────────────────────────
        fact_checks = report.get("fact_checks") or []
        if fact_checks:
            doc.add_heading("Quality Assessment — Fact Checks", level=1)
            table = doc.add_table(rows=1, cols=3)
            table.style = "Table Grid"
            hdr_cells = table.rows[0].cells
            for cell, txt in zip(hdr_cells, ["Claim", "Verdict", "Evidence"]):
                cell.text = txt
                if cell.paragraphs[0].runs:
                    cell.paragraphs[0].runs[0].bold = True

            for fc in fact_checks:
                row = table.add_row().cells
                row[0].text = str(fc.get("claim", ""))[:120]
                row[1].text = str(fc.get("verdict", ""))
                row[2].text = str(fc.get("evidence", ""))[:150]

        # ── Serialize ─────────────────────────────────────────────────────────
        buf = io.BytesIO()
        doc.save(buf)
        buf.seek(0)

    except Exception as e:
        raise HTTPException(500, f"Word generation failed: {e}")

    os.makedirs(settings.EXPORT_PATH, exist_ok=True)
    slug = re.sub(r"[^\w-]", "_", topic[:40])
    fname = f"{settings.EXPORT_PATH}/{slug}_{session_id[:8]}.docx"
    with open(fname, "wb") as f:
        f.write(buf.getvalue())
    buf.seek(0)

    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{slug}_{session_id[:8]}.docx"'},
    )


# ── WebSocket ─────────────────────────────────────────────────────────────────
@app.websocket("/ws/{session_id}")
async def ws_endpoint(ws: WebSocket, session_id: str):
    await manager.connect(session_id, ws)
    try:
        for entry in db.get_progress(session_id):
            await ws.send_text(json.dumps({
                "agent": entry["agent"], "message": entry["message"], "data": entry["data"],
            }, default=str))
        q = manager._queues.get(session_id)
        if q:
            while True:
                try:
                    item = await asyncio.wait_for(q.get(), timeout=90.0)
                    if item.get("__done__"):
                        break
                    await ws.send_text(json.dumps(item, default=str))
                except asyncio.TimeoutError:
                    sess = db.get_session(session_id)
                    if sess and sess["status"] != "running":
                        break
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(session_id)
