import { appendFile, writeFile } from "fs/promises";
import { execFile } from "child_process";
import path from "path";
import { promisify } from "util";
import { findProjectRoot } from "@/lib/project-root";
import { apiPortLabel } from "@/lib/api-config";

const execFileAsync = promisify(execFile);

export async function runApiRestart(userEmail?: string): Promise<{ ok: boolean; detail?: string }> {
  const root = findProjectRoot();
  const devDir = path.join(root, ".dev");
  const lockFile = path.join(devDir, "api-restarting.lock");
  const logFile = path.join(devDir, "restart-api-web.log");
  const script = path.join(root, "scripts", "restart-api.ps1");

  const stamp = new Date().toISOString();
  await writeFile(lockFile, stamp, "utf8");
  await appendFile(logFile, `\n[${stamp}] restart requested${userEmail ? ` by ${userEmail}` : ""}\n`);

  try {
    const { stdout, stderr } = await execFileAsync(
      "powershell.exe",
      ["-ExecutionPolicy", "Bypass", "-NoProfile", "-File", script],
      { cwd: root, windowsHide: true, timeout: 120_000 },
    );
    await appendFile(
      logFile,
      `[${new Date().toISOString()}] finished ok\n${stdout}\n${stderr}\n`,
    );
    return { ok: true };
  } catch (err) {
    const message = err instanceof Error ? err.message : "Restart failed";
    await appendFile(logFile, `[${new Date().toISOString()}] failed: ${message}\n`).catch(() => {});
    return { ok: false, detail: message };
  }
}

export function apiPort(): string {
  return apiPortLabel();
}
