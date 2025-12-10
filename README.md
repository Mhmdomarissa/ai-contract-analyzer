# Contract Review System Monorepo

This repository bootstraps a Contract Review System with a FastAPI backend, a Next.js frontend scaffold, shared tooling, and infrastructure ready for migrations, Celery tasks, and continuous linting.

## Structure

- `backend/` — FastAPI application, Alembic migrations, Docker assets.
- `frontend/` — Next.js + Redux Toolkit UI scaffold using atomic design and shadcn/ui.
- `nginx/` — reverse-proxy configuration that fronts the frontend and API for production traffic.
- `.husky/` — git hooks running `pnpm lint` before each commit.
- `infra/terraform/` — optional Terraform snippet for provisioning the required security group in AWS.
- `docker-compose.yml` — orchestrates API, PostgreSQL, Redis, frontend, worker, and the nginx gateway.

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
4. **Run services (fronted by nginx on port 80)**:
   ```bash
   docker compose up --build -d nginx worker
   # or during development
   docker compose up
   ```
   This starts PostgreSQL, Redis, FastAPI (`api`), Celery (`worker`), the Next.js frontend, and nginx. Nginx proxies:
   - `http://<host>/` → frontend (Next.js)
   - `http://<host>/api/...` → FastAPI backend

5. **Local frontend-only development** (optional):
   ```bash
   cd frontend
   pnpm dev
   ```
   When running the dev server directly, point `NEXT_PUBLIC_API_BASE_URL` back to `http://localhost:8000/api/v1`.

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

## Deployment Notes

- **Public access**: open TCP/80 (and optionally 443) to the EC2 instance/load balancer so nginx can serve traffic. The frontend now calls the backend through `/api/` on the same origin, so no extra CORS headers are required.
- **Environment**: `frontend/.env.local` defaults `NEXT_PUBLIC_API_BASE_URL=/api/v1`, keeping client calls relative to the host name. Override it only when you intentionally bypass nginx (e.g., local dev hitting a remote API).
- **Security groups via Terraform**: the `infra/terraform` module provisions a reusable AWS security group that allows HTTP/HTTPS ingress and restricts SSH to specific CIDRs. Adjust the variables, run `terraform init && terraform apply`, then attach the security group to the EC2 instance hosting this stack.

