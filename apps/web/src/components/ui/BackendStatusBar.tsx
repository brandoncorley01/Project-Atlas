"use client";

import { useApiRestart } from "@/lib/use-api-restart";

/** Warning strip when API is down in local dev (restart is in the header). */
export function BackendStatusBar() {
  const { isDev, connection, port, message } = useApiRestart();

  if (!isDev || (connection !== "down" && connection !== "restarting" && !message)) {
    return null;
  }

  return (
    <div
      className="fixed inset-x-0 bottom-[4.25rem] z-[100] border-t border-amber-500/40 bg-amber-950/95 px-4 py-2 shadow-lg backdrop-blur-sm sm:bottom-0"
      role="alert"
    >
      <p className="mx-auto max-w-3xl text-center text-xs text-amber-100 sm:text-sm">
        {connection === "restarting"
          ? message ?? "Restarting API… (~30 seconds)"
          : message ?? `Backend unreachable on port ${port} — use Restart API in the header.`}
      </p>
    </div>
  );
}
