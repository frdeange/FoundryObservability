"""
Example 08 — Continuous Evaluation Rules (Sync)

Sets up a continuous evaluation rule that automatically evaluates
every agent response using built-in evaluators.

Usage:
    python examples/08_eval_continuous/eval_continuous.py

Environment variables:
    AZURE_AI_PROJECT_ENDPOINT          — Your Foundry project endpoint
    AZURE_AI_MODEL_DEPLOYMENT_NAME     — Model deployment name
    AZURE_AI_AGENT_NAME                — Agent name (default: ContinuousEvalDemo)
"""

import os
import time

from dotenv import load_dotenv

load_dotenv()

from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import (
    PromptAgentDefinition,
    EvaluationRule,
    ContinuousEvaluationRuleAction,
    EvaluationRuleFilter,
    EvaluationRuleEventType,
)

endpoint = os.environ["AZURE_AI_PROJECT_ENDPOINT"]
model = os.environ.get("AZURE_AI_MODEL_DEPLOYMENT_NAME", "gpt-4o-mini")
agent_name = os.environ.get("AZURE_AI_AGENT_NAME", "ContinuousEvalDemo")

with (
    DefaultAzureCredential() as credential,
    AIProjectClient(endpoint=endpoint, credential=credential) as project_client,
    project_client.get_openai_client() as openai_client,
):
    # --- Step 1: Create an agent ---
    agent = project_client.agents.create_version(
        agent_name=agent_name,
        definition=PromptAgentDefinition(
            model=model,
            instructions="You are a helpful assistant that answers general questions",
        ),
    )
    print(f"Agent created: {agent.name} (version: {agent.version})")

    # --- Step 2: Create an evaluation for continuous use ---
    # Note: data_source_config scenario is "responses" for continuous evaluation
    data_source_config = {"type": "azure_ai_source", "scenario": "responses"}
    testing_criteria = [
        {
            "type": "azure_ai_evaluator",
            "name": "violence_detection",
            "evaluator_name": "builtin.violence",
        },
    ]

    eval_object = openai_client.evals.create(
        name="Continuous Evaluation",
        data_source_config=data_source_config,  # type: ignore
        testing_criteria=testing_criteria,  # type: ignore
    )
    print(f"Evaluation created (id: {eval_object.id})")

    # --- Step 3: Create the continuous evaluation rule ---
    rule = project_client.evaluation_rules.create_or_update(
        id="continuous-eval-demo-rule",
        evaluation_rule=EvaluationRule(
            display_name="Continuous Eval Demo Rule",
            description="Evaluates every agent response for violence",
            action=ContinuousEvaluationRuleAction(
                eval_id=eval_object.id,
                max_hourly_runs=100,
            ),
            event_type=EvaluationRuleEventType.RESPONSE_COMPLETED,
            filter=EvaluationRuleFilter(agent_name=agent.name),
            enabled=True,
        ),
    )
    print(f"Continuous eval rule created: {rule.id}")

    # --- Step 4: Run the agent to generate responses that trigger evaluations ---
    conversation = openai_client.conversations.create(
        items=[{"type": "message", "role": "user", "content": "What is the capital of France?"}],
    )
    print(f"Conversation created: {conversation.id}")

    response = openai_client.responses.create(
        conversation=conversation.id,
        extra_body={"agent_reference": {"name": agent.name, "type": "agent_reference"}},
    )
    print(f"Response: {response.output_text}")

    # Send a few more messages
    for i in range(3):
        openai_client.conversations.items.create(
            conversation_id=conversation.id,
            items=[{"type": "message", "role": "user", "content": f"Question {i + 1}: Tell me something interesting"}],
        )
        response = openai_client.responses.create(
            conversation=conversation.id,
            extra_body={"agent_reference": {"name": agent.name, "type": "agent_reference"}},
        )
        print(f"Response {i + 1}: {response.output_text[:80]}...")
        time.sleep(2)

    # --- Step 5: Check for evaluation runs ---
    print("\nWaiting for evaluation runs to appear...")
    for attempt in range(10):
        time.sleep(10)
        eval_runs = openai_client.evals.runs.list(eval_id=eval_object.id, order="desc", limit=5)
        if len(eval_runs.data) > 0:
            print(f"Found {len(eval_runs.data)} eval run(s)!")
            for run in eval_runs.data:
                print(f"  Run {run.id}: status={run.status}")
                if run.report_url:
                    print(f"  Report: {run.report_url}")
            break
        print(f"  Attempt {attempt + 1}/10 — no runs yet...")


