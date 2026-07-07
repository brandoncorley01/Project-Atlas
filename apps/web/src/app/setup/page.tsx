"use client";

import { useState } from "react";
import Link from "next/link";

export default function SetupPage() {
  const [supabaseUrl, setSupabaseUrl] = useState("");
  const [anonKey, setAnonKey] = useState("");
  const [serviceRoleKey, setServiceRoleKey] = useState("");
  const [jwtSecret, setJwtSecret] = useState("");
  const [userId, setUserId] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);

    const response = await fetch("/api/setup", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        supabaseUrl,
        anonKey,
        serviceRoleKey,
        jwtSecret,
        userId,
      }),
    });

    const data = await response.json();
    setLoading(false);

    if (!response.ok) {
      setError(data.error ?? "Setup failed");
      return;
    }

    setSuccess(true);
  }

  if (success) {
    return (
      <div className="flex min-h-screen items-center justify-center px-4">
        <div className="w-full max-w-lg rounded-xl border border-border bg-surface p-8 text-center">
          <h1 className="text-xl font-bold text-success">Configuration saved</h1>
          <p className="mt-4 text-sm text-muted">
            Restart the frontend and backend servers so the new keys load, then sign in.
          </p>
          <ol className="mt-4 space-y-2 text-left text-sm text-muted">
            <li>1. Stop both terminals (Ctrl+C)</li>
            <li>2. Start backend: <code className="text-foreground">uvicorn app.main:app --reload</code></li>
            <li>3. Start frontend: <code className="text-foreground">npm run dev</code></li>
          </ol>
          <p className="mt-6 text-sm">
            Or say <strong>restart servers</strong> in Cursor chat.
          </p>
          <Link
            href="/login"
            className="mt-6 inline-block rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white"
          >
            Go to login
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen flex-col items-center justify-center px-4 py-10">
      <div className="w-full max-w-lg rounded-xl border border-border bg-surface p-8">
        <h1 className="text-2xl font-bold text-accent">Project Atlas Setup</h1>
        <p className="mt-2 text-sm text-muted">
          Paste your Supabase keys once. We&apos;ll save them to your local env files (not committed to git).
        </p>

        <div className="mt-4 rounded-lg border border-border bg-background p-3 text-xs text-muted">
          <p className="font-medium text-foreground">Where to find these:</p>
          <p className="mt-1">Supabase → Project Settings → API</p>
          <p>JWT Secret: same page, scroll to JWT Settings</p>
          <p>User UUID: Authentication → Users → your email</p>
        </div>

        <form onSubmit={handleSubmit} className="mt-6 space-y-4">
          <Field
            label="Project URL"
            value={supabaseUrl}
            onChange={setSupabaseUrl}
            placeholder="https://abcdefgh.supabase.co"
          />
          <Field
            label="Anon public key"
            value={anonKey}
            onChange={setAnonKey}
            placeholder="eyJ... or sb_publishable_..."
          />
          <Field
            label="Service role key (backend only)"
            value={serviceRoleKey}
            onChange={setServiceRoleKey}
            placeholder="eyJ... or sb_secret_..."
            secret
          />
          <Field
            label="JWT secret"
            value={jwtSecret}
            onChange={setJwtSecret}
            placeholder="your-jwt-secret"
            secret
          />
          <Field
            label="Your user UUID"
            value={userId}
            onChange={setUserId}
            placeholder="a1b2c3d4-e5f6-..."
          />

          {error && (
            <p className="rounded-lg bg-danger/10 px-3 py-2 text-sm text-danger">{error}</p>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full rounded-lg bg-accent px-4 py-2 font-medium text-white disabled:opacity-50"
          >
            {loading ? "Saving…" : "Save configuration"}
          </button>
        </form>
      </div>
    </div>
  );
}

function Field({
  label,
  value,
  onChange,
  placeholder,
  secret,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder: string;
  secret?: boolean;
}) {
  return (
    <div>
      <label className="mb-1 block text-sm text-muted">{label}</label>
      <input
        type={secret ? "password" : "text"}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        required
        className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm outline-none focus:border-accent"
      />
    </div>
  );
}
