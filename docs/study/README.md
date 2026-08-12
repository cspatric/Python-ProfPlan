# Technology study guide (LaTeX)

A 54-page guide to every technology in the ProfPlan stack. For each one:
what it is, how it works, **what it does in this project**, a 30-second
explanation to say out loud, and the follow-up questions you will be asked.

Companion to [`../architecture/ARCHITECTURE.md`](../architecture/ARCHITECTURE.md):
that document is the map, this one explains every box on it.

## Build

Needs a TeX distribution with TikZ, `tcolorbox` and `pgfplots`
(`texlive-latex-extra` and `texlive-pictures` on Debian/Ubuntu). No external
tooling, no network.

```bash
pdflatex profplan-tech-guide.tex
pdflatex profplan-tech-guide.tex   # second pass for the table of contents
```

The output is `profplan-tech-guide.pdf`.

## Layout

| Path | Contents |
|---|---|
| `profplan-tech-guide.tex` | Preamble: palette, heading styles, the five content boxes, figure slots |
| `parts/00-how-to-use.tex` | How the guide is structured, the map, the eight flows |
| `parts/05-architecture.tex` | Modular monolith, the four layers, Service pattern vs CQRS, one request end to end |
| `parts/10-edge-runtime.tex` | Docker & Compose, Traefik, ASGI/Uvicorn, FastAPI, Pydantic, httpx/asyncpg/tenacity |
| `parts/20-data.tex` | PostgreSQL, pgvector, SQLAlchemy + Alembic, PgBouncer, Redis, MinIO |
| `parts/30-async.tex` | Celery, Flower |
| `parts/40-ai-rag.tex` | RAG, chunking and parsing libraries, Ollama + bge-m3, the LLM gateway, the planner, prompt injection |
| `parts/50-observability.tex` | Prometheus, node-exporter, Loki + Promtail, OpenTelemetry + Tempo, Grafana |
| `parts/60-security.tex` | Argon2id, JWT + cookies, password reset and email verification, CSRF, security headers, rate limiting, uploads, audit |
| `parts/70-quality.tex` | pytest, Locust, Ruff + uv, CI, Adminer + Postman |
| `parts/80-playbook.tex` | Six sentences that narrate the map, a demo script, trade-offs, cheat sheet, technology-to-file index, glossary |
| `figures/` | Optional real screenshots, see [`figures/README.md`](figures/README.md) |

The five recurring boxes are `\begin{role}`, `\begin{pitch}`, `\begin{qabox}`,
`\begin{gotcha}`, and the `\tech{name}{subtitle}{color}` heading. Colors match
the architecture diagram: grey edge, blue API, purple async, green data, orange
LLM, teal observability.
