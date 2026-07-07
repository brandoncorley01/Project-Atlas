# Project Atlas

Private-first AI decision intelligence platform. Internal codename for what may become **EdgeIQ AI**.

## What it does

Answers: **"What are the best opportunities available right now?"**

Ranks opportunities across:
- Retail options swing trading (highest priority)
- Stock swing trading
- Sports betting
- Cross-sport parlays

## Repo structure

```
apps/web/     → Next.js dashboard (Vercel)
apps/api/     → FastAPI backend (Render/Railway)
docs/         → PRD, architecture, API spec, roadmap
supabase/     → Database migrations
```

## Quick start

### Prerequisites

- Node.js 20+
- Python 3.11+
- Supabase account (for Milestone 1)

### Frontend

```bash
cd apps/web
cp .env.local.example .env.local   # fill in after Supabase setup
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000)

### Backend

```bash
cd apps/api
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8000
```

Open [http://localhost:8000/docs](http://localhost:8000/docs)

### Database

1. Create a Supabase project at [supabase.com](https://supabase.com)
2. Run `supabase/migrations/20250629000000_initial_schema.sql` in the SQL editor
3. Copy URL and keys into `.env` files

## Documentation

| Doc | Description |
|-----|-------------|
| [docs/01-prd.md](docs/01-prd.md) | Product requirements |
| [docs/02-architecture.md](docs/02-architecture.md) | System architecture |
| [docs/03-folder-structure.md](docs/03-folder-structure.md) | Repo layout |
| [docs/04-database-schema.sql](docs/04-database-schema.sql) | Schema reference |
| [docs/05-api-spec.md](docs/05-api-spec.md) | API routes |
| [docs/06-data-providers.md](docs/06-data-providers.md) | External APIs |
| [docs/07-ui-blueprint.md](docs/07-ui-blueprint.md) | UI wireframes |
| [docs/08-build-roadmap.md](docs/08-build-roadmap.md) | Build milestones |

## Disclaimer

Project Atlas is a decision-support tool. It does not provide financial advice or guarantee profits. All trading and betting involves risk.

## Next step

**Milestone 1:** Set up Supabase, wire authentication, run the database migration.

Say **"start milestone 1"** when ready.
