"""
Example 03 — Tracing to Azure Monitor (Sync)

Sends traces to Application Insights, viewable in the Foundry portal Traces tab.

Usage:
    python examples/03_tracing_azure_monitor/tracing_azure_monitor.py

Environment variables:
    AZURE_AI_PROJECT_ENDPOINT          — Your Foundry project endpoint
    AZURE_AI_MODEL_DEPLOYMENT_NAME     — Model deployment name
    AZURE_EXPERIMENTAL_ENABLE_GENAI_TRACING=true
"""

import os

from dotenv import load_dotenv

load_dotenv()

# --- Application code (Azure Monitor setup requires the project client) ---
from opentelemetry import trace
from azure.monitor.opentelemetry import configure_azure_monitor
from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import PromptAgentDefinition

agent = None

with (
    DefaultAzureCredential() as credential,
    AIProjectClient(
        endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"],
        credential=credential,
    ) as project_client,
):
    # --- Get Application Insights connection string from the project ---
    connection_string = project_client.telemetry.get_application_insights_connection_string()
    print(f"Application Insights connected: {connection_string[:50]}...")

    # --- Configure Azure Monitor as the trace exporter ---
    configure_azure_monitor(connection_string=connection_string)

    # --- Create a span for this scenario ---
    tracer = trace.get_tracer(__name__)
    scenario = os.path.basename(__file__)

    with tracer.start_as_current_span(scenario):
        with project_client.get_openai_client() as openai_client:
            # Create an agent
            agent = project_client.agents.create_version(
                agent_name="TracingAzureMonitorDemo",
                definition=PromptAgentDefinition(
                    model=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
                    instructions="You are a helpful assistant. Keep answers brief.",
                ),
            )
            print(f"Agent created: {agent.name} (id: {agent.id})")

            # Conversation
            conversation = openai_client.conversations.create()

            response = openai_client.responses.create(
                conversation=conversation.id,
                extra_body={
                    "agent_reference": {
                        "name": agent.name,
                        "id": agent.id,
                        "type": "agent_reference",
                    }
                },
                input="What is the size of France in square miles?",
            )
            print(f"Response: {response.output_text}")

            openai_client.conversations.delete(conversation_id=conversation.id)
            print("Conversation deleted")

    # NOTE: Agent is intentionally NOT deleted so you can see traces
    # associated with it in the Foundry portal.
    # To clean up manually later:
    #   project_client.agents.delete_version(agent_name="TracingAzureMonitorDemo", agent_version="1")

print(f"\nTraces sent to Azure Monitor!")
print(f"Agent kept alive: {agent.name} (id: {agent.id})")
print(f"\nView traces in (allow 2-5 min for ingestion):")
print(f"  1. Foundry portal → Your project → Agents → Traces tab")
print(f"  2. Azure portal → Application Insights → Transaction search")
