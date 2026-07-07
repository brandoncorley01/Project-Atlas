# Deploy Atlas — mobile off your local network

Atlas uses a **BFF pattern**: your phone only talks to the Next.js app; the server proxies to FastAPI. You never expose port `8012` to the internet.

**GitHub repo:** [github.com/brandoncorley01/project-atlas](https://github.com/brandoncorley01/project-atlas)

---

## Phase 0 — Push code to GitHub (one time)

If the repo is not on GitHub yet:

1. Create an empty repo at [github.com/new](https://github.com/new) named **project-atlas** (private recommended).
2. From the project folder:

```powershell
cd "c:\Users\brand\OneDrive\Desktop\Project Atlas"

git add .
git commit -m "Ship v1: learning loop, deploy configs for Vercel + Render"
git branch -M main
git remote add origin https://github.com/brandoncorley01/project-atlas.git
git push -u origin main
```

If `origin` already exists, update it:

```powershell
git remote set-url origin https://github.com/brandoncorley01/project-atlas.git
git push -u origin main
```

---

## Option A — Quick test (tunnel, ~5 minutes)

Use this while your PC runs `npm run dev`. Good for testing off Wi‑Fi before a full deploy.

### 1. Start dev stack

```powershell
npm run dev
```

### 2. Start tunnel (new terminal)

```powershell
npm run dev:tunnel
```

Copy the `https://….trycloudflare.com` URL (or ngrok URL if you use ngrok).

### 3. Supabase auth URLs

In [Supabase Dashboard](https://supabase.com/dashboard) → **Authentication** → **URL Configuration**:

| Field | Value |
|-------|--------|
| **Site URL** | Your tunnel URL, e.g. `https://xyz.trycloudflare.com` |
| **Redirect URLs** | Same URL + `https://xyz.trycloudflare.com/**` |

### 4. Open on phone

Use the **tunnel HTTPS URL** on cellular or any network. Sign in again if prompted.

**Limits:** PC must stay on; tunnel URL changes each run (unless you use a paid static domain).

---

## Option B — Production (Vercel + Render + Supabase)

Always-on HTTPS. Recommended once v1 is stable.

### Architecture

```
Phone → https://your-app.vercel.app
         └─ /api/atlas/* (BFF, server-side auth)
              └─ https://atlas-api.onrender.com/api/v1/*
Supabase → auth + database (already cloud)
```

### Step 1 — Deploy API (Render)

1. Push this repo to GitHub.
2. [Render](https://render.com) → **New** → **Blueprint** → connect repo → use `render.yaml`.
3. Set environment variables (copy from `apps/api/.env`):

| Variable | Notes |
|----------|--------|
| `SUPABASE_*` | Same as local `.env` |
| `FINNHUB_API_KEY` | Optional |
| `ODDS_API_KEY` | Comma-separated keys |
| `CORS_ORIGINS` | Your Vercel URL, e.g. `https://project-atlas-brandoncorley01.vercel.app` |
| `ENVIRONMENT` | `production` |
| `DEFAULT_USER_ID` | Your Supabase user UUID (for future cron jobs) |

4. Deploy → note API URL: `https://atlas-api-xxxx.onrender.com`

5. Verify: `https://atlas-api-xxxx.onrender.com/api/v1/health`

### Step 2 — Deploy web (Vercel)

1. [Vercel](https://vercel.com) → **Import** repo.
2. Set **Root Directory** to `apps/web`.
3. Environment variables:

| Variable | Value |
|----------|--------|
| `NEXT_PUBLIC_SUPABASE_URL` | `https://niqcehpxqkvwaqpbsdii.supabase.co` |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Your anon key |
| `NEXT_PUBLIC_API_URL` | `https://atlas-api-xxxx.onrender.com/api/v1` |

Do **not** set `NEXT_PUBLIC_ATLAS_DEV` in production (hides dev Restart button).

4. Deploy → note URL: `https://project-atlas-brandoncorley01.vercel.app` (or similar — use your actual Vercel URL)

### Step 3 — Supabase production URLs

| Field | Value |
|-------|--------|
| **Site URL** | `https://project-atlas-brandoncorley01.vercel.app` (your real Vercel URL) |
| **Redirect URLs** | `https://project-atlas-brandoncorley01.vercel.app/**` |

Keep localhost URLs if you still develop locally.

### Step 4 — Lock down (recommended)

- Supabase → disable public signups if this is personal-only
- Rotate `CRON_SECRET` on Render
- Never commit `apps/api/.env` or `apps/web/.env.local`

### Step 5 — Test on phone

1. Open Vercel URL on cellular.
2. Sign in.
3. Dashboard loads → run a sports scan.
4. Log a Win/Loss on a pick card.

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| Login loops | Add exact Vercel/tunnel URL to Supabase redirect URLs |
| API 503 on Vercel | Check `NEXT_PUBLIC_API_URL`; wake Render free tier (first request ~30s) |
| CORS errors | Set `CORS_ORIGINS` on Render to your Vercel domain |
| Odds scan fails | `ODDS_API_KEY` only on **Render**, not in browser env |

---

## After deploy → Milestone 2 features

With mobile off LAN, focus shifts to:

1. Scheduled auto-grade (stocks, options, sports)
2. Parlay learning loop
3. Richer calibration UI

See `docs/08-build-roadmap.md` Milestone 10–11.
