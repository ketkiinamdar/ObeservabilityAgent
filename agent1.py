import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

from azure.identity import DefaultAzureCredential
from azure.monitor.query import LogsQueryClient

from langchain.agents import create_agent
from langchain.tools import tool
from langchain_ollama import ChatOllama
from azure_devops_client import get_recent_builds
from azure_monitor_client import (
    get_application_exceptions,
    get_failed_application_requests,
    get_failed_dependencies,
    get_azure_activity,
)
from azure_monitor_client import get_rca_test_logs

load_dotenv()

# ---------------------------------------------------------
# Configuration
# ---------------------------------------------------------

OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3:8b")
OLLAMA_BASE_URL = os.getenv(
    "OLLAMA_BASE_URL", "http://localhost:11434"
)

WORKSPACE_ID = os.getenv("LOG_ANALYTICS_WORKSPACE_ID")
APPINSIGHTS_WORKSPACE_ID = os.getenv(
    "APPINSIGHTS_WORKSPACE_ID", WORKSPACE_ID
)

AZDO_ORG = os.getenv("AZDO_ORG")
AZDO_PROJECT = os.getenv("AZDO_PROJECT")
AZDO_TOKEN = os.getenv("AZDO_TOKEN")

TERRAFORM_FILE = Path(
    os.getenv(
        "TERRAFORM_CHANGES_FILE",
        "./data/terraform_changes.json"
    )
)

credential = DefaultAzureCredential()
logs_client = LogsQueryClient(credential)


def validate_lookback(hours: int) -> int:
    """Restrict investigations to a reasonable time window."""
    if not 1 <= hours <= 24:
        raise ValueError("lookback_hours must be between 1 and 24")
    return hours


def safe_service_name(name: str) -> str:
    """Basic escaping for service names inserted into KQL literals."""
    return name.replace("\\", "\\\\").replace("'", "\\'")


def query_workspace(workspace_id: str, query: str, hours: int):
    """Run a read-only Log Analytics query and return JSON records."""
    validate_lookback(hours)

    if not workspace_id:
        return {"error": "Workspace ID is not configured"}

    response = logs_client.query_workspace(
        workspace_id=workspace_id,
        query=query,
        timespan=timedelta(hours=hours),
    )

    # Fail closed rather than silently using incomplete evidence.
    if not hasattr(response, "tables") or not response.tables:
        return {"error": "Query returned no usable table"}

    table = response.tables[0]
    columns = [column.name for column in table.columns]

    return [
        dict(zip(columns, row))
        for row in table.rows[:100]
    ]


# ---------------------------------------------------------
# Tool 1: Azure Monitor / Log Analytics
# ---------------------------------------------------------
@tool
def get_log_analytics_exceptions(lookback_hours: int = 1) -> str:
    """Retrieve real application exceptions from Log Analytics.
    Use this to investigate exceptions and probable application failures."""

    data = get_application_exceptions(lookback_hours)
    return json.dumps(data, default=str)


@tool
def get_log_analytics_failed_requests(lookback_hours: int = 1) -> str:
    """Retrieve real failed application requests from Log Analytics.
    Use this to investigate HTTP failures and application availability."""

    data = get_failed_application_requests(lookback_hours)
    return json.dumps(data, default=str)


@tool
def get_log_analytics_failed_dependencies(
    lookback_hours: int = 1,
) -> str:
    """Retrieve real failed dependencies from Log Analytics.
    Use this to investigate SQL, database and external service failures."""

    data = get_failed_dependencies(lookback_hours)
    return json.dumps(data, default=str)


@tool
def get_log_analytics_azure_activity(
    lookback_hours: int = 24,
) -> str:
    """Retrieve recent Azure management operations.
    Use this to investigate infrastructure and configuration changes."""

    data = get_azure_activity(lookback_hours)
    return json.dumps(data, default=str)

@tool
def read_rca_test_logs(lookback_hours: int = 24) -> str:
    """
    Reads synthetic RCA test events from the RCA_Test_CL_CL
    Log Analytics table. Use this tool to investigate test incidents,
    correlate events using CorrelationId, and identify possible causes.
    """
    result = get_rca_test_logs(lookback_hours)
    return str(result)

# ---------------------------------------------------------
# Tool 2: Application Insights
# ---------------------------------------------------------

@tool
def get_application_insights_signals(
    service_name: str = "insurance-policy-api",
    lookback_hours: int = 1,
) -> str:
    """
    Retrieve simulated Application Insights requests, exceptions,
    and dependency performance signals.

    Args:
        service_name: Application or service to investigate.
        lookback_hours: Lookback period between 1 and 24 hours.
    """

    result = get_dummy_application_insights_signals(
        service_name=service_name,
        lookback_hours=lookback_hours,
    )

    return json.dumps(result)




# ---------------------------------------------------------
# Tool 3: Azure DevOps deployment/build history
# ---------------------------------------------------------
@tool
def get_azure_devops_deployments(lookback_hours: int = 24) -> str:
    """
    Retrieve real Azure DevOps build and pipeline history.
    Use this to investigate recent deployments, failed builds,
    build timestamps, branches and source versions.
    """

    try:
        data = get_recent_builds(lookback_hours)
        return json.dumps(data, indent=2)

    except Exception as exc:
        # Report the failure explicitly; do not return fake data.
        return json.dumps({
            "source": "AZURE_DEVOPS_REST_API",
            "error": str(exc),
            "data_available": False,
        })

# ---------------------------------------------------------
# Tool 4: Read-only Terraform change history
# ---------------------------------------------------------

@tool
def get_terraform_changes(
    service_name: str,
    lookback_hours: int = 2
) -> dict:
    """
    Read sanitized Terraform change summaries.

    Does not execute Terraform and does not read state files.
    """
    hours = validate_lookback(lookback_hours)

    if not TERRAFORM_FILE.exists():
        return {
            "source": "Terraform change summary",
            "error": "Change summary file not found"
        }

    try:
        payload = json.loads(
            TERRAFORM_FILE.read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError):
        return {
            "source": "Terraform change summary",
            "error": "Change summary could not be read"
        }

    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    service_lower = service_name.lower()
    results = []

    for change in payload.get("changes", []):
        # Fail closed if a timestamp is missing or invalid.
        try:
            timestamp = datetime.fromisoformat(
                change["timestamp"].replace("Z", "+00:00")
            )
        except (KeyError, TypeError, ValueError):
            continue

        if timestamp < cutoff:
            continue

        resource = str(change.get("resource_name", ""))
        service = str(change.get("service", ""))

        if (
            service_lower not in service.lower()
            and service_lower not in resource.lower()
        ):
            continue

        # Only return approved fields. Never pass raw plan data.
        results.append({
            "timestamp": change.get("timestamp"),
            "environment": change.get("environment"),
            "service": change.get("service"),
            "pipeline": change.get("pipeline"),
            "run_id": change.get("run_id"),
            "resource_type": change.get("resource_type"),
            "resource_name": change.get("resource_name"),
            "actions": change.get("actions"),
            "summary": change.get("summary"),
        })

    return {
        "source": "Terraform change summary",
        "service": service_name,
        "lookback_hours": hours,
        "changes": results,
    }


# ---------------------------------------------------------
# Agent instructions and creation
# ---------------------------------------------------------

SYSTEM_PROMPT = """
### Observability investigation instructions

You have three monitoring tools:

1. get_azure_monitor_signals
   - Retrieves simulated request health, error rates and latency trends.

2. get_application_insights_signals
   - Retrieves simulated application exceptions, request performance and dependency failures.

3. get_azure_devops_deployments
   - Retrieves simulated build and deployment history.

For an application degradation investigation:

1. Retrieve monitoring signals from all three tools.
2. Identify when the degradation began.
3. Compare the monitoring timeline with deployment timestamps.
4. Examine Application Insights exceptions and dependency failures.
5. Determine whether the deployment, database dependency, or another factor could explain the symptoms.
6. Separate observed facts, correlations, hypotheses and confirmed causes.
7. Recommend additional checks before suggesting rollback or remediation.

All data currently comes from simulated test fixtures.

Never describe simulated observations as real production incidents. Do not create real ServiceNow incidents or perform remediation actions during testing.

### Mandatory incident report requirements

For every incident investigation, produce a report with exactly these 13 numbered sections in this order:

1. Description of incident
2. Affected Service
3. Customer Impact
4. Start Time
5. Detection Time
6. Symptoms
7. Recent changes
8. Probable root-cause
9. Alternative Hypotheses
10. Confidence
11. Recommended Actions
12. Validation Criteria
13. Rollback Option

Investigation procedure:

1. Use Azure DevOps tools to identify recent builds, releases,
   commits and deployment changes.

2. Use Log Analytics tools to retrieve application exceptions,
   failed requests, failed dependencies and Azure management
   operations.

3. Correlate events using timestamps, service names, operation IDs,
   deployment versions and other available evidence.

4. Establish the incident timeline using actual event timestamps.
   Distinguish the earliest observed symptom from the actual incident
   start time and detection time.

5. A recent deployment is a possible cause, not proof of causation.
   Validate it against telemetry and other available evidence.

6. Clearly distinguish observed facts, inferences and alternative
   hypotheses.
7. Use only information returned by the tools or explicitly supplied by the user.
8. Distinguish observed facts, inferences, and unverified hypotheses.
9. Do not invent detection timestamps, customer counts, transaction losses, configuration changes, or infrastructure changes.
10. If information is unavailable, write "Unknown — evidence not available."
11. Use explicit timestamps with timezone when available.
12. Base confidence on evidence quality, consistency, coverage, and alternative explanations. Do not invent a numerical probability.
13. Provide actionable recommendations and measurable validation criteria.
14. Treat rollback as a proposal requiring human approval, not an action to execute.

When investigating an incident:
1. Query the RCA test table when synthetic test data is relevant.
2. Use CorrelationId to correlate related events.
3. Compare event timestamps to identify the sequence of events.
4. Consider deployment, application errors and dependency failures together.
5. Clearly identify synthetic test data as test evidence.
6. Never treat synthetic test events as actual production incidents.

OUTPUT:

Produce a readable Markdown incident report with all 13 sections. Do not omit a section because information is missing. State missing evidence explicitly.
"""

llm = ChatOllama(
    model=OLLAMA_MODEL,
    base_url=OLLAMA_BASE_URL,
    temperature=0,
)

tools = [
    get_log_analytics_exceptions,
    get_log_analytics_failed_requests,
    get_log_analytics_failed_dependencies,
    get_log_analytics_azure_activity,
    get_azure_devops_deployments,
    read_rca_test_logs,
]

agent = create_agent(
    model=llm,
    tools=tools,
    system_prompt=SYSTEM_PROMPT,
)


def run_investigation(
    service_name: str,
    environment: str,
    lookback_hours: int
):
    validate_lookback(lookback_hours)

    request = f"""
    Investigate possible degradation affecting service:
    {service_name}

    Environment: {environment}
    Lookback window: {lookback_hours} hours

    Collect evidence from all four configured sources, correlate
    the findings, and generate the requested RCA report.
    """

    result = agent.invoke({
        "messages": [
            {"role": "user", "content": request}
        ]
    })

    # The last message is normally the agent's final response.
    final_message = result["messages"][-1]
    report = final_message.content

    output_dir = Path("reports")
    output_dir.mkdir(exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime(
        "%Y%m%dT%H%M%SZ"
    )

    output_file = output_dir / f"rca_{timestamp}.md"
    output_file.write_text(report, encoding="utf-8")

    print(report)
    print(f"\nReport saved to: {output_file.resolve()}")


if __name__ == "__main__":
    run_investigation(
        service_name=os.getenv("SERVICE_NAME", "policy-api"),
        environment=os.getenv("ENVIRONMENT", "production"),
        lookback_hours=int(os.getenv("LOOKBACK_HOURS", "2")),
    )