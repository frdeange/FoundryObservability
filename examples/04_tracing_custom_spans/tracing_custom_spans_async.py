"""
Example 04 — Custom Spans, Attributes, and trace_function (Async)

Async variant: custom span processors, @trace_function, and manual spans.

Usage:
    python examples/04_tracing_custom_spans/tracing_custom_spans_async.py

Environment variables:
    AZURE_AI_PROJECT_ENDPOINT          — Your Foundry project endpoint
    AZURE_AI_MODEL_DEPLOYMENT_NAME     — Model deployment name
    AZURE_EXPERIMENTAL_ENABLE_GENAI_TRACING=true
"""

import asyncio
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


class CustomAttributeSpanProcessor(SpanProcessor):
    """Adds application-level metadata to every span."""

    def on_start(self, span: Span, parent_context=None):
        span.set_attribute("app.session_id", "demo-session-001")
        span.set_attribute("app.environment", "development")
        span.set_attribute("app.version", "1.0.0")

    def on_end(self, span: ReadableSpan):
        pass


tracer_provider = TracerProvider()
tracer_provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
trace.set_tracer_provider(tracer_provider)

provider = cast(TracerProvider, trace.get_tracer_provider())
provider.add_span_processor(CustomAttributeSpanProcessor())

# --- Enable SDK instrumentation ---
from azure.ai.projects.telemetry import AIProjectInstrumentor, trace_function

AIProjectInstrumentor().instrument()


# --- Custom functions with @trace_function decorator ---
@trace_function()
def enrich_query(query: str, context: str) -> str:
    return f"[Context: {context}] {query}"


@trace_function()
def format_response(response_text: str, format_type: str = "plain") -> dict:
    return {
        "text": response_text,
        "format": format_type,
        "char_count": len(response_text),
    }


# --- Application code ---
from azure.identity.aio import DefaultAzureCredential
from azure.ai.projects.aio import AIProjectClient
from azure.ai.projects.models import PromptAgentDefinition

tracer = trace.get_tracer(__name__)


async def main():
    with tracer.start_as_current_span("custom_spans_demo_async"):
        async with (
            DefaultAzureCredential() as credential,
            AIProjectClient(
                endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"],
                credential=credential,
            ) as project_client,
        ):
            async with project_client.get_openai_client() as openai_client:
                agent = await project_client.agents.create_version(
                    agent_name="CustomSpansDemoAsync",
                    definition=PromptAgentDefinition(
                        model=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
                        instructions="You are a helpful assistant. Keep answers brief.",
                    ),
                )
                print(f"Agent created: {agent.name}")

                conversation = await openai_client.conversations.create()

                with tracer.start_as_current_span("process_user_request"):
                    enriched = enrich_query("What is AI?", "technology overview")
                    print(f"Enriched query: {enriched}")

                response = await openai_client.responses.create(
                    conversation=conversation.id,
                    extra_body={"agent_reference": {"name": agent.name, "type": "agent_reference"}},
                    input="What is AI?",
                )

                with tracer.start_as_current_span("process_agent_response"):
                    formatted = format_response(response.output_text, format_type="summary")
                    print(f"Formatted response: {formatted}")

                await openai_client.conversations.delete(conversation_id=conversation.id)
                await project_client.agents.delete_version(
                    agent_name=agent.name, agent_version=agent.version
                )
                print("Cleanup complete")


asyncio.run(main())
