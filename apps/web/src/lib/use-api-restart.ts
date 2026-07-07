"use client";

import { useCallback, useEffect, useRef, useState } from "react";

export function useApiRestart() {
  const devModeHint = process.env.NEXT_PUBLIC_ATLAS_DEV === "true";
  const [isDev, setIsDev] = useState(devModeHint);
  const [connection, setConnection] = useState<"checking" | "up" | "down" | "restarting">("checking");
  const [port, setPort] = useState("8012");
  const [message, setMessage] = useState<string | null>(null);
  const restartingRef = useRef(false);

  const checkHealth = useCallback(async (): Promise<boolean> => {
    try {
      const res = await fetch("/api/dev/health", {
        cache: "no-store",
        credentials: "include",
        signal: AbortSignal.timeout(10000),
      });
      const data = (await res.json()) as { ok: boolean; dev: boolean; port?: string };
      if (!data.dev) {
        setIsDev(false);
        return true;
      }
      setIsDev(true);
      if (data.port) setPort(data.port);
      const up = res.ok && data.ok;
      if (!restartingRef.current) {
        setConnection(up ? "up" : "down");
      }
      return up;
    } catch {
      setIsDev(true);
      if (!restartingRef.current) {
        setConnection("down");
      }
      return false;
    }
  }, []);

  useEffect(() => {
    void checkHealth();
    const id = setInterval(() => void checkHealth(), 15000);
    return () => clearInterval(id);
  }, [checkHealth]);

  const restartApi = useCallback(async () => {
    restartingRef.current = true;
    setConnection("restarting");
    setMessage("Stopping and restarting API (~60s)…");
    window.dispatchEvent(new CustomEvent("atlas:api-restarting"));

    try {
      const res = await fetch("/api/dev/restart-api", {
        method: "POST",
        credentials: "include",
        signal: AbortSignal.timeout(130_000),
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) {
        const detail = typeof body.detail === "string" ? body.detail : "Restart failed";
        setMessage(detail);
        setConnection("down");
        restartingRef.current = false;
        return;
      }

      setMessage("Verifying API…");
      for (let i = 0; i < 8; i++) {
        if (await checkHealth()) {
          restartingRef.current = false;
          setConnection("up");
          setMessage("API restarted.");
          window.dispatchEvent(new CustomEvent("atlas:dashboard-refresh"));
          window.dispatchEvent(new CustomEvent("atlas:api-online"));
          setTimeout(() => setMessage(null), 5000);
          return;
        }
        await new Promise((r) => setTimeout(r, 3000));
      }
      restartingRef.current = false;
      setMessage("Restart finished — tap Retry on Dashboard if still red.");
      setConnection("down");
    } catch (err) {
      restartingRef.current = false;
      const msg = err instanceof Error ? err.message : "Request failed";
      setMessage(msg.includes("timeout") ? "Restart timed out — run npm run dev:restart-api on PC" : msg);
      setConnection("down");
    }
  }, [checkHealth]);

  return { isDev, connection, port, message, checkHealth, restartApi };
}
