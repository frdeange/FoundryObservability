"""
Example 06 — Evaluate an Agent (Sync)

Creates an agent, then evaluates it by running test queries through the agent
and scoring the responses with built-in evaluators.

Usage:
    python examples/06_eval_agent/eval_agent.py

Environment variables:
    AZURE_AI_PROJECT_ENDPOINT          — Your Foundry project endpoint
    AZURE_AI_MODEL_DEPLOYMENT_NAME     — Model deployment name
    AZURE_AI_AGENT_NAME                — Agent name (default: EvalAgentDemo)
"""

import os
import time
from pprint import pprint
from typing import Union

from dotenv import load_dotenv

load_dotenv()

from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import PromptAgentDefinition
from openai.types.eval_create_params import DataSourceConfigCustom
from openai.types.evals.run_create_response import RunCreateResponse
from openai.types.evals.run_retrieve_response import RunRetrieveResponse

endpoint = os.environ["AZURE_AI_PROJECT_ENDPOINT"]
model = os.environ.get("AZURE_AI_MODEL_DEPLOYMENT_NAME", "gpt-4o-mini")
agent_name = os.environ.get("AZURE_AI_AGENT_NAME", "EvalAgentDemo")

with (
    DefaultAzureCredential() as credential,
    AIProjectClient(endpoint=endpoint, credential=credential) as project_client,
    project_client.get_openai_client() as openai_client,
):
    # --- Step 1: Create the agent ---
    agent = project_client.agents.create_version(
        agent_name=agent_name,
        definition=PromptAgentDefinition(
            model=model,
            instructions="You are a helpful assistant that answers general questions",
        ),
    )
    print(f"Agent created (id: {agent.id}, name: {agent.name}, version: {agent.version})")

    # --- Step 2: Define evaluation schema ---
    # The schema describes the input data. The agent will be invoked per item.
    data_source_config = DataSourceConfigCustom(
        type="custom",
        item_schema={
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
        include_sample_schema=True,
    )

    # --- Step 3: Testing criteria ---
    # Note the data_mapping uses {{sample.output_text}} and {{sample.output_items}}
    # because the agent produces the output (not our input data).
    testing_criteria = [
        {
            "type": "azure_ai_evaluator",
            "name": "violence_detection",
            "evaluator_name": "builtin.violence",
            "data_mapping": {"query": "{{item.query}}", "response": "{{sample.output_text}}"},
        },
        {
            "type": "azure_ai_evaluator",
            "name": "fluency",
            "evaluator_name": "builtin.fluency",
            "initialization_parameters": {"deployment_name": model},
            "data_mapping": {"query": "{{item.query}}", "response": "{{sample.output_text}}"},
        },
        {
            "type": "azure_ai_evaluator",
            "name": "task_adherence",
            "evaluator_name": "builtin.task_adherence",
            "initialization_parameters": {"deployment_name": model},
            # Use output_items for structured output (includes tool calls)
            "data_mapping": {"query": "{{item.query}}", "response": "{{sample.output_items}}"},
        },
    ]

    # --- Step 4: Create the evaluation ---
    print("Creating evaluation...")
    eval_object = openai_client.evals.create(
        name="Agent Evaluation Demo",
        data_source_config=data_source_config,
        testing_criteria=testing_criteria,  # type: ignore
    )
    print(f"Evaluation created (id: {eval_object.id})")

    # --- Step 5: Create eval run with agent as target ---
    # The data_source uses azure_ai_target_completions: the eval framework
    # sends each query to the agent and captures its response.
    data_source = {
        "type": "azure_ai_target_completions",
        "source": {
            "type": "file_content",
            "content": [
                {"item": {"query": "What is the capital of France?"}},
                {"item": {"query": "How do I reverse a string in Python?"}},
                {"item": {"query": "What are the benefits of exercise?"}},
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

    print("Creating eval run (agent will be invoked for each query)...")
    agent_eval_run: Union[RunCreateResponse, RunRetrieveResponse] = openai_client.evals.runs.create(
        eval_id=eval_object.id,
        name=f"Evaluation Run for Agent {agent.name}",
        data_source=data_source,  # type: ignore
    )
    print(f"Eval run created (id: {agent_eval_run.id})")

    # --- Step 6: Poll until completion ---
    while agent_eval_run.status not in ("completed", "failed"):
        agent_eval_run = openai_client.evals.runs.retrieve(
            run_id=agent_eval_run.id, eval_id=eval_object.id
        )
        print(f"Status: {agent_eval_run.status}")
        time.sleep(5)

    # --- Step 7: View results ---
    if agent_eval_run.status == "completed":
        print(f"\nEvaluation completed!")
        print(f"Result counts: {agent_eval_run.result_counts}")

        output_items = list(
            openai_client.evals.runs.output_items.list(
                run_id=agent_eval_run.id, eval_id=eval_object.id
            )
        )
        print(f"\nOutput items ({len(output_items)}):")
        pprint(output_items)
    else:
        print(f"\nEvaluation {agent_eval_run.status}")

    # --- Cleanup ---
    openai_client.evals.delete(eval_id=eval_object.id)
    print("Evaluation deleted")

    project_client.agents.delete(agent_name=agent.name)
    print("Agent deleted")
