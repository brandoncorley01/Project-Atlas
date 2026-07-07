# Project Atlas — System Architecture

See conversation-approved Phase 2 architecture. Summary:

**Stack:** Next.js (Vercel) + FastAPI (Render/Railway) + Supabase (Postgres, Auth, Storage)

**AI model:** Deterministic scoring + LLM for news classification and explanations only.

**Security:** JWT auth, RLS on all tables, API keys server-side only.

**Jobs:** Cron-based refresh (5–30 min), not real-time streaming in V1.

**Monorepo:** `apps/web`, `apps/api`, `docs/`, `supabase/migrations/`
