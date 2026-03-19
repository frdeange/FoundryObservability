"""
Example 10 — Agent Tracing with Tools (Sync)

Traces a multi-tool agent: creates an agent with a FunctionTool,
runs a conversation that triggers tool calls, and captures all
spans (agent creation, tool calls, LLM interactions).

Usage:
    python examples/10_agent_tracing/agent_tracing.py

Environment variables:
    AZURE_AI_PROJECT_ENDPOINT          — Your Foundry project endpoint
    AZURE_AI_MODEL_DEPLOYMENT_NAME     — Model deployment name
    AZURE_EXPERIMENTAL_ENABLE_GENAI_TRACING=true
"""

import json
import os

from dotenv import load_dotenv

load_dotenv()

# --- OpenTelemetry setup: console exporter (swap for Aspire/Azure Monitor as needed) ---
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
from azure.ai.projects.models import PromptAgentDefinition, FunctionTool
from openai.types.responses import FunctionCallOutput

tracer = trace.get_tracer(__name__)


# --- Local function that the agent can call ---
def get_weather(city: str) -> str:
    """Simulate a weather lookup."""
    weather_data = {
        "paris": "Sunny, 22°C",
        "london": "Cloudy, 15°C",
        "tokyo": "Rainy, 18°C",
        "madrid": "Sunny, 28°C",
    }
    return weather_data.get(city.lower(), f"No data for {city}")


# Define the tool for the agent
weather_tool = FunctionTool(
    name="get_weather",
    parameters={
        "type": "object",
        "properties": {
            "city": {"type": "string", "description": "The city to get weather for"},
        },
        "required": ["city"],
        "additionalProperties": False,
    },
    description="Get current weather for a city.",
    strict=True,
)

with tracer.start_as_current_span("agent_tracing_demo"):
    with (
        DefaultAzureCredential() as credential,
        AIProjectClient(
            endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"],
            credential=credential,
        ) as project_client,
        project_client.get_openai_client() as openai_client,
    ):
        # Create agent with tools
        agent = project_client.agents.create_version(
            agent_name="AgentTracingDemo",
            definition=PromptAgentDefinition(
                model=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
                instructions="You are a helpful weather assistant. Use the get_weather tool to answer weather questions.",
                tools=[weather_tool],
            ),
        )
        print(f"Agent created: {agent.name} (id: {agent.id})")

        conversation = openai_client.conversations.create()

        # Ask a question that should trigger a tool call
        response = openai_client.responses.create(
            conversation=conversation.id,
            extra_body={
                "agent_reference": {
                    "name": agent.name,
                    "id": agent.id,
                    "type": "agent_reference",
                }
            },
            input="What's the weather like in Paris?",
        )

        # Process tool calls if any
        function_calls = [output for output in response.output if output.type == "function_call"]
        if function_calls:
            tool_outputs = []
            for fc in function_calls:
                args = json.loads(fc.arguments)
                result = get_weather(**args)
                print(f"Tool call: {fc.name}({args}) → {result}")
                tool_outputs.append(
                    FunctionCallOutput(type="function_call_output", call_id=fc.call_id, output=result)
                )

            # Send tool results back to the agent
            response = openai_client.responses.create(
                conversation=conversation.id,
                extra_body={
                    "agent_reference": {
                        "name": agent.name,
                        "id": agent.id,
                        "type": "agent_reference",
                    }
                },
                input=tool_outputs,
            )

        print(f"Agent response: {response.output_text}")

        # Cleanup
        openai_client.conversations.delete(conversation_id=conversation.id)
        project_client.agents.delete_version(agent_name=agent.name, agent_version=agent.version)
        print("Cleanup complete")

print("\nCheck the console output for spans showing:")
print("  - Agent creation")
print("  - responses.create calls")
print("  - Tool call spans (function_call)")
