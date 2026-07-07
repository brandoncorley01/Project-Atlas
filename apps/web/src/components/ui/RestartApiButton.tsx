"use client";

import { useApiRestart } from "@/lib/use-api-restart";

export function RestartApiButton() {
  const { isDev, connection, message, restartApi } = useApiRestart();

  if (!isDev) return null;

  const restarting = connection === "restarting";
  const isDown = connection === "down";

  return (
    <div className="flex flex-col items-end gap-0.5">
      <button
        type="button"
        onClick={() => void restartApi()}
        disabled={restarting}
        title="Restart the local FastAPI backend (~60 seconds)"
        className={`min-h-[44px] rounded-md border px-2.5 py-1.5 text-sm font-semibold transition-colors disabled:opacity-50 sm:px-3 ${
          isDown || restarting
            ? "border-amber-400 bg-amber-500 text-amber-950 shadow-md shadow-amber-500/30 animate-pulse"
            : "border-border text-muted hover:bg-surface-hover hover:text-foreground"
        }`}
      >
        {restarting ? "Restarting…" : (
          <>
            <span className="sm:hidden">Restart</span>
            <span className="hidden sm:inline">Restart API</span>
          </>
        )}
      </button>
      {message && (
        <span
          className={`max-w-[11rem] truncate text-[10px] leading-tight sm:max-w-xs sm:text-xs ${
            isDown ? "text-amber-300" : "text-muted"
          }`}
          title={message}
        >
          {message}
        </span>
      )}
    </div>
  );
}
