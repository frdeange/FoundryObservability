"""
Example 11 — Agent-Specific Evaluation (Async)

Async variant: evaluates an agent with agent-specific evaluators.

Usage:
    python examples/11_agent_evaluation/agent_evaluation_async.py

Environment variables:
    AZURE_AI_PROJECT_ENDPOINT          — Your Foundry project endpoint
    AZURE_AI_MODEL_DEPLOYMENT_NAME     — Model deployment name
    AZURE_AI_AGENT_NAME                — Agent name (default: AgentEvalDemoAsync)
"""

import asyncio
import os
from pprint import pprint

from dotenv import load_dotenv

load_dotenv()

from azure.identity.aio import DefaultAzureCredential
from azure.ai.projects.aio import AIProjectClient
from azure.ai.projects.models import PromptAgentDefinition, FunctionTool
from openai.types.eval_create_params import DataSourceConfigCustom

endpoint = os.environ["AZURE_AI_PROJECT_ENDPOINT"]
model = os.environ.get("AZURE_AI_MODEL_DEPLOYMENT_NAME", "gpt-4o-mini")
agent_name = os.environ.get("AZURE_AI_AGENT_NAME", "AgentEvalDemoAsync")

weather_tool = FunctionTool(
    name="get_weather",
    parameters={
        "type": "object",
        "properties": {"city": {"type": "string", "description": "City name"}},
        "required": ["city"],
        "additionalProperties": False,
    },
    description="Get current weather for a city.",
    strict=True,
)


async def main():
    async with (
        DefaultAzureCredential() as credential,
        AIProjectClient(endpoint=endpoint, credential=credential) as project_client,
    ):
        async with project_client.get_openai_client() as openai_client:
            agent = await project_client.agents.create_version(
                agent_name=agent_name,
                definition=PromptAgentDefinition(
                    model=model,
                    instructions="You are a weather assistant. Use the get_weather tool.",
                    tools=[weather_tool],
                ),
            )
            print(f"Agent created: {agent.name} (version: {agent.version})")

            data_source_config = DataSourceConfigCustom(
                type="custom",
                item_schema={
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                    "required": ["query"],
                },
                include_sample_schema=True,
            )

            testing_criteria = [
                {
                    "type": "azure_ai_evaluator",
                    "name": "tool_call_accuracy",
                    "evaluator_name": "builtin.tool_call_accuracy",
                    "initialization_parameters": {"deployment_name": model},
                    "data_mapping": {"query": "{{item.query}}", "response": "{{sample.output_items}}"},
                },
                {
                    "type": "azure_ai_evaluator",
                    "name": "task_adherence",
                    "evaluator_name": "builtin.task_adherence",
                    "initialization_parameters": {"deployment_name": model},
                    "data_mapping": {"query": "{{item.query}}", "response": "{{sample.output_items}}"},
                },
                {
                    "type": "azure_ai_evaluator",
                    "name": "response_completeness",
                    "evaluator_name": "builtin.response_completeness",
                    "initialization_parameters": {"deployment_name": model},
                    "data_mapping": {"query": "{{item.query}}", "response": "{{sample.output_text}}"},
                },
            ]

            eval_object = await openai_client.evals.create(
                name="Agent-Specific Evaluation (Async)",
                data_source_config=data_source_config,
                testing_criteria=testing_criteria,  # type: ignore
            )
            print(f"Evaluation created (id: {eval_object.id})")

            data_source = {
                "type": "azure_ai_target_completions",
                "source": {
                    "type": "file_content",
                    "content": [
                        {"item": {"query": "What's the weather in Paris?"}},
                        {"item": {"query": "Is it raining in Tokyo?"}},
                    ],
                },
                "input_messages": {
                    "type": "template",
                    "template": [
                        {"type": "message", "role": "user", "content": {"type": "input_text", "text": "{{item.query}}"}}
                    ],
                },
                "target": {"type": "azure_ai_agent", "name": agent.name, "version": agent.version},
            }

            eval_run = await openai_client.evals.runs.create(
                eval_id=eval_object.id,
                name=f"Agent Eval Async {agent.name}",
                data_source=data_source,  # type: ignore
            )
            print(f"Eval run created (id: {eval_run.id})")

            while eval_run.status not in ("completed", "failed"):
                eval_run = await openai_client.evals.runs.retrieve(
                    run_id=eval_run.id, eval_id=eval_object.id
                )
                print(f"Status: {eval_run.status}")
                await asyncio.sleep(5)

            if eval_run.status == "completed":
                print(f"\nAgent evaluation completed! Results: {eval_run.result_counts}")
                output_items = []
                async for item in openai_client.evals.runs.output_items.list(
                    run_id=eval_run.id, eval_id=eval_object.id
                ):
                    output_items.append(item)
                pprint(output_items)

            await openai_client.evals.delete(eval_id=eval_object.id)
            await project_client.agents.delete(agent_name=agent.name)
            print("Cleanup complete")


asyncio.run(main())
