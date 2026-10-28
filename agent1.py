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
from dummy_data import get_dummy_azure_monitor_signals
from dummy_application_insights import (
    get_dummy_application_insights_signals,
)

from dummy_azure_devops import (
    get_dummy_azure_devops_deployments,
)

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
def get_azure_monitor_signals(
    service_name: str = "insurance-policy-api",
    lookback_hours: int = 1,
) -> str:
    """
    Retrieve Azure Monitor-style application health signals.

    Currently returns simulated test data. Use it to investigate
    application failures, latency degradation, and deployment correlation.

    Args:
        service_name: Name of the application to investigate.
        lookback_hours: Lookback period between 1 and 24 hours.
    """

    result = get_dummy_azure_monitor_signals(
        service_name=service_name,
        lookback_hours=lookback_hours,
    )

    return json.dumps(result)

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

1. Call get_azure_monitor_signals.
2. Call get_application_insights_signals.
3. Call get_azure_devops_deployments.
4. Correlate timestamps, services, deployment versions, errors, exceptions, and dependency behavior.
5. Use only information returned by the tools or explicitly supplied by the user.
6. Distinguish observed facts, inferences, and unverified hypotheses.
7. Do not invent detection timestamps, customer counts, transaction losses, configuration changes, or infrastructure changes.
8. If information is unavailable, write "Unknown — evidence not available."
9. Use explicit timestamps with timezone when available.
10. Base confidence on evidence quality, consistency, coverage, and alternative explanations. Do not invent a numerical probability.
11. Provide actionable recommendations and measurable validation criteria.
12. Treat rollback as a proposal requiring human approval, not an action to execute.

SIMULATED DATA SAFETY:

The current data sources return simulated test data. Clearly label the report as a simulation. Never describe simulated observations as actual production events.

OUTPUT:

Produce a readable Markdown incident report with all 13 sections. Do not omit a section because information is missing. State missing evidence explicitly.
"""

llm = ChatOllama(
    model=OLLAMA_MODEL,
    base_url=OLLAMA_BASE_URL,
    temperature=0,
)

tools = [
    get_azure_monitor_signals,
    get_application_insights_signals,
    get_azure_devops_deployments,
    get_terraform_changes,
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