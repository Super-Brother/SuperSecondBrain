import { app, BrowserWindow, dialog, ipcMain, shell } from "electron";
import { spawn, type ChildProcess } from "node:child_process";
import net from "node:net";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

let backendProcess: ChildProcess | null = null;
let backendBaseUrl = "";

function repoRoot(): string {
  return path.resolve(__dirname, "..", "..");
}

async function getFreePort(): Promise<number> {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.listen(0, "127.0.0.1", () => {
      const address = server.address();
      if (typeof address === "object" && address) {
        const port = address.port;
        server.close(() => resolve(port));
      } else {
        reject(new Error("Failed to allocate port"));
      }
    });
  });
}

async function waitForHealth(baseUrl: string): Promise<void> {
  const started = Date.now();
  while (Date.now() - started < 120000) {
    try {
      const res = await fetch(`${baseUrl}/health`);
      if (res.ok) return;
    } catch {
      // retry until timeout
    }
    await new Promise((resolve) => setTimeout(resolve, 1000));
  }
  throw new Error("Backend did not become healthy within 120s");
}

async function startBackend(): Promise<void> {
  const port = await getFreePort();
  backendBaseUrl = `http://127.0.0.1:${port}`;
  const userDataDir = app.getPath("userData");

  if (!app.isPackaged) {
    backendProcess = spawn(
      "conda",
      [
        "run",
        "-n",
        "secondbrain-chat",
        "python",
        "-m",
        "src.desktop_backend",
        "--port",
        String(port),
        "--user-data-dir",
        userDataDir
      ],
      {
        cwd: repoRoot(),
        stdio: "inherit",
        env: {
          ...process.env,
          SECONDBRAIN_DESKTOP_MODE: "1",
          SECONDBRAIN_USER_DATA_DIR: userDataDir
        }
      }
    );
  } else {
    const executable = path.join(process.resourcesPath, "secondbrain-backend");
    backendProcess = spawn(
      executable,
      ["--port", String(port), "--user-data-dir", userDataDir],
      {
        stdio: "inherit",
        env: {
          ...process.env,
          SECONDBRAIN_DESKTOP_MODE: "1",
          SECONDBRAIN_USER_DATA_DIR: userDataDir
        }
      }
    );
  }

  await waitForHealth(backendBaseUrl);
}

function stopBackend(): void {
  if (backendProcess && !backendProcess.killed) {
    backendProcess.kill();
  }
  backendProcess = null;
}

async function createWindow(): Promise<void> {
  await startBackend();

  const win = new BrowserWindow({
    width: 1280,
    height: 820,
    minWidth: 980,
    minHeight: 680,
    title: "SecondBrain Chat",
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false
    }
  });

  if (!app.isPackaged) {
    await win.loadURL("http://127.0.0.1:5173");
  } else {
    await win.loadFile(path.join(__dirname, "..", "dist", "index.html"));
  }
}

ipcMain.handle("backend:getBaseUrl", () => backendBaseUrl);
ipcMain.handle("dialog:selectVaultDirectory", async () => {
  const result = await dialog.showOpenDialog({ properties: ["openDirectory"] });
  return result.canceled ? null : result.filePaths[0];
});
ipcMain.handle("shell:openExternal", async (_event, target: string) => {
  await shell.openExternal(target);
  return true;
});
ipcMain.handle("shell:openPath", async (_event, target: string) => {
  const error = await shell.openPath(target);
  return { ok: !error, error };
});

app.whenReady().then(createWindow);
app.on("window-all-closed", () => app.quit());
app.on("before-quit", stopBackend);
