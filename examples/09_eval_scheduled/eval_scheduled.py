"""
Example 09 — Scheduled Evaluations (Sync)

Creates a dataset, evaluation, and schedule that runs recurring
evaluations (e.g., daily at 9 AM).

Prerequisites:
    - The project's Managed Identity must have the "Azure AI User" role.
      See docs/05-monitoring.md for RBAC setup instructions.

Usage:
    python examples/09_eval_scheduled/eval_scheduled.py

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
from azure.ai.projects.models import (
    DatasetVersion,
    Schedule,
    RecurrenceTrigger,
    DailyRecurrenceSchedule,
    EvaluationScheduleTask,
)
from openai.types.eval_create_params import DataSourceConfigCustom
from openai.types.evals.create_eval_jsonl_run_data_source_param import (
    CreateEvalJSONLRunDataSourceParam,
    SourceFileID,
)

endpoint = os.environ["AZURE_AI_PROJECT_ENDPOINT"]
model = os.environ.get("AZURE_AI_MODEL_DEPLOYMENT_NAME", "gpt-4o-mini")

# Path to sample data
script_dir = os.path.dirname(os.path.abspath(__file__))
data_file = os.path.join(script_dir, "..", "data", "sample_data_evaluation.jsonl")

with (
    DefaultAzureCredential() as credential,
    AIProjectClient(endpoint=endpoint, credential=credential) as project_client,
    project_client.get_openai_client() as client,
):
    # --- Step 1: Upload a dataset ---
    print("Uploading dataset...")
    dataset: DatasetVersion = project_client.datasets.upload_file(
        name="scheduled-eval-demo-data",
        version="1",
        file_path=data_file,
    )
    print(f"Dataset uploaded: {dataset.name} (id: {dataset.id})")

    # --- Step 2: Create evaluation ---
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
            "required": [],
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
            "name": "coherence",
            "evaluator_name": "builtin.coherence",
            "initialization_parameters": {"deployment_name": model},
            "data_mapping": {"query": "{{item.query}}", "response": "{{item.response}}"},
        },
    ]

    print("Creating evaluation...")
    eval_object = client.evals.create(
        name="Scheduled Evaluation Demo",
        data_source_config=data_source_config,
        testing_criteria=testing_criteria,  # type: ignore
    )
    print(f"Evaluation created (id: {eval_object.id})")

    # --- Step 3: Create the eval run config ---
    eval_run_config = {
        "eval_id": eval_object.id,
        "name": "scheduled_run",
        "data_source": CreateEvalJSONLRunDataSourceParam(
            type="jsonl",
            source=SourceFileID(type="file_id", id=dataset.id if dataset.id else ""),
        ),
    }

    # --- Step 4: Create a schedule ---
    print("Creating schedule (daily at 9 AM)...")
    schedule = Schedule(
        display_name="Daily Evaluation Schedule Demo",
        enabled=True,
        trigger=RecurrenceTrigger(
            interval=1,
            schedule=DailyRecurrenceSchedule(hours=[9]),
        ),
        task=EvaluationScheduleTask(
            eval_id=eval_object.id,
            eval_run=eval_run_config,
        ),
    )

    schedule_response = project_client.beta.schedules.create_or_update(
        schedule_id="daily-eval-demo-schedule",
        schedule=schedule,
    )
    print(f"Schedule created: {schedule_response.schedule_id}")
    pprint(schedule_response)

    # --- Step 5: List schedule runs ---
    time.sleep(5)
    schedule_runs = project_client.beta.schedules.list_runs(schedule_response.schedule_id)
    print(f"\nSchedule runs:")
    for run in schedule_runs:
        pprint(run)

    # --- Cleanup ---
    project_client.beta.schedules.delete(schedule_response.schedule_id)
    print("\nSchedule deleted")
    client.evals.delete(eval_id=eval_object.id)
    print("Evaluation deleted")
    project_client.datasets.delete(name=dataset.name, version=dataset.version)
    print("Dataset deleted")
