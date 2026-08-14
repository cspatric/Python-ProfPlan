# Reading a trace

Tempo stores traces and has **no interface of its own**, and is deliberately not
published to the host. Grafana is the only window onto it. If you are looking
for a Tempo port, that is why you cannot find one.

## Opening one

1. <http://localhost:3000> (`admin` / `admin`)
2. Menu (☰) → **Explore**
3. Datasource selector, top left: switch from Prometheus to **Tempo**
4. Tab **TraceQL**, paste a trace id, or tab **Search** to browse by service
5. Time range, top right: **Last 1 hour**

## Three things that look like "it is broken" and are not

**A wide time range makes the search fail.** Tempo refuses any window longer
than **168 hours** with `range specified by start and end exceeds 168h0m0s`.
Setting the picker to something generous, like 2003 to 2027, returns nothing at
all, and Grafana reports the error quietly enough to miss. Widening the range
does not find more traces; past seven days it finds none. Looking a trace up by
id ignores the window entirely, so with an id in hand the picker does not
matter.

**A brand-new trace takes a few seconds to appear.** The ingester holds spans
briefly before they become searchable, measured here at about ten seconds.
Upload a document and search immediately and you will find nothing.

**Most of what you see is the metrics probe.** The background probe in
`app/infrastructure/telemetry/metrics.py` runs every 15 seconds in every worker
and each round produces its own small trace (`PING`, `LLEN`, `SELECT`,
`connect`). With four workers that is sixteen traces a minute, and they crowd
out the ones you care about in a recency-ordered list. Search by name to skip
them:

```
{ name = "POST /api/v1/documents" }
```

## From a log line to its trace

This is the reason all three signals exist together.
`RequestLoggingMiddleware` puts the `trace_id` on every request log line, so
Loki finds the request and Tempo explains it:

```
{container="backend-api-1"} | json | trace_id="<id>"
{container="backend-api-1"} | json | user_email="teacher@example.com"
```

Take the `trace_id` from the resulting line, paste it into the TraceQL tab, and
you are looking at the same request from the inside.

## What a good trace shows

A document upload, captured on a live stack:

```
+   0ms  profplan-api     POST /api/v1/documents        118ms   ← returns 202
+ 109ms  profplan-api     apply_async/documents.ingest    7ms   ← enqueues
+ 118ms  profplan-worker  run/documents.ingest         4586ms   ← another process
+ 281ms  profplan-worker  POST (embedding)             4351ms   ← the real cost
```

Thirty spans, two services, one trace: the context crossed the Redis broker, so
the HTTP request and the background job that outlived it are the same story.
And the answer it gives is one no aggregate metric would: **93% of the ingestion
was the embedding call**, not our code.
