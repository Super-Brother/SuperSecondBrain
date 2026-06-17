export {};

declare global {
  interface Window {
    secondbrain: {
      getBackendBaseUrl(): Promise<string>;
      selectVaultDirectory(): Promise<string | null>;
      openExternal(target: string): Promise<boolean>;
      openPath(target: string): Promise<{ ok: boolean; error?: string }>;
    };
  }
}
