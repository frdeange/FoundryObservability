"""
Example 04c — Custom Spans with Azure Monitor

Same custom spans, attributes, and @trace_function as 04,
but traces are sent to Azure Monitor / Application Insights.
Visible in the Foundry portal Traces tab.

Usage:
    python examples/04_tracing_custom_spans/tracing_custom_spans_azure_monitor.py

Then view traces in (allow 2-5 min for ingestion):
  1. Foundry portal → Your project → Agents → Traces tab
  2. Azure portal → Application Insights → Transaction search

Environment variables:
    AZURE_AI_PROJECT_ENDPOINT          — Your Foundry project endpoint
    AZURE_AI_MODEL_DEPLOYMENT_NAME     — Model deployment name
    AZURE_EXPERIMENTAL_ENABLE_GENAI_TRACING=true
"""

import os
from typing import cast

from dotenv import load_dotenv

load_dotenv()

# --- Application code (Azure Monitor setup requires the project client) ---
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider, SpanProcessor, ReadableSpan, Span
from azure.monitor.opentelemetry import configure_azure_monitor
from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import PromptAgentDefinition


# --- Custom span processor: adds attributes to every span ---
class CustomAttributeSpanProcessor(SpanProcessor):
    """Adds application-level metadata to every span."""

    def on_start(self, span: Span, parent_context=None):
        span.set_attribute("app.session_id", "demo-session-001")
        span.set_attribute("app.environment", "development")
        span.set_attribute("app.version", "1.0.0")

    def on_end(self, span: ReadableSpan):
        pass


with (
    DefaultAzureCredential() as credential,
    AIProjectClient(
        endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"],
        credential=credential,
    ) as project_client,
):
    # --- Get App Insights connection string and configure Azure Monitor ---
    connection_string = project_client.telemetry.get_application_insights_connection_string()
    print(f"Application Insights connected: {connection_string[:50]}...")
    configure_azure_monitor(connection_string=connection_string)

    # Register the custom span processor
    provider = cast(TracerProvider, trace.get_tracer_provider())
    provider.add_span_processor(CustomAttributeSpanProcessor())

    # --- Enable SDK instrumentation ---
    from azure.ai.projects.telemetry import AIProjectInstrumentor, trace_function

    AIProjectInstrumentor().instrument()

    # --- Custom functions with @trace_function() decorator ---
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

    # --- Main logic ---
    tracer = trace.get_tracer(__name__)
    scenario = os.path.basename(__file__)

    with tracer.start_as_current_span(scenario):
        with project_client.get_openai_client() as openai_client:
            agent = project_client.agents.create_version(
                agent_name="CustomSpansAzureMonitorDemo",
                definition=PromptAgentDefinition(
                    model=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
                    instructions="You are a helpful assistant. Keep answers brief.",
                ),
            )
            print(f"Agent created: {agent.name} (id: {agent.id})")

            conversation = openai_client.conversations.create()

            with tracer.start_as_current_span("process_user_request"):
                enriched = enrich_query("What is AI?", "technology overview")
                print(f"Enriched query: {enriched}")

            response = openai_client.responses.create(
                conversation=conversation.id,
                extra_body={
                    "agent_reference": {
                        "name": agent.name,
                        "id": agent.id,
                        "type": "agent_reference",
                    }
                },
                input="What is AI?",
            )

            with tracer.start_as_current_span("process_agent_response"):
                formatted = format_response(response.output_text, format_type="summary")
                print(f"Formatted response: {formatted}")

            openai_client.conversations.delete(conversation_id=conversation.id)
            print("Conversation deleted")

    # Agent intentionally NOT deleted so traces are visible in Foundry portal

print(f"\nTraces sent to Azure Monitor!")
print(f"Agent kept alive: CustomSpansAzureMonitorDemo")
print(f"\nView traces in (allow 2-5 min for ingestion):")
print(f"  1. Foundry portal → Your project → Agents → Traces tab")
print(f"  2. Azure portal → Application Insights → Transaction search")
print(f"\nCustom attributes to look for:")
print(f"  - app.session_id, app.environment, app.version")
print(f"  - code.function.parameter.* on enrich_query / format_response spans")
