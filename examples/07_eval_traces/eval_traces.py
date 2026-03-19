"""
Example 07 — Evaluate from Application Insights Traces (Sync)

Queries trace IDs from Application Insights and evaluates agent behavior
using trace-based data sources.

Usage:
    python examples/07_eval_traces/eval_traces.py

Environment variables:
    AZURE_AI_PROJECT_ENDPOINT          — Your Foundry project endpoint
    AZURE_AI_MODEL_DEPLOYMENT_NAME     — Model deployment name
    APPINSIGHTS_RESOURCE_ID            — Application Insights resource ID
    AGENT_ID                           — Agent ID for filtering traces
    TRACE_LOOKBACK_HOURS               — Hours to look back (default: 1)
"""

import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List
from pprint import pprint

from dotenv import load_dotenv

load_dotenv()

from azure.identity import DefaultAzureCredential
from azure.monitor.query import LogsQueryClient, LogsQueryStatus
from azure.ai.projects import AIProjectClient

endpoint = os.environ["AZURE_AI_PROJECT_ENDPOINT"]
appinsights_resource_id = os.environ["APPINSIGHTS_RESOURCE_ID"]
agent_id = os.environ["AGENT_ID"]
model = os.environ.get("AZURE_AI_MODEL_DEPLOYMENT_NAME", "gpt-4o-mini")
lookback_hours = int(os.environ.get("TRACE_LOOKBACK_HOURS", "1"))


def build_evaluator_config(name: str, evaluator_name: str) -> Dict[str, Any]:
    """Create a standard evaluator config for trace evaluations."""
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
    """Query Application Insights for trace IDs (operation_Id) filtered by agent ID and time range."""
    query = f"""
    dependencies
    | where timestamp between (datetime({start.isoformat()}) .. datetime({end.isoformat()}))
    | extend agent_id = tostring(customDimensions["gen_ai.agent.id"])
    | where agent_id == "{tracked_agent_id}"
    | distinct operation_Id
    """
    with DefaultAzureCredential() as cred:
        client = LogsQueryClient(cred)
        response = client.query_resource(resource_id, query=query, timespan=None)

    if response.status == LogsQueryStatus.SUCCESS:
        return [row[0] for table in response.tables for row in table.rows]

    print(f"Query failed: {response.status}")
    return []


def main():
    end_time = datetime.now(tz=timezone.utc)
    start_time = end_time - timedelta(hours=lookback_hours)

    print(f"Querying App Insights for traces...")
    print(f"Agent ID: {agent_id}")
    print(f"Time range: {start_time.isoformat()} to {end_time.isoformat()}")

    trace_ids = get_trace_ids(appinsights_resource_id, agent_id, start_time, end_time)

    if not trace_ids:
        print("No trace IDs found. Make sure your agent has run recently with tracing enabled.")
        return

    print(f"\nFound {len(trace_ids)} trace IDs:")
    for tid in trace_ids:
        print(f"  - {tid}")

    with (
        DefaultAzureCredential() as credential,
        AIProjectClient(endpoint=endpoint, credential=credential) as project_client,
        project_client.get_openai_client() as client,
    ):
        # Define trace-specific evaluators
        testing_criteria = [
            build_evaluator_config("intent_resolution", "builtin.intent_resolution"),
            build_evaluator_config("task_adherence", "builtin.task_adherence"),
        ]

        print("\nCreating evaluation...")
        eval_object = client.evals.create(
            name="Trace-Based Evaluation",
            data_source_config={"type": "azure_ai_source", "scenario": "traces"},  # type: ignore
            testing_criteria=testing_criteria,  # type: ignore
        )
        print(f"Evaluation created (id: {eval_object.id})")

        # Create eval run with trace IDs
        data_source = {
            "type": "azure_ai_traces",
            "trace_ids": trace_ids,
            "lookback_hours": lookback_hours,
        }

        print("Creating eval run with trace IDs...")
        eval_run = client.evals.runs.create(
            eval_id=eval_object.id,
            name=f"trace_eval_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            metadata={"agent_id": agent_id},
            data_source=data_source,  # type: ignore
        )
        print(f"Eval run created (id: {eval_run.id})")

        while True:
            run = client.evals.runs.retrieve(run_id=eval_run.id, eval_id=eval_object.id)
            if run.status in ("completed", "failed", "canceled"):
                break
            print(f"Status: {run.status}")
            time.sleep(5)

        if run.status == "completed":
            print(f"\nEvaluation completed!")
            output_items = list(
                client.evals.runs.output_items.list(run_id=run.id, eval_id=eval_object.id)
            )
            pprint(output_items)
            print(f"\nReport URL: {run.report_url}")

        client.evals.delete(eval_id=eval_object.id)
        print("Evaluation deleted")


if __name__ == "__main__":
    main()
