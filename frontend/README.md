## Contract Review Frontend

This directory hosts the Contract Review System UI built with:

- [Next.js App Router](https://nextjs.org/docs) (latest stable release, TypeScript + Tailwind v4).
- [Redux Toolkit + RTK Query](https://redux.js.org/) for state and API orchestration.
- [shadcn/ui](https://ui.shadcn.com/docs/installation) components layered into an atomic design system (atoms → molecules → organisms → templates → pages).

### Commands

```bash
# install (from repo root)
pnpm install

# run dev server
pnpm dev

# lint + fix
pnpm lint
pnpm lint:fix

# type-check & tests
pnpm typecheck
pnpm test
```

### Env Vars

Copy `.env.example` to `.env.local` and set:

```
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000/api/v1
```

### Project layout

- `src/app` — Next.js app router entrypoints + global providers.
- `src/components` — atomic directories (`atoms/`, `molecules/`, `organisms/`, `templates/`, `pages/`, `providers/`).
- `src/features` — Redux slices per domain (contracts today, more soon).
- `src/services` — RTK Query clients (shared fetchBaseQuery with env-driven base URL).
- `src/types` — shared TypeScript contracts aligned with backend schemas.

### Testing

Jest (via `next test`) + Testing Library ensure UI atoms behave as expected. Add new tests adjacent to components (e.g., `atoms/__tests__`).
