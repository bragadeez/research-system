"""
frontend/app.py — Autonomous Research AI  (v3 — real-time, zero lag)

Key fix: @st.fragment(run_every=2) isolates the progress section.
Only that fragment rerenders every 2 s — the rest of the page stays static.
This eliminates the full-page-rerender lag completely.

Also fixed: HTML rendering bug (fact-checks now use native st components,
not raw HTML strings inside st.markdown).
"""
import time
import requests
import streamlit as st
from datetime import datetime

# ─────────────────────────────────────────────────────────────────────────────
st.set_page_config(page_title="Research AI", page_icon="🔬",
                   layout="wide", initial_sidebar_state="expanded")

st.markdown("""<style>
[data-testid="stAppViewContainer"]  { background:#0d1117; }
[data-testid="stSidebar"]           { background:#161b22; border-right:1px solid #21262d; }

/* Stage bar */
.stages { display:flex; gap:0; margin:4px 0 12px; }
.stage  { flex:1; text-align:center; padding:8px 2px; font-size:0.72rem;
          border-top:2px solid #21262d; color:#6b7280; }
.stage.done   { border-top-color:#4ade80; color:#4ade80; }
.stage.active { border-top-color:#7c3aed; color:#a78bfa; font-weight:700;
                animation:pulse 1.4s ease-in-out infinite; }
@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.6} }

/* Log */
.logbox { background:#0d1117; border-radius:8px; padding:12px 14px;
          font-family:monospace; font-size:0.78rem; max-height:260px;
          overflow-y:auto; border:1px solid #21262d; }
.le     { padding:2px 0 2px 10px; margin:1px 0; color:#c9d1d9;
          border-left:2px solid #30363d; }
.le.planner    { border-left-color:#a78bfa; }
.le.search     { border-left-color:#60a5fa; }
.le.extraction { border-left-color:#22d3ee; }
.le.aggregator { border-left-color:#4ade80; }
.le.synthesis  { border-left-color:#34d399; }
.le.critic     { border-left-color:#fbbf24; }
.le.ranker     { border-left-color:#c084fc; }
.le.system     { border-left-color:#4b5563; color:#6b7280; }

/* Conf bar */
.cbar-wrap { display:flex; align-items:center; gap:10px; margin:6px 0; }
.cbar      { flex:1; height:5px; background:#21262d; border-radius:3px; overflow:hidden; }
.cfill     { height:100%; border-radius:3px; }

/* Sug cards */
.scard { background:#161b22; border:1px solid #30363d; border-radius:10px;
         padding:10px 14px; font-size:0.82rem; color:#c9d1d9;
         cursor:pointer; transition:.15s; }
.scard:hover { border-color:#7c3aed; background:#1e1b4b; color:#a78bfa; }

/* FC rows */
.fc-row { display:flex; gap:10px; padding:7px 0;
          border-bottom:1px solid #21262d; align-items:flex-start; }
.fc-row:last-child { border-bottom:none; }
.fc-badge { flex-shrink:0; padding:2px 8px; border-radius:12px;
            font-size:0.72rem; font-weight:600; }
.sup   { background:#052e16; color:#4ade80; }
.unsup { background:#450a0a; color:#f87171; }
.unc   { background:#431407; color:#fb923c; }

#MainMenu,footer,header{visibility:hidden}
[data-testid="stToolbar"]{display:none}
</style>""", unsafe_allow_html=True)

API = "http://localhost:8000"

SUGGESTIONS = [
    ("🧬", "mRNA cancer vaccine latest advances"),
    ("🤖", "Multi-agent AI systems architectures"),
    ("🌿", "Climate change impact on food security"),
    ("⚛️",  "Quantum error correction breakthroughs"),
    ("🧠", "LLM alignment techniques: RLHF vs DPO"),
    ("💊", "CRISPR gene therapy clinical trials 2024"),
    ("🔋", "Solid-state battery technology progress"),
    ("🛰️", "Vision transformers in remote sensing"),
]

STAGE_NAMES = ["Plan","Search","Extract","Rank","Write","Critique"]
STAGE_ICONS = ["🧠","🔍","🔬","📊","📝","✅"]
STATUS_STAGE = {"planning":0,"searching":1,"extracting":2,
                "synthesizing":4,"validating":5,"complete":6}


# ── Helpers ───────────────────────────────────────────────────────────────────
def api(path, default=None):
    try:
        r = requests.get(f"{API}{path}", timeout=8)
        return r.json() if r.ok else default
    except Exception:
        return default

def post(path, data=None):
    try:
        r = requests.post(f"{API}{path}", json=data or {}, timeout=12)
        return r.json() if r.ok else None
    except Exception:
        return None

def delete(path):
    try:
        return requests.delete(f"{API}{path}", timeout=8).ok
    except Exception:
        return False

def ts(iso):
    try:
        return datetime.fromisoformat(iso).strftime("%b %d  %H:%M")
    except Exception:
        return iso

def conf_color(c):
    if not c: return "#6b7280"
    return "#4ade80" if c >= 0.75 else ("#fbbf24" if c >= 0.55 else "#f87171")

def conf_label(c):
    if c >= 0.8: return "High"
    if c >= 0.65: return "Good"
    if c >= 0.5: return "Fair"
    return "Low"

def stage_bar_html(status):
    idx  = STATUS_STAGE.get(status, -1)
    done = status == "complete"
    items = ""
    for i,(icon,name) in enumerate(zip(STAGE_ICONS, STAGE_NAMES)):
        cls = "done" if (done or i < idx) else ("active" if i == idx else "")
        items += f'<div class="stage {cls}">{icon}<br>{name}</div>'
    return f'<div class="stages">{items}</div>'

def log_html(entries):
    rows = ""
    for e in entries[-30:]:
        ag  = e.get("agent","system")
        msg = e.get("message","").replace("<","&lt;").replace(">","&gt;")
        rows += f'<div class="le {ag}">{msg}</div>'
    return f'<div class="logbox">{rows}</div>'

def conf_bar_html(c):
    pct   = int(c * 100)
    color = conf_color(c)
    return (f'<div class="cbar-wrap">'
            f'<span style="font-size:.78rem;color:#8b949e;min-width:70px">Confidence</span>'
            f'<div class="cbar"><div class="cfill" style="width:{pct}%;background:{color}"></div></div>'
            f'<span style="font-size:.9rem;font-weight:700;color:{color}">{pct}%</span>'
            f'<span style="font-size:.72rem;color:{color};font-weight:600"> {conf_label(c)}</span>'
            f'</div>')

def status_pill(status):
    colors = {"complete":"#052e16:#4ade80","running":"#1e3a5f:#60a5fa","error":"#450a0a:#f87171"}
    bg,fg  = colors.get(status,"#21262d:#c9d1d9").split(":")
    icons  = {"complete":"✅","running":"🔄","error":"❌"}
    return (f'<span style="background:{bg};color:{fg};padding:4px 12px;'
            f'border-radius:20px;font-size:.8rem;font-weight:600">'
            f'{icons.get(status,"⏳")} {status.title()}</span>')


# ════════════════════════════════════════════════════════════════════════════
# LIVE FRAGMENT — only this block auto-rerenders every 2 seconds
# ════════════════════════════════════════════════════════════════════════════
@st.fragment(run_every=2)
def live_research():
    sid = st.session_state.get("active_sid")
    if not sid:
        # Empty state — show how-it-works cards
        st.markdown('<p style="color:#8b949e;font-size:.85rem">How it works</p>',
                    unsafe_allow_html=True)
        cols = st.columns(6)
        for col, (icon, name) in zip(cols, zip(STAGE_ICONS, STAGE_NAMES)):
            descs = ["Breaks query into sub-tasks","DDG + arXiv + Semantic Scholar",
                     "Batched GLM extraction","Credibility scoring","RAG-enhanced report","Fact-check + score"]
            col.markdown(
                f'<div class="scard" style="text-align:center;cursor:default">'
                f'<div style="font-size:1.4rem">{icon}</div>'
                f'<div style="font-weight:700;font-size:.8rem;margin:4px 0">{name}</div>'
                f'<div style="font-size:.7rem;color:#6b7280">{descs[STAGE_ICONS.index(icon)]}</div>'
                f'</div>', unsafe_allow_html=True)
        return

    # ── Fetch latest data ──────────────────────────────────────────────────
    data     = api(f"/api/research/{sid}", {})
    session  = data.get("session", {})
    report   = data.get("report")
    progress = data.get("progress", [])
    status   = session.get("status", "running")
    conf     = session.get("confidence") or 0.0

    topic    = st.session_state.get("active_topic", session.get("topic","Research"))

    # ── Progress card ──────────────────────────────────────────────────────
    st.markdown(
        f'<div style="background:#161b22;border:1px solid #21262d;border-radius:14px;padding:18px 22px">'
        f'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">'
        f'<div><div style="font-size:1rem;font-weight:700;color:#e6edf3">{topic[:80]}</div>'
        f'<div style="font-size:.75rem;color:#6b7280;margin-top:2px">Session: {sid[:8]}…</div></div>'
        f'{status_pill(status)}</div>'
        f'{stage_bar_html(status)}'
        f'</div>', unsafe_allow_html=True)

    # ── Metrics ────────────────────────────────────────────────────────────
    c1,c2,c3,c4 = st.columns(4)
    c1.metric("Sources",   session.get("sources")  or "—")
    c2.metric("Findings",  session.get("findings") or "—")
    c3.metric("Log lines", len(progress))
    c4.metric("Status",    status.title())

    # ── Confidence bar (only when we have one) ─────────────────────────────
    if conf > 0:
        st.markdown(conf_bar_html(conf), unsafe_allow_html=True)

    # ── Live log ───────────────────────────────────────────────────────────
    log_expanded = st.session_state.get("log_open", True)
    tog_label = "▼ Hide log" if log_expanded else "▶ Show log"
    if st.button(tog_label, key="tog_log"):
        st.session_state["log_open"] = not log_expanded
        st.rerun()

    if log_expanded and progress:
        st.markdown(log_html(progress), unsafe_allow_html=True)

    # ── Complete: show report ──────────────────────────────────────────────
    if status == "complete" and report:
        st.success(f"🎉 Research complete! Confidence: **{conf:.0%}**")

        # Download + action buttons
        b1,b2,b3,b4 = st.columns([1,1,1,2])
        with b1:
            md_resp = requests.get(f"{API}/api/export/{sid}/md", timeout=15)
            if md_resp.ok:
                st.download_button("📥 Markdown", md_resp.text,
                                   f"report_{sid[:8]}.md", "text/markdown",
                                   use_container_width=True)
        with b2:
            dcx = requests.get(f"{API}/api/export/{sid}/docx", timeout=30)
            if dcx.ok:
                st.download_button("📄 Word (.docx)", dcx.content,
                                   f"report_{sid[:8]}.docx",
                                   "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                                   use_container_width=True)
            else:
                st.caption("docx: run `pip install python-docx`")
        with b3:
            if st.button("🔄 Continue", use_container_width=True,
                         help="Run more targeted follow-up searches to improve confidence"):
                r = post(f"/api/research/{sid}/continue")
                if r:
                    st.session_state["log_open"] = True
                    st.rerun()
        with b4:
            if st.button("✖ Clear", use_container_width=True):
                del st.session_state["active_sid"]
                st.session_state.pop("active_topic", None)
                st.rerun()

        # ── LLM Evaluation panel (native Streamlit — NO raw HTML rendering) ──
        fc_list = report.get("fact_checks") or []
        crit    = report.get("critique","")
        if fc_list or crit:
            with st.expander(f"🔬 LLM Evaluation — {len(fc_list)} claims fact-checked", expanded=False):
                if crit:
                    st.info(f"**Critic assessment:** {crit}")
                if fc_list:
                    # Native Streamlit rendering — no HTML bugs
                    verdict_icons = {"supported":"✅","unsupported":"❌","uncertain":"❓"}
                    verdict_colors = {"supported":"🟢","unsupported":"🔴","uncertain":"🟡"}
                    for fc in fc_list:
                        v    = fc.get("verdict","uncertain")
                        icon = verdict_icons.get(v,"❓")
                        col1, col2 = st.columns([1, 5])
                        with col1:
                            st.markdown(f"**{icon} {v}**")
                        with col2:
                            st.markdown(f"_{fc.get('claim','')[:150]}_")
                            if fc.get("evidence"):
                                st.caption(fc["evidence"])
                        st.divider()

                    # Summary stats
                    s = sum(1 for f in fc_list if f.get("verdict")=="supported")
                    u = sum(1 for f in fc_list if f.get("verdict")=="unsupported")
                    n = sum(1 for f in fc_list if f.get("verdict")=="uncertain")
                    sc1,sc2,sc3 = st.columns(3)
                    sc1.metric("✅ Supported",   s)
                    sc2.metric("❌ Unsupported", u)
                    sc3.metric("❓ Uncertain",   n)

        # ── Report body ────────────────────────────────────────────────────
        st.divider()
        st.markdown(report["content"])

    elif status == "error":
        st.error("Pipeline error — check the log above for details.")
        if st.button("✖ Clear session"):
            del st.session_state["active_sid"]
            st.rerun()


# ════════════════════════════════════════════════════════════════════════════
# SIDEBAR
# ════════════════════════════════════════════════════════════════════════════
health_data = api("/health", {})
health_ok   = bool(health_data)
all_sessions_data = api("/api/sessions?limit=100", {"sessions":[]})
all_sessions      = (all_sessions_data or {}).get("sessions", [])
done_sessions     = [s for s in all_sessions if s["status"] == "complete"]

with st.sidebar:
    st.markdown("## 🔬 Research AI")
    if health_ok:
        st.success("🟢 API online")
        if not health_data.get("docx", True):
            st.warning("⚠️ Word export: `pip install python-docx`")
    else:
        st.error("🔴 API offline — run `./run.sh`")
    st.divider()
    c1,c2 = st.columns(2)
    c1.metric("Sessions", len(all_sessions))
    c2.metric("Done", len(done_sessions))
    st.divider()
    st.markdown("""**Stack**
- 🤖 Gemini 2.5 Flash
- 🦙 Ollama GLM (batched)
- 🔍 DDG + arXiv + S2
- 🧠 ChromaDB + BGE""")
    st.caption("🆓 Zero cost · Local · Private")


# ════════════════════════════════════════════════════════════════════════════
# TABS
# ════════════════════════════════════════════════════════════════════════════
tab1, tab2, tab3 = st.tabs(["🔬 Research", "📚 History", "📄 Report Viewer"])


# ════ TAB 1 ══════════════════════════════════════════════════════════════════
with tab1:
    # Hero
    st.markdown(
        '<p style="font-size:2.4rem;font-weight:800;background:linear-gradient(135deg,#7c3aed,#2563eb,#059669);'
        '-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;margin:0">'
        'Autonomous Research AI</p>'
        '<p style="color:#8b949e;margin-top:4px;margin-bottom:1.5rem">Ask anything. Get a full cited research report.</p>',
        unsafe_allow_html=True)

    # Suggestion cards — clicking sets session_state prefill
    st.markdown('<p style="color:#8b949e;font-size:.8rem">Suggested topics</p>', unsafe_allow_html=True)
    sg_cols = st.columns(4)
    for i, (icon, sug) in enumerate(SUGGESTIONS):
        with sg_cols[i % 4]:
            label = f"{icon} {sug[:32]}…" if len(sug) > 32 else f"{icon} {sug}"
            if st.button(label, key=f"sg{i}", use_container_width=True):
                st.session_state["topic_prefill"] = sug
                st.rerun()

    st.markdown("")

    # Input
    topic_val = st.session_state.pop("topic_prefill", "")
    topic_in  = st.text_area("Topic", value=topic_val,
                              placeholder="e.g. 'Latest advances in quantum error correction'",
                              height=80, label_visibility="collapsed")

    btn1, btn2, _ = st.columns([1,1,5])
    with btn1:
        go = st.button("🚀 Start Research", type="primary",
                       use_container_width=True, disabled=not health_ok)
    with btn2:
        latest_done = next((s for s in all_sessions if s["status"]=="complete"), None)
        cont = st.button("🔄 Continue Research", use_container_width=True,
                         disabled=(not health_ok or not latest_done),
                         help="Improve confidence of the most recent report")

    if go and topic_in.strip():
        resp = post("/api/research", {"topic": topic_in.strip()})
        if resp and resp.get("session_id"):
            st.session_state["active_sid"]   = resp["session_id"]
            st.session_state["active_topic"] = topic_in.strip()
            st.session_state["log_open"]     = True
            st.rerun()
        else:
            st.error("Failed to start — is the API running?")
    elif go:
        st.warning("Enter a topic first.")

    if cont and latest_done:
        r = post(f"/api/research/{latest_done['id']}/continue")
        if r:
            st.session_state["active_sid"]   = latest_done["id"]
            st.session_state["active_topic"] = latest_done["topic"]
            st.session_state["log_open"]     = True
            st.rerun()

    st.divider()

    # ── Live fragment (auto-refreshes every 2 s, rest of page stays still) ──
    live_research()


# ════ TAB 2 ══════════════════════════════════════════════════════════════════
with tab2:
    st.markdown("## 📚 Research History")
    if not all_sessions:
        st.info("No sessions yet.")
    else:
        flt = st.selectbox("Filter", ["All","complete","running","error"],
                           label_visibility="collapsed")
        shown = all_sessions if flt == "All" else [s for s in all_sessions if s["status"]==flt]
        st.caption(f"{len(shown)} sessions")

        for s in shown:
            conf = s.get("confidence") or 0
            icon = {"complete":"✅","running":"🔄","error":"❌"}.get(s["status"],"⏳")
            with st.expander(f"{icon} {s['topic'][:60]}   ·   {ts(s['created_at'])}", expanded=False):
                m1,m2,m3,m4 = st.columns(4)
                m1.metric("Status",     s["status"].title())
                m2.metric("Confidence", f"{conf:.0%}" if conf else "—")
                m3.metric("Findings",   s.get("findings") or "—")
                m4.metric("Sources",    s.get("sources")  or "—")
                b1,b2,b3,_ = st.columns([1,1,1,4])
                if b1.button("📄 View", key=f"v_{s['id']}"):
                    st.session_state["viewer_sid"] = s["id"]
                if b2.button("🔄 Re-run", key=f"r_{s['id']}"):
                    r2 = post(f"/api/research/{s['id']}/continue")
                    if r2:
                        st.session_state.update({"active_sid":s["id"],"active_topic":s["topic"],"log_open":True})
                        st.rerun()
                if b3.button("🗑️ Delete", key=f"d_{s['id']}"):
                    if delete(f"/api/sessions/{s['id']}"):
                        time.sleep(0.2); st.rerun()


# ════ TAB 3 ══════════════════════════════════════════════════════════════════
with tab3:
    st.markdown("## 📄 Report Viewer")
    if not done_sessions:
        st.info("No completed reports yet.")
    else:
        opts = {f"{s['topic'][:60]}  ({ts(s['created_at'])})": s["id"] for s in done_sessions}
        default = None
        if "viewer_sid" in st.session_state:
            for k,v in opts.items():
                if v == st.session_state["viewer_sid"]:
                    default = k; break

        sel = st.selectbox("Report", list(opts.keys()),
                           index=list(opts.keys()).index(default) if default else 0)
        sid = opts[sel]
        d   = api(f"/api/research/{sid}", {})
        ses = d.get("session", {})
        rep = d.get("report")

        if rep:
            conf = ses.get("confidence") or 0.0
            m1,m2,m3,m4 = st.columns(4)
            m1.metric("Confidence", f"{conf:.0%}", delta=conf_label(conf))
            m2.metric("Findings",   ses.get("findings") or "—")
            m3.metric("Sources",    ses.get("sources")  or "—")
            m4.metric("Words",      rep.get("word_count") or "—")

            st.markdown(conf_bar_html(conf), unsafe_allow_html=True)

            dl1, dl2, _ = st.columns([1,1,5])
            with dl1:
                mdr = requests.get(f"{API}/api/export/{sid}/md", timeout=15)
                if mdr.ok:
                    st.download_button("📥 Markdown", mdr.text,
                                       f"report_{sid[:8]}.md","text/markdown",
                                       use_container_width=True)
            with dl2:
                dxr = requests.get(f"{API}/api/export/{sid}/docx", timeout=30)
                if dxr.ok:
                    st.download_button("📄 Word (.docx)", dxr.content,
                                       f"report_{sid[:8]}.docx",
                                       "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                                       use_container_width=True)

            st.divider()

            # ── Evaluation panel (native components — no HTML rendering bug) ──
            with st.expander("🔬 LLM Evaluation & Methodology", expanded=True):
                st.markdown("""**How confidence is measured**

After writing the report a dedicated **Critic Agent** (Gemini 2.5 Flash) reviews it 
independently. It extracts key factual claims, checks each against the evidence pool, 
assigns a verdict, and computes a 0–100% confidence score.
> ≥ 75% = most claims supported by ≥2 independent sources""")

                st.markdown(conf_bar_html(conf), unsafe_allow_html=True)

                crit = rep.get("critique","")
                if crit:
                    st.info(f"**Critic summary:** {crit}")

                fc_list = rep.get("fact_checks") or []
                if fc_list:
                    st.markdown(f"**{len(fc_list)} claims verified:**")
                    verdict_icons  = {"supported":"✅","unsupported":"❌","uncertain":"❓"}
                    for fc in fc_list:
                        v    = fc.get("verdict","uncertain")
                        icon = verdict_icons.get(v,"❓")
                        c1,c2 = st.columns([1,5])
                        c1.markdown(f"**{icon} {v}**")
                        c2.markdown(f"_{fc.get('claim','')[:150]}_")
                        if fc.get("evidence"):
                            c2.caption(fc["evidence"])
                        st.divider()

                    s = sum(1 for f in fc_list if f.get("verdict")=="supported")
                    u = sum(1 for f in fc_list if f.get("verdict")=="unsupported")
                    n = sum(1 for f in fc_list if f.get("verdict")=="uncertain")
                    sc1,sc2,sc3 = st.columns(3)
                    sc1.metric("✅ Supported",   s)
                    sc2.metric("❌ Unsupported", u)
                    sc3.metric("❓ Uncertain",   n)

            st.divider()
            st.markdown(rep["content"])
        else:
            st.warning("Report not available.")
