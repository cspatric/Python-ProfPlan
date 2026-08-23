# ProfPlan — System Architecture

> Eight diagrams, one story — the same story the presentation script tells, in
> the same order. Each diagram backs one block of the script: the boxes are the
> things the narration points at, and nothing appears here that the narration
> does not say.

- **Repository scope:** backend only (the React frontend lives in its own repo).
- **Style:** modular monolith, layered / Clean-Architecture-inspired
  (`presentation → application → domain → infrastructure`), Service pattern.
- **Runtime:** one Docker Compose file, one container per responsibility,
  two networks (frontal = Traefik ↔ API, internal = data services — Postgres,
  Redis, Ollama and PgBouncer are never exposed to the host).

> The decisions behind this shape, and what each one cost, are recorded in
> [`docs/adr/`](../adr/README.md). Read those before changing anything that
> looks backwards; several of them are, on purpose.

## The diagrams

| File | Script block | Shows |
|---|---|---|
| [`A0-backend-overview.mmd`](./A0-backend-overview.mmd) | 2 · Architecture and stack | The whole backend in one picture: Traefik at the left edge, the API's two halves (middleware chain + 13 modules), Celery below, the isolated data layer, the AI gateway and the observability stack |
| [`D1-monolith-and-layers.mmd`](./D1-monolith-and-layers.mmd) | 3 · Modular monolith | Monolith-vs-microservices, the four layers, the dependency rule, the ownership invariant |
| [`D2-request-end-to-end.mmd`](./D2-request-end-to-end.mmd) | 4 · A request end to end | Middleware order (and why it is reversed), 422 before app code, repository scoping, audit in the same transaction, cookies/OAuth/OIDC |
| [`D3-ai-end-to-end.mmd`](./D3-ai-end-to-end.mmd) | 5 · AI end to end | Ingestion on top, the gateway in the center (two tiers with their exact models, Bedrock, circuit breaker), retrieval at the bottom, plan generation and the PDF |
| [`D4-observability.mmd`](./D4-observability.mmd) | 6 · Observability | Three pipelines (Prometheus, Promtail→Loki, OTLP→Collector→Tempo), 12 alert rules, 4 SLOs, Grafana, CI validation |
| [`D5-scale.mmd`](./D5-scale.mmd) | 7 · Scale | Measured (28 runs, 750-user ceiling, endurance), calculated (the 0.13 coefficient), the four spreading layers, expected bottlenecks |
| [`D6-cost.mmd`](./D6-cost.mmd) | 8 · Cost — cued as `[MOSTRE D6]` | Local-first savings, the measured numbers (84%/23% inversion, 0.0125 vs 0.11 vs 0.79 USD), ledger + monthly budget, where saving was refused |
| [`D7-production-aws.mmd`](./D7-production-aws.mmd) | 8 · Production infrastructure | Terraform's 38 resources: VPC, EC2, RDS, S3, SSM, split observability, backup state |

The matching `.png` of each file is the render used in slides and in the video.

Re-render one after editing it:

```bash
cd docs/architecture
npx @mermaid-js/mermaid-cli -i D3-ai-end-to-end.mmd -o D3-ai-end-to-end.png -w 3000 -b white
```

Regenerate everything:

```bash
cd docs/architecture
for f in A0-*.mmd D*.mmd; do
  npx @mermaid-js/mermaid-cli -i "$f" -o "${f%.mmd}.png" -w 3000 -b white
done
```

> **Keep these pasteable, if you edit them.** Excalidraw's Mermaid importer
> chokes on `subgraph`, `%%` comments, YAML frontmatter, invisible `~~~` links and
> `<br/>`, and it fails *silently* — it drops back to pasting one flat image
> instead of shapes. Every diagram here avoids all five: groups are header nodes
> joined to their first child by a dotted link, and line breaks are Mermaid
> markdown strings (backticks). Verify a change renders with `mermaid-cli` before
> committing it; a parse error there is a silent failure in Excalidraw.

**Going deeper than the map.** [`docs/study/`](../study/) holds a 45-page LaTeX
guide to every technology on these diagrams — what it is, how it works, what it
does *here*, a 30-second explanation of each, and the follow-up questions.
Build it with `pdflatex profplan-tech-guide.tex` (twice).
