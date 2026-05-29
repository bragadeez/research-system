import type { ChatMessage, ChatResponse, ResearchMode } from "../types";


const API_BASE = "http://localhost:8000";

export async function startResearch(
  topic: string,
  researchMode: ResearchMode = "standard"
): Promise<{ session_id: string; status: string }> {
  const res = await fetch(`${API_BASE}/api/research`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ topic, research_mode: researchMode }),
  });
  if (!res.ok) throw new Error(`Failed to start research: ${res.statusText}`);
  return res.json();
}

export async function getResearch(sessionId: string) {
  const res = await fetch(`${API_BASE}/api/research/${sessionId}`);
  if (!res.ok) throw new Error(`Failed to fetch research: ${res.statusText}`);
  return res.json();
}

export async function listSessions(limit = 50) {
  const res = await fetch(`${API_BASE}/api/sessions?limit=${limit}`);
  if (!res.ok) throw new Error("Failed to list sessions");
  return res.json();
}

export async function deleteSession(sessionId: string) {
  const res = await fetch(`${API_BASE}/api/sessions/${sessionId}`, { method: "DELETE" });
  if (!res.ok) throw new Error("Failed to delete session");
  return res.json();
}

export async function continueResearch(sessionId: string) {
  const res = await fetch(`${API_BASE}/api/research/${sessionId}/continue`, { method: "POST" });
  if (!res.ok) throw new Error("Failed to continue research");
  return res.json();
}

export async function checkHealth() {
  try {
    const res = await fetch(`${API_BASE}/health`, { signal: AbortSignal.timeout(4000) });
    return res.ok ? res.json() : null;
  } catch {
    return null;
  }
}

export function getExportUrl(sessionId: string, format: "md" | "docx") {
  return `${API_BASE}/api/export/${sessionId}/${format}`;
}

export function createWebSocket(sessionId: string): WebSocket {
  return new WebSocket(`ws://localhost:8000/ws/${sessionId}`);
}

export async function importResearch(payload: any): Promise<{ session_id: string; status: string }> {
  const res = await fetch(`${API_BASE}/api/import`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(`Failed to import research: ${res.statusText}`);
  return res.json();
}

// ── Chat RAG APIs ────────────────────────────────────────────────────────────

export async function chatWithReport(sessionId: string, message: string): Promise<ChatResponse> {
  const res = await fetch(`${API_BASE}/api/research/${sessionId}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message }),
  });
  if (!res.ok) throw new Error(`Failed to send message: ${res.statusText}`);
  return res.json();
}

export async function getChatHistory(sessionId: string): Promise<{ history: ChatMessage[] }> {
  const res = await fetch(`${API_BASE}/api/research/${sessionId}/chat/history`);
  if (!res.ok) throw new Error(`Failed to load chat history: ${res.statusText}`);
  return res.json();
}

export async function clearChatHistory(sessionId: string): Promise<{ status: string }> {
  const res = await fetch(`${API_BASE}/api/research/${sessionId}/chat`, { method: "DELETE" });
  if (!res.ok) throw new Error(`Failed to clear chat history: ${res.statusText}`);
  return res.json();
}

export async function buildChatIndex(sessionId: string): Promise<{ status: string }> {
  const res = await fetch(`${API_BASE}/api/research/${sessionId}/chat/build`, { method: "POST" });
  if (!res.ok) throw new Error(`Failed to build vector store: ${res.statusText}`);
  return res.json();
}


