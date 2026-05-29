// src/App.tsx
import { useState, useEffect, useCallback, useRef } from "react";
import {
  FlaskConical, History, FileText, Wifi, WifiOff,
  Search, Brain, Microscope, BarChart2, PenLine, CheckCircle2,
  Loader2, CheckCheck, XCircle, HelpCircle, Download, RefreshCw,
  Trash2, ChevronDown, ChevronUp, X, Play, ArrowRight,
  Sparkles, Clock, BookOpen, Zap, Copy, ClipboardCheck
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Session, ResearchData, ProgressEntry, ChatMessage, ChatSource } from "./types";
import {
  startResearch, getResearch, listSessions, deleteSession,
  continueResearch, checkHealth, getExportUrl, createWebSocket,
  importResearch, chatWithReport, getChatHistory, clearChatHistory,
} from "./api/client";

// ─── Types ──────────────────────────────────────────────────────────────────
type Tab = "research" | "history" | "viewer";

// ─── Constants ──────────────────────────────────────────────────────────────
const STAGES = [
  { key: "planning",     icon: Brain,       label: "Plan" },
  { key: "searching",    icon: Search,      label: "Search" },
  { key: "extracting",   icon: Microscope,  label: "Extract" },
  { key: "synthesizing", icon: PenLine,     label: "Write" },
  { key: "validating",   icon: BarChart2,   label: "Critique" },
  { key: "complete",     icon: CheckCircle2,label: "Done" },
];

const STATUS_STAGE_INDEX: Record<string, number> = {
  planning: 0, searching: 1, extracting: 2,
  synthesizing: 3, validating: 4, complete: 5,
};

const SUGGESTIONS = [
  { icon: "🧬", text: "mRNA cancer vaccine latest advances" },
  { icon: "🤖", text: "Multi-agent AI systems architectures" },
];

const AGENT_COLORS: Record<string, string> = {
  planner:    "var(--accent)",
  search:     "#06b6d4",     // Cyan
  extraction: "#4ade80",     // Lime Green
  aggregator: "#fbbf24",     // Amber
  synthesis:  "var(--accent)", // Yellow-green
  critic:     "#f87171",     // Coral Red
  ranker:     "#a0a3ad",     // Dim Grey
  system:     "var(--text-muted)",
};

// ─── Helper Components ───────────────────────────────────────────────────────
function ConfidenceBar({ value }: { value: number }) {
  const pct = Math.round(value * 100);
  const label = pct >= 85 ? "Verified" : pct >= 70 ? "Credible" : pct >= 50 ? "Moderate" : "Low";
  const labelClass = pct >= 70 ? "badge-accent" : pct >= 50 ? "badge-yellow" : "badge-red";
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 12, margin: "4px 0" }}>
      <span style={{ fontSize: "0.78rem", color: "var(--text-muted)", minWidth: 86, fontWeight: 600, letterSpacing: "0.03em", textTransform: "uppercase" }}>Confidence</span>
      <div className="conf-bar-track">
        <div className="conf-bar-fill" style={{ width: `${pct}%` }} />
      </div>
      <span style={{ fontSize: "1.05rem", fontWeight: 900, color: "var(--text-primary)", minWidth: 42, textAlign: "right" }}>{pct}%</span>
      <span className={`badge ${labelClass}`} style={{ textTransform: "uppercase", fontSize: "0.68rem" }}>{label}</span>
    </div>
  );
}

function StageTracker({ status }: { status: string }) {
  const activeIdx = STATUS_STAGE_INDEX[status] ?? -1;
  const isDone = status === "complete";
  return (
    <div className="stage-tracker">
      {STAGES.map((stage, i) => {
        const Icon = stage.icon;
        const done   = isDone || i < activeIdx;
        const active = i === activeIdx && !isDone;
        return (
          <div key={stage.key} className={`stage-item ${done ? "done" : active ? "active" : ""}`}>
            <Icon size={14} style={{ display: "block", margin: "0 auto 5px", transition: "all 0.3s ease", transform: active ? "scale(1.15)" : "none" }} className={active ? "animate-pulse" : undefined} />
            {stage.label}
          </div>
        );
      })}
    </div>
  );
}

function MetricCard({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="metric-card">
      <div className="metric-value">{value ?? "—"}</div>
      <div className="metric-label">{label}</div>
    </div>
  );
}

function StatusPill({ status }: { status: string }) {
  const isRunning = ["running", "planning", "searching", "extracting", "synthesizing", "validating"].includes(status);
  const displayStatus = isRunning ? "running" : status;
  const icons: Record<string, React.ReactNode> = {
    complete: <CheckCheck size={12} />,
    running:  <Loader2 size={12} className="animate-spin" />,
    error:    <XCircle size={12} />,
  };
  const pillClass = displayStatus === "complete" ? "status-complete" : displayStatus === "error" ? "status-error" : "status-running";
  const label = isRunning
    ? (status === "running" ? "Running" : `${status.charAt(0).toUpperCase() + status.slice(1)}…`)
    : status.charAt(0).toUpperCase() + status.slice(1);
  return (
    <span className={`status-pill ${pillClass}`}>
      {icons[displayStatus]}{label}
    </span>
  );
}

function LiveLog({ entries }: { entries: ProgressEntry[] }) {
  const ref = useRef<HTMLDivElement>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (ref.current) ref.current.scrollTop = ref.current.scrollHeight;
  }, [entries]);

  const handleCopy = () => {
    const text = entries.map(e => `[${e.agent.toUpperCase()}] ${e.message}`).join("\n");
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="terminal-window">
      <div className="terminal-header" style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
          <div className="terminal-dot red" />
          <div className="terminal-dot yellow" />
          <div className="terminal-dot green" />
        </div>
        <span className="mono" style={{ fontSize: "0.7rem", color: "var(--text-muted)", fontWeight: 500, letterSpacing: "0.04em" }}>
          PIPELINE ACTIVITY LOG
        </span>
        <button
          onClick={handleCopy}
          className="btn btn-secondary btn-sm"
          style={{ padding: "3px 10px", gap: 4, fontSize: "0.7rem" }}
        >
          {copied ? <ClipboardCheck size={11} color="var(--accent)" /> : <Copy size={11} />}
          {copied ? "Copied!" : "Copy"}
        </button>
      </div>
      <div ref={ref} style={{
        fontFamily: "'JetBrains Mono', monospace", fontSize: "0.74rem",
        maxHeight: 260, overflowY: "auto", color: "#c9d2e0",
        display: "flex", flexDirection: "column", gap: 4, padding: "2px 0",
        lineHeight: 1.55,
      }}>
        {entries.length === 0 ? (
          <div style={{ color: "var(--text-muted)", padding: "16px 0", textAlign: "center", fontStyle: "italic" }}>Awaiting pipeline events…</div>
        ) : (
          entries.slice(-60).map((e, i) => (
            <div key={i} style={{
              padding: "2px 4px 2px 12px",
              borderLeft: `2px solid ${AGENT_COLORS[e.agent] ?? "var(--border-dim)"}`,
            }}>
              <span style={{ color: AGENT_COLORS[e.agent] ?? "var(--text-secondary)", fontWeight: 700, marginRight: 7, fontSize: "0.68rem", letterSpacing: "0.02em" }}>
                [{e.agent.toUpperCase()}]
              </span>
              <span style={{ color: "#b0b8c8" }}>{e.message}</span>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

function FactCheckPanel({ factChecks, critique }: { factChecks: ResearchData["report"] extends null ? never : NonNullable<ResearchData["report"]>["fact_checks"]; critique: string }) {
  const [expandedIndex, setExpandedIndex] = useState<number | null>(null);

  const icons: Record<string, React.ReactNode> = {
    supported:   <CheckCheck size={15} color="var(--accent)" />,
    unsupported: <XCircle size={15} color="#f87171" />,
    uncertain:   <HelpCircle size={15} color="#fbbf24" />,
  };
  
  const s = factChecks.filter(f => f.verdict === "supported").length;
  const u = factChecks.filter(f => f.verdict === "unsupported").length;
  const n = factChecks.filter(f => f.verdict === "uncertain").length;

  return (
    <div style={{ marginTop: 18 }}>
      {critique && (
        <div style={{
          background: "var(--accent-glow)", border: "1px solid var(--accent-muted)",
          borderRadius: "var(--radius)", padding: "16px 20px", marginBottom: 20,
          color: "#e1e3e6", fontSize: "0.9rem", lineHeight: 1.6
        }}>
          <span style={{ color: "var(--accent)", fontWeight: 800, textTransform: "uppercase", fontSize: "0.76rem", display: "block", marginBottom: 4, letterSpacing: "0.02em" }}>
            Critic Auditor Verdict
          </span>
          {critique}
        </div>
      )}
      
      <div style={{ display: "flex", gap: 12, marginBottom: 20 }}>
        {[{ label: "Supported Claims", val: s, color: "var(--accent)" }, { label: "Unsupported", val: u, color: "#f87171" }, { label: "Uncertain", val: n, color: "#fbbf24" }].map(m => (
          <div key={m.label} style={{
            flex: 1, background: "rgba(17, 18, 21, 0.4)", border: "1px solid var(--border-soft)",
            borderRadius: "var(--radius)", padding: "14px", textAlign: "center",
          }}>
            <div style={{ fontSize: "1.6rem", fontWeight: 900, color: m.color }}>{m.val}</div>
            <div style={{ fontSize: "0.74rem", color: "var(--text-secondary)", fontWeight: 500, marginTop: 2 }}>{m.label}</div>
          </div>
        ))}
      </div>
      
      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        {factChecks.map((fc, i) => {
          const isExpanded = expandedIndex === i;
          return (
            <div key={i} style={{
              background: "rgba(255, 255, 255, 0.01)", border: `1px solid ${isExpanded ? "var(--accent-muted)" : "var(--border-soft)"}`,
              borderRadius: "var(--radius)", padding: "14px 18px", transition: "all 0.2s ease"
            }}>
              <div 
                style={{ display: "flex", gap: 12, alignItems: "flex-start", cursor: fc.evidence ? "pointer" : "default" }}
                onClick={() => fc.evidence && setExpandedIndex(isExpanded ? null : i)}
              >
                <div style={{ marginTop: 2, flexShrink: 0 }}>{icons[fc.verdict]}</div>
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: "0.92rem", color: "#ffffff", fontWeight: 600, lineHeight: 1.4 }}>{fc.claim}</div>
                  <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 6 }}>
                    <span className={`badge ${fc.verdict === "supported" ? "badge-accent" : fc.verdict === "unsupported" ? "badge-red" : "badge-yellow"}`}>
                      {fc.verdict.toUpperCase()}
                    </span>
                    {fc.evidence && (
                      <span style={{ fontSize: "0.72rem", color: "var(--text-muted)", fontWeight: 500 }}>
                        {isExpanded ? "Click to hide evidence" : "Click to view raw evidence source"}
                      </span>
                    )}
                  </div>
                </div>
              </div>
              
              {isExpanded && fc.evidence && (
                <div style={{ 
                  marginTop: 12, padding: "12px 16px", background: "rgba(0,0,0,0.2)",
                  borderLeft: `2.5px solid ${fc.verdict === "supported" ? "var(--accent)" : fc.verdict === "unsupported" ? "var(--red)" : "var(--yellow)"}`,
                  borderRadius: "0 6px 6px 0", fontSize: "0.84rem", color: "var(--text-secondary)", lineHeight: 1.5,
                  animation: "slideDown 0.2s ease"
                }}>
                  <strong style={{ color: "#fff", display: "block", marginBottom: 4, fontSize: "0.78rem", textTransform: "uppercase", letterSpacing: "0.02em" }}>
                    Source Context:
                  </strong>
                  "{fc.evidence}"
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function ExportButtons({ sessionId }: { sessionId: string; report?: unknown }) {
  const downloadFile = async (format: "md" | "docx") => {
    const url = getExportUrl(sessionId, format);
    const res = await fetch(url);
    if (!res.ok) return alert(`Export failed: ${res.statusText}`);
    const blob = await res.blob();
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `report_${sessionId.slice(0, 8)}.${format}`;
    a.click();
  };

  const downloadJson = async () => {
    try {
      const res = await fetch(`http://localhost:8000/api/research/${sessionId}`);
      if (!res.ok) throw new Error("Failed to fetch session data");
      const data = await res.json();
      const a = document.createElement("a");
      a.href = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }));
      a.download = `scholarnode_session_${sessionId.slice(0, 8)}.json`;
      a.click();
    } catch (e) {
      alert(`JSON export failed: ${e}`);
    }
  };

  const btnStyle: React.CSSProperties = {
    display: "inline-flex", alignItems: "center", gap: 5,
    padding: "5px 12px", borderRadius: 8,
    background: "var(--bg-elevated)", border: "1px solid var(--border)",
    color: "var(--text-secondary)", fontSize: "0.78rem", fontWeight: 600,
    cursor: "pointer", fontFamily: "inherit",
    transition: "all 0.18s var(--ease-smooth)",
  };
  const btnHover = (e: React.MouseEvent<HTMLButtonElement>) => {
    const b = e.currentTarget;
    b.style.borderColor = "var(--accent-muted)";
    b.style.color = "var(--accent)";
    b.style.background = "var(--accent-subtle)";
    b.style.transform = "translateY(-1px)";
  };
  const btnLeave = (e: React.MouseEvent<HTMLButtonElement>) => {
    const b = e.currentTarget;
    b.style.borderColor = "var(--border)";
    b.style.color = "var(--text-secondary)";
    b.style.background = "var(--bg-elevated)";
    b.style.transform = "none";
  };

  return (
    <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
      <button style={btnStyle} onMouseEnter={btnHover} onMouseLeave={btnLeave} onClick={() => downloadFile("md")}>
        <Download size={12} /> Markdown
      </button>
      <button style={btnStyle} onMouseEnter={btnHover} onMouseLeave={btnLeave} onClick={() => downloadFile("docx")}>
        <Download size={12} /> Word
      </button>
      <button style={btnStyle} onMouseEnter={btnHover} onMouseLeave={btnLeave} onClick={downloadJson}>
        <Download size={12} /> JSON
      </button>
    </div>
  );
}

// ─── Live Research Panel ─────────────────────────────────────────────────────
function LiveResearchPanel({ sessionId, topic, onClear }: {
  sessionId: string; topic: string; onClear: () => void;
}) {
  const [data, setData] = useState<ResearchData | null>(null);
  const [logOpen, setLogOpen] = useState(true);
  const [evalOpen, setEvalOpen] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const pollRef = useRef<number | null>(null);

  const fetchData = useCallback(async () => {
    try {
      const d = await getResearch(sessionId);
      setData(d);
      return d;
    } catch { return null; }
  }, [sessionId]);

  useEffect(() => {
    fetchData();

    // WebSocket for real-time updates
    const ws = createWebSocket(sessionId);
    wsRef.current = ws;

    ws.onmessage = () => fetchData();
    ws.onerror = () => {
      // Fallback to polling if WebSocket fails
      if (!pollRef.current) {
        pollRef.current = window.setInterval(fetchData, 3000);
      }
    };

    return () => {
      ws.close();
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [sessionId, fetchData]);

  // Stop polling once complete
  useEffect(() => {
    if (data?.session?.status !== "running" && pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, [data?.session?.status]);

  if (!data) {
    return (
      <div style={{ textAlign: "center", padding: 48, color: "var(--text-secondary)" }}>
        <Loader2 size={28} className="animate-spin" style={{ margin: "0 auto 12px", color: "var(--accent)" }} />
        Loading research session…
      </div>
    );
  }

  const { session, report, progress } = data;
  const status = session?.status ?? "running";
  const conf = session?.confidence ?? 0;

  return (
    <div className="animate-fade">
      {/* Header card */}
      <div className="card" style={{ marginBottom: 16, padding: "18px 24px" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 14 }}>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontSize: "1.12rem", fontWeight: 700, color: "var(--text-primary)", lineHeight: 1.3, marginBottom: 8 }} className="truncate">
              {topic}
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <span className="mono" style={{
                fontSize: "0.7rem", color: "var(--text-muted)",
                background: "rgba(255,255,255,0.04)", border: "1px solid var(--border-soft)",
                padding: "2px 8px", borderRadius: 4,
              }}>
                {sessionId.slice(0, 8)}…
              </span>
              <StatusPill status={status} />
            </div>
          </div>
          <button
            className="btn btn-ghost btn-sm"
            onClick={onClear}
            title="Dismiss panel"
            style={{ flexShrink: 0, marginLeft: 8 }}
            onMouseEnter={e => { (e.currentTarget as HTMLButtonElement).style.background = "rgba(248,113,113,0.08)"; (e.currentTarget as HTMLButtonElement).style.color = "var(--red)"; }}
            onMouseLeave={e => { (e.currentTarget as HTMLButtonElement).style.background = ""; (e.currentTarget as HTMLButtonElement).style.color = ""; }}
          >
            <X size={14} />
          </button>
        </div>
        <StageTracker status={status} />
      </div>

      {/* Metrics */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 10, marginBottom: 16 }}>
        <MetricCard label="Sources"  value={session?.sources  ?? "—"} />
        <MetricCard label="Findings" value={session?.findings ?? "—"} />
        <MetricCard label="Log Lines" value={progress.length} />
        <MetricCard label="Status"   value={status.charAt(0).toUpperCase() + status.slice(1)} />
      </div>

      {/* Confidence bar */}
      {conf > 0 && <div className="card" style={{ marginBottom: 16 }}><ConfidenceBar value={conf} /></div>}

      {/* Live log */}
      <div className="card" style={{ marginBottom: 16 }}>
        <button className="section-toggle" onClick={() => setLogOpen(v => !v)}>
          {logOpen ? <ChevronUp size={14} color="var(--accent)" /> : <ChevronDown size={14} color="var(--accent)" />}
          Activity Logs
          <span style={{ marginLeft: 4, fontSize: "0.72rem", color: "var(--text-muted)", fontWeight: 500 }}>({progress.length} entries)</span>
        </button>
        {logOpen && (
          <div style={{ marginTop: 14 }}>
            <LiveLog entries={progress} />
          </div>
        )}
      </div>

      {/* Complete state */}
      {status === "complete" && report && (
        <div className="animate-fade">
        <div style={{
            background: "linear-gradient(90deg, rgba(186,255,57,0.08) 0%, rgba(186,255,57,0.03) 100%)",
            border: "1px solid rgba(186,255,57,0.28)",
            borderRadius: "var(--radius-lg)", padding: "16px 22px",
            display: "flex", alignItems: "center", justifyContent: "space-between",
            marginBottom: 16,
            boxShadow: "0 4px 24px rgba(186,255,57,0.07), inset 0 1px 0 rgba(186,255,57,0.1)",
          }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <div style={{
                width: 36, height: 36, borderRadius: 10, flexShrink: 0,
                background: "rgba(186,255,57,0.1)", border: "1px solid rgba(186,255,57,0.25)",
                display: "flex", alignItems: "center", justifyContent: "center", fontSize: "1.1rem",
              }}>🎉</div>
              <div>
                <div style={{ color: "var(--accent)", fontWeight: 800, fontSize: "0.92rem" }}>
                  Research Complete
                </div>
                <div style={{ color: "var(--text-secondary)", fontSize: "0.78rem", marginTop: 1 }}>
                  Confidence score: {Math.round(conf * 100)}%
                </div>
              </div>
            </div>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap", justifyContent: "flex-end" }}>
              <ExportButtons sessionId={sessionId} report={report} />
              <button className="btn btn-secondary btn-sm" onClick={() => continueResearch(sessionId).then(fetchData)}>
                <RefreshCw size={13} /> Continue
              </button>
            </div>
          </div>

          {/* Evaluation panel */}
          {(report.fact_checks?.length > 0 || report.critique) && (
            <div className="card" style={{ marginBottom: 16 }}>
              <button
                onClick={() => setEvalOpen(v => !v)}
                style={{
                  display: "flex", alignItems: "center", gap: 6, background: "none",
                  border: "none", color: "var(--text-secondary)", cursor: "pointer",
                  fontSize: "0.86rem", fontWeight: 600, width: "100%", outline: "none"
                }}
              >
                {evalOpen ? <ChevronUp size={14} color="var(--accent)" /> : <ChevronDown size={14} color="var(--accent)" />}
                🔬 LLM Evaluation Report — {report.fact_checks?.length ?? 0} claims fact-checked
              </button>
              {evalOpen && (
                <FactCheckPanel factChecks={report.fact_checks ?? []} critique={report.critique ?? ""} />
              )}
            </div>
          )}

          {/* Report body */}
          <div className="card">
            <div className="report-body">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{report.content}</ReactMarkdown>
            </div>
          </div>
        </div>
      )}

      {status === "error" && (
        <div style={{
          background: "rgba(248,113,113,.08)", border: "1px solid rgba(248,113,113,.2)",
          borderRadius: "var(--radius-lg)", padding: 20, color: "#f87171",
        }}>
          <XCircle size={18} style={{ marginBottom: 6 }} />
          <div>Pipeline failed — check the Activity Logs for details.</div>
        </div>
      )}
    </div>
  );
}

// ─── Research Tab ────────────────────────────────────────────────────────────
function ResearchTab({ onSessionStart, activeSessionId, activeTopic, onClearSession }: {
  onSessionStart: (id: string, topic: string, mode: "standard" | "heavy") => void;
  activeSessionId: string | null;
  activeTopic: string;
  onClearSession: () => void;
}) {
  const [topic, setTopic] = useState("");
  const [loading, setLoading] = useState(false);
  const [researchMode, setResearchMode] = useState<"standard" | "heavy">("standard");
  const [activeStep, setActiveStep] = useState<number | null>(null); // for interactive diagram
  const startingRef = useRef(false); // guard against double-click

  const handleStart = async () => {
    if (!topic.trim() || loading || startingRef.current || !!activeSessionId) return;
    startingRef.current = true;
    setLoading(true);
    try {
      const { session_id } = await startResearch(topic.trim(), researchMode);
      onSessionStart(session_id, topic.trim(), researchMode);
    } catch (e) {
      alert(`Failed to start research: ${e}`);
    } finally {
      setLoading(false);
      startingRef.current = false;
    }
  };

  const diagramSteps = researchMode === "heavy" ? [
    {
      num: 1,
      title: "User Query Input & Intent Parsing",
      subtitle: "Preparing session parameters and academic context",
      icon: FileText,
      engine: "FastAPI Endpoint Manager",
      desc: "ScholarNode AI establishes a unique session ID in the SQLite database with the research mode flag set to Heavy, initializing parameters.",
      why: "Allows tracking and persisting the academic research run cleanly."
    },
    {
      num: 2,
      title: "Planner Agent (Topic Deconstruction)",
      subtitle: "Generating academic research outline",
      icon: Brain,
      engine: "Gemini 3.5 Flash (Planning)",
      desc: "Deconstructs the research topic into 3 to 5 core subtopics and defines targeted scientific search terms optimized for academic indexes.",
      why: "Ensures the search is scoped for deep literature review synthesis."
    },
    {
      num: 3,
      title: "Academic Search Agent (Parallel Literature Retrieval)",
      subtitle: "Searching peer-reviewed open access papers",
      icon: Search,
      engine: "arXiv, Semantic Scholar, PMC, CORE, OpenAlex APIs",
      desc: "Simultaneously queries five major academic search endpoints to retrieve raw research papers, including their year of publication and citation counts.",
      why: "Bypasses standard blogs, news, and forums to fetch direct peer-reviewed scientific findings."
    },
    {
      num: 4,
      title: "Citation Impact Ranking (Citation/Year Scoring)",
      subtitle: "Filtering by normalized citation index",
      icon: BarChart2,
      engine: "Formula: citations / (years_age + 1)",
      desc: "Computes a normalized citation score for each paper. Only the top-K papers (highest scores) are passed to the next stages, filtering out low-impact publications.",
      why: "Highlights papers with high scientific consensus and citation count relative to their publication age."
    },
    {
      num: 5,
      title: "Extraction Agent (Claim Extraction)",
      subtitle: "Mining empirical findings and methodologies",
      icon: Microscope,
      engine: "Gemini 3.1 Flash-Lite",
      desc: "Extracts primary claims, methodology statements, and empirical data points from the selected papers in parallel batches, mapping them to exact source citations.",
      why: "Captures hard scientific facts, omitting speculation and generic text."
    },
    {
      num: 6,
      title: "Evidence Aggregator (Clustering Findings)",
      subtitle: "Consolidating literature agreement & debates",
      icon: PenLine,
      engine: "In-Memory Semantic Matrix Aggregator",
      desc: "Clusters related claims from different papers and flags contradictions or competing theories in the academic discourse.",
      why: "Groups evidence to highlight consensus views and identify debate areas."
    },
    {
      num: 7,
      title: "Heavy Synthesis Agent (Drafting Academic Report)",
      subtitle: "Generating formal report with gaps & bibliography",
      icon: BookOpen,
      engine: "Gemini 3.5 Flash (Synthesis)",
      desc: "Drafts a comprehensive academic paper containing an Abstract, Literature Review, Consensus/Contradictions sections, Research Gaps, Novelty Suggestions, and an APA Bibliography.",
      why: "Creates a rigorously formatted, publication-ready research document."
    },
    {
      num: 8,
      title: "Critic Agent (Line-by-Line Academic Audit)",
      subtitle: "Validating report claims against peer-reviewed source pool",
      icon: CheckCircle2,
      engine: "Gemini 3.5 Flash (Auditor)",
      desc: "Audits every claim made in the synthesis against the raw paper data. Triggers retry loops to fetch additional papers if details need verification.",
      why: "Ensures the report contains zero hallucinations and represents high-accuracy scientific synthesis."
    },
    {
      num: 9,
      title: "Final Response & Document Exports",
      subtitle: "Generating Markdown, PDF/Word, and JSON datasets",
      icon: CheckCheck,
      engine: "Office Open XML & RAG Index Ingester",
      desc: "Saves the session state and builds a ChromaDB vector store index of the report so you can converse with it using the RAG chatbot.",
      why: "Delivers portable document exports and prepares the instant chatbot interface."
    }
  ] : [
    {
      num: 1,
      title: "User Query Input & Intent Parsing",
      subtitle: "Preparing session parameters and async contexts",
      icon: FileText,
      engine: "FastAPI Endpoint Manager",
      desc: "ScholarNode AI receives your research topic, establishes a unique session ID in the SQLite database, and initializes the background logging and state variables.",
      why: "Sets up an isolated, trackable runtime state so logs and findings persist even if the server restarts."
    },
    {
      num: 2,
      title: "Planner Agent (Topic Deconstruction)",
      subtitle: "Brainstorming a structured research outline",
      icon: Brain,
      engine: "Gemini 3.5 Flash (Planning)",
      desc: "Analyzes the query's underlying intent and splits it into 3 to 5 discrete subtopics. For each subtopic, it defines query strategies, source kinds (academic/news), and expected evidence.",
      why: "Guides targeted, multi-dimensional search patterns instead of executing shallow, single-sentence web queries."
    },
    {
      num: 3,
      title: "Search Agent (Parallel Data Retrieval)",
      subtitle: "Scouring indexes and scraping raw text bodies",
      icon: Search,
      engine: "Tavily API, DDG, arXiv, Semantic Scholar, Wikipedia",
      desc: "Queries search APIs in parallel. Then, it runs raw document scraper loops using Trafilatura, Readability-lxml, and BeautifulSoup to fetch full page texts while respecting rate limits.",
      why: "Aggregates recent news, standard web documentation, and peer-reviewed literature in one step."
    },
    {
      num: 4,
      title: "Source Ranking Module (Quality Filtering)",
      subtitle: "Scoring domain credibility and query relevance",
      icon: BarChart2,
      engine: "BAAI/bge-small-en-v1.5 Embeddings",
      desc: "Converts crawled documents to vectors and measures relevance. Adds credibility weights based on domain endings (.edu, .gov, or academic journals score highest) to rank sources.",
      why: "Discards commercial advertisements, forums, and landing pages to ensure only trustworthy sources are referenced."
    },
    {
      num: 5,
      title: "Extraction Agent (Claim Extraction)",
      subtitle: "Parsing articles into factual evidence claims",
      icon: Microscope,
      engine: "Gemini 3.1 Flash-Lite (Batch Extraction)",
      desc: "Processes source paragraphs using Gemini in parallel batches. It extracts atomic fact-claims, assigns truth ratings, and records exact paragraph locations for strict citation mapping.",
      why: "Sifts out opinionated editorial text, marketing noise, and fluff, producing a database of clean facts."
    },
    {
      num: 6,
      title: "Evidence Aggregator (Clustering Findings)",
      subtitle: "Grouping supporting facts and catching disagreements",
      icon: PenLine,
      engine: "In-Memory Semantic Matrix Aggregator",
      desc: "Groups matching claims from diverse sources into singular findings. It flags contradictory statements to highlight scientific disputes or hallucinated data.",
      why: "Consolidates matching arguments to reduce duplicates and highlights issues where sources disagree."
    },
    {
      num: 7,
      title: "Synthesis Agent (Drafting structured report)",
      subtitle: "Writing a publication-ready scientific draft",
      icon: BookOpen,
      engine: "Gemini 3.5 Flash (Synthesis)",
      desc: "Transforms the findings and bibliography links into a detailed 1,500+ word markdown report containing an Executive Summary, Section Analyses, and Limitations.",
      why: "Translates abstract fact nodes into readable, professional, fully cited academic prose."
    },
    {
      num: 8,
      title: "Critic Agent (Line-by-Line Fact Audit)",
      subtitle: "Auditing assertions against the evidence pool",
      icon: CheckCircle2,
      engine: "Gemini 3.5 Flash (Auditor & Critic)",
      desc: "Extracts every claim in the written draft and compares it back to the scraped raw evidence. Computes confidence scores. If gaps are found, it triggers a targeted follow-up query loop.",
      why: "Ensures the system produces zero hallucinations by double-checking that every statement has primary evidence."
    },
    {
      num: 9,
      title: "Final Response & Document Exports",
      subtitle: "Finalizing database states and generating file exports",
      icon: CheckCheck,
      engine: "Office Open XML & Markdown Compiler",
      desc: "Closes the active session status, saves final metrics, and generates download bundles for Markdown, Word DOCX, and raw session JSON datasets.",
      why: "Delivers portable, production-ready files that can be imported to any another ScholarNode machine."
    }
  ];

  return (
    <div>
      {/* ── Hero ─────────────────────────────────────────────────────────── */}
      <div style={{ textAlign: "center", padding: "68px 0 50px", position: "relative" }}>
        {/* Multi-layer ambient glow */}
        <div style={{
          position: "absolute", top: 0, left: "50%", transform: "translateX(-50%)",
          width: 500, height: 400,
          background: "radial-gradient(ellipse at 50% 30%, rgba(186,255,57,0.07) 0%, rgba(186,255,57,0.02) 40%, transparent 70%)",
          zIndex: 0, pointerEvents: "none",
        }} />
        <div style={{
          position: "absolute", top: "20%", left: "20%",
          width: 200, height: 200,
          background: "radial-gradient(circle, rgba(186,255,57,0.04) 0%, transparent 70%)",
          zIndex: 0, pointerEvents: "none", filter: "blur(20px)",
        }} />

        {/* Logo icon */}
        <div style={{ position: "relative", zIndex: 1, marginBottom: 28 }}>
          <div style={{
            display: "inline-flex", alignItems: "center", justifyContent: "center",
            width: 72, height: 72, borderRadius: 22,
            background: "linear-gradient(135deg, rgba(186,255,57,0.15), rgba(186,255,57,0.04))",
            border: "1px solid rgba(186,255,57,0.3)",
            boxShadow: "0 0 40px rgba(186,255,57,0.15), inset 0 1px 0 rgba(255,255,255,0.1)",
            animation: "borderGlow 4s ease-in-out infinite",
          }}>
            <FlaskConical size={30} color="var(--accent)" />
          </div>
        </div>

        <div style={{ position: "relative", zIndex: 1 }}>
          <h1 className="hero-title" style={{ marginBottom: 18 }}>ScholarNode AI</h1>

          <p style={{ color: "var(--text-secondary)", fontSize: "1.08rem", maxWidth: 520, margin: "0 auto 40px", lineHeight: 1.65 }}>
            Generate fully cited, validated research reports in minutes. Powered by a 9-step multi-agent pipeline with automated fallback.
          </p>

          {/* Suggestion chips */}
          <div style={{ display: "flex", flexWrap: "wrap", gap: 10, justifyContent: "center", maxWidth: 700, margin: "0 auto 36px" }}>
            {SUGGESTIONS.map((s, i) => (
              <button
                key={i}
                onClick={() => setTopic(s.text)}
                style={{
                  background: "rgba(255,255,255,0.025)",
                  border: "1px solid var(--border)",
                  borderRadius: 24, padding: "8px 18px",
                  fontSize: "0.84rem", color: "var(--text-secondary)", cursor: "pointer",
                  transition: "all 0.22s var(--ease-smooth)",
                  display: "flex", alignItems: "center", gap: 7, fontFamily: "inherit",
                }}
                onMouseEnter={e => {
                  const b = e.currentTarget as HTMLButtonElement;
                  b.style.borderColor = "var(--accent-muted)";
                  b.style.color = "var(--accent)";
                  b.style.background = "var(--accent-subtle)";
                  b.style.transform = "translateY(-2px)";
                  b.style.boxShadow = "0 6px 20px var(--accent-glow)";
                }}
                onMouseLeave={e => {
                  const b = e.currentTarget as HTMLButtonElement;
                  b.style.borderColor = "var(--border)";
                  b.style.color = "var(--text-secondary)";
                  b.style.background = "rgba(255,255,255,0.025)";
                  b.style.transform = "none";
                  b.style.boxShadow = "none";
                }}
              >
                <span>{s.icon}</span> {s.text}
              </button>
            ))}
          </div>

          {/* Input area */}
          <div style={{ maxWidth: 700, margin: "0 auto" }}>
            <div
              className="input-wrap"
              style={{ marginBottom: 14 }}
            >
              <textarea
                value={topic}
                onChange={e => setTopic(e.target.value)}
                onKeyDown={e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleStart(); } }}
                placeholder="Enter your research query… e.g. CRISPR gene therapy for rare diseases"
                rows={2}
                className="input-field"
              />
            </div>

            {/* Mode Selector */}
            <div style={{ display: "flex", gap: 10, marginBottom: 16 }}>
              {(["standard", "heavy"] as const).map(mode => (
                <button
                  key={mode}
                  onClick={() => setResearchMode(mode)}
                  style={{
                    flex: 1, padding: "11px 14px", borderRadius: 10,
                    border: researchMode === mode ? "1px solid var(--accent-muted)" : "1px solid var(--border-soft)",
                    background: researchMode === mode ? "var(--accent-glow)" : "rgba(255,255,255,0.01)",
                    color: researchMode === mode ? "var(--accent)" : "var(--text-muted)",
                    fontSize: "0.86rem", fontWeight: researchMode === mode ? 700 : 500,
                    cursor: "pointer", transition: "all 0.2s var(--ease-smooth)",
                    fontFamily: "inherit",
                    display: "flex", alignItems: "center", justifyContent: "center", gap: 7,
                    boxShadow: researchMode === mode ? "inset 0 0 24px var(--accent-subtle)" : "none",
                  }}
                  onMouseEnter={e => { if (researchMode !== mode) { (e.currentTarget as HTMLButtonElement).style.borderColor = "var(--border)"; (e.currentTarget as HTMLButtonElement).style.color = "var(--text-secondary)"; } }}
                  onMouseLeave={e => { if (researchMode !== mode) { (e.currentTarget as HTMLButtonElement).style.borderColor = "var(--border-soft)"; (e.currentTarget as HTMLButtonElement).style.color = "var(--text-muted)"; } }}
                >
                  {mode === "standard" ? <Zap size={14} /> : <BookOpen size={14} />}
                  {mode === "standard" ? "Standard Research" : "Research Heavy"}
                  {researchMode === mode && <span style={{ width: 5, height: 5, borderRadius: "50%", background: "var(--accent)", boxShadow: "0 0 6px var(--accent)", marginLeft: 2 }} />}
                </button>
              ))}
            </div>

            {researchMode === "heavy" && (
              <div style={{
                background: "rgba(186,255,57,0.03)", border: "1px solid rgba(186,255,57,0.12)",
                borderRadius: 10, padding: "12px 16px", marginBottom: 16,
                fontSize: "0.82rem", color: "var(--text-secondary)", lineHeight: 1.5, textAlign: "left",
              }}>
                <strong style={{ color: "var(--accent)", display: "block", marginBottom: 5 }}>📚 Research Heavy Mode</strong>
                Queries academic databases (arXiv, PubMed, Semantic Scholar, CORE, OpenAlex). Ranks papers by citation-per-year impact score and produces a formal academic report with bibliography and novelty gaps.
              </div>
            )}

            <button
              className="btn btn-primary btn-xl btn-full"
              onClick={handleStart}
              disabled={!topic.trim() || loading || !!activeSessionId}
              style={{ borderRadius: 14 }}
            >
              {loading ? <Loader2 size={18} className="animate-spin" /> : <Play size={18} />}
              {loading ? "Initializing…" : activeSessionId ? "Research Running…" : "Start Research"}
            </button>
            <p style={{ fontSize: "0.72rem", color: "var(--text-muted)", marginTop: 10, letterSpacing: "0.02em" }}>
              Press <kbd>Enter</kbd> to submit · <kbd>Shift+Enter</kbd> for new line
            </p>
          </div>
        </div>
      </div>

      {/* System Architecture & Methodology Flowchart */}
      {!activeSessionId && (
        <div style={{ margin: "56px auto 24px", maxWidth: 900, borderTop: "1px solid var(--border-soft)", paddingTop: 48 }}>
          <h3 style={{
            fontSize: "1.7rem", fontWeight: 900, textAlign: "center", marginBottom: 8,
            color: "var(--accent)", letterSpacing: "-0.02em"
          }}>
            System Architecture & Methodology Flowchart
          </h3>
          <p style={{ textAlign: "center", color: "var(--text-secondary)", fontSize: "0.92rem", marginBottom: 40, maxWidth: 640, margin: "0 auto 40px" }}>
            Explore the multi-agent pipeline from query parsing to exports. Click on any stage below to inspect the agents, models, and algorithms driving that step.
          </p>

          <div className="diagram-container animate-fade">
            {diagramSteps.map((step, idx) => {
              const StepIcon = step.icon;
              const isOpen = activeStep === idx;
              return (
                <div key={idx} style={{ display: "flex", flexDirection: "column" }}>
                  <div
                    className={`diagram-step ${isOpen ? "active" : ""}`}
                    onClick={() => setActiveStep(isOpen ? null : idx)}
                  >
                    <div className="diagram-badge">{step.num}</div>
                    <div className="diagram-icon-wrapper">
                      <StepIcon size={18} />
                    </div>
                    <div style={{ flex: 1 }}>
                      <div style={{ fontSize: "0.98rem", fontWeight: 700, color: "var(--text-primary)" }}>{step.title}</div>
                      <div style={{ fontSize: "0.78rem", color: "var(--text-secondary)", marginTop: 2 }}>{step.subtitle}</div>
                    </div>
                    <span style={{
                      fontSize: "0.7rem", fontWeight: 700, textTransform: "uppercase",
                      color: "var(--text-secondary)", border: "1px solid var(--border-soft)",
                      padding: "3px 8px", borderRadius: 4, background: "rgba(0,0,0,0.25)", fontFamily: "monospace"
                    }}>
                      {step.engine.split(" ")[0]}
                    </span>
                  </div>

                  {isOpen && (
                    <div className="diagram-detail animate-fade">
                      <div style={{ display: "flex", gap: 16, flexDirection: "column" }}>
                        <div>
                          <span style={{ fontSize: "0.72rem", color: "var(--text-muted)", textTransform: "uppercase", fontWeight: 700, display: "block", marginBottom: 4, letterSpacing: "0.02em" }}>
                            General Concept (Non-IT Friendly)
                          </span>
                          <p style={{ color: "var(--text-primary)", fontSize: "0.88rem", margin: 0, lineHeight: 1.5 }}>
                            {step.desc}
                          </p>
                        </div>
                        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
                          <div>
                            <span style={{ fontSize: "0.72rem", color: "var(--text-muted)", textTransform: "uppercase", fontWeight: 700, display: "block", marginBottom: 4, letterSpacing: "0.02em" }}>
                              Why it matters
                            </span>
                            <p style={{ color: "var(--text-secondary)", fontSize: "0.84rem", margin: 0, lineHeight: 1.45 }}>
                              {step.why}
                            </p>
                          </div>
                          <div>
                            <span style={{ fontSize: "0.72rem", color: "var(--text-muted)", textTransform: "uppercase", fontWeight: 700, display: "block", marginBottom: 4, letterSpacing: "0.02em" }}>
                              Underlying Engine / Model
                            </span>
                            <span className="badge badge-accent" style={{ fontSize: "0.75rem", fontWeight: 700, display: "inline-flex", padding: "4px 10px" }}>
                              {step.engine}
                            </span>
                          </div>
                        </div>
                      </div>
                    </div>
                  )}

                  {idx < diagramSteps.length - 1 && (
                    <div className="diagram-arrow-container">
                      <div className="diagram-arrow-line" />
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Active session — persists across tab switches via lifted state */}
      {activeSessionId && (
        <div style={{ marginTop: 24 }}>
          <LiveResearchPanel
            sessionId={activeSessionId}
            topic={activeTopic}
            onClear={onClearSession}
          />
        </div>
      )}
    </div>
  );
}

// ─── History Tab ─────────────────────────────────────────────────────────────
const FILTER_LABELS: Record<string, string> = {
  all: "All Sessions",
  complete: "Completed",
  running: "In Progress",
  error: "Failed",
};

const FILTER_ICONS: Record<string, React.ReactNode> = {
  all: <History size={12} />,
  complete: <CheckCheck size={12} />,
  running: <Loader2 size={12} />,
  error: <XCircle size={12} />,
};

function HistoryTab({ onView }: { onView: (sessionId: string) => void }) {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [filter, setFilter] = useState<"all" | "complete" | "running" | "error">("all");
  const [loading, setLoading] = useState(true);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { sessions: s } = await listSessions(100);
      setSessions(s);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const isRunningStatus = (status: string) =>
    ["running", "planning", "searching", "extracting", "synthesizing", "validating"].includes(status);

  const shown = filter === "all" ? sessions : sessions.filter(s => {
    if (filter === "running") return isRunningStatus(s.status);
    if (filter === "complete") return s.status === "complete";
    if (filter === "error") return s.status === "error";
    return true;
  });

  // Counts for badges
  const counts = {
    all: sessions.length,
    complete: sessions.filter(s => s.status === "complete").length,
    running: sessions.filter(s => isRunningStatus(s.status)).length,
    error: sessions.filter(s => s.status === "error").length,
  };

  const handleDelete = async (id: string) => {
    if (!confirm("Delete this session?")) return;
    await deleteSession(id);
    load();
  };

  const handleContinue = async (id: string) => {
    await continueResearch(id);
    load();
  };

  const handleImport = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    try {
      const reader = new FileReader();
      reader.onload = async (event) => {
        try {
          const payload = JSON.parse(event.target?.result as string);
          if (!payload.session) {
            alert("Invalid JSON format: missing session field");
            return;
          }
          await importResearch(payload);
          alert("Session imported successfully!");
          load();
        } catch (err) {
          alert(`Failed to import JSON: ${err}`);
        }
      };
      reader.readAsText(file);
    } catch (err) {
      alert(`Failed to read file: ${err}`);
    }
    e.target.value = "";
  };

  const filterColors: Record<string, string> = {
    all: "var(--accent)", complete: "#4ade80", running: "#fbbf24", error: "#f87171",
  };

  return (
    <div>
      {/* Page header */}
      <div className="page-header">
        <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 16 }}>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 6 }}>
              <div className="page-header-icon"><History size={16} /></div>
              <h2 className="page-title">Research History</h2>
            </div>
            <p className="page-subtitle">All past and active sessions — {sessions.length} total</p>
          </div>
          <div style={{ display: "flex", gap: 8, flexShrink: 0 }}>
            <button className="btn btn-secondary btn-sm" onClick={load} title="Refresh">
              <RefreshCw size={13} />
            </button>
            <button className="btn btn-secondary btn-sm" onClick={() => fileInputRef.current?.click()} style={{ gap: 5 }}>
              <Download size={13} style={{ transform: "rotate(180deg)" }} /> Import
            </button>
            <input type="file" ref={fileInputRef} onChange={handleImport} accept=".json" style={{ display: "none" }} />
          </div>
        </div>

        {/* Filter tabs */}
        <div style={{ display: "flex", gap: 6, marginTop: 20, flexWrap: "wrap" }}>
          {(["all", "complete", "running", "error"] as const).map(f => {
            const isActive = filter === f;
            const ac = filterColors[f];
            return (
              <button
                key={f}
                onClick={() => setFilter(f)}
                className="filter-tab"
                style={{
                  border: isActive ? `1px solid ${ac}45` : undefined,
                  background: isActive ? `${ac}10` : undefined,
                  color: isActive ? ac : undefined,
                  fontWeight: isActive ? 700 : undefined,
                }}
              >
                {FILTER_ICONS[f]}
                {FILTER_LABELS[f]}
                <span
                  className="filter-count"
                  style={{
                    background: isActive ? `${ac}18` : undefined,
                    color: isActive ? ac : undefined,
                  }}
                >
                  {counts[f]}
                </span>
              </button>
            );
          })}
        </div>
      </div>

      {loading ? (
        <div style={{ textAlign: "center", padding: 60, color: "var(--text-muted)" }}>
          <Loader2 size={26} className="animate-spin" style={{ margin: "0 auto 14px", color: "var(--accent)" }} />
          <p style={{ fontSize: "0.85rem" }}>Loading sessions…</p>
        </div>
      ) : shown.length === 0 ? (
        <div style={{
          textAlign: "center", padding: "60px 24px",
          background: "var(--bg-surface)", borderRadius: "var(--radius-lg)",
          border: "1px dashed var(--border-soft)",
        }}>
          <BookOpen size={36} style={{ margin: "0 auto 16px", opacity: 0.15, color: "var(--accent)" }} />
          <p style={{ color: "var(--text-muted)", fontWeight: 500, marginBottom: 12 }}>
            {filter === "all" ? "No sessions yet — start a research run!" : `No ${FILTER_LABELS[filter].toLowerCase()} sessions.`}
          </p>
          {filter !== "all" && (
            <button className="btn btn-ghost btn-sm" onClick={() => setFilter("all")}>View all sessions</button>
          )}
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {shown.map(s => (
            <div key={s.id} className="history-card">
              <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 12 }}>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: "0.94rem", fontWeight: 600, marginBottom: 8, color: "var(--text-primary)", lineHeight: 1.4 }} className="truncate">
                    {s.topic}
                  </div>
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 10, fontSize: "0.75rem", color: "var(--text-muted)" }}>
                    <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
                      <Clock size={11} /> {new Date(s.created_at).toLocaleString()}
                    </span>
                    {(s.confidence ?? 0) > 0 && (
                      <span style={{ display: "flex", alignItems: "center", gap: 4, color: "var(--accent)" }}>
                        <Zap size={11} /> {Math.round((s.confidence ?? 0) * 100)}% confidence
                      </span>
                    )}
                    {s.findings > 0 && (
                      <span style={{ display: "flex", alignItems: "center", gap: 4 }}><Microscope size={11} /> {s.findings} findings</span>
                    )}
                    {s.sources > 0 && (
                      <span style={{ display: "flex", alignItems: "center", gap: 4 }}><BookOpen size={11} /> {s.sources} sources</span>
                    )}
                  </div>
                </div>
                <div style={{ display: "flex", gap: 6, alignItems: "center", flexShrink: 0 }}>
                  <StatusPill status={s.status} />
                  {s.status === "complete" && (
                    <button
                      className="btn btn-secondary btn-sm"
                      onClick={() => onView(s.id)}
                      style={{ gap: 4 }}
                    >
                      <ArrowRight size={13} /> View
                    </button>
                  )}
                  <button className="btn btn-ghost btn-sm" onClick={() => handleContinue(s.id)} title="Continue research">
                    <RefreshCw size={13} />
                  </button>
                  <button className="btn btn-danger btn-sm" onClick={() => handleDelete(s.id)} title="Delete session">
                    <Trash2 size={13} />
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ─── Viewer Tab ──────────────────────────────────────────────────────────────
function ViewerTab({
  initialSessionId,
  onSessionChange,
}: {
  initialSessionId?: string;
  onSessionChange?: (id: string) => void;
}) {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [selectedId, setSelectedId] = useState(initialSessionId ?? "");
  const [data, setData] = useState<ResearchData | null>(null);
  const [evalOpen, setEvalOpen] = useState(true);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const loadSessions = useCallback(() => {
    listSessions(100).then(({ sessions: s }) => {
      const done = s.filter((x: Session) => x.status === "complete");
      setSessions(done);
      if (!selectedId && done.length > 0) setSelectedId(done[0].id);
    });
  }, [selectedId]);

  useEffect(() => {
    loadSessions();
  }, []);

  useEffect(() => {
    if (initialSessionId) setSelectedId(initialSessionId);
  }, [initialSessionId]);

  useEffect(() => {
    if (!selectedId) return;
    getResearch(selectedId).then(setData);
  }, [selectedId]);

  useEffect(() => {
    if (selectedId && onSessionChange) {
      onSessionChange(selectedId);
    }
  }, [selectedId, onSessionChange]);

  const report = data?.report;
  const session = data?.session;

  const handleImport = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    try {
      const reader = new FileReader();
      reader.onload = async (event) => {
        try {
          const payload = JSON.parse(event.target?.result as string);
          if (!payload.session) {
            alert("Invalid JSON format: missing session field");
            return;
          }
          const res = await importResearch(payload);
          alert("Report imported successfully!");
          setSelectedId(res.session_id);
          loadSessions();
        } catch (err) {
          alert(`Failed to import JSON: ${err}`);
        }
      };
      reader.readAsText(file);
    } catch (err) {
      alert(`Failed to read file: ${err}`);
    }
    e.target.value = "";
  };

  return (
    <div>
      {/* Page header */}
      <div className="page-header">
        <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 16, flexWrap: "wrap" }}>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 6 }}>
              <div className="page-header-icon"><FileText size={16} /></div>
              <h2 className="page-title">Report Viewer</h2>
            </div>
            <p className="page-subtitle">
              {sessions.length === 0 ? "No completed reports yet" : `${sessions.length} completed report${sessions.length !== 1 ? "s" : ""} available`}
            </p>
          </div>
          <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
            <button className="btn btn-secondary btn-sm" onClick={() => fileInputRef.current?.click()} style={{ gap: 5 }}>
              <Download size={13} style={{ transform: "rotate(180deg)" }} /> Import
            </button>
            <input type="file" ref={fileInputRef} onChange={handleImport} accept=".json" style={{ display: "none" }} />
            {sessions.length > 0 && (
              <select
                value={selectedId}
                onChange={e => setSelectedId(e.target.value)}
                className="report-select"
              >
                {sessions.map(s => (
                  <option key={s.id} value={s.id}>
                    {s.topic.slice(0, 58)} — {new Date(s.created_at).toLocaleDateString()}
                  </option>
                ))}
              </select>
            )}
          </div>
        </div>
      </div>

      {!report ? (
        <div style={{ textAlign: "center", padding: 64, color: "var(--text-muted)" }}>
          <FileText size={32} style={{ margin: "0 auto 12px", opacity: .3 }} />
          <p>{sessions.length === 0 ? "No completed reports yet." : "Select a report above."}</p>
        </div>
      ) : (
        <div className="animate-fade">
          {/* Metrics */}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 10, marginBottom: 16 }}>
            <MetricCard label="Confidence" value={session?.confidence ? `${Math.round(session.confidence * 100)}%` : "—"} />
            <MetricCard label="Findings"   value={session?.findings ?? "—"} />
            <MetricCard label="Sources"    value={session?.sources ?? "—"} />
            <MetricCard label="Words"      value={report.word_count ?? "—"} />
          </div>

          {session?.confidence && (
            <div className="card" style={{ marginBottom: 16 }}>
              <ConfidenceBar value={session.confidence} />
            </div>
          )}

          {/* Export */}
          <div className="card" style={{ marginBottom: 16, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <span style={{ fontSize: "0.86rem", color: "var(--text-secondary)", fontWeight: 500 }}>Export this report</span>
            <ExportButtons sessionId={selectedId} report={report} />
          </div>

          {/* Evaluation */}
          {(report.fact_checks?.length > 0 || report.critique) && (
            <div className="card" style={{ marginBottom: 16 }}>
              <button
                onClick={() => setEvalOpen(v => !v)}
                style={{
                  display: "flex", alignItems: "center", gap: 6, background: "none",
                  border: "none", color: "var(--text-secondary)", cursor: "pointer",
                  fontSize: "0.86rem", fontWeight: 600, width: "100%", outline: "none"
                }}
              >
                {evalOpen ? <ChevronUp size={14} color="var(--accent)" /> : <ChevronDown size={14} color="var(--accent)" />}
                🔬 LLM Evaluation Report — {report.fact_checks?.length ?? 0} claims fact-checked
              </button>
              {evalOpen && (
                <FactCheckPanel factChecks={report.fact_checks ?? []} critique={report.critique ?? ""} />
              )}
            </div>
          )}

          {/* Report */}
          <div className="card">
            <div className="report-body">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{report.content}</ReactMarkdown>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ─── Root App ────────────────────────────────────────────────────────────────
// ─── Chat RAG Panel Component ───────────────────────────────────────────────
function ChatPanel({ sessionId }: { sessionId: string }) {
  const [isOpen, setIsOpen]       = useState(false);
  const [isExpanded, setIsExpanded] = useState(false);
  const [messages, setMessages]   = useState<ChatMessage[]>([]);
  const [input, setInput]         = useState("");
  const [loading, setLoading]     = useState(false);
  const [sources, setSources]     = useState<ChatSource[]>([]);
  const [showSources, setShowSources] = useState(false);
  const chatEndRef = useRef<HTMLDivElement>(null);
  const inputRef   = useRef<HTMLInputElement>(null);

  const loadHistory = useCallback(async () => {
    try {
      const res = await getChatHistory(sessionId);
      setMessages(res.history || []);
    } catch (e) {
      console.error("Failed to load chat history", e);
    }
  }, [sessionId]);

  useEffect(() => { if (isOpen) { loadHistory(); setTimeout(() => inputRef.current?.focus(), 120); } }, [isOpen, loadHistory]);
  useEffect(() => { chatEndRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages]);

  const handleSend = async () => {
    if (!input.trim() || loading) return;
    const userMsg = input.trim();
    setInput("");
    setMessages(prev => [...prev, { role: "user", content: userMsg }]);
    setLoading(true);
    try {
      const res = await chatWithReport(sessionId, userMsg);
      setMessages(prev => [...prev, { role: "assistant", content: res.answer }]);
      setSources(res.sources || []);
      if (res.sources?.length > 0) setShowSources(true);
    } catch (e) {
      setMessages(prev => [...prev, { role: "assistant", content: `Error generating response: ${e}` }]);
    } finally {
      setLoading(false);
    }
  };

  const handleClear = async () => {
    if (!confirm("Clear chat history?")) return;
    try {
      await clearChatHistory(sessionId);
      setMessages([]);
      setSources([]);
      setShowSources(false);
    } catch (e) {
      alert(`Failed to clear: ${e}`);
    }
  };

  // ── Collapsed FAB ─────────────────────────────────────────────────────────
  if (!isOpen) {
    return (
      <button
        onClick={() => setIsOpen(true)}
        title="Chat with Report"
        style={{
          position: "fixed", bottom: 28, right: 28,
          width: 58, height: 58, borderRadius: "50%",
          background: "linear-gradient(135deg, var(--accent), var(--accent-light))",
          border: "2px solid rgba(186,255,57,0.35)",
          color: "#000", cursor: "pointer",
          display: "flex", alignItems: "center", justifyContent: "center",
          boxShadow: "0 6px 28px rgba(0,0,0,0.5), 0 0 24px var(--accent-glow)",
          zIndex: 9999,
          transition: "transform 0.25s cubic-bezier(.34,1.56,.64,1), box-shadow 0.25s ease",
        }}
        onMouseEnter={e => {
          e.currentTarget.style.transform = "scale(1.12)";
          e.currentTarget.style.boxShadow = "0 8px 36px rgba(0,0,0,0.6), 0 0 36px var(--accent-muted)";
        }}
        onMouseLeave={e => {
          e.currentTarget.style.transform = "none";
          e.currentTarget.style.boxShadow = "0 6px 28px rgba(0,0,0,0.5), 0 0 24px var(--accent-glow)";
        }}
      >
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.3" strokeLinecap="round" strokeLinejoin="round">
          <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
        </svg>
      </button>
    );
  }

  // ── Dynamic panel dimensions ───────────────────────────────────────────────
  const panelW = isExpanded ? "min(680px, 92vw)" : "min(400px, 92vw)";
  const panelH = isExpanded ? "min(680px, 88vh)" : "min(540px, 88vh)";

  return (
    <div style={{
      position: "fixed",
      bottom: 24, right: 24,
      width: panelW, height: panelH,
      borderRadius: 20,
      background: "linear-gradient(180deg, var(--bg-elevated) 0%, var(--bg-surface) 100%)",
      border: "1px solid rgba(186,255,57,0.18)",
      boxShadow: "0 24px 64px rgba(0,0,0,0.75), 0 0 40px rgba(186,255,57,0.06)",
      display: "flex", flexDirection: "column", overflow: "hidden",
      zIndex: 9999,
      transition: "width 0.3s cubic-bezier(.4,0,.2,1), height 0.3s cubic-bezier(.4,0,.2,1)",
    }}>

      {/* ── Header ─────────────────────────────────────────────────────────── */}
      <div style={{
        padding: "14px 16px",
        borderBottom: "1px solid rgba(186,255,57,0.12)",
        background: "linear-gradient(90deg, rgba(186,255,57,0.07) 0%, rgba(0,0,0,0.3) 100%)",
        display: "flex", justifyContent: "space-between", alignItems: "center",
        flexShrink: 0,
      }}>
        {/* Title */}
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <div style={{
            width: 9, height: 9, borderRadius: "50%",
            background: "var(--accent)",
            boxShadow: "0 0 8px var(--accent-muted)",
            animation: "pulseGlow 2.5s ease-in-out infinite",
          }} />
          <span style={{ fontWeight: 800, fontSize: "0.92rem", letterSpacing: "0.01em" }}>Chat with Report</span>
          <span style={{
            fontSize: "0.65rem", fontWeight: 700, letterSpacing: "0.06em",
            background: "rgba(186,255,57,0.12)", color: "var(--accent)",
            border: "1px solid rgba(186,255,57,0.25)", borderRadius: 4, padding: "2px 7px",
          }}>RAG</span>
        </div>

        {/* Controls */}
        <div style={{ display: "flex", gap: 4, alignItems: "center" }}>
          {/* Expand/Collapse */}
          <button
            onClick={() => setIsExpanded(v => !v)}
            title={isExpanded ? "Shrink" : "Expand"}
            className="btn btn-ghost btn-sm"
            style={{ padding: "5px 6px", borderRadius: 8, transition: "all 0.2s ease" }}
            onMouseEnter={e => { (e.currentTarget as HTMLButtonElement).style.background = "rgba(186,255,57,0.08)"; (e.currentTarget as HTMLButtonElement).style.color = "var(--accent)"; }}
            onMouseLeave={e => { (e.currentTarget as HTMLButtonElement).style.background = "transparent"; (e.currentTarget as HTMLButtonElement).style.color = ""; }}
          >
            {isExpanded ? (
              /* collapse icon */
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="4 14 10 14 10 20"/><polyline points="20 10 14 10 14 4"/>
                <line x1="10" y1="14" x2="3" y2="21"/><line x1="21" y1="3" x2="14" y2="10"/>
              </svg>
            ) : (
              /* expand icon */
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="15 3 21 3 21 9"/><polyline points="9 21 3 21 3 15"/>
                <line x1="21" y1="3" x2="14" y2="10"/><line x1="3" y1="21" x2="10" y2="14"/>
              </svg>
            )}
          </button>

          {/* Clear */}
          <button
            onClick={handleClear}
            title="Clear Chat"
            className="btn btn-ghost btn-sm"
            style={{ padding: "5px 6px", borderRadius: 8, transition: "all 0.2s ease" }}
            onMouseEnter={e => { (e.currentTarget as HTMLButtonElement).style.background = "rgba(248,113,113,0.1)"; (e.currentTarget as HTMLButtonElement).style.color = "var(--red)"; }}
            onMouseLeave={e => { (e.currentTarget as HTMLButtonElement).style.background = "transparent"; (e.currentTarget as HTMLButtonElement).style.color = ""; }}
          >
            <Trash2 size={14} />
          </button>

          {/* Close */}
          <button
            onClick={() => setIsOpen(false)}
            title="Close"
            className="btn btn-ghost btn-sm"
            style={{ padding: "5px 6px", borderRadius: 8, transition: "all 0.2s ease" }}
            onMouseEnter={e => { (e.currentTarget as HTMLButtonElement).style.background = "rgba(255,255,255,0.06)"; (e.currentTarget as HTMLButtonElement).style.color = "#fff"; }}
            onMouseLeave={e => { (e.currentTarget as HTMLButtonElement).style.background = "transparent"; (e.currentTarget as HTMLButtonElement).style.color = ""; }}
          >
            <X size={15} />
          </button>
        </div>
      </div>

      {/* ── Messages ───────────────────────────────────────────────────────── */}
      <div style={{ flex: 1, padding: "16px 14px", overflowY: "auto", display: "flex", flexDirection: "column", gap: 14 }}>
        {messages.length === 0 && (
          <div style={{ textAlign: "center", color: "var(--text-muted)", marginTop: 50, padding: "0 20px" }}>
            <div style={{
              width: 52, height: 52, borderRadius: "50%", margin: "0 auto 16px",
              background: "rgba(186,255,57,0.06)", border: "1px solid rgba(186,255,57,0.15)",
              display: "flex", alignItems: "center", justifyContent: "center", fontSize: "1.5rem",
            }}>💬</div>
            <p style={{ fontSize: "0.9rem", fontWeight: 600, color: "var(--text-secondary)", marginBottom: 6 }}>Chat with your Report</p>
            <p style={{ fontSize: "0.78rem", color: "var(--text-muted)", lineHeight: 1.6 }}>
              Ask anything about the research, findings, sources, or methodology.
            </p>
          </div>
        )}

        {messages.map((m, i) => (
          <div
            key={i}
            style={{
              alignSelf: m.role === "user" ? "flex-end" : "flex-start",
              maxWidth: isExpanded ? "80%" : "88%",
              transition: "max-width 0.3s ease",
            }}
          >
            {/* Role label */}
            <div style={{
              fontSize: "0.65rem", fontWeight: 700, letterSpacing: "0.07em",
              color: m.role === "user" ? "var(--accent)" : "var(--text-muted)",
              marginBottom: 4, textAlign: m.role === "user" ? "right" : "left",
              textTransform: "uppercase",
            }}>
              {m.role === "user" ? "You" : "ScholarNode AI"}
            </div>

            {/* Bubble */}
            <div
              style={{
                background: m.role === "user"
                  ? "linear-gradient(135deg, rgba(186,255,57,0.14), rgba(186,255,57,0.06))"
                  : "rgba(255,255,255,0.025)",
                border: m.role === "user"
                  ? "1px solid rgba(186,255,57,0.30)"
                  : "1px solid rgba(255,255,255,0.06)",
                borderRadius: m.role === "user" ? "14px 14px 4px 14px" : "14px 14px 14px 4px",
                padding: "10px 14px",
                wordBreak: "break-word",
                transition: "border-color 0.2s ease, box-shadow 0.2s ease",
              }}
              onMouseEnter={e => {
                (e.currentTarget as HTMLDivElement).style.borderColor = m.role === "user"
                  ? "rgba(186,255,57,0.55)" : "rgba(255,255,255,0.14)";
                (e.currentTarget as HTMLDivElement).style.boxShadow = m.role === "user"
                  ? "0 4px 16px rgba(186,255,57,0.08)" : "0 4px 16px rgba(0,0,0,0.4)";
              }}
              onMouseLeave={e => {
                (e.currentTarget as HTMLDivElement).style.borderColor = m.role === "user"
                  ? "rgba(186,255,57,0.30)" : "rgba(255,255,255,0.06)";
                (e.currentTarget as HTMLDivElement).style.boxShadow = "none";
              }}
            >
              {m.role === "user" ? (
                <span style={{ fontSize: "0.86rem", color: "var(--accent)", lineHeight: 1.5 }}>{m.content}</span>
              ) : (
                <div className="chat-markdown">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{m.content}</ReactMarkdown>
                </div>
              )}
            </div>
          </div>
        ))}

        {/* Typing indicator */}
        {loading && (
          <div style={{ alignSelf: "flex-start", display: "flex", alignItems: "center", gap: 8 }}>
            <div style={{
              background: "rgba(255,255,255,0.025)", border: "1px solid rgba(255,255,255,0.06)",
              borderRadius: "14px 14px 14px 4px", padding: "10px 14px",
              display: "flex", alignItems: "center", gap: 8,
            }}>
              <Loader2 size={13} className="animate-spin" color="var(--accent)" />
              <span style={{ fontSize: "0.78rem", color: "var(--text-secondary)", letterSpacing: "0.02em" }}>
                Thinking…
              </span>
            </div>
          </div>
        )}
        <div ref={chatEndRef} />
      </div>

      {/* ── Sources Drawer ─────────────────────────────────────────────────── */}
      {showSources && sources.length > 0 && (
        <div style={{
          borderTop: "1px solid rgba(186,255,57,0.10)",
          background: "rgba(0,0,0,0.35)",
          padding: "8px 14px", maxHeight: 120, overflowY: "auto", flexShrink: 0,
        }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
            <span style={{ fontSize: "0.67rem", color: "var(--accent)", fontWeight: 800, letterSpacing: "0.08em" }}>
              📎 RETRIEVED SOURCES
            </span>
            <button
              onClick={() => setShowSources(false)}
              style={{
                background: "none", border: "none", color: "var(--text-muted)",
                cursor: "pointer", fontSize: "0.7rem", padding: "2px 6px", borderRadius: 4,
                transition: "color 0.15s ease",
              }}
              onMouseEnter={e => (e.currentTarget.style.color = "var(--text-primary)")}
              onMouseLeave={e => (e.currentTarget.style.color = "var(--text-muted)")}
            >
              Hide
            </button>
          </div>
          {sources.map((s, idx) => (
            <div
              key={idx}
              style={{
                fontSize: "0.7rem", color: "var(--text-secondary)", marginBottom: 5,
                padding: "4px 8px", borderRadius: 6, background: "rgba(255,255,255,0.02)",
                border: "1px solid rgba(255,255,255,0.04)",
                textOverflow: "ellipsis", overflow: "hidden", whiteSpace: "nowrap",
                transition: "background 0.15s ease, border-color 0.15s ease",
                cursor: "default",
              }}
              onMouseEnter={e => { (e.currentTarget as HTMLDivElement).style.background = "rgba(255,255,255,0.04)"; (e.currentTarget as HTMLDivElement).style.borderColor = "rgba(186,255,57,0.15)"; }}
              onMouseLeave={e => { (e.currentTarget as HTMLDivElement).style.background = "rgba(255,255,255,0.02)"; (e.currentTarget as HTMLDivElement).style.borderColor = "rgba(255,255,255,0.04)"; }}
            >
              <span style={{ color: "var(--accent)", fontWeight: 700, marginRight: 4 }}>
                [{s.type.toUpperCase()}]
              </span>
              {s.url
                ? <a href={s.url} target="_blank" rel="noreferrer" style={{ color: "var(--accent)", textDecoration: "underline" }}>{s.title}</a>
                : <span>{s.title}</span>
              }
              <span style={{ color: "var(--text-muted)", marginLeft: 4 }}>— "{s.snippet}"</span>
            </div>
          ))}
        </div>
      )}

      {/* ── Input Bar ──────────────────────────────────────────────────────── */}
      <div style={{
        padding: "10px 12px 12px",
        borderTop: "1px solid rgba(186,255,57,0.10)",
        background: "rgba(0,0,0,0.25)",
        flexShrink: 0,
      }}>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <input
            ref={inputRef}
            type="text"
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => { if (e.key === "Enter" && !e.shiftKey) handleSend(); }}
            placeholder="Ask a question about the report…"
            style={{
              flex: 1,
              background: "rgba(255,255,255,0.04)",
              border: "1px solid rgba(186,255,57,0.15)",
              borderRadius: 10,
              padding: "9px 13px",
              color: "var(--text-primary)",
              fontSize: "0.85rem",
              outline: "none",
              fontFamily: "inherit",
              transition: "border-color 0.2s ease, box-shadow 0.2s ease, background 0.2s ease",
            }}
            onFocus={e => {
              e.currentTarget.style.borderColor = "rgba(186,255,57,0.5)";
              e.currentTarget.style.boxShadow   = "0 0 0 3px rgba(186,255,57,0.08)";
              e.currentTarget.style.background  = "rgba(255,255,255,0.06)";
            }}
            onBlur={e => {
              e.currentTarget.style.borderColor = "rgba(186,255,57,0.15)";
              e.currentTarget.style.boxShadow   = "none";
              e.currentTarget.style.background  = "rgba(255,255,255,0.04)";
            }}
          />
          <button
            onClick={handleSend}
            disabled={!input.trim() || loading}
            style={{
              background: input.trim() && !loading
                ? "linear-gradient(135deg, var(--accent), var(--accent-light))"
                : "rgba(186,255,57,0.08)",
              border: "1px solid rgba(186,255,57,0.3)",
              borderRadius: 10,
              padding: "9px 16px",
              color: input.trim() && !loading ? "#000" : "var(--text-muted)",
              fontWeight: 700,
              fontSize: "0.84rem",
              cursor: input.trim() && !loading ? "pointer" : "not-allowed",
              fontFamily: "inherit",
              display: "flex", alignItems: "center", gap: 6,
              transition: "all 0.2s ease",
              flexShrink: 0,
            }}
            onMouseEnter={e => {
              if (input.trim() && !loading) {
                (e.currentTarget as HTMLButtonElement).style.transform = "translateY(-1px)";
                (e.currentTarget as HTMLButtonElement).style.boxShadow = "0 4px 16px rgba(186,255,57,0.25)";
              }
            }}
            onMouseLeave={e => {
              (e.currentTarget as HTMLButtonElement).style.transform = "none";
              (e.currentTarget as HTMLButtonElement).style.boxShadow = "none";
            }}
          >
            {loading ? <Loader2 size={14} className="animate-spin" /> : (
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/>
              </svg>
            )}
            Send
          </button>
        </div>
        {/* Keyboard hint */}
        <div style={{ fontSize: "0.63rem", color: "var(--text-muted)", marginTop: 6, textAlign: "right", letterSpacing: "0.03em" }}>
          Press <kbd style={{ background: "rgba(255,255,255,0.06)", border: "1px solid var(--border-soft)", padding: "1px 5px", borderRadius: 4, fontFamily: "inherit" }}>Enter</kbd> to send
        </div>
      </div>
    </div>
  );
}

// ─── Root App ────────────────────────────────────────────────────────────────
export default function App() {
  const [tab, setTab] = useState<Tab>("research");
  const [healthy, setHealthy] = useState<boolean | null>(null);
  const [sessions, setSessions] = useState<Session[]>([]);
  const [viewerSessionId, setViewerSessionId] = useState<string | undefined>();
  // Lifted active session state — survives tab switches
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [activeTopic, setActiveTopic] = useState<string>("");

  useEffect(() => {
    checkHealth().then(h => setHealthy(!!h));
    listSessions(100).then(({ sessions: s }) => setSessions(s)).catch(() => {});
    const iv = setInterval(() => {
      checkHealth().then(h => setHealthy(!!h));
      listSessions(100).then(({ sessions: s }) => setSessions(s)).catch(() => {});
    }, 15000);
    return () => clearInterval(iv);
  }, []);

  const handleSessionStart = (id: string, topic: string, _mode: "standard" | "heavy") => {
    setActiveSessionId(id);
    setActiveTopic(topic);
    listSessions(100).then(({ sessions: s }) => setSessions(s)).catch(() => {});
  };

  const handleClearSession = () => {
    setActiveSessionId(null);
    setActiveTopic("");
  };

  const handleViewSession = (id: string) => {
    setViewerSessionId(id);
    setTab("viewer");
  };

  const TABS = [
    { key: "research" as Tab, icon: FlaskConical, label: "Research" },
    { key: "history"  as Tab, icon: History,      label: "History" },
    { key: "viewer"   as Tab, icon: FileText,      label: "Reports" },
  ];

  const activeThemeClass = 
    tab === "history" ? "theme-history" 
    : tab === "viewer" ? "theme-viewer" 
    : activeSessionId ? "theme-live" 
    : "theme-research";

  let chatSessionId: string | null = null;
  if (tab === "viewer" && viewerSessionId) {
    chatSessionId = viewerSessionId;
  } else if (tab === "research" && activeSessionId) {
    chatSessionId = activeSessionId;
  }
  const targetSession = sessions.find(s => s.id === chatSessionId);
  const showChat = targetSession && targetSession.status === "complete";

  return (
    <div className={activeThemeClass} style={{ minHeight: "100vh", background: "var(--bg-base)", display: "flex", flexDirection: "column" }}>
      {/* ── Navigation ───────────────────────────────────────────────────── */}
      <nav className="nav-shell">
        <div className="nav-inner">
          {/* Logo */}
          <a className="nav-logo">
            <div className="nav-logo-icon">
              <Sparkles size={15} color="#000" />
            </div>
            <span className="nav-logo-text">ScholarNode AI</span>
          </a>

          {/* Tabs */}
          <div style={{ display: "flex", gap: 2, flex: 1 }}>
            {TABS.map(t => {
              const Icon = t.icon;
              return (
                <button
                  key={t.key}
                  onClick={() => setTab(t.key)}
                  className={`nav-tab ${tab === t.key ? "active" : ""}`}
                >
                  <Icon size={14} />
                  {t.label}
                  {t.key === "history" && sessions.length > 0 && (
                    <span className="nav-badge">{sessions.length}</span>
                  )}
                </button>
              );
            })}
          </div>

          {/* API status pill */}
          <div className={`nav-status ${healthy === null ? "" : healthy ? "online" : "offline"}`}>
            {healthy === null ? (
              <span style={{ color: "var(--text-muted)", fontSize: "0.78rem" }}>Checking…</span>
            ) : healthy ? (
              <><Wifi size={13} /><span style={{ fontWeight: 700, fontSize: "0.78rem" }}>API Online</span></>
            ) : (
              <><WifiOff size={13} /><span style={{ fontWeight: 700, fontSize: "0.78rem" }}>Offline</span></>
            )}
          </div>
        </div>
      </nav>

      {/* ── Content ──────────────────────────────────────────────────────── */}
      <main style={{ flex: 1, padding: "0 28px 60px" }}>
        <div style={{ maxWidth: 1140, margin: "0 auto" }}>
          {healthy === false && (
            <div className="offline-banner">
              <WifiOff size={14} />
              API is offline. Run: <code>uvicorn api.server:app --reload</code>
            </div>
          )}
          <div style={{ paddingTop: 24 }}>
            {tab === "research" && (
              <ResearchTab
                onSessionStart={handleSessionStart}
                activeSessionId={activeSessionId}
                activeTopic={activeTopic}
                onClearSession={handleClearSession}
              />
            )}
            {tab === "history" && <HistoryTab onView={handleViewSession} />}
            {tab === "viewer" && (
              <ViewerTab
                initialSessionId={viewerSessionId}
                onSessionChange={(id) => setViewerSessionId(id)}
              />
            )}
          </div>
        </div>
      </main>

      {showChat && chatSessionId && <ChatPanel sessionId={chatSessionId} />}
    </div>
  );
}
