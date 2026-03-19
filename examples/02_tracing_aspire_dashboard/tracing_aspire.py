"""
Example 02 — Tracing to Aspire Dashboard (Sync)

Sends traces to the Aspire Dashboard via OTLP gRPC.
Open http://localhost:18888 to visualize traces.

Prerequisites:
    docker compose up -d   (or the devcontainer auto-starts it)

Usage:
    python examples/02_tracing_aspire_dashboard/tracing_aspire.py

Environment variables:
    AZURE_AI_PROJECT_ENDPOINT          — Your Foundry project endpoint
    AZURE_AI_MODEL_DEPLOYMENT_NAME     — Model deployment name
    AZURE_EXPERIMENTAL_ENABLE_GENAI_TRACING=true
    OTEL_EXPORTER_OTLP_ENDPOINT        — OTLP endpoint (default: http://localhost:4317)
"""

import os

from dotenv import load_dotenv

load_dotenv()

# --- OpenTelemetry setup: export spans to Aspire Dashboard via OTLP ---
from azure.core.settings import settings

settings.tracing_implementation = "opentelemetry"

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.resources import Resource
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

otlp_endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")

resource = Resource.create({"service.name": "foundry-observability-demo"})
otlp_exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True)
tracer_provider = TracerProvider(resource=resource)
tracer_provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
trace.set_tracer_provider(tracer_provider)

# --- Enable SDK instrumentation ---
from azure.ai.projects.telemetry import AIProjectInstrumentor

AIProjectInstrumentor().instrument()

# --- Application code ---
from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import PromptAgentDefinition

tracer = trace.get_tracer(__name__)
scenario = os.path.basename(__file__)

print(f"Sending traces to Aspire Dashboard at {otlp_endpoint}")
print("Open http://localhost:18888 to view traces\n")

with tracer.start_as_current_span(scenario):
    with (
        DefaultAzureCredential() as credential,
        AIProjectClient(
            endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"],
            credential=credential,
        ) as project_client,
        project_client.get_openai_client() as openai_client,
    ):
        # Create an agent
        agent = project_client.agents.create_version(
            agent_name="TracingAspireDemo",
            definition=PromptAgentDefinition(
                model=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
                instructions="You are a helpful assistant. Keep answers brief.",
            ),
        )
        print(f"Agent created: {agent.name} (id: {agent.id})")

        # Create a conversation
        conversation = openai_client.conversations.create()

        # Turn 1
        response = openai_client.responses.create(
            conversation=conversation.id,
            extra_body={"agent_reference": {"name": agent.name, "type": "agent_reference"}},
            input="What are the top 3 largest cities in Spain?",
        )
        print(f"Response: {response.output_text}")

        # Turn 2
        response = openai_client.responses.create(
            conversation=conversation.id,
            extra_body={"agent_reference": {"name": agent.name, "type": "agent_reference"}},
            input="Which one has the best weather?",
        )
        print(f"Response: {response.output_text}")

        # Cleanup
        openai_client.conversations.delete(conversation_id=conversation.id)
        project_client.agents.delete_version(agent_name=agent.name, agent_version=agent.version)

        # Flush to ensure all spans are exported before exit
        tracer_provider.force_flush()
        print("\nTraces sent! Check the Aspire Dashboard at http://localhost:18888")
