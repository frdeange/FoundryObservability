"""
Example 05 — Evaluation with Inline Data (Sync)

Creates an evaluation with built-in evaluators (violence, f1, coherence)
and runs it against inline JSONL data.

Usage:
    python examples/05_eval_inline_data/eval_inline_data.py

Environment variables:
    AZURE_AI_PROJECT_ENDPOINT          — Your Foundry project endpoint
    AZURE_AI_MODEL_DEPLOYMENT_NAME     — Model deployment name
"""

import os
import time
from pprint import pprint

from dotenv import load_dotenv

load_dotenv()

from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient
from openai.types.eval_create_params import DataSourceConfigCustom
from openai.types.evals.create_eval_jsonl_run_data_source_param import (
    CreateEvalJSONLRunDataSourceParam,
    SourceFileContent,
    SourceFileContentContent,
)

endpoint = os.environ["AZURE_AI_PROJECT_ENDPOINT"]
model = os.environ.get("AZURE_AI_MODEL_DEPLOYMENT_NAME", "gpt-4o-mini")

with (
    DefaultAzureCredential() as credential,
    AIProjectClient(endpoint=endpoint, credential=credential) as project_client,
    project_client.get_openai_client() as client,
):
    # --- Step 1: Define the data schema ---
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

    # --- Step 2: Define testing criteria (evaluators) ---
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

    # --- Step 3: Create the evaluation ---
    print("Creating evaluation...")
    eval_object = client.evals.create(
        name="Inline Data Evaluation Demo",
        data_source_config=data_source_config,
        testing_criteria=testing_criteria,  # type: ignore
    )
    print(f"Evaluation created (id: {eval_object.id})")

    # --- Step 4: Create an eval run with inline data ---
    print("Creating eval run with inline data...")
    eval_run = client.evals.runs.create(
        eval_id=eval_object.id,
        name="inline_data_run",
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
                            "query": "How do I improve my writing skills?",
                            "context": "Writing improvement techniques",
                            "ground_truth": "Practice regularly and read widely",
                            "response": "Read extensively, write daily, seek feedback, and study grammar fundamentals.",
                        }
                    ),
                    SourceFileContentContent(
                        item={
                            "query": "What is the capital of France?",
                            "context": "Geography question about European capitals",
                            "ground_truth": "Paris",
                            "response": "The capital of France is Paris.",
                        }
                    ),
                    SourceFileContentContent(
                        item={
                            "query": "Explain quantum computing",
                            "context": "Complex scientific concept explanation",
                            "ground_truth": "Quantum computing uses quantum mechanics principles",
                            "response": "Quantum computing leverages quantum mechanical phenomena like superposition and entanglement to process information.",
                        }
                    ),
                ],
            ),
        ),
    )
    print(f"Eval run created (id: {eval_run.id})")

    # --- Step 5: Poll until completion ---
    while True:
        run = client.evals.runs.retrieve(run_id=eval_run.id, eval_id=eval_object.id)
        if run.status in ("completed", "failed", "canceled"):
            break
        print(f"Status: {run.status} — waiting...")
        time.sleep(5)

    # --- Step 6: View results ---
    if run.status == "completed":
        print(f"\nEvaluation completed!")
        print(f"Result counts: {run.result_counts}")
        print(f"Report URL: {run.report_url}")

        output_items = list(
            client.evals.runs.output_items.list(run_id=run.id, eval_id=eval_object.id)
        )
        print(f"\nOutput items ({len(output_items)}):")
        pprint(output_items)
    else:
        print(f"\nEvaluation {run.status}")

    # --- Cleanup ---
    client.evals.delete(eval_id=eval_object.id)
    print("\nEvaluation deleted")
