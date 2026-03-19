"""
Example 05 — Evaluation with Inline Data (Async)

Async variant: eval with built-in evaluators and inline JSONL data.

Usage:
    python examples/05_eval_inline_data/eval_inline_data_async.py

Environment variables:
    AZURE_AI_PROJECT_ENDPOINT          — Your Foundry project endpoint
    AZURE_AI_MODEL_DEPLOYMENT_NAME     — Model deployment name
"""

import asyncio
import os
from pprint import pprint

from dotenv import load_dotenv

load_dotenv()

from azure.identity.aio import DefaultAzureCredential
from azure.ai.projects.aio import AIProjectClient
from openai.types.eval_create_params import DataSourceConfigCustom
from openai.types.evals.create_eval_jsonl_run_data_source_param import (
    CreateEvalJSONLRunDataSourceParam,
    SourceFileContent,
    SourceFileContentContent,
)

endpoint = os.environ["AZURE_AI_PROJECT_ENDPOINT"]
model = os.environ.get("AZURE_AI_MODEL_DEPLOYMENT_NAME", "gpt-4o-mini")


async def main():
    async with (
        DefaultAzureCredential() as credential,
        AIProjectClient(endpoint=endpoint, credential=credential) as project_client,
    ):
        async with project_client.get_openai_client() as client:
            data_source_config = DataSourceConfigCustom(
                type="custom",
                item_schema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "response": {"type": "string"},
                        "context": {"type": "string"},
                        "ground_truth": {"type": "string"},
                    },
                    "required": ["query", "response"],
                },
                include_sample_schema=True,
            )

            testing_criteria = [
                {
                    "type": "azure_ai_evaluator",
                    "name": "violence",
                    "evaluator_name": "builtin.violence",
                    "data_mapping": {"query": "{{item.query}}", "response": "{{item.response}}"},
                },
                {
                    "type": "azure_ai_evaluator",
                    "name": "f1",
                    "evaluator_name": "builtin.f1_score",
                    "data_mapping": {"response": "{{item.response}}", "ground_truth": "{{item.ground_truth}}"},
                },
                {
                    "type": "azure_ai_evaluator",
                    "name": "coherence",
                    "evaluator_name": "builtin.coherence",
                    "initialization_parameters": {"deployment_name": model},
                    "data_mapping": {"query": "{{item.query}}", "response": "{{item.response}}"},
                },
            ]

            print("Creating evaluation...")
            eval_object = await client.evals.create(
                name="Inline Data Evaluation Demo (Async)",
                data_source_config=data_source_config,
                testing_criteria=testing_criteria,  # type: ignore
            )
            print(f"Evaluation created (id: {eval_object.id})")

            print("Creating eval run with inline data...")
            eval_run = await client.evals.runs.create(
                eval_id=eval_object.id,
                name="inline_data_run_async",
                data_source=CreateEvalJSONLRunDataSourceParam(
                    type="jsonl",
                    source=SourceFileContent(
                        type="file_content",
                        content=[
                            SourceFileContentContent(
                                item={
                                    "query": "What are some tips for staying healthy?",
                                    "context": "Health and wellness advice",
                                    "ground_truth": "Exercise regularly, eat balanced meals, and get enough sleep",
                                    "response": "To stay healthy, focus on regular exercise, a balanced diet, adequate sleep, and stress management.",
                                }
                            ),
                            SourceFileContentContent(
                                item={
                                    "query": "What is the capital of France?",
                                    "context": "Geography",
                                    "ground_truth": "Paris",
                                    "response": "The capital of France is Paris.",
                                }
                            ),
                        ],
                    ),
                ),
            )
            print(f"Eval run created (id: {eval_run.id})")

            while True:
                run = await client.evals.runs.retrieve(run_id=eval_run.id, eval_id=eval_object.id)
                if run.status in ("completed", "failed", "canceled"):
                    break
                print(f"Status: {run.status} — waiting...")
                await asyncio.sleep(5)

            if run.status == "completed":
                print(f"\nEvaluation completed!")
                print(f"Result counts: {run.result_counts}")
                output_items = []
                async for item in client.evals.runs.output_items.list(
                    run_id=run.id, eval_id=eval_object.id
                ):
                    output_items.append(item)
                print(f"\nOutput items ({len(output_items)}):")
                pprint(output_items)
            else:
                print(f"\nEvaluation {run.status}")

            await client.evals.delete(eval_id=eval_object.id)
            print("\nEvaluation deleted")


asyncio.run(main())
