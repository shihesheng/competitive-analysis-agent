# Local Development Setup

This project runs a FastAPI backend and a React/Vite frontend.

## Environment Files

Backend local env:

```text
backend/.env
```

Fill these if you want real Ark/Doubao calls:

```text
ARK_API_KEY=
ARK_EP=
```

For stable local frontend/backend integration tests, keep these as `0`:

```text
RESEARCH_AGENT_USE_LLM=0
EVIDENCE_AGENT_USE_LLM=0
PRODUCT_AGENT_USE_LLM=0
BUSINESS_AGENT_USE_LLM=0
```

After the Ark values are valid, change the relevant flags to `1` to enable model calls.

Frontend local env:

```text
frontend/.env
```

Default API URL:

```text
VITE_API_BASE_URL=http://127.0.0.1:8000
```

## One-Time Setup

From the repository root:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup-dev.ps1
```

This creates `backend/.venv`, installs Python dependencies, and runs `npm install` in `frontend`.

If Node/npm is missing, install Node.js LTS first, then rerun the setup script.

## Run Backend And Frontend Together

```powershell
powershell -ExecutionPolicy Bypass -File scripts\start-dev.ps1
```

Open:

```text
http://127.0.0.1:5173
```

Backend health check:

```text
http://127.0.0.1:8000/health
```

## Manual Commands

Backend:

```powershell
cd backend
.\.venv\Scripts\python.exe main.py
```

Frontend:

```powershell
cd frontend
npm run dev -- --host 127.0.0.1
```
