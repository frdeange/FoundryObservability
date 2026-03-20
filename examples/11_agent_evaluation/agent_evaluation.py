"""
Example 11 — Agent-Specific Evaluation (Sync)

Evaluates an agent using agent-specific evaluators:
tool_call_accuracy, task_adherence, intent_resolution, response_completeness.

Uses the structured output ({{sample.output_items}}) to evaluate tool usage behavior.

Usage:
    python examples/11_agent_evaluation/agent_evaluation.py

Environment variables:
    AZURE_AI_PROJECT_ENDPOINT          — Your Foundry project endpoint
    AZURE_AI_MODEL_DEPLOYMENT_NAME     — Model deployment name
    AZURE_AI_AGENT_NAME                — Agent name (default: AgentEvalDemo)
"""

import os
import time
from pprint import pprint
from typing import Union

from dotenv import load_dotenv

load_dotenv()

from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import PromptAgentDefinition, FunctionTool
from openai.types.eval_create_params import DataSourceConfigCustom
from openai.types.evals.run_create_response import RunCreateResponse
from openai.types.evals.run_retrieve_response import RunRetrieveResponse

endpoint = os.environ["AZURE_AI_PROJECT_ENDPOINT"]
model = os.environ.get("AZURE_AI_MODEL_DEPLOYMENT_NAME", "gpt-4o-mini")
agent_name = os.environ.get("AZURE_AI_AGENT_NAME", "AgentEvalDemo")

# Define tool for the agent
weather_tool = FunctionTool(
    name="get_weather",
    parameters={
        "type": "object",
        "properties": {
            "city": {"type": "string", "description": "City name"},
        },
        "required": ["city"],
        "additionalProperties": False,
    },
    description="Get current weather for a city.",
    strict=True,
)

with (
    DefaultAzureCredential() as credential,
    AIProjectClient(endpoint=endpoint, credential=credential) as project_client,
    project_client.get_openai_client() as openai_client,
):
    # --- Step 1: Create agent with tools ---
    agent = project_client.agents.create_version(
        agent_name=agent_name,
        definition=PromptAgentDefinition(
            model=model,
            instructions="You are a weather assistant. Use the get_weather tool to answer weather questions accurately.",
            tools=[weather_tool],
        ),
    )
    print(f"Agent created: {agent.name} (version: {agent.version})")

    # --- Step 2: Define schema and agent-specific evaluators ---
    data_source_config = DataSourceConfigCustom(
        type="custom",
        item_schema={
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
        include_sample_schema=True,
    )

    # Agent-specific testing criteria using {{sample.output_items}} for structured output
    testing_criteria = [
        {
            "type": "azure_ai_evaluator",
            "name": "tool_call_accuracy",
            "evaluator_name": "builtin.tool_call_accuracy",
            "initialization_parameters": {"deployment_name": model},
            "data_mapping": {
                "query": "{{item.query}}",
                "response": "{{sample.output_items}}",
            },
        },
        {
            "type": "azure_ai_evaluator",
            "name": "task_adherence",
            "evaluator_name": "builtin.task_adherence",
            "initialization_parameters": {"deployment_name": model},
            "data_mapping": {
                "query": "{{item.query}}",
                "response": "{{sample.output_items}}",
            },
        },
        {
            "type": "azure_ai_evaluator",
            "name": "intent_resolution",
            "evaluator_name": "builtin.intent_resolution",
            "initialization_parameters": {"deployment_name": model},
            "data_mapping": {
                "query": "{{item.query}}",
                "response": "{{sample.output_items}}",
            },
        },
        {
            "type": "azure_ai_evaluator",
            "name": "response_completeness",
            "evaluator_name": "builtin.response_completeness",
            "initialization_parameters": {"deployment_name": model},
            "data_mapping": {
                "query": "{{item.query}}",
                "response": "{{sample.output_text}}",
            },
        },
    ]

    # --- Step 3: Create evaluation ---
    print("Creating evaluation with agent-specific evaluators...")
    eval_object = openai_client.evals.create(
        name="Agent-Specific Evaluation Demo",
        data_source_config=data_source_config,
        testing_criteria=testing_criteria,  # type: ignore
    )
    print(f"Evaluation created (id: {eval_object.id})")

    # --- Step 4: Run eval with agent as target ---
    data_source = {
        "type": "azure_ai_target_completions",
        "source": {
            "type": "file_content",
            "content": [
                {"item": {"query": "What's the weather in Paris?"}},
                {"item": {"query": "Is it raining in Tokyo right now?"}},
                {"item": {"query": "Compare the weather in London and Madrid"}},
            ],
        },
        "input_messages": {
            "type": "template",
            "template": [
                {"type": "message", "role": "user", "content": {"type": "input_text", "text": "{{item.query}}"}}
            ],
        },
        "target": {
            "type": "azure_ai_agent",
            "name": agent.name,
            "version": agent.version,
        },
    }

    print("Creating eval run (agent will be invoked with tool calls)...")
    eval_run: Union[RunCreateResponse, RunRetrieveResponse] = openai_client.evals.runs.create(
        eval_id=eval_object.id,
        name=f"Agent Eval {agent.name}",
        data_source=data_source,  # type: ignore
    )
    print(f"Eval run created (id: {eval_run.id})")

    # --- Step 5: Poll and view results ---
    while eval_run.status not in ("completed", "failed"):
        eval_run = openai_client.evals.runs.retrieve(run_id=eval_run.id, eval_id=eval_object.id)
        print(f"Status: {eval_run.status}")
        time.sleep(5)

    if eval_run.status == "completed":
        print(f"\nAgent evaluation completed!")
        print(f"Result counts: {eval_run.result_counts}")
        print(f"Report URL: {eval_run.report_url}")

        output_items = list(
            openai_client.evals.runs.output_items.list(run_id=eval_run.id, eval_id=eval_object.id)
        )
        print(f"\nDetailed results ({len(output_items)} items):")
        pprint(output_items)
    else:
        print(f"\nEvaluation {eval_run.status}")


