# TenderIQ

TenderIQ is an intelligent end-to-end procurement and digital bidding platform. This repository currently contains only the platform foundation; business modules will be implemented incrementally.

## Architecture

- `frontend/` — Next.js App Router application with TypeScript, Tailwind CSS, and ESLint
- `backend/` — Express API with TypeScript, Zod environment validation, CORS, Helmet, and Prisma
- `backend/ai-service/` — isolated, minimal FastAPI service for future document intelligence
- PostgreSQL — relational database, accessed through Prisma

```text
TenderIQ/
├── frontend/
│   └── src/app/
├── backend/
│   ├── src/
│   ├── prisma/
│   └── ai-service/
├── docker-compose.yml
└── README.md
```

## Prerequisites

- Node.js 20.19 or newer and npm
- Python 3.10 or newer
- PostgreSQL 14 or newer, or Docker with Docker Compose

## Environment setup

Copy `frontend/.env.example` to `frontend/.env.local` and `backend/.env.example` to `backend/.env`. The development values are safe local defaults; change the database credentials for any shared or deployed environment.

Frontend variable:

- `NEXT_PUBLIC_API_URL` — public URL of the main API

Backend variables:

- `NODE_ENV` — `development`, `test`, or `production`
- `PORT` — API port (default `5000`)
- `CORS_ORIGIN` — allowed frontend origin
- `DATABASE_URL` — PostgreSQL connection URL used by Prisma

## Start PostgreSQL

With Docker installed, run from the repository root:

```sh
docker compose up -d postgres
```

Alternatively, provide a `DATABASE_URL` for an existing PostgreSQL instance.

## Run the applications

Frontend (`http://localhost:3000`):

```sh
cd frontend
npm install
npm run dev
```

Main API (`http://localhost:5000`):

```sh
cd backend
npm install
npm run prisma:generate
npm run dev
```

AI service (`http://localhost:8000`):

```sh
cd backend/ai-service
python -m venv .venv
# Activate the environment for your shell.
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8000
```

## Validation commands

- Frontend: `npm run lint`, `npm run typecheck`, `npm run build`
- Backend: `npm run lint`, `npm run typecheck`, `npm run build`
- Prisma: `npm run prisma:validate`, `npm run prisma:generate`

## Health endpoints

- Main API: `GET http://localhost:5000/health`
- AI service: `GET http://localhost:8000/health`
