"""
Example 04 — Custom Spans, Attributes, and trace_function (Sync)

Demonstrates:
  - Custom span processors that add attributes to every span
  - The @trace_function decorator for tracing your own functions
  - Manual span creation with tracer.start_as_current_span()

Usage:
    python examples/04_tracing_custom_spans/tracing_custom_spans.py

Environment variables:
    AZURE_AI_PROJECT_ENDPOINT          — Your Foundry project endpoint
    AZURE_AI_MODEL_DEPLOYMENT_NAME     — Model deployment name
    AZURE_EXPERIMENTAL_ENABLE_GENAI_TRACING=true
"""

import os
from typing import cast

from dotenv import load_dotenv

load_dotenv()

# --- OpenTelemetry setup ---
from azure.core.settings import settings

settings.tracing_implementation = "opentelemetry"

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider, SpanProcessor, ReadableSpan, Span
from opentelemetry.sdk.trace.export import SimpleSpanProcessor, ConsoleSpanExporter


# --- Custom span processor: adds attributes to every span ---
class CustomAttributeSpanProcessor(SpanProcessor):
    """Adds application-level metadata to every span."""

    def on_start(self, span: Span, parent_context=None):
        # Add to all spans
        span.set_attribute("app.session_id", "demo-session-001")
        span.set_attribute("app.environment", "development")
        span.set_attribute("app.version", "1.0.0")

    def on_end(self, span: ReadableSpan):
        pass


# Set up tracing with console exporter + custom processor
tracer_provider = TracerProvider()
tracer_provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
trace.set_tracer_provider(tracer_provider)

# Register the custom processor
provider = cast(TracerProvider, trace.get_tracer_provider())
provider.add_span_processor(CustomAttributeSpanProcessor())

# --- Enable SDK instrumentation ---
from azure.ai.projects.telemetry import AIProjectInstrumentor, trace_function

AIProjectInstrumentor().instrument()

# --- Custom functions with @trace_function decorator ---


@trace_function
def enrich_query(query: str, context: str) -> str:
    """Enriches a user query with context. Parameters and return value are auto-traced."""
    return f"[Context: {context}] {query}"


@trace_function
def format_response(response_text: str, format_type: str = "plain") -> dict:
    """Formats an agent response. All parameters are captured as span attributes."""
    return {
        "text": response_text,
        "format": format_type,
        "char_count": len(response_text),
    }


# --- Application code ---
from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import PromptAgentDefinition

tracer = trace.get_tracer(__name__)

with tracer.start_as_current_span("custom_spans_demo"):
    with (
        DefaultAzureCredential() as credential,
        AIProjectClient(
            endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"],
            credential=credential,
        ) as project_client,
        project_client.get_openai_client() as openai_client,
    ):
        agent = project_client.agents.create_version(
            agent_name="CustomSpansDemo",
            definition=PromptAgentDefinition(
                model=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
                instructions="You are a helpful assistant. Keep answers brief.",
            ),
        )
        print(f"Agent created: {agent.name}")

        conversation = openai_client.conversations.create()

        # Use the traced custom function to enrich the query
        with tracer.start_as_current_span("process_user_request"):
            enriched = enrich_query("What is AI?", "technology overview")
            print(f"Enriched query: {enriched}")

        # Call the agent
        response = openai_client.responses.create(
            conversation=conversation.id,
            extra_body={"agent_reference": {"name": agent.name, "type": "agent_reference"}},
            input="What is AI?",
        )

        # Use the traced custom function to format the response
        with tracer.start_as_current_span("process_agent_response"):
            formatted = format_response(response.output_text, format_type="summary")
            print(f"Formatted response: {formatted}")

        # Cleanup
        openai_client.conversations.delete(conversation_id=conversation.id)
        project_client.agents.delete_version(agent_name=agent.name, agent_version=agent.version)
        print("Cleanup complete")

print("\nCheck the console output above for spans with custom attributes:")
print("  - app.session_id, app.environment, app.version on every span")
print("  - code.function.parameter.* and code.function.return.value on @trace_function spans")
