# Contract Review System Monorepo

This repository bootstraps a Contract Review System with a FastAPI backend, a Next.js frontend scaffold, shared tooling, and infrastructure ready for migrations, Celery tasks, and continuous linting.

## Structure

- `backend/` — FastAPI application, Alembic migrations, Docker assets.
- `frontend/` — Next.js + Redux Toolkit UI scaffold using atomic design and shadcn/ui.
- `.husky/` — git hooks running `pnpm lint` before each commit.
- `docker-compose.yml` — orchestrates API, PostgreSQL, and Redis services.

## Getting Started

1. **Install Node & pnpm**, then install workspace deps + Husky:
   ```bash
   pnpm install
   pnpm prepare
   ```
2. **Create a Python virtual environment** (3.11 recommended) and install backend dependencies:
   ```bash
   cd backend
   python -m venv .venv
   .venv\\Scripts\\activate  # Windows
   pip install -e ".[dev]"
   ```
3. **Copy environment variables**:
   ```bash
   cp backend/.env.example backend/.env
   cp frontend/.env.example frontend/.env.local
   ```
4. **Run services**:
   ```bash
   docker compose up --build
   ```
5. **Run the frontend (separate terminal)**:
   ```bash
   pnpm frontend:dev
   ```

## Tooling

- **Husky** (`.husky/pre-commit`) runs `pnpm lint` (Next.js ESLint).
- **Ruff + Black** keep Python style consistent (`pyproject.toml`).
- **Alembic** manages database migrations (`backend/alembic`).
- **Redux Toolkit + RTK Query** orchestrate client state/data fetching.
- **shadcn/ui + Tailwind CSS v4** provide composable design tokens and components.

## Next Steps

- Flesh out real contract/clauses APIs and connect the RTK Query services.
- Replace mock contract data with live responses & add protected routes once auth is ready.
- Expand Celery tasks, add background processing, and wire observability in both tiers.

