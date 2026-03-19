"""
Example 08 — Continuous Evaluation Rules (Async)

Async variant: sets up continuous evaluation rules.

Usage:
    python examples/08_eval_continuous/eval_continuous_async.py

Environment variables:
    AZURE_AI_PROJECT_ENDPOINT          — Your Foundry project endpoint
    AZURE_AI_MODEL_DEPLOYMENT_NAME     — Model deployment name
    AZURE_AI_AGENT_NAME                — Agent name (default: ContinuousEvalDemoAsync)
"""

import asyncio
import os

from dotenv import load_dotenv

load_dotenv()

from azure.identity.aio import DefaultAzureCredential
from azure.ai.projects.aio import AIProjectClient
from azure.ai.projects.models import (
    PromptAgentDefinition,
    EvaluationRule,
    ContinuousEvaluationRuleAction,
    EvaluationRuleFilter,
    EvaluationRuleEventType,
)

endpoint = os.environ["AZURE_AI_PROJECT_ENDPOINT"]
model = os.environ.get("AZURE_AI_MODEL_DEPLOYMENT_NAME", "gpt-4o-mini")
agent_name = os.environ.get("AZURE_AI_AGENT_NAME", "ContinuousEvalDemoAsync")


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
                    instructions="You are a helpful assistant that answers general questions",
                ),
            )
            print(f"Agent created: {agent.name}")

            eval_object = await openai_client.evals.create(
                name="Continuous Evaluation (Async)",
                data_source_config={"type": "azure_ai_source", "scenario": "responses"},  # type: ignore
                testing_criteria=[
                    {"type": "azure_ai_evaluator", "name": "violence", "evaluator_name": "builtin.violence"},
                ],  # type: ignore
            )
            print(f"Evaluation created (id: {eval_object.id})")

            rule = await project_client.evaluation_rules.create_or_update(
                id="continuous-eval-demo-rule-async",
                evaluation_rule=EvaluationRule(
                    display_name="Continuous Eval Demo Rule (Async)",
                    description="Evaluates every agent response for violence",
                    action=ContinuousEvaluationRuleAction(eval_id=eval_object.id, max_hourly_runs=100),
                    event_type=EvaluationRuleEventType.RESPONSE_COMPLETED,
                    filter=EvaluationRuleFilter(agent_name=agent.name),
                    enabled=True,
                ),
            )
            print(f"Continuous eval rule created: {rule.id}")

            # Run the agent
            conversation = await openai_client.conversations.create(
                items=[{"type": "message", "role": "user", "content": "What is the capital of France?"}],
            )
            response = await openai_client.responses.create(
                conversation=conversation.id,
                extra_body={"agent_reference": {"name": agent.name, "type": "agent_reference"}},
            )
            print(f"Response: {response.output_text}")

            # Wait for eval runs
            print("\nWaiting for evaluation runs...")
            for attempt in range(10):
                await asyncio.sleep(10)
                eval_runs = await openai_client.evals.runs.list(eval_id=eval_object.id, order="desc", limit=5)
                if len(eval_runs.data) > 0:
                    print(f"Found {len(eval_runs.data)} eval run(s)!")
                    break
                print(f"  Attempt {attempt + 1}/10...")

            # Cleanup
            await project_client.evaluation_rules.delete(id=rule.id)
            await openai_client.evals.delete(eval_id=eval_object.id)
            await openai_client.conversations.delete(conversation_id=conversation.id)
            await project_client.agents.delete_version(agent_name=agent.name, agent_version=agent.version)
            print("Cleanup complete")


asyncio.run(main())
