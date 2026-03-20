# Tracing Deep-Dive

Tracing captures the execution flow of your AI application — every LLM call, tool invocation, and agent decision — so you can debug, optimize, and understand what happened.

## Enabling Tracing

### Step 1: Set the Feature Gate

Tracing is an **experimental preview feature**. You must opt in:

```bash
export AZURE_EXPERIMENTAL_ENABLE_GENAI_TRACING=true
```

This must be set **before** calling `AIProjectInstrumentor().instrument()`.

### Step 2: Instrument

```python
from azure.ai.projects.telemetry import AIProjectInstrumentor

AIProjectInstrumentor().instrument()
```

This hooks into the SDK and automatically creates spans for:
- Agent creation and deletion
- `responses.create()` calls
- `conversations.create()` / `.items.create()` calls
- Tool invocations
- Token usage

## Choosing an Exporter

You need an exporter to actually **see** the traces. Here are the three options, from simplest to production-ready:

| | Console | Aspire Dashboard | Azure Monitor |
|--|---------|------------------|---------------|
| **Setup** | None | Docker container | App Insights connection |
| **UI** | stdout text | Full trace explorer | Foundry Portal + App Insights |
| **Queryable** | No | No (local only) | Yes (Kusto/KQL) |
| **Persisted** | No (gone on exit) | Session only | 90 days (configurable) |
| **Production-ready** | No | No | Yes |
| **Cost** | Free | Free | Azure Monitor pricing |
| **Best for** | Quick debugging | Local development | Production + trace-based evals |

### Option A: Console (fastest for debugging)

Prints spans to stdout. No infrastructure needed.

```python
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor, ConsoleSpanExporter

tracer_provider = TracerProvider()
tracer_provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
trace.set_tracer_provider(tracer_provider)
```

→ [Example 01: Console Tracing](../examples/01_tracing_console/)

### Option B: Aspire Dashboard (best local UI)

Sends traces to the Aspire Dashboard via OTLP gRPC. You get a full trace explorer UI.

```python
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

otlp_exporter = OTLPSpanExporter(endpoint="http://localhost:4317", insecure=True)
tracer_provider = TracerProvider()
tracer_provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
trace.set_tracer_provider(tracer_provider)
```

Make sure the Aspire Dashboard is running (`docker compose up -d`) and then open http://localhost:18888.

→ [Example 02: Aspire Dashboard](../examples/02_tracing_aspire_dashboard/)

### Option C: Azure Monitor (production)

Sends traces to Application Insights, viewable in the Foundry portal.

```python
from azure.monitor.opentelemetry import configure_azure_monitor

connection_string = project_client.telemetry.get_application_insights_connection_string()
configure_azure_monitor(connection_string=connection_string)
```

→ [Example 03: Azure Monitor](../examples/03_tracing_azure_monitor/)

## Content Recording

By default, traces capture **metadata only** (model name, token counts, latency). To also capture **message contents** and **tool call details**:

```bash
export OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=true
```

What changes when enabled:

| | Content Recording OFF (default) | Content Recording ON |
|--|---|-|
| System prompts | Not captured | Full text in span events |
| User messages | Not captured | Full text in span events |
| Assistant responses | Not captured | Full text in span events |
| Tool call arguments | Not captured | JSON arguments in span events |
| Tool call results | Not captured | JSON results in span events |
| Token counts | Always captured | Always captured |
| Model name/latency | Always captured | Always captured |

> **Warning:** Message content may contain sensitive user data. Only enable this in development or when you understand the privacy implications.
>
> **Note:** This flag only affects the **automatic SDK instrumentation**. Custom function tracing via `@trace_function` always captures parameters and return values regardless of this setting.

## Creating Custom Spans

Use the `tracer` to create your own spans for application-level operations:

```python
tracer = trace.get_tracer(__name__)

with tracer.start_as_current_span("my_custom_operation"):
    # Your code here — this block becomes a span in the trace
    result = do_something()
```

## Tracing Your Own Functions

The `trace_function` decorator automatically traces function parameters and return values:

```python
from azure.ai.projects.telemetry import trace_function

@trace_function()
def get_weather(city: str) -> str:
    return f"Weather in {city}: sunny, 25°C"
```

Parameters are recorded as `code.function.parameter.<name>` and return values as `code.function.return.value`.

> **Note:** `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT` does **not** affect custom function tracing. When using `@trace_function`, parameters and return values are **always** traced.

## Custom Span Processors

Add custom attributes to every span using a `SpanProcessor`:

```python
from opentelemetry.sdk.trace import SpanProcessor, ReadableSpan, Span

class CustomAttributeSpanProcessor(SpanProcessor):
    def on_start(self, span: Span, parent_context=None):
        span.set_attribute("app.session_id", "abc-123")
        span.set_attribute("app.environment", "development")

    def on_end(self, span: ReadableSpan):
        pass

# Register it
provider = trace.get_tracer_provider()
provider.add_span_processor(CustomAttributeSpanProcessor())
```

→ [Example 04: Custom Spans](../examples/04_tracing_custom_spans/)

## Trace Context Propagation

When enabled, the SDK injects [W3C Trace Context](https://www.w3.org/TR/trace-context/) headers (`traceparent`, `tracestate`) into HTTP requests, so client-side and server-side spans share the same trace ID.

```bash
export AZURE_TRACING_GEN_AI_ENABLE_TRACE_CONTEXT_PROPAGATION=true
```

### Baggage Propagation

Baggage headers can carry additional key-value pairs through the trace. Disabled by default for security — baggage may contain sensitive data.

```bash
export AZURE_TRACING_GEN_AI_TRACE_CONTEXT_PROPAGATION_INCLUDE_BAGGAGE=true
```

> **Security:** Review what data your application adds to OpenTelemetry baggage before enabling this. Baggage is sent to Azure OpenAI and may be logged.

## Binary Data Tracing

When content recording is enabled, binary data (images, files) traces only file IDs and filenames by default. To include full binary data:

```bash
export AZURE_TRACING_GEN_AI_INCLUDE_BINARY_DATA=true
```

> **Warning:** This can significantly increase trace size. Ensure your backend supports the expected payload sizes.

## Disabling Automatic Instrumentation

The SDK automatically instruments `responses` and `conversations` APIs. To disable:

```bash
export AZURE_TRACING_GEN_AI_INSTRUMENT_RESPONSES_API=false
```

## Viewing Traces

| Location | How to access |
|----------|--------------|
| **Console** | stdout when using `ConsoleSpanExporter` |
| **Aspire Dashboard** | http://localhost:18888 → Traces tab |
| **Foundry Portal** | Project → Agents → Traces tab |
| **Application Insights** | Azure Portal → Application Insights resource → Transaction search |

### Tips for the Foundry Portal

- Pass the **agent ID** in your response requests so traces are correlated with the agent in the portal:
  ```python
  response = openai_client.responses.create(
      conversation=conversation.id,
      extra_body={"agent_reference": {"name": agent.name, "id": agent.id, "type": "agent_reference"}},
      input="Hello!",
  )
  ```
- Traces are retained for **90 days** by default.
- You can search by Conversation ID, Response ID, or Trace ID.

---

**Next:** [Evaluations Deep-Dive →](04-evaluations.md)
