import { useState } from "react";
import { apiGet, apiPost } from "../api/client";
import type { DesktopConfig, DesktopStatus } from "../types";

const defaultConfig: DesktopConfig = {
  vault_path: "",
  llm_base_url: "http://localhost:11434/v1",
  llm_api_key: "not-needed",
  llm_model: "qwen2.5:3b",
  embedding_model: "BAAI/bge-large-zh-v1.5",
  reranker_model: "BAAI/bge-reranker-base",
  onboarding_complete: false,
};

export function Onboarding({ onDone }: { onDone: () => void }) {
  const [cfg, setCfg] = useState<DesktopConfig>(defaultConfig);
  const [importPath, setImportPath] = useState("");
  const [importOverwrite, setImportOverwrite] = useState(false);
  const [taskId, setTaskId] = useState<string | null>(null);
  const [taskStatus, setTaskStatus] = useState<{ status: string; message: string; error?: string } | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function selectVault() {
    const selected = await window.secondbrain.selectVaultDirectory();
    if (selected) {
      setCfg((prev) => ({ ...prev, vault_path: selected }));
    }
  }

  async function handleImport() {
    setError(null);
    if (!importPath) {
      setError("请输入源数据目录");
      return;
    }
    try {
      await apiPost("/api/v1/desktop/import-data", {
        source_data_dir: importPath,
        overwrite: importOverwrite,
      });
      setImportPath("");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  async function handleSubmit() {
    setError(null);
    if (!cfg.vault_path) {
      setError("请选择 vault 目录");
      return;
    }

    try {
      await apiPost("/api/v1/desktop/config", { ...cfg, onboarding_complete: true });
      const task = await apiPost<{ task_id: string; status: string }>("/api/v1/index/build");
      setTaskId(task.task_id);
      pollTask(task.task_id);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  async function pollTask(id: string) {
    for (let i = 0; i < 300; i++) {
      const status = await apiGet<{ status: string; message: string; error?: string }>(`/api/v1/index/tasks/${id}`);
      setTaskStatus(status);
      if (status.status === "succeeded" || status.status === "failed") {
        if (status.status === "succeeded") {
          onDone();
        }
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
    <div className="onboarding">
      <div className="onboarding-card">
        <h1>欢迎使用 SecondBrain Chat</h1>
        <p className="subtitle">配置你的知识库和模型，即可开始本地问答。</p>

        {error && <div className="error">{error}</div>}

        <section>
          <h2>1. 选择 Vault 目录</h2>
          <div className="field-row">
            <input
              type="text"
              value={cfg.vault_path}
              onChange={(e) => updateField("vault_path", e.target.value)}
              placeholder="/path/to/vault"
            />
            <button onClick={selectVault}>选择目录</button>
          </div>
        </section>

        <section>
          <h2>2. LLM 配置</h2>
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

          <label>模型名称</label>
          <input
            type="text"
            value={cfg.llm_model}
            onChange={(e) => updateField("llm_model", e.target.value)}
          />
        </section>

        <section>
          <h2>3. Embedding / Reranker</h2>
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
          <h2>4. 导入已有数据（可选）</h2>
          <div className="field-row">
            <input
              type="text"
              value={importPath}
              onChange={(e) => setImportPath(e.target.value)}
              placeholder="/path/to/project/data"
            />
          </div>
          <label className="checkbox">
            <input
              type="checkbox"
              checked={importOverwrite}
              onChange={(e) => setImportOverwrite(e.target.checked)}
            />
            覆盖已有数据
          </label>
          <button onClick={handleImport}>导入现有项目数据</button>
        </section>

        {taskStatus && (
          <div className={`task-status ${taskStatus.status}`}>
            {taskStatus.message}
            {taskStatus.error && <span className="task-error">: {taskStatus.error}</span>}
          </div>
        )}

        <button
          className="primary"
          onClick={handleSubmit}
          disabled={!!taskId && taskStatus?.status !== "failed"}
        >
          {taskId ? "构建索引中..." : "保存配置并构建索引"}
        </button>
      </div>
    </div>
  );
}
