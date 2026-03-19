"""
Example 03 — Tracing to Azure Monitor (Async)

Async variant: sends traces to Application Insights.

Usage:
    python examples/03_tracing_azure_monitor/tracing_azure_monitor_async.py

Environment variables:
    AZURE_AI_PROJECT_ENDPOINT          — Your Foundry project endpoint
    AZURE_AI_MODEL_DEPLOYMENT_NAME     — Model deployment name
    AZURE_EXPERIMENTAL_ENABLE_GENAI_TRACING=true
"""

import asyncio
import os

from dotenv import load_dotenv

load_dotenv()

from opentelemetry import trace
from azure.monitor.opentelemetry import configure_azure_monitor
from azure.identity.aio import DefaultAzureCredential
from azure.ai.projects.aio import AIProjectClient
from azure.ai.projects.models import PromptAgentDefinition

# Note: We need a sync client briefly to get the connection string,
# since configure_azure_monitor is a sync setup call.
from azure.identity import DefaultAzureCredential as SyncCredential
from azure.ai.projects import AIProjectClient as SyncClient


async def main():
    # Get App Insights connection string (sync, one-time setup)
    with (
        SyncCredential() as sync_cred,
        SyncClient(endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"], credential=sync_cred) as sync_client,
    ):
        connection_string = sync_client.telemetry.get_application_insights_connection_string()
        print(f"Application Insights connected: {connection_string[:50]}...")

    configure_azure_monitor(connection_string=connection_string)

    tracer = trace.get_tracer(__name__)
    scenario = os.path.basename(__file__)

    with tracer.start_as_current_span(scenario):
        async with (
            DefaultAzureCredential() as credential,
            AIProjectClient(
                endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"],
                credential=credential,
            ) as project_client,
        ):
            async with project_client.get_openai_client() as openai_client:
                agent = await project_client.agents.create_version(
                    agent_name="TracingAzureMonitorDemoAsync",
                    definition=PromptAgentDefinition(
                        model=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
                        instructions="You are a helpful assistant. Keep answers brief.",
                    ),
                )
                print(f"Agent created: {agent.name} (id: {agent.id})")

                conversation = await openai_client.conversations.create()

                response = await openai_client.responses.create(
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

                await openai_client.conversations.delete(conversation_id=conversation.id)
                await project_client.agents.delete_version(
                    agent_name=agent.name, agent_version=agent.version
                )

    print("\nTraces sent to Azure Monitor!")
    print("View them in: Foundry portal → Your project → Agents → Traces tab")


asyncio.run(main())
