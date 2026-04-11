# Humariri Calendar App — Claude Code Briefing

## What this project is
A family calendar web app called "Humariri Calendar" (named after our street in NZ).
Built by Mark as a vibe coding learning project. Currently deployed and in use by the family.

## The family
- **Mark** (Dad) — avatar colour: #4299e1 (blue)
- **Julie** (Mum) — avatar colour: #ed64a6 (pink)
- **Ryan** (son, 10) — avatar colour: #48bb78 (green)
- **Noah** (son, 8) — avatar colour: #ed8936 (orange)

## Live URLs
- Frontend: https://humariri-calendar.netlify.app
- Backend: https://calendar-app-production-c70a.up.railway.app

## Tech stack
- Frontend: vanilla HTML, CSS, JavaScript (index.html — single file)
- Backend: Python, FastAPI, SQLite (main.py)
- AI: OpenAI gpt-4o-mini for weekly family summary
- Deployed: Railway (backend) + Netlify (frontend)

## Key things to know
- Mark is NOT a developer — explain things clearly and simply
- Always use plain English explanations alongside code changes
- Secrets live in .env only — never hardcode API keys
- API_BASE in index.html points to the Railway URL
- PowerShell terminal — avoid && syntax, use separate lines
- Run backend with: python -m uvicorn main:app --reload

## Current priorities
- Migrate database from SQLite to PostgreSQL (Railway)
- Add simple password protection
- Keep all existing functionality intact

## Code style preferences
- Keep it simple and readable
- Add comments explaining what things do
- Mobile-first design
- Existing colour scheme: indigo/purple (#4f46e5, #7c3aed)