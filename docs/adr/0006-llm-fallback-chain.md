# 0006 — One gateway, four providers, a breaker they share

**Status:** Accepted

## Context

The product cannot write a plan without a model, and models are the least
reliable dependency in the stack: they rate-limit, time out, change behaviour
and occasionally go down. Calls come from two places (the API and the workers),
and both can run in several replicas.

## Decision

Every AI call goes through one `LLMGateway`. It tries providers in order,
Anthropic, OpenAI, Gemini, and finally a local Ollama that can never be
disabled, and it holds a semaphore so the number of concurrent calls is bounded
regardless of how many requests arrive.

Failures feed a circuit breaker whose state lives **in Redis**, not in the
process: three failures open it, thirty seconds later it goes half open. Every
API and worker replica shares that judgement.

No database connection is held while a call is in flight, since a call can take
a minute and connections are the scarcer resource.

## Consequences

- One place to add a provider, one place to bound concurrency, one place that
  knows whether a provider is currently trusted.
- The last provider is local, so "every provider failed" means the machine
  itself is in trouble rather than a vendor having a bad afternoon.
- Breaker state in Redis means a replica that just started does not have to
  rediscover an outage the others already know about.
- The order is a cost and quality ranking baked into code and settings. It is
  not adaptive: it will keep trying a slow-but-up provider ahead of a fast one.

## What would change this

- **A provider that needs different prompting.** The gateway assumes one prompt
  works everywhere; a provider needing its own would push that knowledge into
  the gateway and is the point at which this abstraction starts to leak.
- **Cost becoming the binding constraint.** Routing by price per token, or by
  measured latency, is a different design from a fixed chain.

## Amendment — every remote provider moved behind Bedrock

The shape above is unchanged: one gateway, an ordered chain, a shared breaker, a
local last resort. What changed is who the remote rungs talk to. Anthropic,
OpenAI and Gemini were three vendors, three credentials, three billing
relationships and three SDK dialects; they are now three **model families**
reached through **Amazon Bedrock**, which speaks one Converse API and reports
tokens the same way whatever answers.

What that buys: one credential to rotate, one invoice to read, and a cost table
that covers every remote model because they all report usage identically. What
it costs: the chain no longer survives *Bedrock* being down — it survives a
model family being down. Ollama at the end is what keeps that from being a
single point of failure, and it is now carrying more of that weight than it did
when the rungs were independent vendors.

The chain is also per tier rather than global, since the tiers fail for
different reasons: `claude → openai → ollama` for writing an activity,
`nova → openai → ollama` for the short, high-volume calls. Each family keeps a
larger and a smaller model so the tier chooses the size, not just the vendor.
