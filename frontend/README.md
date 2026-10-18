# DataMind frontend

Web interface for **DataMind — Talk to Your Data** (PS1). Ask a question in plain language and see the answer with the SQL that ran, the returned rows, a chart when the data supports one, and the evidence behind it.

- Implementation notes: [docs/FRONTEND_IMPLEMENTATION.md](docs/FRONTEND_IMPLEMENTATION.md)
- Backend contract: [docs/API_CONTRACT.md](docs/API_CONTRACT.md)

## Requirements

- Node.js 20.9 or newer (tested with Node 22.22, npm 10.9)
- The DataMind FastAPI backend running locally, or use demo mode to explore the UI without it

## Run on Windows (PowerShell or the VS Code terminal)

```powershell
cd frontend
npm ci
Copy-Item .env.example .env.local
# edit .env.local if the backend is not on http://localhost:8000
npm run dev
```

Open http://localhost:3000.

macOS/Linux: same commands, with `cp .env.example .env.local`.

Production build: `npm run build` then `npm start`.

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `NEXT_PUBLIC_API_BASE_URL` | `http://localhost:8000` | Backend base URL. Shipped to the browser, so never put secrets in it. |
| `NEXT_PUBLIC_DEMO_MODE` | `false` | Start in demo mode (bundled, clearly labeled sample fixtures; nothing is queried). |

Snowflake and model credentials belong in the backend's `.env` only. The frontend never asks for them.

## Scripts

| Command | What it does |
|---|---|
| `npm run dev` | Development server on port 3000 |
| `npm run build` / `npm start` | Production build and server |
| `npm run typecheck` | TypeScript strict check |
| `npm run lint` | ESLint |
| `npm test` | Vitest unit tests |

## Troubleshooting

- **"Backend offline"**: the API is not reachable at `NEXT_PUBLIC_API_BASE_URL`. Start the backend, then press the refresh icon in the header. Restart `npm run dev` after editing `.env.local`.
- **CORS error in the browser console**: allow `http://localhost:3000` in the FastAPI `CORSMiddleware`.
- **"Unexpected response"**: the backend answered with a shape that does not match `docs/API_CONTRACT.md`. The detail line names the first mismatching field.
