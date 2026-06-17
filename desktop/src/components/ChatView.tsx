import { useEffect, useRef, useState } from "react";
import { apiGet, apiPost, getBaseUrl } from "../api/client";
import type { ChatMessage, Source } from "../types";

function obsidianUrl(vaultPath: string, sourcePath: string): string | null {
  if (!sourcePath.endsWith(".md")) return null;
  const vaultName = vaultPath.split("/").filter(Boolean).at(-1);
  if (!vaultName) return null;
  const marker = `${vaultName}/`;
  const idx = sourcePath.indexOf(marker);
  const relative = idx >= 0 ? sourcePath.slice(idx + marker.length) : sourcePath;
  return `obsidian://open?vault=${encodeURIComponent(vaultName)}&file=${encodeURIComponent(relative)}`;
}

function SourceItem({ source, vaultPath }: { source: Source; vaultPath: string }) {
  async function open() {
    const sourcePath = source.source || "";
    const url = obsidianUrl(vaultPath, sourcePath);
    if (url) {
      await window.secondbrain.openExternal(url);
    } else if (sourcePath) {
      await window.secondbrain.openPath(sourcePath);
    }
  }

  return (
    <button className="source-chip" onClick={open}>
      <span className="source-title">{source.title || source.source || "来源"}</span>
      {source.score !== undefined && <span className="source-score">{source.score.toFixed(3)}</span>}
    </button>
  );
}

export function ChatView({ vaultPath }: { vaultPath: string }) {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const bottomRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function sendMessage() {
    const query = input.trim();
    if (!query || streaming) return;

    setInput("");
    setStreaming(true);

    const currentSession = sessionId || (await apiPost<{ session_id: string }>("/api/v1/sessions")).session_id;
    if (currentSession !== sessionId) {
      setSessionId(currentSession);
    }

    setMessages((prev) => [...prev, { role: "user", content: query }]);

    const baseUrl = await getBaseUrl();
    const response = await fetch(`${baseUrl}/api/v1/chat/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query, session_id: currentSession }),
    });

    if (!response.body) {
      setStreaming(false);
      return;
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder("utf-8");
    let answer = "";
    let sources: Source[] = [];
    let buffer = "";

    setMessages((prev) => [...prev, { role: "assistant", content: "", sources: [] }]);

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";

      for (const line of lines) {
        if (!line.startsWith("data: ")) continue;
        const payload = line.slice(6).trim();
        if (!payload) continue;
        try {
          const event = JSON.parse(payload);
          if (event.type === "answer" && event.content) {
            answer += event.content;
            setMessages((prev) => {
              const next = [...prev];
              const last = next[next.length - 1];
              if (last && last.role === "assistant") {
                last.content = answer;
                last.sources = sources;
              }
              return next;
            });
          } else if (event.type === "sources" && Array.isArray(event.data)) {
            sources = event.data;
            setMessages((prev) => {
              const next = [...prev];
              const last = next[next.length - 1];
              if (last && last.role === "assistant") {
                last.sources = sources;
              }
              return next;
            });
          }
        } catch {
          // ignore malformed event
        }
      }
    }

    setStreaming(false);
  }

  return (
    <div className="chat-view">
      <div className="chat-messages">
        {messages.map((m, idx) => (
          <div key={idx} className={`message ${m.role}`}>
            <div className="message-content">{m.content}</div>
            {m.sources && m.sources.length > 0 && (
              <div className="message-sources">
                {m.sources.map((s, sidx) => (
                  <SourceItem key={sidx} source={s} vaultPath={vaultPath} />
                ))}
              </div>
            )}
          </div>
        ))}
        <div ref={bottomRef} />
      </div>

      <div className="chat-input-bar">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && sendMessage()}
          placeholder="输入问题..."
          disabled={streaming}
        />
        <button onClick={sendMessage} disabled={streaming || !input.trim()}>
          发送
        </button>
      </div>
    </div>
  );
}
