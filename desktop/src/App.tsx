import { useEffect, useState } from "react";
import { apiGet } from "./api/client";
import { Onboarding } from "./components/Onboarding";
import type { DesktopStatus } from "./types";

export function App() {
  const [status, setStatus] = useState<DesktopStatus | null>(null);
  const [loading, setLoading] = useState(true);

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

  if (loading) {
    return (
      <main className="app-shell">
        <p>加载中...</p>
      </main>
    );
  }

  if (!status || !status.onboarding_complete) {
    return <Onboarding onDone={() => setStatus((prev) => prev ? { ...prev, onboarding_complete: true } : null)} />;
  }

  return (
    <main className="app-shell">
      <h1>SecondBrain Chat</h1>
      <p>Onboarding complete. Chat UI will be wired here.</p>
    </main>
  );
}
