export type DesktopStatus = {
  desktop_mode: boolean;
  onboarding_complete: boolean;
  vault_path: string;
  user_data_dir: string;
  index_dir: string;
  index_loaded: boolean;
  stats: Record<string, unknown>;
};

export type Source = {
  title?: string;
  source?: string;
  domain?: string;
  score?: number;
};

export type ChatMessage = {
  role: "user" | "assistant";
  content: string;
  sources?: Source[];
};

export type DesktopConfig = {
  vault_path: string;
  llm_base_url: string;
  llm_api_key: string;
  llm_model: string;
  embedding_model: string;
  reranker_model: string;
  onboarding_complete: boolean;
};
