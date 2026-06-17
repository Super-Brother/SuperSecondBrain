import { useEffect, useState } from "react";
import { apiGet } from "./api/client";
import { ChatView } from "./components/ChatView";
import { Onboarding } from "./components/Onboarding";
import { SessionList } from "./components/SessionList";
import { SettingsView } from "./components/SettingsView";
import type { DesktopStatus } from "./types";

type View = "chat" | "settings";

export function App() {
  const [status, setStatus] = useState<DesktopStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [view, setView] = useState<View>("chat");
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(null);

  useEffect(() => {
    apiGet<DesktopStatus>("/api/v1/desktop/status")
      .then((s) => {
        setStatus(s);
        setLoading(false);
      })
      .catch(() => {
        setLoading(false);
      });
  }, []);

  async function refreshStatus() {
    const s = await apiGet<DesktopStatus>("/api/v1/desktop/status");
    setStatus(s);
  }

  if (loading) {
    return (
      <main className="app-shell">
        <p>加载中...</p>
      </main>
    );
  }

  if (!status || !status.onboarding_complete) {
    return <Onboarding onDone={refreshStatus} />;
  }

  return (
    <div className="app-layout">
      <aside className="app-sidebar">
        <div className="app-brand">SecondBrain Chat</div>
        <SessionList
          selectedSessionId={selectedSessionId}
          onSelectSession={setSelectedSessionId}
          onNewSession={setSelectedSessionId}
        />
        <div className="sidebar-footer">
          <button onClick={() => setView(view === "settings" ? "chat" : "settings")}>
            {view === "settings" ? "返回对话" : "设置"}
          </button>
        </div>
      </aside>
      <main className="app-main">
        {view === "settings" ? (
          <SettingsView onBack={() => setView("chat")} />
        ) : (
          <ChatView vaultPath={status.vault_path} />
        )}
      </main>
    </div>
  );
}
