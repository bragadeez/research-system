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
import type { Session, ResearchData, ProgressEntry } from "./types";
import {
  startResearch, getResearch, listSessions, deleteSession,
  continueResearch, checkHealth, getExportUrl, createWebSocket,
  importResearch,
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
  const color = "var(--accent)";
  const glowColor = "var(--accent-glow)";
  const label = pct >= 85 ? "Verified" : pct >= 70 ? "Credible" : pct >= 50 ? "Moderate" : "Low Confidence";
  
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 14, margin: "6px 0" }}>
      <span style={{ fontSize: "0.8rem", color: "var(--text-secondary)", minWidth: 90, fontWeight: 600, letterSpacing: "0.02em" }}>
        Confidence
      </span>
      <div style={{ flex: 1, height: 8, background: "rgba(255,255,255,0.03)", borderRadius: 6, border: "1px solid var(--border-soft)", overflow: "hidden", position: "relative" }}>
        <div style={{
          width: `${pct}%`, height: "100%", background: `linear-gradient(to right, #ffffff, ${color})`, borderRadius: 6,
          boxShadow: `0 0 12px ${glowColor}`,
          transition: "width 0.8s cubic-bezier(0.4, 0, 0.2, 1)"
        }} />
      </div>
      <span style={{ fontSize: "1rem", fontWeight: 800, color: "var(--text-primary)" }}>{pct}%</span>
      <span style={{ 
        fontSize: "0.7rem", fontWeight: 700, 
        color: pct >= 70 ? "var(--accent)" : pct >= 50 ? "var(--yellow)" : "var(--red)", 
        border: `1px solid ${pct >= 70 ? "var(--accent-muted)" : pct >= 50 ? "rgba(251,191,36,0.2)" : "rgba(248,113,113,0.2)"}`,
        background: pct >= 70 ? "var(--accent-glow)" : pct >= 50 ? "rgba(251,191,36,0.05)" : "rgba(248,113,113,0.05)",
        padding: "2px 8px", borderRadius: 4, textTransform: "uppercase" 
      }}>
        {label}
      </span>
    </div>
  );
}

function StageTracker({ status }: { status: string }) {
  const activeIdx = STATUS_STAGE_INDEX[status] ?? -1;
  const isDone = status === "complete";
  
  return (
    <div style={{ display: "flex", gap: 8, margin: "22px 0 8px" }}>
      {STAGES.map((stage, i) => {
        const Icon = stage.icon;
        const done   = isDone || i < activeIdx;
        const active = i === activeIdx && !isDone;
        
        return (
          <div key={stage.key} style={{
            flex: 1, textAlign: "center", padding: "12px 6px 10px",
            borderTop: `2.5px solid ${done ? "var(--accent)" : active ? "#ffffff" : "var(--border-soft)"}`,
            color: done ? "var(--accent)" : active ? "#ffffff" : "var(--text-muted)",
            fontSize: "0.76rem", fontWeight: active ? 800 : 500,
            background: active ? "var(--accent-glow)" : "transparent",
            borderRadius: "0 0 10px 10px",
            transition: "all 0.3s cubic-bezier(0.4, 0, 0.2, 1)",
            boxShadow: active ? "0 4px 12px var(--accent-glow)" : "none",
          }}>
            <Icon size={15} style={{
              display: "block", margin: "0 auto 6px",
              color: done ? "var(--accent)" : active ? "#ffffff" : "var(--text-muted)",
              transform: active ? "scale(1.12)" : "none",
              transition: "all 0.3s ease"
            }} className={active ? "animate-pulse" : undefined} />
            {stage.label}
          </div>
        );
      })}
    </div>
  );
}

function MetricCard({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="card" style={{
      padding: "16px 20px", textAlign: "center", display: "flex", flexDirection: "column",
      justifyContent: "center", gap: 4, borderRadius: "var(--radius)", background: "rgba(17, 18, 21, 0.4)"
    }}>
      <div style={{ fontSize: "1.6rem", fontWeight: 900, color: "var(--text-primary)", letterSpacing: "-0.01em" }}>
        {value ?? "—"}
      </div>
      <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)", fontWeight: 500, textTransform: "uppercase", letterSpacing: "0.03em" }}>
        {label}
      </div>
    </div>
  );
}

function StatusPill({ status }: { status: string }) {
  const isRunning = ["running", "planning", "searching", "extracting", "synthesizing", "validating"].includes(status);
  const displayStatus = isRunning ? "running" : status;

  const cfg: Record<string, { bg: string; color: string; icon: React.ReactNode }> = {
    complete: { bg: "var(--accent-glow)",  color: "var(--accent)", icon: <CheckCheck size={12} /> },
    running:  { bg: "rgba(255,255,255,.03)",  color: "#ffffff", icon: <Loader2 size={12} className="animate-spin" /> },
    error:    { bg: "rgba(248,113,113,.08)", color: "#f87171", icon: <XCircle size={12} /> },
  };
  
  const c = cfg[displayStatus] ?? { bg: "var(--bg-elevated)", color: "var(--text-secondary)", icon: null };
  const label = isRunning 
    ? (status === "running" ? "Running" : `${status.charAt(0).toUpperCase() + status.slice(1)}…`) 
    : status.charAt(0).toUpperCase() + status.slice(1);

  return (
    <span style={{
      display: "inline-flex", alignItems: "center", gap: 6,
      background: c.bg, color: c.color, border: `1px solid ${c.color}25`,
      padding: "6px 14px", borderRadius: 24, fontSize: "0.78rem", fontWeight: 700,
      boxShadow: isRunning ? "0 0 10px rgba(255, 255, 255, 0.02)" : "none",
    }}>
      {c.icon}{label}
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
        <div style={{ display: "flex", gap: 6 }}>
          <div className="terminal-dot red" />
          <div className="terminal-dot yellow" />
          <div className="terminal-dot green" />
        </div>
        <span style={{ fontSize: "0.72rem", fontFamily: "'JetBrains Mono', monospace", color: "var(--text-muted)", fontWeight: 500 }}>
          ScholarNode Pipeline Activity Logs
        </span>
        <button 
          onClick={handleCopy}
          className="btn btn-secondary btn-sm"
          style={{ padding: "4px 8px", gap: 4, height: 22, fontSize: "0.68rem", borderRadius: 4, border: "1px solid var(--border)" }}
        >
          {copied ? <ClipboardCheck size={11} color="var(--accent)" /> : <Copy size={11} />}
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
      <div ref={ref} style={{
        fontFamily: "'JetBrains Mono', monospace", fontSize: "0.76rem",
        maxHeight: 260, overflowY: "auto", color: "#e4e4e7", display: "flex", flexDirection: "column", gap: 5, padding: "4px 0"
      }}>
        {entries.length === 0 ? (
          <div style={{ color: "var(--text-muted)", padding: "10px 0", textAlign: "center" }}>Initializing process log stream...</div>
        ) : (
          entries.slice(-50).map((e, i) => (
            <div key={i} style={{
              padding: "2px 0 2px 10px", margin: 0,
              borderLeft: `2.5px solid ${AGENT_COLORS[e.agent] ?? "var(--border-dim)"}`,
              lineHeight: 1.5
            }}>
              <span style={{ color: AGENT_COLORS[e.agent] ?? "var(--text-secondary)", fontWeight: 600, marginRight: 8, letterSpacing: "-0.01em" }}>
                [{e.agent.toUpperCase()}]
              </span>
              {e.message}
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

  return (
    <div style={{ display: "flex", gap: 8 }}>
      <button className="btn btn-secondary btn-sm" onClick={() => downloadFile("md")}>
        <Download size={13} /> Markdown
      </button>
      <button className="btn btn-secondary btn-sm" onClick={() => downloadFile("docx")}>
        <Download size={13} /> Word (.docx)
      </button>
      <button className="btn btn-secondary btn-sm" onClick={downloadJson}>
        <Download size={13} /> JSON Data
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
      <div className="card" style={{ marginBottom: 16 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 12 }}>
          <div>
            <div style={{ fontSize: "1.1rem", fontWeight: 700, color: "var(--text-primary)" }}>{topic}</div>
            <div style={{ fontSize: "0.76rem", color: "var(--text-muted)", marginTop: 3, fontFamily: "monospace" }}>
              Session: {sessionId.slice(0, 8)}…
            </div>
          </div>
          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <StatusPill status={status} />
            <button className="btn btn-ghost btn-sm" onClick={onClear}><X size={14} /></button>
          </div>
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
        <button
          onClick={() => setLogOpen(v => !v)}
          style={{
            display: "flex", alignItems: "center", gap: 6, background: "none",
            border: "none", color: "var(--text-secondary)", cursor: "pointer",
            fontSize: "0.86rem", fontWeight: 600, width: "100%", outline: "none"
          }}
        >
          {logOpen ? <ChevronUp size={14} color="var(--accent)" /> : <ChevronDown size={14} color="var(--accent)" />}
          Activity Logs ({progress.length} entries)
        </button>
        {logOpen && (
          <div style={{ marginTop: 12 }}>
            <LiveLog entries={progress} />
          </div>
        )}
      </div>

      {/* Complete state */}
      {status === "complete" && report && (
        <div className="animate-fade">
          <div style={{
            background: "var(--accent-glow)", border: "1px solid var(--accent-muted)",
            borderRadius: "var(--radius-lg)", padding: "14px 20px",
            display: "flex", alignItems: "center", justifyItems: "center", justifyContent: "space-between",
            marginBottom: 16,
            boxShadow: "0 4px 16px var(--accent-glow)"
          }}>
            <span style={{ color: "var(--accent)", fontWeight: 700, fontSize: "0.92rem", display: "inline-flex", alignItems: "center", gap: 6 }}>
              🎉 Research completed successfully! Confidence: {Math.round(conf * 100)}%
            </span>
            <div style={{ display: "flex", gap: 8 }}>
              <ExportButtons sessionId={sessionId} report={report} />
              <button className="btn btn-secondary btn-sm" onClick={() => continueResearch(sessionId).then(fetchData)}>
                <RefreshCw size={13} /> Continue Research
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
  onSessionStart: (id: string, topic: string) => void;
  activeSessionId: string | null;
  activeTopic: string;
  onClearSession: () => void;
}) {
  const [topic, setTopic] = useState("");
  const [loading, setLoading] = useState(false);
  const [activeStep, setActiveStep] = useState<number | null>(null); // for interactive diagram
  const startingRef = useRef(false); // guard against double-click

  const handleStart = async () => {
    if (!topic.trim() || loading || startingRef.current || !!activeSessionId) return;
    startingRef.current = true;
    setLoading(true);
    try {
      const { session_id } = await startResearch(topic.trim());
      onSessionStart(session_id, topic.trim());
    } catch (e) {
      alert(`Failed to start research: ${e}`);
    } finally {
      setLoading(false);
      startingRef.current = false;
    }
  };

  const diagramSteps = [
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
      engine: "Groq Llama 3.3 70B (High-Volume Free Tier)",
      desc: "Processes source paragraphs using an ultra-fast LLM. It extracts atomic fact-claims, assigns truth ratings, and records exact paragraph locations for strict citation mapping.",
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
      {/* Hero */}
      <div style={{ textAlign: "center", padding: "64px 0 44px", position: "relative" }}>
        {/* Ambient background glow */}
        <div style={{
          position: "absolute", top: "5%", left: "50%", transform: "translateX(-50%)",
          width: 320, height: 320, background: "radial-gradient(circle, rgba(186,255,57,0.06) 0%, rgba(0,0,0,0) 75%)",
          zIndex: -1, pointerEvents: "none"
        }} />
        
        <div style={{ display: "inline-flex", alignItems: "center", gap: 10, marginBottom: 24 }}>
          <div style={{
            width: 60, height: 60, borderRadius: 18,
            background: "linear-gradient(135deg, var(--accent), var(--accent-light))",
            display: "flex", alignItems: "center", justifyContent: "center",
            boxShadow: "0 0 35px var(--accent-glow)",
          }}>
            <FlaskConical size={28} color="#000000" />
          </div>
        </div>
        
        <h1 style={{
          fontSize: "3.4rem", fontWeight: 900, letterSpacing: "-0.03em", lineHeight: 1.15, marginBottom: 16,
          background: "linear-gradient(135deg, #ffffff 30%, var(--accent) 75%, var(--border-dim) 100%)",
          WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent", backgroundClip: "text",
        }}>
          ScholarNode AI
        </h1>
        
        <p style={{ color: "var(--text-secondary)", fontSize: "1.05rem", maxWidth: 540, margin: "0 auto 36px", lineHeight: 1.6 }}>
          Explore the frontiers of science. Generate fully cited, validated research reports in minutes powered by Gemini's free tier with automated fallback.
        </p>

        {/* Suggestion chips */}
        <div style={{
          display: "flex", flexWrap: "wrap", gap: 10, justifyContent: "center",
          maxWidth: 700, margin: "0 auto 36px",
        }}>
          {SUGGESTIONS.map((s, i) => (
            <button
              key={i}
              onClick={() => setTopic(s.text)}
              style={{
                background: "rgba(17, 18, 21, 0.5)",
                border: "1px solid var(--border)",
                borderRadius: 24, padding: "8px 18px",
                fontSize: "0.84rem", color: "var(--text-secondary)", cursor: "pointer",
                transition: "all .2s ease",
                display: "flex", alignItems: "center", gap: 6, fontFamily: "inherit",
              }}
              onMouseEnter={e => {
                (e.currentTarget as HTMLButtonElement).style.borderColor = "var(--accent)";
                (e.currentTarget as HTMLButtonElement).style.color = "var(--accent)";
                (e.currentTarget as HTMLButtonElement).style.transform = "translateY(-1px)";
                (e.currentTarget as HTMLButtonElement).style.boxShadow = "0 4px 12px var(--accent-glow)";
              }}
              onMouseLeave={e => {
                (e.currentTarget as HTMLButtonElement).style.borderColor = "var(--border)";
                (e.currentTarget as HTMLButtonElement).style.color = "var(--text-secondary)";
                (e.currentTarget as HTMLButtonElement).style.transform = "none";
                (e.currentTarget as HTMLButtonElement).style.boxShadow = "none";
              }}
            >
              <span>{s.icon}</span> {s.text}
            </button>
          ))}
        </div>

        {/* Input area */}
        <div style={{ maxWidth: 680, margin: "0 auto" }}>
          <div style={{
            background: "var(--bg-surface)",
            border: "1px solid var(--border)",
            borderRadius: 16, padding: "3px",
            boxShadow: "inset 0 2px 4px rgba(0,0,0,0.5)",
            transition: "all 0.3s ease",
            marginBottom: 16
          }}
          onFocusCapture={e => {
            e.currentTarget.style.borderColor = "var(--accent)";
            e.currentTarget.style.boxShadow = "0 0 16px var(--accent-glow)";
          }}
          onBlurCapture={e => {
            e.currentTarget.style.borderColor = "var(--border)";
            e.currentTarget.style.boxShadow = "inset 0 2px 4px rgba(0,0,0,0.5)";
          }}
          >
            <textarea
              value={topic}
              onChange={e => setTopic(e.target.value)}
              onKeyDown={e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleStart(); } }}
              placeholder="Enter query..."
              rows={2}
              style={{
                width: "100%", padding: "14px 16px",
                background: "transparent", border: "none",
                borderRadius: 13, color: "var(--text-primary)",
                fontSize: "1rem", resize: "none", fontFamily: "inherit",
                outline: "none", lineHeight: 1.5,
              }}
            />
          </div>
          <button
            className="btn btn-primary btn-lg btn-full"
            onClick={handleStart}
            disabled={!topic.trim() || loading || !!activeSessionId}
            style={{
              borderRadius: 14,
              border: "none",
            }}
          >
            {loading ? <Loader2 size={18} className="animate-spin" /> : <Play size={18} />}
            {loading ? "Starting…" : activeSessionId ? "Research Running…" : "Start Research"}
          </button>
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

  return (
    <div>
      {/* Page header */}
      <div style={{
        marginBottom: 28,
        paddingBottom: 24,
        borderBottom: "1px solid var(--border-soft)"
      }}>
        <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 16 }}>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 6 }}>
              <div style={{
                width: 32, height: 32, borderRadius: 8,
                background: "rgba(96, 165, 250, 0.1)",
                border: "1px solid rgba(96, 165, 250, 0.2)",
                display: "flex", alignItems: "center", justifyContent: "center",
              }}>
                <History size={16} color="var(--accent)" />
              </div>
              <h2 style={{ fontSize: "1.4rem", fontWeight: 800, letterSpacing: "-0.02em" }}>Research History</h2>
            </div>
            <p style={{ fontSize: "0.85rem", color: "var(--text-muted)", margin: 0 }}>
              All your past and active research sessions — {sessions.length} total
            </p>
          </div>
          <button className="btn btn-secondary btn-sm" onClick={() => fileInputRef.current?.click()} style={{ gap: 5, flexShrink: 0 }}>
            <Download size={13} style={{ transform: "rotate(180deg)" }} /> Import Session
          </button>
          <input type="file" ref={fileInputRef} onChange={handleImport} accept=".json" style={{ display: "none" }} />
        </div>

        {/* Filter tabs */}
        <div style={{ display: "flex", gap: 6, marginTop: 20 }}>
          {(["all", "complete", "running", "error"] as const).map(f => {
            const isActive = filter === f;
            const filterColors: Record<string, string> = {
              all: "var(--accent)",
              complete: "#4ade80",
              running: "#fbbf24",
              error: "#f87171",
            };
            const accentColor = filterColors[f];
            return (
              <button
                key={f}
                onClick={() => setFilter(f)}
                style={{
                  display: "inline-flex", alignItems: "center", gap: 6,
                  padding: "7px 14px", borderRadius: 8,
                  border: isActive ? `1px solid ${accentColor}50` : "1px solid var(--border-soft)",
                  background: isActive ? `${accentColor}12` : "var(--bg-surface)",
                  color: isActive ? accentColor : "var(--text-secondary)",
                  fontSize: "0.82rem", fontWeight: isActive ? 700 : 500,
                  cursor: "pointer", transition: "all 0.2s ease", fontFamily: "inherit",
                }}
              >
                {FILTER_ICONS[f]}
                {FILTER_LABELS[f]}
                <span style={{
                  background: isActive ? `${accentColor}20` : "rgba(255,255,255,0.04)",
                  color: isActive ? accentColor : "var(--text-muted)",
                  borderRadius: 10, padding: "1px 7px", fontSize: "0.72rem", fontWeight: 700,
                }}>
                  {counts[f]}
                </span>
              </button>
            );
          })}
          <button
            className="btn btn-ghost btn-sm"
            onClick={load}
            style={{ marginLeft: "auto" }}
            title="Refresh"
          >
            <RefreshCw size={13} />
          </button>
        </div>
      </div>

      {loading ? (
        <div style={{ textAlign: "center", padding: 48, color: "var(--text-muted)" }}>
          <Loader2 size={24} className="animate-spin" style={{ margin: "0 auto 12px", color: "var(--accent)" }} />
          <p style={{ fontSize: "0.85rem" }}>Loading sessions…</p>
        </div>
      ) : shown.length === 0 ? (
        <div style={{
          textAlign: "center", padding: "56px 24px",
          background: "var(--bg-surface)", borderRadius: "var(--radius-lg)",
          border: "1px dashed var(--border)",
        }}>
          <BookOpen size={36} style={{ margin: "0 auto 14px", opacity: .2, color: "var(--accent)" }} />
          <p style={{ color: "var(--text-muted)", fontWeight: 500 }}>
            {filter === "all" ? "No sessions yet. Start a research run!" : `No ${FILTER_LABELS[filter].toLowerCase()} sessions.`}
          </p>
          {filter !== "all" && (
            <button className="btn btn-ghost btn-sm" onClick={() => setFilter("all")} style={{ marginTop: 10 }}>
              View all sessions
            </button>
          )}
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {shown.map(s => (
            <div key={s.id} className="card" style={{ padding: "14px 20px" }}>
              <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 12 }}>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: "0.92rem", fontWeight: 600, marginBottom: 6, color: "var(--text-primary)", lineHeight: 1.4 }}>
                    {s.topic}
                  </div>
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 12, fontSize: "0.75rem", color: "var(--text-secondary)" }}>
                    <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
                      <Clock size={11} /> {new Date(s.created_at).toLocaleString()}
                    </span>
                    {(s.confidence ?? 0) > 0 && (
                      <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
                        <Zap size={11} color="var(--accent)" /> {Math.round((s.confidence ?? 0) * 100)}% confidence
                      </span>
                    )}
                    {s.findings > 0 && <span style={{ display: "flex", alignItems: "center", gap: 4 }}><Microscope size={11} /> {s.findings} findings</span>}
                    {s.sources > 0 && <span style={{ display: "flex", alignItems: "center", gap: 4 }}><BookOpen size={11} /> {s.sources} sources</span>}
                  </div>
                </div>
                <div style={{ display: "flex", gap: 6, alignItems: "center", flexShrink: 0 }}>
                  <StatusPill status={s.status} />
                  {s.status === "complete" && (
                    <button className="btn btn-secondary btn-sm" onClick={() => onView(s.id)}>
                      <ArrowRight size={13} /> View Report
                    </button>
                  )}
                  <button className="btn btn-secondary btn-sm" onClick={() => handleContinue(s.id)} title="Continue research">
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
function ViewerTab({ initialSessionId }: { initialSessionId?: string }) {
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
      <div style={{
        marginBottom: 28,
        paddingBottom: 24,
        borderBottom: "1px solid var(--border-soft)"
      }}>
        <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 16, flexWrap: "wrap" }}>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 6 }}>
              <div style={{
                width: 32, height: 32, borderRadius: 8,
                background: "rgba(59, 130, 246, 0.1)",
                border: "1px solid rgba(59, 130, 246, 0.2)",
                display: "flex", alignItems: "center", justifyContent: "center",
              }}>
                <FileText size={16} color="var(--accent)" />
              </div>
              <h2 style={{ fontSize: "1.4rem", fontWeight: 800, letterSpacing: "-0.02em" }}>Report Viewer</h2>
            </div>
            <p style={{ fontSize: "0.85rem", color: "var(--text-muted)", margin: 0 }}>
              {sessions.length === 0 ? "No completed reports yet" : `${sessions.length} completed report${sessions.length !== 1 ? "s" : ""} available`}
            </p>
          </div>
          <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
            <button className="btn btn-secondary btn-sm" onClick={() => fileInputRef.current?.click()} style={{ gap: 5 }}>
              <Download size={13} style={{ transform: "rotate(180deg)" }} /> Import Report
            </button>
            <input type="file" ref={fileInputRef} onChange={handleImport} accept=".json" style={{ display: "none" }} />
            {sessions.length > 0 && (
              <select
                value={selectedId}
                onChange={e => setSelectedId(e.target.value)}
                style={{
                  background: "var(--bg-surface)", border: "1px solid var(--border)",
                  color: "var(--text-primary)", padding: "8px 14px", borderRadius: "var(--radius)",
                  fontSize: "0.85rem", fontFamily: "inherit", cursor: "pointer", maxWidth: 420,
                  outline: "none",
                }}
              >
                {sessions.map(s => (
                  <option key={s.id} value={s.id}>
                    {s.topic.slice(0, 55)} — {new Date(s.created_at).toLocaleDateString()}
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

  const handleSessionStart = (id: string, topic: string) => {
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

  return (
    <div className={activeThemeClass} style={{ minHeight: "100vh", background: "var(--bg-base)", display: "flex", flexDirection: "column" }}>
      {/* Nav */}
      <nav style={{
        borderBottom: "1px solid var(--border)", padding: "0 24px",
        background: "rgba(10, 11, 13, 0.85)",
        position: "sticky", top: 0, zIndex: 100,
        backdropFilter: "blur(12px)",
        boxShadow: "0 4px 30px rgba(0, 0, 0, 0.3)",
      }}>
        <div style={{ maxWidth: 1100, margin: "0 auto", display: "flex", alignItems: "center", height: 56 }}>
          {/* Logo */}
          <div style={{ display: "flex", alignItems: "center", gap: 10, marginRight: 40 }}>
            <div style={{
              width: 30, height: 30, borderRadius: 8,
              background: "linear-gradient(135deg, var(--accent), var(--accent-light))",
              display: "flex", alignItems: "center", justifyContent: "center",
            }}>
              <Sparkles size={14} color="#000000" />
            </div>
            <span style={{ fontWeight: 800, fontSize: "0.98rem", letterSpacing: "-0.01em" }}>ScholarNode AI</span>
          </div>

          {/* Tabs */}
          <div style={{ display: "flex", gap: 4, flex: 1 }}>
            {TABS.map(t => {
              const Icon = t.icon;
              return (
                <button
                  key={t.key}
                  onClick={() => setTab(t.key)}
                  style={{
                    display: "flex", alignItems: "center", gap: 6, padding: "8px 14px",
                    background: tab === t.key ? "var(--accent-glow)" : "none",
                    border: tab === t.key ? "1px solid var(--accent-muted)" : "1px solid transparent",
                    borderRadius: "var(--radius)", color: tab === t.key ? "var(--accent)" : "var(--text-secondary)",
                    cursor: "pointer", fontSize: "0.85rem", fontFamily: "inherit", fontWeight: tab === t.key ? 700 : 500,
                    transition: "all 0.15s ease",
                  }}
                >
                  <Icon size={14} />
                  {t.label}
                  {t.key === "history" && sessions.length > 0 && (
                    <span style={{
                      background: "rgba(255, 255, 255, 0.05)", borderRadius: 10,
                      padding: "1px 6px", fontSize: "0.68rem", color: "var(--text-secondary)", marginLeft: 2
                    }}>{sessions.length}</span>
                  )}
                </button>
              );
            })}
          </div>

          {/* API status */}
          <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: "0.78rem" }}>
            {healthy === null ? (
              <span style={{ color: "var(--text-muted)" }}>Checking…</span>
            ) : healthy ? (
              <><Wifi size={13} color="var(--accent)" /><span style={{ color: "var(--accent)", fontWeight: 600 }}>API Online</span></>
            ) : (
              <><WifiOff size={13} color="#f87171" /><span style={{ color: "#f87171", fontWeight: 600 }}>API Offline</span></>
            )}
          </div>
        </div>
      </nav>

      {/* Content */}
      <main style={{ flex: 1, padding: "0 24px 48px" }}>
        <div style={{ maxWidth: 1100, margin: "0 auto" }}>
          {/* API offline warning */}
          {healthy === false && (
            <div style={{
              margin: "16px 0",
              background: "rgba(248,113,113,.08)", border: "1px solid rgba(248,113,113,.2)",
              borderRadius: "var(--radius)", padding: "12px 16px",
              color: "#f87171", fontSize: "0.85rem",
              display: "flex", alignItems: "center", gap: 8,
            }}>
              <WifiOff size={14} />
              API is offline. Run: <code style={{ background: "var(--bg-elevated)", padding: "2px 6px", borderRadius: 4, color: "#f87171", border: "1px solid rgba(248,113,113,.15)" }}>uvicorn api.server:app --reload</code>
            </div>
          )}

          <div style={{ paddingTop: 24 }}>
            {tab === "research" && <ResearchTab
              onSessionStart={handleSessionStart}
              activeSessionId={activeSessionId}
              activeTopic={activeTopic}
              onClearSession={handleClearSession}
            />}
            {tab === "history"  && <HistoryTab onView={handleViewSession} />}
            {tab === "viewer"   && <ViewerTab initialSessionId={viewerSessionId} />}
          </div>
        </div>
      </main>
    </div>
  );
}
