# Async Patterns

Every example in this repository includes both a **sync** and an **async** variant. This document explains when and why to use each.

## Sync vs Async — Quick Comparison

| Aspect | Sync | Async |
|--------|------|-------|
| **Import** | `from azure.ai.projects import AIProjectClient` | `from azure.ai.projects.aio import AIProjectClient` |
| **Auth** | `from azure.identity import DefaultAzureCredential` | `from azure.identity.aio import DefaultAzureCredential` |
| **Context manager** | `with client:` | `async with client:` |
| **Method calls** | `client.agents.create_version(...)` | `await client.agents.create_version(...)` |
| **Dependency** | None extra | Requires `aiohttp` |
| **Complexity** | Low | Moderate |

## When to Use Sync

Use synchronous code when:

- **Learning and prototyping** — Simpler mental model, easier to debug step-by-step.
- **Scripts and one-off tasks** — Running a single evaluation, testing a single agent.
- **Sequential workflows** — When each step depends on the previous one and there's no opportunity for parallelism.
- **Small-scale operations** — Running a few evaluations, tracing a single agent.

```python
# Simple, readable, sequential
with AIProjectClient(endpoint=endpoint, credential=credential) as client:
    agent = client.agents.create_version(agent_name="test", definition=definition)
    # ... do work ...
    client.agents.delete_version(agent_name=agent.name, agent_version=agent.version)
```

## When to Use Async

Use asynchronous code when:

- **Production web services** — Handling multiple concurrent requests without blocking the event loop (e.g., FastAPI, aiohttp servers).
- **Batch operations** — Running multiple evaluations or agent conversations concurrently.
- **Multi-agent orchestration** — Communicating with multiple agents simultaneously.
- **High throughput** — When you need to maximize throughput and minimize idle time waiting for I/O.

```python
import asyncio

async def main():
    async with (
        DefaultAzureCredential() as credential,
        AIProjectClient(endpoint=endpoint, credential=credential) as client,
    ):
        agent = await client.agents.create_version(agent_name="test", definition=definition)
        # ... do work ...
        await client.agents.delete_version(agent_name=agent.name, agent_version=agent.version)

asyncio.run(main())
```

### Concurrent Operations Example

```python
import asyncio

async def evaluate_query(openai_client, eval_id, query):
    """Run an eval for a single query."""
    run = await openai_client.evals.runs.create(
        eval_id=eval_id,
        name=f"eval_{query[:20]}",
        data_source=build_data_source(query),
    )
    return run

async def main():
    async with get_client() as (project_client, openai_client):
        # Run multiple evaluations concurrently
        queries = ["What is AI?", "Explain quantum computing", "How does Python work?"]
        results = await asyncio.gather(
            *[evaluate_query(openai_client, eval_id, q) for q in queries],
            return_exceptions=True,  # Don't let one failure cancel everything
        )
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                print(f"Query {i} failed: {result}")
            else:
                print(f"Run {result.id}: {result.status}")
```

> **Always use `return_exceptions=True`** with `asyncio.gather()` when running independent operations. Without it, a single failure raises immediately and cancels all other tasks.

## Pros and Cons

### Async Advantages

| Advantage | Details |
|-----------|---------|
| **Concurrency** | Run multiple I/O operations simultaneously without threads |
| **Non-blocking** | Your application stays responsive while waiting for API calls |
| **Scalability** | Handle thousands of concurrent operations with minimal memory |
| **Framework compatibility** | Required for modern Python web frameworks (FastAPI, Starlette) |
| **Resource efficiency** | Single thread handles many connections, lower memory per connection |

### Async Disadvantages

| Disadvantage | Details |
|--------------|---------|
| **Complexity** | `async`/`await` syntax adds cognitive overhead |
| **Debugging** | Stack traces can be harder to read; `pdb` works differently |
| **All-or-nothing** | One blocking call in an async context blocks everything |
| **Library compatibility** | Not all libraries support async; mixing sync/async requires care |
| **Extra dependency** | Requires `aiohttp` package |
| **Error handling** | Exception propagation through `gather()` needs explicit handling |

## Async Pattern Reference

### Basic Client Setup

```python
import asyncio
import os
from azure.ai.projects.aio import AIProjectClient
from azure.identity.aio import DefaultAzureCredential

async def main():
    async with (
        DefaultAzureCredential() as credential,
        AIProjectClient(
            endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"],
            credential=credential,
        ) as project_client,
    ):
        async with project_client.get_openai_client() as openai_client:
            # Your code here
            pass

asyncio.run(main())
```

### Tracing with Async

Tracing setup (OpenTelemetry) is the **same** for both sync and async — the `AIProjectInstrumentor` and `TracerProvider` are configured before the async context. Only the client usage changes.

```python
# Tracing setup (same as sync)
from azure.ai.projects.telemetry import AIProjectInstrumentor
AIProjectInstrumentor().instrument()

# Then use the async client
async def main():
    async with get_async_client() as client:
        agent = await client.agents.create_version(...)
```

### Converting Sync to Async Checklist

1. Add `import asyncio` and `from azure.ai.projects.aio import AIProjectClient`
2. Change `from azure.identity import` → `from azure.identity.aio import`
3. Wrap `with` blocks → `async with`
4. Add `await` before every SDK method call
5. Wrap the entry point in `asyncio.run(main())`
6. Ensure `aiohttp` is installed

### Common Pitfalls

| Pitfall | What happens | Fix |
|---------|-------------|-----|
| Forgetting `await` | Returns a coroutine object instead of the result | Add `await` before every SDK call |
| Mixing sync/async clients | `TypeError` or unexpected blocking | Use `from azure.ai.projects.aio` consistently |
| Blocking call in async | Entire event loop freezes | Move blocking work to `asyncio.to_thread()` |
| `gather()` without `return_exceptions` | One failure cancels all tasks | Add `return_exceptions=True` |

---

**Previous:** [Evaluator Reference](07-evaluator-reference.md) | **Back to:** [README](../README.md)
