"""
Example 09 — Scheduled Evaluations (Async)

Async variant: creates scheduled recurring evaluations.

Usage:
    python examples/09_eval_scheduled/eval_scheduled_async.py

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
script_dir = os.path.dirname(os.path.abspath(__file__))
data_file = os.path.join(script_dir, "..", "data", "sample_data_evaluation.jsonl")


async def main():
    async with (
        DefaultAzureCredential() as credential,
        AIProjectClient(endpoint=endpoint, credential=credential) as project_client,
    ):
        async with project_client.get_openai_client() as client:
            print("Uploading dataset...")
            dataset: DatasetVersion = await project_client.datasets.upload_file(
                name="scheduled-eval-demo-data-async",
                version="1",
                file_path=data_file,
            )
            print(f"Dataset uploaded: {dataset.name}")

            data_source_config = DataSourceConfigCustom(
                type="custom",
                item_schema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "response": {"type": "string"},
                    },
                    "required": [],
                },
                include_sample_schema=True,
            )

            eval_object = await client.evals.create(
                name="Scheduled Evaluation Demo (Async)",
                data_source_config=data_source_config,
                testing_criteria=[
                    {
                        "type": "azure_ai_evaluator",
                        "name": "coherence",
                        "evaluator_name": "builtin.coherence",
                        "initialization_parameters": {"deployment_name": model},
                        "data_mapping": {"query": "{{item.query}}", "response": "{{item.response}}"},
                    },
                ],  # type: ignore
            )
            print(f"Evaluation created (id: {eval_object.id})")

            schedule = Schedule(
                display_name="Daily Eval Schedule (Async)",
                enabled=True,
                trigger=RecurrenceTrigger(interval=1, schedule=DailyRecurrenceSchedule(hours=[9])),
                task=EvaluationScheduleTask(
                    eval_id=eval_object.id,
                    eval_run={
                        "eval_id": eval_object.id,
                        "name": "scheduled_run_async",
                        "data_source": CreateEvalJSONLRunDataSourceParam(
                            type="jsonl",
                            source=SourceFileID(type="file_id", id=dataset.id if dataset.id else ""),
                        ),
                    },
                ),
            )

            schedule_response = await project_client.beta.schedules.create_or_update(
                schedule_id="daily-eval-demo-schedule-async",
                schedule=schedule,
            )
            print(f"Schedule created: {schedule_response.schedule_id}")

            await asyncio.sleep(5)
            schedule_runs = project_client.beta.schedules.list_runs(schedule_response.schedule_id)
            print("Schedule runs:")
            async for run in schedule_runs:
                pprint(run)




asyncio.run(main())
