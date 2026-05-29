// src/types/index.ts

export type ResearchMode = "standard" | "heavy";

export interface Session {
  id: string;
  topic: string;
  status: "running" | "complete" | "error" | "pending";
  created_at: string;
  updated_at: string;
  confidence: number | null;
  findings: number;
  sources: number;
  research_mode?: ResearchMode;
}

export interface FactCheck {
  claim: string;
  verdict: "supported" | "unsupported" | "uncertain";
  evidence: string;
}

export interface Report {
  id: string;
  session_id: string;
  content: string;
  critique: string;
  fact_checks: FactCheck[];
  word_count: number;
  created_at: string;
}

export interface ProgressEntry {
  id: number;
  session_id: string;
  agent: string;
  message: string;
  data: Record<string, unknown>;
  created_at: string;
}

export interface ResearchData {
  session: Session;
  report: Report | null;
  progress: ProgressEntry[];
}

export type PipelineStatus =
  | "pending"
  | "planning"
  | "searching"
  | "extracting"
  | "synthesizing"
  | "validating"
  | "complete"
  | "error";

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  created_at?: string;
}

export interface ChatSource {
  type: string;
  title: string;
  url?: string;
  snippet: string;
}

export interface ChatResponse {
  answer: string;
  sources: ChatSource[];
}

