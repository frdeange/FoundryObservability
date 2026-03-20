"""
Example 07 — Evaluate from Application Insights Traces (Async)

Async variant: queries trace IDs from App Insights and evaluates them.

Usage:
    python examples/07_eval_traces/eval_traces_async.py

Environment variables:
    AZURE_AI_PROJECT_ENDPOINT          — Your Foundry project endpoint
    AZURE_AI_MODEL_DEPLOYMENT_NAME     — Model deployment name
    APPINSIGHTS_RESOURCE_ID            — Application Insights resource ID
    AGENT_ID                           — Agent ID for filtering traces
    TRACE_LOOKBACK_HOURS               — Hours to look back (default: 1)
"""

import asyncio
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List
from pprint import pprint

from dotenv import load_dotenv

load_dotenv()

from azure.identity import DefaultAzureCredential as SyncCredential
from azure.identity.aio import DefaultAzureCredential
from azure.monitor.query import LogsQueryClient, LogsQueryStatus
from azure.ai.projects.aio import AIProjectClient

endpoint = os.environ["AZURE_AI_PROJECT_ENDPOINT"]
appinsights_resource_id = os.environ["APPINSIGHTS_RESOURCE_ID"]
agent_id = os.environ["AGENT_ID"]
model = os.environ.get("AZURE_AI_MODEL_DEPLOYMENT_NAME", "gpt-4o-mini")
lookback_hours = int(os.environ.get("TRACE_LOOKBACK_HOURS", "1"))


def build_evaluator_config(name: str, evaluator_name: str) -> Dict[str, Any]:
    return {
        "type": "azure_ai_evaluator",
        "name": name,
        "evaluator_name": evaluator_name,
        "data_mapping": {
            "query": "{{query}}",
            "response": "{{response}}",
            "tool_definitions": "{{tool_definitions}}",
        },
        "initialization_parameters": {"deployment_name": model},
    }


def get_trace_ids(resource_id: str, tracked_agent_id: str, start: datetime, end: datetime) -> List[str]:
    """Sync helper — LogsQueryClient doesn't have a standard async variant."""
    query = f"""
    dependencies
    | where timestamp between (datetime({start.isoformat()}) .. datetime({end.isoformat()}))
    | extend agent_id = tostring(customDimensions["gen_ai.agent.id"])
    | where agent_id == "{tracked_agent_id}"
    | distinct operation_Id
    """
    with SyncCredential() as cred:
        client = LogsQueryClient(cred)
        response = client.query_resource(resource_id, query=query, timespan=None)

    if response.status == LogsQueryStatus.SUCCESS:
        return [row[0] for table in response.tables for row in table.rows]
    return []


async def main():
    end_time = datetime.now(tz=timezone.utc)
    start_time = end_time - timedelta(hours=lookback_hours)

    print(f"Querying App Insights for traces (agent: {agent_id})...")
    trace_ids = get_trace_ids(appinsights_resource_id, agent_id, start_time, end_time)

    if not trace_ids:
        print("No trace IDs found.")
        return

    print(f"Found {len(trace_ids)} trace IDs")

    async with (
        DefaultAzureCredential() as credential,
        AIProjectClient(endpoint=endpoint, credential=credential) as project_client,
    ):
        async with project_client.get_openai_client() as client:
            testing_criteria = [
                build_evaluator_config("intent_resolution", "builtin.intent_resolution"),
                build_evaluator_config("task_adherence", "builtin.task_adherence"),
            ]

            eval_object = await client.evals.create(
                name="Trace-Based Evaluation (Async)",
                data_source_config={"type": "azure_ai_source", "scenario": "traces"},  # type: ignore
                testing_criteria=testing_criteria,  # type: ignore
            )
            print(f"Evaluation created (id: {eval_object.id})")

            eval_run = await client.evals.runs.create(
                eval_id=eval_object.id,
                name=f"trace_eval_async_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                data_source={"type": "azure_ai_traces", "trace_ids": trace_ids, "lookback_hours": lookback_hours},  # type: ignore
            )

            while True:
                run = await client.evals.runs.retrieve(run_id=eval_run.id, eval_id=eval_object.id)
                if run.status in ("completed", "failed", "canceled"):
                    break
                await asyncio.sleep(5)

            if run.status == "completed":
                print(f"Evaluation completed! Report: {run.report_url}")




asyncio.run(main())
