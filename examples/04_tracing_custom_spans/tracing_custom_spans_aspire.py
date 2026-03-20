"""
Example 04b — Custom Spans with Aspire Dashboard

Same custom spans, attributes, and @trace_function as 04,
but traces are sent to the Aspire Dashboard for visual exploration.

Prerequisites:
    docker compose up -d   (or the devcontainer auto-starts it)

Usage:
    python examples/04_tracing_custom_spans/tracing_custom_spans_aspire.py

Then open http://localhost:18888 → Traces tab to see:
  - Custom attributes (app.session_id, app.environment, app.version) on every span
  - @trace_function spans (enrich_query, format_response) with parameters captured
  - Manual spans (process_user_request, process_agent_response) grouping operations

Environment variables:
    AZURE_AI_PROJECT_ENDPOINT          — Your Foundry project endpoint
    AZURE_AI_MODEL_DEPLOYMENT_NAME     — Model deployment name
    AZURE_EXPERIMENTAL_ENABLE_GENAI_TRACING=true
    OTEL_EXPORTER_OTLP_ENDPOINT        — OTLP endpoint (default: http://localhost:4317)
"""

import os
from typing import cast

from dotenv import load_dotenv

load_dotenv()

# --- OpenTelemetry setup: OTLP exporter to Aspire Dashboard ---
from azure.core.settings import settings

settings.tracing_implementation = "opentelemetry"

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider, SpanProcessor, ReadableSpan, Span
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.resources import Resource
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

otlp_endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")


# --- Helper: get the real logged-in user from the Azure credential ---
def get_current_user_info() -> dict:
    """Extract real user info from the Azure CLI token (jwt claims)."""
    import json
    import base64
    from azure.identity import DefaultAzureCredential as SyncCred

    with SyncCred() as cred:
        token = cred.get_token("https://management.azure.com/.default")
    # Decode JWT payload (second segment) without verification — we just need the claims
    payload = token.token.split(".")[1]
    payload += "=" * (-len(payload) % 4)  # Fix base64 padding
    claims = json.loads(base64.urlsafe_b64decode(payload))
    return {
        "email": claims.get("upn") or claims.get("unique_name") or claims.get("email", "unknown"),
        "name": claims.get("name", "unknown"),
        "oid": claims.get("oid", "unknown"),       # User object ID
        "tid": claims.get("tid", "unknown"),        # Tenant ID
    }


# Get the REAL current user
user_info = get_current_user_info()
print(f"Detected user: {user_info['name']} ({user_info['email']})\n")


# --- Custom span processor: adds REAL user info to every span ---
class CustomAttributeSpanProcessor(SpanProcessor):
    """Adds real user identity and app metadata to every span."""

    def on_start(self, span: Span, parent_context=None):
        span.set_attribute("app.user.email", user_info["email"])
        span.set_attribute("app.user.name", user_info["name"])
        span.set_attribute("app.user.id", user_info["oid"])
        span.set_attribute("app.tenant.id", user_info["tid"])
        span.set_attribute("app.environment", "development")
        span.set_attribute("app.version", "1.0.0")

    def on_end(self, span: ReadableSpan):
        pass


# Set up tracing with OTLP exporter + custom processor
resource = Resource.create({"service.name": "custom-spans-demo"})
otlp_exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True)
tracer_provider = TracerProvider(resource=resource)
tracer_provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
trace.set_tracer_provider(tracer_provider)

# Register the custom processor
provider = cast(TracerProvider, trace.get_tracer_provider())
provider.add_span_processor(CustomAttributeSpanProcessor())

# --- Enable SDK instrumentation ---
from azure.ai.projects.telemetry import AIProjectInstrumentor, trace_function

AIProjectInstrumentor().instrument()

# --- Custom functions with @trace_function() decorator ---


@trace_function()
def enrich_query(query: str, context: str) -> str:
    """Enriches a user query with context. Parameters and return value are auto-traced."""
    return f"[Context: {context}] {query}"


@trace_function()
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

print(f"Sending traces to Aspire Dashboard at {otlp_endpoint}")
print("Open http://localhost:18888 to view traces\n")

with tracer.start_as_current_span("custom_spans_aspire_demo"):
    with (
        DefaultAzureCredential() as credential,
        AIProjectClient(
            endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"],
            credential=credential,
        ) as project_client,
        project_client.get_openai_client() as openai_client,
    ):
        agent = project_client.agents.create_version(
            agent_name="CustomSpansAspireDemo",
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

tracer_provider.force_flush()
print("\nTraces sent! Check Aspire Dashboard at http://localhost:18888")
print("Look for trace 'custom_spans_aspire_demo' and explore:")
print("  - app.session_id, app.environment, app.version on every span")
print("  - enrich_query and format_response spans with code.function.parameter.* attributes")
print("  - process_user_request and process_agent_response grouping spans")
