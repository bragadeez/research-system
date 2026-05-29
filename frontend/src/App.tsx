// src/App.tsx
import { useState, useEffect, useCallback, useRef } from "react";
import {
  FlaskConical, History, FileText, Wifi, WifiOff,
  Search, Brain, Microscope, BarChart2, PenLine, CheckCircle2,
  Loader2, CheckCheck, XCircle, HelpCircle, Download, RefreshCw,
  Trash2, ChevronDown, ChevronUp, X, Play, ArrowRight,
  Sparkles, Clock, BookOpen, Zap,
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
  planner:    "#a78bfa",
  search:     "#60a5fa",
  extraction: "#22d3ee",
  aggregator: "#4ade80",
  synthesis:  "#34d399",
  critic:     "#fbbf24",
  ranker:     "#c084fc",
  system:     "#484f58",
};

// ─── Helper Components ───────────────────────────────────────────────────────
function ConfidenceBar({ value }: { value: number }) {
  const pct = Math.round(value * 100);
  const color = pct >= 75 ? "#4ade80" : pct >= 55 ? "#fbbf24" : "#f87171";
  const label = pct >= 80 ? "High" : pct >= 65 ? "Good" : pct >= 50 ? "Fair" : "Low";
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 10, margin: "6px 0" }}>
      <span style={{ fontSize: "0.75rem", color: "var(--text-secondary)", minWidth: 72 }}>Confidence</span>
      <div style={{ flex: 1, height: 5, background: "var(--bg-hover)", borderRadius: 3, overflow: "hidden" }}>
        <div style={{ width: `${pct}%`, height: "100%", background: color, borderRadius: 3, transition: "width 0.5s ease" }} />
      </div>
      <span style={{ fontSize: "0.92rem", fontWeight: 700, color }}>{pct}%</span>
      <span style={{ fontSize: "0.72rem", fontWeight: 600, color }}>{label}</span>
    </div>
  );
}

function StageTracker({ status }: { status: string }) {
  const activeIdx = STATUS_STAGE_INDEX[status] ?? -1;
  const isDone = status === "complete";
  return (
    <div style={{ display: "flex", gap: 0, margin: "14px 0 4px" }}>
      {STAGES.map((stage, i) => {
        const Icon = stage.icon;
        const done   = isDone || i < activeIdx;
        const active = i === activeIdx && !isDone;
        return (
          <div key={stage.key} style={{
            flex: 1, textAlign: "center", padding: "8px 4px",
            borderTop: `2px solid ${done ? "#4ade80" : active ? "#7c3aed" : "#21262d"}`,
            color: done ? "#4ade80" : active ? "#a78bfa" : "#484f58",
            fontSize: "0.68rem", fontWeight: active ? 700 : 400,
            animation: active ? "pulse 1.4s ease-in-out infinite" : undefined,
            transition: "all .3s ease",
          }}>
            <Icon size={14} style={{ display: "block", margin: "0 auto 3px" }} />
            {stage.label}
          </div>
        );
      })}
    </div>
  );
}

function MetricCard({ label, value }: { label: string; value: string | number }) {
  return (
    <div style={{
      background: "var(--bg-elevated)", border: "1px solid var(--border)",
      borderRadius: "var(--radius)", padding: "12px 16px", textAlign: "center",
    }}>
      <div style={{ fontSize: "1.4rem", fontWeight: 800, color: "var(--text-primary)" }}>{value ?? "—"}</div>
      <div style={{ fontSize: "0.72rem", color: "var(--text-secondary)", marginTop: 2 }}>{label}</div>
    </div>
  );
}

function StatusPill({ status }: { status: string }) {
  const isRunning = ["running", "planning", "searching", "extracting", "synthesizing", "validating"].includes(status);
  const displayStatus = isRunning ? "running" : status;

  const cfg: Record<string, { bg: string; color: string; icon: React.ReactNode }> = {
    complete: { bg: "rgba(74,222,128,.1)",  color: "#4ade80", icon: <CheckCheck size={12} /> },
    running:  { bg: "rgba(96,165,250,.1)",  color: "#60a5fa", icon: <Loader2 size={12} className="animate-spin" /> },
    error:    { bg: "rgba(248,113,113,.1)", color: "#f87171", icon: <XCircle size={12} /> },
  };
  const c = cfg[displayStatus] ?? { bg: "var(--bg-elevated)", color: "var(--text-secondary)", icon: null };
  const label = isRunning 
    ? (status === "running" ? "Running" : `${status.charAt(0).toUpperCase() + status.slice(1)}...`) 
    : status.charAt(0).toUpperCase() + status.slice(1);

  return (
    <span style={{
      display: "inline-flex", alignItems: "center", gap: 5,
      background: c.bg, color: c.color,
      padding: "4px 12px", borderRadius: 20, fontSize: "0.78rem", fontWeight: 600,
    }}>
      {c.icon}{label}
    </span>
  );
}

function LiveLog({ entries }: { entries: ProgressEntry[] }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (ref.current) ref.current.scrollTop = ref.current.scrollHeight;
  }, [entries]);

  return (
    <div ref={ref} style={{
      background: "var(--bg-base)", border: "1px solid var(--border)",
      borderRadius: "var(--radius)", padding: "12px 14px",
      fontFamily: "'JetBrains Mono', monospace", fontSize: "0.75rem",
      maxHeight: 260, overflowY: "auto",
    }}>
      {entries.slice(-40).map((e, i) => (
        <div key={i} style={{
          padding: "2px 0 2px 10px", margin: "1px 0",
          color: "#c9d1d9", borderLeft: `2px solid ${AGENT_COLORS[e.agent] ?? "#30363d"}`,
        }}>
          {e.message}
        </div>
      ))}
    </div>
  );
}

function FactCheckPanel({ factChecks, critique }: { factChecks: ResearchData["report"] extends null ? never : NonNullable<ResearchData["report"]>["fact_checks"]; critique: string }) {
  const icons: Record<string, React.ReactNode> = {
    supported:   <CheckCheck size={14} color="#4ade80" />,
    unsupported: <XCircle size={14} color="#f87171" />,
    uncertain:   <HelpCircle size={14} color="#fbbf24" />,
  };
  const s = factChecks.filter(f => f.verdict === "supported").length;
  const u = factChecks.filter(f => f.verdict === "unsupported").length;
  const n = factChecks.filter(f => f.verdict === "uncertain").length;

  return (
    <div style={{ marginTop: 16 }}>
      {critique && (
        <div style={{
          background: "rgba(96,165,250,.08)", border: "1px solid rgba(96,165,250,.2)",
          borderRadius: "var(--radius)", padding: "12px 16px", marginBottom: 16,
          color: "var(--text-primary)", fontSize: "0.85rem",
        }}>
          <span style={{ color: "#60a5fa", fontWeight: 600 }}>Critic: </span>{critique}
        </div>
      )}
      <div style={{ display: "flex", gap: 10, marginBottom: 16 }}>
        {[{ label: "Supported", val: s, color: "#4ade80" }, { label: "Unsupported", val: u, color: "#f87171" }, { label: "Uncertain", val: n, color: "#fbbf24" }].map(m => (
          <div key={m.label} style={{
            flex: 1, background: "var(--bg-elevated)", border: "1px solid var(--border)",
            borderRadius: "var(--radius)", padding: "10px", textAlign: "center",
          }}>
            <div style={{ fontSize: "1.3rem", fontWeight: 800, color: m.color }}>{m.val}</div>
            <div style={{ fontSize: "0.72rem", color: "var(--text-secondary)" }}>{m.label}</div>
          </div>
        ))}
      </div>
      {factChecks.map((fc, i) => (
        <div key={i} style={{
          display: "flex", gap: 12, padding: "10px 0",
          borderBottom: i < factChecks.length - 1 ? "1px solid var(--border-soft)" : undefined,
          alignItems: "flex-start",
        }}>
          <div style={{ marginTop: 2, flexShrink: 0 }}>{icons[fc.verdict]}</div>
          <div>
            <div style={{ fontSize: "0.85rem", color: "var(--text-primary)" }}>{fc.claim}</div>
            {fc.evidence && (
              <div style={{ fontSize: "0.78rem", color: "var(--text-secondary)", marginTop: 4 }}>{fc.evidence}</div>
            )}
          </div>
        </div>
      ))}
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
        <Loader2 size={28} className="animate-spin" style={{ margin: "0 auto 12px" }} />
        Loading research data…
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
            <div style={{ fontSize: "1.05rem", fontWeight: 700, color: "var(--text-primary)" }}>{topic}</div>
            <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginTop: 3 }}>
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
            fontSize: "0.82rem", fontWeight: 500, width: "100%",
          }}
        >
          {logOpen ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
          Activity Log ({progress.length} entries)
        </button>
        {logOpen && progress.length > 0 && (
          <div style={{ marginTop: 10 }}>
            <LiveLog entries={progress} />
          </div>
        )}
      </div>

      {/* Complete state */}
      {status === "complete" && report && (
        <div className="animate-fade">
          <div style={{
            background: "rgba(74,222,128,.08)", border: "1px solid rgba(74,222,128,.2)",
            borderRadius: "var(--radius-lg)", padding: "14px 20px",
            display: "flex", alignItems: "center", justifyContent: "space-between",
            marginBottom: 16,
          }}>
            <span style={{ color: "#4ade80", fontWeight: 600 }}>
              🎉 Research complete! Confidence: {Math.round(conf * 100)}%
            </span>
            <div style={{ display: "flex", gap: 8 }}>
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
                  fontSize: "0.82rem", fontWeight: 500, width: "100%",
                }}
              >
                {evalOpen ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                🔬 LLM Evaluation — {report.fact_checks?.length ?? 0} claims fact-checked
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
          <div>Pipeline failed — check the Activity Log for details.</div>
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

  return (
    <div>
      {/* Hero */}
      <div style={{ textAlign: "center", padding: "64px 0 44px", position: "relative" }}>
        {/* Ambient background glow */}
        <div style={{
          position: "absolute", top: "5%", left: "50%", transform: "translateX(-50%)",
          width: 320, height: 320, background: "radial-gradient(circle, rgba(124,58,237,0.18) 0%, rgba(0,0,0,0) 70%)",
          zIndex: -1, pointerEvents: "none"
        }} />
        <div style={{ display: "inline-flex", alignItems: "center", gap: 10, marginBottom: 24 }}>
          <div style={{
            width: 60, height: 60, borderRadius: 16,
            background: "linear-gradient(135deg, #7c3aed, #2563eb)",
            display: "flex", alignItems: "center", justifyContent: "center",
            boxShadow: "0 0 35px rgba(124,58,237,.5)",
          }}>
            <FlaskConical size={28} color="#fff" />
          </div>
        </div>
        <h1 style={{
          fontSize: "3.2rem", fontWeight: 800, letterSpacing: "-0.03em", lineHeight: 1.15, marginBottom: 16,
          background: "linear-gradient(135deg, #c084fc, #60a5fa, #34d399)",
          WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent", backgroundClip: "text",
        }}>
          ScholarNode AI
        </h1>
        <p style={{ color: "var(--text-secondary)", fontSize: "1.05rem", maxWidth: 520, margin: "0 auto 36px", lineHeight: 1.6 }}>
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
                background: "rgba(26, 29, 36, 0.6)",
                border: "1px solid rgba(48, 54, 61, 0.8)",
                borderRadius: 20, padding: "8px 16px",
                fontSize: "0.82rem", color: "var(--text-secondary)", cursor: "pointer",
                transition: "all .2s ease",
                display: "flex", alignItems: "center", gap: 6, fontFamily: "inherit",
              }}
              onMouseEnter={e => {
                (e.currentTarget as HTMLButtonElement).style.borderColor = "#7c3aed";
                (e.currentTarget as HTMLButtonElement).style.color = "#a78bfa";
                (e.currentTarget as HTMLButtonElement).style.transform = "scale(1.02)";
              }}
              onMouseLeave={e => {
                (e.currentTarget as HTMLButtonElement).style.borderColor = "rgba(48, 54, 61, 0.8)";
                (e.currentTarget as HTMLButtonElement).style.color = "var(--text-secondary)";
                (e.currentTarget as HTMLButtonElement).style.transform = "none";
              }}
            >
              <span>{s.icon}</span> {s.text}
            </button>
          ))}
        </div>

        {/* Input area */}
        <div style={{ maxWidth: 680, margin: "0 auto" }}>
          <div style={{
            background: "linear-gradient(135deg, rgba(124, 58, 237, 0.15), rgba(37, 99, 235, 0.05))",
            border: "1px solid rgba(124, 58, 237, 0.3)",
            borderRadius: 16, padding: "3px",
            boxShadow: "0 8px 32px rgba(0, 0, 0, 0.4)",
            transition: "all 0.3s ease",
            marginBottom: 16
          }}
          onFocusCapture={e => e.currentTarget.style.borderColor = "#7c3aed"}
          onBlurCapture={e => e.currentTarget.style.borderColor = "rgba(124, 58, 237, 0.3)"}
          >
            <textarea
              value={topic}
              onChange={e => setTopic(e.target.value)}
              onKeyDown={e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleStart(); } }}
              placeholder="Enter query..."
              rows={2}
              style={{
                width: "100%", padding: "14px 16px",
                background: "var(--bg-surface)", border: "none",
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
              background: "linear-gradient(135deg, #7c3aed, #2563eb)",
              border: "none",
              boxShadow: "0 4px 20px rgba(124,58,237,0.3)",
              transition: "transform 0.2s ease, box-shadow 0.2s ease",
            }}
            onMouseEnter={e => {
              e.currentTarget.style.transform = "translateY(-1px)";
              e.currentTarget.style.boxShadow = "0 6px 24px rgba(124,58,237,0.4)";
            }}
            onMouseLeave={e => {
              e.currentTarget.style.transform = "none";
              e.currentTarget.style.boxShadow = "0 4px 20px rgba(124,58,237,0.3)";
            }}
          >
            {loading ? <Loader2 size={18} className="animate-spin" /> : <Play size={18} />}
            {loading ? "Starting…" : activeSessionId ? "Research Running…" : "Start Research"}
          </button>
        </div>
      </div>

      {/* Pipeline steps */}
      {!activeSessionId && (
        <div style={{ margin: "0 auto 24px", maxWidth: 900 }}>
          <p style={{ textAlign: "center", color: "var(--text-muted)", fontSize: "0.8rem", marginBottom: 20 }}>How it works</p>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(6, 1fr)", gap: 10 }}>
            {STAGES.map((s, i) => {
              const Icon = s.icon;
              const descs = [
                "Breaks query into structured subtopics",
                "DDG + arXiv + Semantic Scholar",
                "Gemini 3.1 Flash Lite extraction",
                "Credibility + embedding scoring",
                "Gemini 3.5 Flash report (with fallback)",
                "Fact-check + validation report",
              ];
              return (
                <div key={s.key} style={{
                  background: "var(--bg-surface)", border: "1px solid var(--border)",
                  borderRadius: "var(--radius-lg)", padding: "16px 10px", textAlign: "center",
                }}>
                  <div style={{
                    width: 36, height: 36, borderRadius: 10,
                    background: "var(--bg-elevated)", display: "flex",
                    alignItems: "center", justifyContent: "center", margin: "0 auto 10px",
                  }}>
                    <Icon size={16} color="var(--accent-light)" />
                  </div>
                  <div style={{ fontSize: "0.8rem", fontWeight: 700, marginBottom: 4 }}>{s.label}</div>
                  <div style={{ fontSize: "0.68rem", color: "var(--text-muted)" }}>{descs[i]}</div>
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

  const shown = filter === "all" ? sessions : sessions.filter(s => {
    if (filter === "running") {
      return ["running", "planning", "searching", "extracting", "synthesizing", "validating"].includes(s.status);
    }
    return s.status === filter;
  });

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
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 24 }}>
        <h2 style={{ fontSize: "1.3rem", fontWeight: 700 }}>Research History</h2>
        <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
          {/* Import JSON button */}
          <button className="btn btn-secondary btn-sm" onClick={() => fileInputRef.current?.click()} style={{ gap: 5 }}>
            <Download size={13} style={{ transform: "rotate(180deg)" }} /> Import Session
          </button>
          <input
            type="file"
            ref={fileInputRef}
            onChange={handleImport}
            accept=".json"
            style={{ display: "none" }}
          />
          <div style={{ display: "flex", gap: 6 }}>
            {(["all", "complete", "running", "error"] as const).map(f => (
              <button
                key={f}
                onClick={() => setFilter(f)}
                className={`btn btn-sm ${filter === f ? "btn-primary" : "btn-secondary"}`}
              >
                {f.charAt(0).toUpperCase() + f.slice(1)}
              </button>
            ))}
          </div>
        </div>
      </div>

      {loading ? (
        <div style={{ textAlign: "center", padding: 48, color: "var(--text-muted)" }}>
          <Loader2 size={24} className="animate-spin" style={{ margin: "0 auto" }} />
        </div>
      ) : shown.length === 0 ? (
        <div style={{ textAlign: "center", padding: 64, color: "var(--text-muted)" }}>
          <BookOpen size={32} style={{ margin: "0 auto 12px", opacity: .3 }} />
          <p>No sessions found.</p>
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          {shown.map(s => (
            <div key={s.id} className="card" style={{ padding: "14px 20px" }}>
              <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 12 }}>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: "0.92rem", fontWeight: 600, marginBottom: 4, color: "var(--text-primary)" }}>
                    {s.topic}
                  </div>
                  <div style={{ display: "flex", gap: 16, fontSize: "0.75rem", color: "var(--text-secondary)" }}>
                    <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
                      <Clock size={11} /> {new Date(s.created_at).toLocaleString()}
                    </span>
                    {s.confidence && (
                      <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
                        <Zap size={11} /> Confidence: {Math.round(s.confidence * 100)}%
                      </span>
                    )}
                    {s.findings > 0 && <span>{s.findings} findings</span>}
                    {s.sources > 0 && <span>{s.sources} sources</span>}
                  </div>
                </div>
                <div style={{ display: "flex", gap: 6, alignItems: "center", flexShrink: 0 }}>
                  <StatusPill status={s.status} />
                  {s.status === "complete" && (
                    <button className="btn btn-secondary btn-sm" onClick={() => onView(s.id)}>
                      <ArrowRight size={13} /> View
                    </button>
                  )}
                  <button className="btn btn-secondary btn-sm" onClick={() => handleContinue(s.id)}>
                    <RefreshCw size={13} />
                  </button>
                  <button className="btn btn-danger btn-sm" onClick={() => handleDelete(s.id)}>
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
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 24 }}>
        <h2 style={{ fontSize: "1.3rem", fontWeight: 700 }}>Report Viewer</h2>
        <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
          {/* Import JSON button */}
          <button className="btn btn-secondary btn-sm" onClick={() => fileInputRef.current?.click()} style={{ gap: 5 }}>
            <Download size={13} style={{ transform: "rotate(180deg)" }} /> Import Report
          </button>
          <input
            type="file"
            ref={fileInputRef}
            onChange={handleImport}
            accept=".json"
            style={{ display: "none" }}
          />
          <select
            value={selectedId}
            onChange={e => setSelectedId(e.target.value)}
            style={{
              background: "var(--bg-surface)", border: "1px solid var(--border)",
              color: "var(--text-primary)", padding: "7px 12px", borderRadius: "var(--radius)",
              fontSize: "0.85rem", fontFamily: "inherit", cursor: "pointer", maxWidth: 420,
            }}
          >
            {sessions.map(s => (
              <option key={s.id} value={s.id}>
                {s.topic.slice(0, 55)} — {new Date(s.created_at).toLocaleDateString()}
              </option>
            ))}
          </select>
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
            <span style={{ fontSize: "0.85rem", color: "var(--text-secondary)" }}>Export this report</span>
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
                  fontSize: "0.82rem", fontWeight: 500, width: "100%",
                }}
              >
                {evalOpen ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                🔬 LLM Evaluation — {report.fact_checks?.length ?? 0} claims fact-checked
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

  return (
    <div style={{ minHeight: "100vh", background: "var(--bg-base)", display: "flex", flexDirection: "column" }}>
      {/* Nav */}
      <nav style={{
        borderBottom: "1px solid rgba(124, 58, 237, 0.2)", padding: "0 24px",
        background: "rgba(17, 19, 24, 0.8)",
        position: "sticky", top: 0, zIndex: 100,
        backdropFilter: "blur(12px)",
        boxShadow: "0 4px 30px rgba(0, 0, 0, 0.2)",
      }}>
        <div style={{ maxWidth: 1100, margin: "0 auto", display: "flex", alignItems: "center", height: 56 }}>
          {/* Logo */}
          <div style={{ display: "flex", alignItems: "center", gap: 10, marginRight: 40 }}>
            <div style={{
              width: 30, height: 30, borderRadius: 8,
              background: "linear-gradient(135deg, #7c3aed, #2563eb)",
              display: "flex", alignItems: "center", justifyContent: "center",
            }}>
              <Sparkles size={14} color="#fff" />
            </div>
            <span style={{ fontWeight: 700, fontSize: "0.95rem", letterSpacing: "-0.01em" }}>ScholarNode AI</span>
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
                    background: tab === t.key ? "var(--bg-elevated)" : "none",
                    border: tab === t.key ? "1px solid var(--border)" : "1px solid transparent",
                    borderRadius: "var(--radius)", color: tab === t.key ? "var(--text-primary)" : "var(--text-secondary)",
                    cursor: "pointer", fontSize: "0.85rem", fontFamily: "inherit", fontWeight: tab === t.key ? 600 : 400,
                    transition: "all .15s ease",
                  }}
                >
                  <Icon size={14} />
                  {t.label}
                  {t.key === "history" && sessions.length > 0 && (
                    <span style={{
                      background: "var(--bg-hover)", borderRadius: 10,
                      padding: "1px 6px", fontSize: "0.68rem", color: "var(--text-muted)",
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
              <><Wifi size={13} color="#4ade80" /><span style={{ color: "#4ade80" }}>API Online</span></>
            ) : (
              <><WifiOff size={13} color="#f87171" /><span style={{ color: "#f87171" }}>API Offline</span></>
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
              API is offline. Run: <code style={{ background: "var(--bg-elevated)", padding: "2px 6px", borderRadius: 4 }}>uvicorn api.server:app --reload</code>
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
