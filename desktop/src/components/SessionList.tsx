import { useEffect, useState } from "react";
import { apiGet, apiPost } from "../api/client";

export type SessionSummary = {
  session_id: string;
  title?: string;
  updated_at: string;
};

export function SessionList({
  selectedSessionId,
  onSelectSession,
  onNewSession,
}: {
  selectedSessionId: string | null;
  onSelectSession: (sessionId: string) => void;
  onNewSession: (sessionId: string) => void;
}) {
  const [sessions, setSessions] = useState<SessionSummary[]>([]);

  async function loadSessions() {
    const result = await apiGet<{ sessions: SessionSummary[] }>("/api/v1/sessions");
    setSessions(result.sessions);
  }

  useEffect(() => {
    loadSessions();
  }, [selectedSessionId]);

  async function createSession() {
    const result = await apiPost<{ session_id: string }>("/api/v1/sessions");
    onNewSession(result.session_id);
    await loadSessions();
  }

  return (
    <div className="session-list">
      <div className="session-list-header">
        <span>对话</span>
        <button onClick={createSession}>新建</button>
      </div>
      <div className="session-items">
        {sessions.map((session) => (
          <button
            key={session.session_id}
            className={`session-item ${session.session_id === selectedSessionId ? "active" : ""}`}
            onClick={() => onSelectSession(session.session_id)}
          >
            <span className="session-title">{session.title || "新对话"}</span>
            <span className="session-time">{new Date(session.updated_at).toLocaleString()}</span>
          </button>
        ))}
      </div>
    </div>
  );
}
