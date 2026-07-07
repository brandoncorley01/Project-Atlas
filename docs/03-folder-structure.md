# Project Atlas — Folder Structure

Monorepo layout for private-first, SaaS-ready development.

```
project-atlas/
├── apps/
│   ├── web/                          # Next.js frontend (Vercel)
│   │   ├── src/
│   │   │   ├── app/                  # App Router pages
│   │   │   │   ├── (auth)/           # Login, signup
│   │   │   │   ├── (dashboard)/      # Protected app routes
│   │   │   │   │   ├── page.tsx      # Home dashboard
│   │   │   │   │   ├── options/
│   │   │   │   │   ├── stocks/
│   │   │   │   │   ├── sports/
│   │   │   │   │   ├── parlays/
│   │   │   │   │   ├── news/
│   │   │   │   │   ├── watchlist/
│   │   │   │   │   ├── alerts/
│   │   │   │   │   └── performance/
│   │   │   │   ├── layout.tsx
│   │   │   │   └── globals.css
│   │   │   ├── components/
│   │   │   │   ├── ui/               # Buttons, badges, cards
│   │   │   │   ├── signals/          # Options, stock, sports cards
│   │   │   │   ├── charts/           # TradingView wrappers
│   │   │   │   ├── layout/           # Nav, sidebar, disclaimer
│   │   │   │   └── dashboard/        # Dashboard widgets
│   │   │   ├── lib/
│   │   │   │   ├── api/              # FastAPI client
│   │   │   │   ├── supabase/         # Auth client
│   │   │   │   └── utils/
│   │   │   ├── hooks/
│   │   │   └── types/                # TypeScript types (mirror API)
│   │   ├── public/
│   │   ├── package.json
│   │   └── .env.local.example
│   │
│   └── api/                          # FastAPI backend (Render/Railway)
│       ├── app/
│       │   ├── main.py               # App entry + CORS
│       │   ├── config.py             # Settings from env
│       │   ├── dependencies.py     # Auth, DB session
│       │   ├── routers/              # HTTP endpoints
│       │   │   ├── health.py
│       │   │   ├── signals.py
│       │   │   ├── news.py
│       │   │   ├── watchlist.py
│       │   │   ├── alerts.py
│       │   │   └── performance.py
│       │   ├── services/             # Business logic
│       │   │   ├── options_service.py
│       │   │   ├── stock_service.py
│       │   │   ├── sports_service.py
│       │   │   ├── parlay_service.py
│       │   │   ├── news_service.py
│       │   │   ├── alert_service.py
│       │   │   └── performance_service.py
│       │   ├── agents/               # AI pipelines
│       │   │   ├── scout.py
│       │   │   ├── analyst.py
│       │   │   ├── planner.py
│       │   │   ├── news_ai.py
│       │   │   └── coach.py
│       │   ├── engine/               # Opportunity Engine
│       │   │   ├── pipeline.py
│       │   │   ├── scoring.py
│       │   │   └── explainer.py
│       │   ├── providers/            # External API adapters
│       │   │   ├── stocks/
│       │   │   ├── options/
│       │   │   ├── news/
│       │   │   └── sports/
│       │   ├── models/               # SQLAlchemy models
│       │   ├── schemas/              # Pydantic request/response
│       │   └── jobs/                 # Scheduled refresh tasks
│       │       ├── refresh_options.py
│       │       ├── refresh_stocks.py
│       │       ├── refresh_sports.py
│       │       ├── refresh_news.py
│       │       └── coach_aggregate.py
│       ├── alembic/                  # DB migrations
│       ├── tests/
│       ├── requirements.txt
│       └── .env.example
│
├── packages/
│   └── shared/                       # Shared types (optional, future)
│       └── types/
│
├── supabase/
│   └── migrations/                     # SQL migrations + RLS policies
│
├── docs/                             # Product & technical docs
│   ├── 01-prd.md
│   ├── 02-architecture.md
│   ├── 03-folder-structure.md
│   ├── 04-database-schema.sql
│   ├── 05-api-spec.md
│   ├── 06-data-providers.md
│   ├── 07-ui-blueprint.md
│   └── 08-build-roadmap.md
│
├── package.json                      # Root npm workspaces
├── .gitignore
└── README.md
```

## Conventions

- **Python:** snake_case files and functions; routers thin, services fat
- **TypeScript:** PascalCase components; camelCase functions
- **API:** `/api/v1/` prefix on all backend routes
- **Env:** Never commit `.env`; use `.env.example` templates
