"""
Example 01 — Tracing to Console (Sync)

The simplest tracing setup: spans are printed to stdout.
No infrastructure needed — great for debugging during development.

Usage:
    python examples/01_tracing_console/tracing_console.py

Environment variables:
    AZURE_AI_PROJECT_ENDPOINT          — Your Foundry project endpoint
    AZURE_AI_MODEL_DEPLOYMENT_NAME     — Model deployment name (e.g., gpt-4o-mini)
    AZURE_EXPERIMENTAL_ENABLE_GENAI_TRACING=true
"""

import os

from dotenv import load_dotenv

load_dotenv()

# --- OpenTelemetry setup: export spans to console ---
from azure.core.settings import settings

settings.tracing_implementation = "opentelemetry"

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor, ConsoleSpanExporter

tracer_provider = TracerProvider()
tracer_provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
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
            agent_name="TracingConsoleDemo",
            definition=PromptAgentDefinition(
                model=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
                instructions="You are a helpful assistant. Keep answers brief.",
            ),
        )
        print(f"Agent created: {agent.name} (id: {agent.id})")

        # Create a conversation and exchange messages
        conversation = openai_client.conversations.create()

        response = openai_client.responses.create(
            conversation=conversation.id,
            extra_body={"agent_reference": {"name": agent.name, "type": "agent_reference"}},
            input="What is the capital of France?",
        )
        print(f"Response: {response.output_text}")

        response = openai_client.responses.create(
            conversation=conversation.id,
            extra_body={"agent_reference": {"name": agent.name, "type": "agent_reference"}},
            input="And what language do they speak there?",
        )
        print(f"Response: {response.output_text}")

        # Cleanup
        openai_client.conversations.delete(conversation_id=conversation.id)
        project_client.agents.delete_version(agent_name=agent.name, agent_version=agent.version)
        print("Cleanup complete")
