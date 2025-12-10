# AI Contract Analyzer - Copilot Instructions

You are working on the **AI Contract Analyzer**, a monorepo containing a FastAPI backend and a Next.js frontend.

## 1. Project Structure & Tech Stack

- **Root**: Monorepo with `backend/` and `frontend/`.
- **Backend**: Python 3.11+, FastAPI, SQLAlchemy 2.0 (Async), Alembic, Pydantic v2, Celery, Redis.
- **Frontend**: Next.js 16 (App Router), React 19, Redux Toolkit (RTK Query), Tailwind CSS v4, shadcn/ui.
- **Infrastructure**: Docker Compose (Postgres, Redis, API), Ollama (Local LLM).

## 2. Architecture & Data Flow

- **API First**: The frontend communicates with the backend via REST API (`/api/v1`).
- **Async Processing**: Heavy tasks (OCR, LLM analysis) are offloaded to Celery workers (`contract-tasks` queue).
- **Data Persistence**: PostgreSQL is the source of truth. Use Alembic for all schema changes.
- **AI Integration**: The backend integrates with local LLM (Ollama) via `LLMService`.

## 3. Backend Guidelines (Python/FastAPI)

- **Code Style**: Follow PEP 8. Use `ruff` for linting and `black` for formatting.
- **Type Hints**: Enforce strict type hints. Use `mypy` compatible types.
- **Database (SQLAlchemy 2.0)**:
  - Use `Mapped` and `mapped_column` for models (see `backend/app/models/contract.py`).
  - Always use asynchronous sessions (`AsyncSession`).
  - **Migrations**:
    - Create: `alembic revision --autogenerate -m "message"`
    - Apply: `alembic upgrade head`
- **Pydantic v2**: Use `model_config` and `Field` for validation.
- **Dependency Injection**: Use FastAPI's `Depends` for services and DB sessions.
- **Celery**: Define tasks in `backend/app/tasks`. Use `celery_app` decorator.

## 4. Frontend Guidelines (Next.js/TypeScript)

- **State Management**:
  - Use **RTK Query** (`frontend/src/services/api.ts`) for all server state/data fetching.
  - Use Redux Toolkit slices for complex global client state.
  - Use local React state (`useState`, `useReducer`) for component-local UI state.
- **Styling**:
  - Use **Tailwind CSS v4**.
  - Use `clsx` and `tailwind-merge` (via `cn` utility) for conditional classes.
  - Follow **shadcn/ui** patterns for components.
- **Components**:
  - Prefer functional components with strict TypeScript interfaces.
  - Place reusable components in `src/components`.
  - Place page-specific components in `src/app/...`.

## 5. Testing & Quality

- **Backend**:
  - Run tests: `pytest` (in `backend/` directory).
  - Use `conftest.py` for fixtures (DB session, client).
- **Frontend**:
  - Run tests: `pnpm test` (Jest).
  - Use `msw` for mocking API requests in tests.
- **Linting**:
  - Backend: `ruff check .`, `black .`
  - Frontend: `pnpm lint`

## 6. Common Workflows & Commands

- **Start Dev Environment**:
  - Backend: `uvicorn app.main:app --reload` (inside `.venv`)
  - Frontend: `pnpm dev`
  - Services: `docker compose up -d redis db`
- **Database Reset**:
  - `docker compose down -v` (wipes data)
  - `alembic upgrade head` (re-creates schema)

## 7. Specific Patterns

- **LLM Integration**: Use `backend/app/services/llm_service.py`. Do not hardcode prompts; consider moving them to config or a dedicated prompt manager if complexity grows.
- **Configuration**: Access env vars via `backend/app/core/config.py` (`settings` object).

Always verify your changes by running relevant tests. If you are unsure about a pattern, check existing files in `backend/app/api` or `frontend/src/features`.
