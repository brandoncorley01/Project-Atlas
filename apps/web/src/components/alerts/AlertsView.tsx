"use client";

import { useState } from "react";
import Link from "next/link";
import { EmptyState } from "@/components/ui/EmptyState";
import { apiRequestHeaders, getApiUrl, usesBffProxy } from "@/lib/api-url";

export interface AlertItem {
  id: string;
  alert_type: string;
  title: string;
  message: string;
  module?: string | null;
  reference_id?: string | null;
  read: boolean;
  created_at?: string;
}

interface AlertsViewProps {
  initialItems: AlertItem[];
}

function moduleLink(module: string | null | undefined, id: string | null | undefined) {
  if (!module || !id) return null;
  if (module === "options") return "/options";
  if (module === "stock") return `/stocks/${id}`;
  if (module === "sports") return `/sports/${id}`;
  if (module === "parlay") return `/parlays/${id}`;
  return null;
}

export function AlertsView({ initialItems }: AlertsViewProps) {
  const [items, setItems] = useState(initialItems);
  const [loading, setLoading] = useState(false);

  async function getToken() {
    if (usesBffProxy()) return undefined;
    const { createClient } = await import("@/lib/supabase/client");
    const { data } = await createClient().auth.getSession();
    return data.session?.access_token ?? undefined;
  }

  async function markRead(id: string) {
    const token = await getToken();
    try {
      await fetch(`${getApiUrl()}/alerts/${id}/read`, {
        method: "PATCH",
        headers: apiRequestHeaders(token),
      });
      setItems((prev) => prev.map((a) => (a.id === id ? { ...a, read: true } : a)));
    } catch {
      /* ignore */
    }
  }

  async function markAllRead() {
    setLoading(true);
    const token = await getToken();
    try {
      await fetch(`${getApiUrl()}/alerts/read-all`, {
        method: "POST",
        headers: apiRequestHeaders(token),
      });
      setItems((prev) => prev.map((a) => ({ ...a, read: true })));
    } catch {
      /* ignore */
    }
    setLoading(false);
  }

  const unread = items.filter((a) => !a.read).length;

  return (
    <div>
      <div className="mb-4 flex items-center justify-between">
        <p className="text-sm text-muted">
          {unread > 0 ? `${unread} unread` : "All caught up"}
        </p>
        {unread > 0 && (
          <button
            type="button"
            onClick={markAllRead}
            disabled={loading}
            className="text-sm text-accent hover:underline disabled:opacity-50"
          >
            Mark all read
          </button>
        )}
      </div>

      {items.length > 0 ? (
        <ul className="space-y-3">
          {items.map((alert) => {
            const href = moduleLink(alert.module, alert.reference_id);
            return (
              <li
                key={alert.id}
                className={`rounded-xl border px-4 py-3 ${
                  alert.read
                    ? "border-border bg-surface/50 opacity-75"
                    : "border-accent/30 bg-accent/5"
                }`}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-medium">{alert.title}</p>
                    <p className="mt-1 text-sm text-muted">{alert.message}</p>
                    {alert.created_at && (
                      <p className="mt-2 text-xs text-muted">
                        {new Date(alert.created_at).toLocaleString()}
                      </p>
                    )}
                    {href && (
                      <Link href={href} className="mt-2 inline-block text-xs text-accent hover:underline">
                        View signal →
                      </Link>
                    )}
                  </div>
                  {!alert.read && (
                    <button
                      type="button"
                      onClick={() => markRead(alert.id)}
                      className="shrink-0 text-xs text-muted hover:text-foreground"
                    >
                      Mark read
                    </button>
                  )}
                </div>
              </li>
            );
          })}
        </ul>
      ) : (
        <EmptyState
          title="No alerts yet"
          description="When Atlas finds a high-scoring signal during a scan, it shows up here automatically. Run a market scan from the bar above to get started."
          action={
            <Link href="/" className="rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-white">
              Go to scanner
            </Link>
          }
        />
      )}
    </div>
  );
}
