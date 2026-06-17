import { useEffect, useState } from "react";
import { apiGet, apiPost } from "../api/client";
import type { DesktopConfig, DesktopStatus } from "../types";

const defaultConfig: DesktopConfig = {
  vault_path: "",
  llm_base_url: "http://localhost:11434/v1",
  llm_api_key: "not-needed",
  llm_model: "qwen2.5:3b",
  embedding_model: "BAAI/bge-large-zh-v1.5",
  reranker_model: "BAAI/bge-reranker-base",
  onboarding_complete: true,
};

export function SettingsView({ onBack }: { onBack: () => void }) {
  const [status, setStatus] = useState<DesktopStatus | null>(null);
  const [cfg, setCfg] = useState<DesktopConfig>(defaultConfig);
  const [taskId, setTaskId] = useState<string | null>(null);
  const [taskStatus, setTaskStatus] = useState<{ status: string; message: string; error?: string } | null>(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    apiGet<DesktopStatus>("/api/v1/desktop/status").then((s) => {
      setStatus(s);
      setCfg({
        vault_path: s.vault_path,
        llm_base_url: "http://localhost:11434/v1",
        llm_api_key: "not-needed",
        llm_model: "qwen2.5:3b",
        embedding_model: "BAAI/bge-large-zh-v1.5",
        reranker_model: "BAAI/bge-reranker-base",
        onboarding_complete: true,
      });
    });
  }, []);

  async function selectVault() {
    const selected = await window.secondbrain.selectVaultDirectory();
    if (selected) {
      setCfg((prev) => ({ ...prev, vault_path: selected }));
    }
  }

  async function saveConfig() {
    await apiPost("/api/v1/desktop/config", cfg);
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  }

  async function rebuildIndex() {
    const task = await apiPost<{ task_id: string; status: string }>("/api/v1/index/build");
    setTaskId(task.task_id);
    pollTask(task.task_id);
  }

  async function pollTask(id: string) {
    for (let i = 0; i < 300; i++) {
      const status = await apiGet<{ status: string; message: string; error?: string }>(`/api/v1/index/tasks/${id}`);
      setTaskStatus(status);
      if (status.status === "succeeded" || status.status === "failed") {
        return;
      }
      await new Promise((resolve) => setTimeout(resolve, 1000));
    }
    setTaskStatus({ status: "failed", message: "索引构建超时" });
  }

  function updateField<K extends keyof DesktopConfig>(key: K, value: DesktopConfig[K]) {
    setCfg((prev) => ({ ...prev, [key]: value }));
  }

  return (
    <div className="settings-view">
      <div className="settings-header">
        <button onClick={onBack}>← 返回</button>
        <h2>设置</h2>
      </div>

      <section>
        <h3>Vault 目录</h3>
        <div className="field-row">
          <input
            type="text"
            value={cfg.vault_path}
            onChange={(e) => updateField("vault_path", e.target.value)}
          />
          <button onClick={selectVault}>选择目录</button>
        </div>
      </section>

      <section>
        <h3>LLM</h3>
        <label>Base URL</label>
        <input
          type="text"
          value={cfg.llm_base_url}
          onChange={(e) => updateField("llm_base_url", e.target.value)}
        />
        <label>API Key</label>
        <input
          type="text"
          value={cfg.llm_api_key}
          onChange={(e) => updateField("llm_api_key", e.target.value)}
        />
        <label>模型</label>
        <input
          type="text"
          value={cfg.llm_model}
          onChange={(e) => updateField("llm_model", e.target.value)}
        />
      </section>

      <section>
        <h3>模型路径</h3>
        <label>Embedding 模型</label>
        <input
          type="text"
          value={cfg.embedding_model}
          onChange={(e) => updateField("embedding_model", e.target.value)}
        />
        <label>Reranker 模型</label>
        <input
          type="text"
          value={cfg.reranker_model}
          onChange={(e) => updateField("reranker_model", e.target.value)}
        />
      </section>

      <section>
        <h3>索引状态</h3>
        {status && (
          <div className="index-status">
            <div>索引已加载: {status.index_loaded ? "是" : "否"}</div>
            <div>数据目录: {status.user_data_dir}</div>
            <div>索引目录: {status.index_dir}</div>
            <div>统计: {JSON.stringify(status.stats)}</div>
          </div>
        )}
        <button onClick={rebuildIndex} disabled={!!taskId && taskStatus?.status !== "failed"}>
          {taskId ? "构建中..." : "重建索引"}
        </button>
        {taskStatus && (
          <div className={`task-status ${taskStatus.status}`}>
            {taskStatus.message}
            {taskStatus.error && <span className="task-error">: {taskStatus.error}</span>}
          </div>
        )}
      </section>

      <div className="settings-actions">
        <button className="primary" onClick={saveConfig}>保存设置</button>
        {saved && <span className="save-hint">已保存</span>}
      </div>
    </div>
  );
}
