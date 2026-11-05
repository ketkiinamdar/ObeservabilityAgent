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
from clients.servicenow_client import search_incidents
from clients.sonarcloud_client import quality_gate, measures, issues
from agents.technology_intelligence import collect as collect_technology_releases
from azure_monitor_client import (
    get_application_exceptions,
    get_failed_application_requests,
    get_failed_dependencies,
    get_azure_activity,
    get_rca_test_logs,
    get_real_application_insights_data,
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
    if not 1 <= hours <= 96:
        raise ValueError("lookback_hours must be between 1 and 96")
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
    lookback_hours: int = 96,
) -> str:
    """Retrieve recent Azure management operations.
    Use this to investigate infrastructure and configuration changes."""

    data = get_azure_activity(lookback_hours)
    return json.dumps(data, default=str)

@tool
def read_rca_test_logs(lookback_hours: int = 96) -> str:
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
def analyze_application_insights(
    lookback_hours: int = 96,
    app_role_name: str = ""
) -> str:
    """
    Retrieves real Application Insights telemetry:
    requests, exceptions, dependencies and traces.

    Use this tool to investigate application failures,
    latency, SQL errors and related telemetry.
    Correlate records using OperationId.
    """

    result = get_real_application_insights_data(
        lookback_hours=lookback_hours,
        app_role_name=app_role_name or None
    )

    return str(result)

# ---------------------------------------------------------
# Tool 3: Azure DevOps deployment/build history
# ---------------------------------------------------------
@tool
def get_azure_devops_deployments(lookback_hours: int = 96) -> str:
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
# Tool 4: Historical ServiceNow incidents (read-only)
# ---------------------------------------------------------
@tool
def get_historical_servicenow_incidents(search_text: str = "", lookback_days: int = 90) -> str:
    """Search historical ServiceNow incidents for similar symptoms and prior resolutions.
    Read-only. Treat matches as historical precedent, not proof of current root cause.
    Avoid customer names, policy numbers or other personal data in search_text."""
    try:
        data = search_incidents(text=search_text, days=lookback_days, limit=100)
        # Minimize exposure of potentially sensitive free-text fields before sending to the LLM.
        safe_rows = []
        for row in data:
            safe_rows.append({k: row.get(k) for k in (
                "number", "short_description", "priority", "state", "assignment_group",
                "opened_at", "closed_at", "close_code", "cmdb_ci"
            ) if k in row})
        return json.dumps({"source": "SERVICENOW_HISTORICAL_INCIDENTS", "count": len(safe_rows), "incidents": safe_rows}, default=str)
    except Exception as exc:
        return json.dumps({"source": "SERVICENOW_HISTORICAL_INCIDENTS", "data_available": False, "error": str(exc)})

# ---------------------------------------------------------
# Tool 5: SonarCloud quality and security posture (read-only)
# ---------------------------------------------------------
@tool
def analyze_sonarcloud_project(project_key: str) -> str:
    """Retrieve SonarCloud quality gate, code metrics and recent issues for a project.
    Use this as supporting engineering-quality evidence; do not infer runtime causation from static analysis alone."""
    try:
        return json.dumps({
            "source": "SONARCLOUD",
            "project_key": project_key,
            "quality_gate": quality_gate(project_key),
            "measures": measures(project_key),
            "issues": issues(project_key),
        }, default=str)
    except Exception as exc:
        return json.dumps({"source": "SONARCLOUD", "project_key": project_key, "data_available": False, "error": str(exc)})

# ---------------------------------------------------------
# Tool 6: Technology release intelligence (RSS/Atom)
# ---------------------------------------------------------
@tool
def get_recent_technology_releases(lookback_days: int = 7) -> str:
    """Collect recent entries from configured technology release RSS/Atom feeds.
    Use for awareness of Terraform, Azure providers, .NET, Python and pipeline task updates.
    A release entry is not proof that the affected technology is used by this service."""
    try:
        result = collect_technology_releases(days=max(1, min(int(lookback_days), 90)))
        return json.dumps({"source": "CONFIGURED_RELEASE_FEEDS", **result}, default=str)
    except Exception as exc:
        return json.dumps({"source": "CONFIGURED_RELEASE_FEEDS", "data_available": False, "error": str(exc)})

# ---------------------------------------------------------
# Agent instructions and creation
# ---------------------------------------------------------

SYSTEM_PROMPT = """
You are an evidence-led observability and engineering intelligence agent for an insurance technology environment.

Available evidence tools:
- Log Analytics: application exceptions, failed requests, failed dependencies, Azure activity and synthetic RCA test logs.
- Application Insights: requests, exceptions, dependencies and traces; correlate by OperationId.
- Azure DevOps: recent pipeline/build history (not guaranteed environment deployment records).
- ServiceNow: historical incident metadata for similar symptoms and prior incident patterns.
- SonarCloud: project quality gate, code metrics and issue summaries.
- Technology release feeds: recent RSS/Atom release announcements for configured technologies.

DATA SOURCE CLASSIFICATION
- Azure Monitor and Application Insights tools are configured to retrieve real telemetry, subject to their implementation and credentials.
- RCA_Test_CL_CL contains synthetic test data. Label it explicitly as synthetic and never describe it as a production incident.
- Azure DevOps build records are build evidence only. Do not call a build a production deployment unless an environment deployment record explicitly confirms it.
- ServiceNow results are historical precedents, not proof of current causation.
- SonarCloud and release-feed findings are supporting engineering context, not proof of runtime failure.
- If a tool reports an error, empty result, or unavailable source, state that limitation. Never silently replace missing data with dummy data.

INVESTIGATION PROCEDURE
1. For an incident investigation, query relevant Log Analytics and Application Insights tools, Azure activity, and Azure DevOps build history. Query the RCA test table only when synthetic test evidence is relevant or requested.
2. Query ServiceNow history when symptoms can be compared with prior incidents. Do not include raw customer identifiers or unnecessary free-text incident details in the report.
3. Query SonarCloud only when a project key is provided or configured by the user. Treat findings as context, not runtime causation.
4. Query release feeds when a technology change could be relevant. Do not claim a release affects the service without confirming its installed version and applicability.
5. Establish a timeline using actual timestamps and timezone. Distinguish earliest observed symptom, incident start estimate and detection time.
6. Correlate by OperationId, CorrelationId, service, environment, timestamps, commit and version where available.
7. A nearby build or release is a hypothesis, not proof. Validate against telemetry and confirmed deployment evidence.
8. Clearly separate observed facts, correlations, inferences, hypotheses and unknowns.
9. Never invent customer impact, customer counts, transaction losses, detection timestamps, deployment events, configuration changes or infrastructure changes.
10. If information is unavailable, write: "Unknown — evidence not available."
11. Do not execute remediation, rollback, configuration changes or ServiceNow write operations. Recommendations requiring changes must be presented for human approval.
12. Base confidence on evidence quality, consistency, source coverage and alternative explanations. Do not invent a numerical probability.

MANDATORY RCA REPORT
For every incident investigation, produce readable Markdown with exactly these 13 numbered sections, in this order:
1. Description of incident
2. Affected Service (application, environment and dependencies)
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

Do not omit a section when evidence is missing. State "Unknown — evidence not available." Include explicit timezone-aware timestamps when available. Label synthetic evidence. Treat rollback as a proposal requiring human approval, not an action to execute.

For general engineering-intelligence requests (not incident RCA), return a concise report grouped by source, include collection timestamps and errors, and distinguish release announcements from confirmed estate impact.
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
    analyze_application_insights,
    get_historical_servicenow_incidents,
    analyze_sonarcloud_project,
    get_recent_technology_releases,
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

    Collect evidence from the relevant configured monitoring, deployment/build, historical incident, code-quality and release-intelligence sources. Clearly report unavailable sources, correlate the findings, and generate the requested 13-section RCA report.
    """

    result = agent.invoke(
    {
        "messages": [
            {"role": "user", "content": request}
        ]
    },
    config={
        "run_name": f"RCA Investigation - {service_name}",
        "tags": [
            "Insurance-RCA",
            "Azure-Monitor",
            "Application-Insights",
            "Azure-DevOps"
        ],
        "metadata": {
            "service_name": service_name,
            "environment": environment,
            "lookback_hours": lookback_hours,
            "investigation_type": "incident-analysis"
        }
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
