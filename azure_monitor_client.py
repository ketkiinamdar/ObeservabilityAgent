import os
from datetime import timedelta

from dotenv import load_dotenv
from azure.identity import DefaultAzureCredential
from azure.monitor.query import LogsQueryClient, LogsQueryStatus
from azure.core.exceptions import HttpResponseError

load_dotenv()

WORKSPACE_ID = os.getenv("LOG_WORKSPACE_ID")

if not WORKSPACE_ID:
    raise RuntimeError(
        "LOG_WORKSPACE_ID is missing from the .env file"
    )

# Uses Azure CLI credentials locally and can use a managed identity
# when the application runs in Azure.
credential = DefaultAzureCredential()
client = LogsQueryClient(credential)


def _query_to_dict(query: str, lookback_hours: int) -> dict:
    """Execute a read-only KQL query and return JSON-compatible data."""

    try:
        response = client.query_workspace(
            workspace_id=WORKSPACE_ID,
            query=query,
            timespan=timedelta(hours=lookback_hours),
        )

        if response.status == LogsQueryStatus.SUCCESS:
            tables = response.tables
        elif response.status == LogsQueryStatus.PARTIAL:
            tables = response.partial_data
        else:
            return {
                "status": "error",
                "error": getattr(response, "message", "Query failed"),
                "rows": [],
            }

        rows = []

        for table in tables:
            # SDK column metadata contains column names.
            column_names = [
                column if isinstance(column, str) else column.name
                for column in table.columns
            ]

            for values in table.rows:
                rows.append(dict(zip(column_names, values)))

        return {
            "status": (
                "success"
                if response.status == LogsQueryStatus.SUCCESS
                else "partial"
            ),
            "row_count": len(rows),
            "rows": rows,
        }

    except HttpResponseError as exc:
        return {
            "status": "error",
            "error": str(exc),
            "rows": [],
        }


def get_application_exceptions(lookback_hours: int = 1) -> dict:
    """Retrieve recent application exceptions."""

    if not 1 <= lookback_hours <= 168:
        raise ValueError("lookback_hours must be between 1 and 168")

    query = """
    AppExceptions
    | where TimeGenerated > ago(1h)
    | project
        TimeGenerated,
        AppRoleName,
        ProblemId,
        ExceptionType = Type,
        Message = OuterMessage,
        OperationId
    | order by TimeGenerated desc
    | take 100
    """.replace("ago(1h)", f"ago({lookback_hours}h)")

    return _query_to_dict(query, lookback_hours)


def get_failed_application_requests(
    lookback_hours: int = 1
) -> dict:
    """Retrieve failed requests and their response times."""

    if not 1 <= lookback_hours <= 168:
        raise ValueError("lookback_hours must be between 1 and 168")

    query = f"""
    AppRequests
    | where TimeGenerated > ago({lookback_hours}h)
    | where Success == false
    | project
        TimeGenerated,
        AppRoleName,
        Name,
        Url,
        ResultCode,
        DurationMs,
        OperationId
    | order by TimeGenerated desc
    | take 100
    """

    return _query_to_dict(query, lookback_hours)


def get_failed_dependencies(
    lookback_hours: int = 1
) -> dict:
    """Retrieve failed database and external dependency calls."""

    if not 1 <= lookback_hours <= 168:
        raise ValueError("lookback_hours must be between 1 and 168")

    query = f"""
    AppDependencies
    | where TimeGenerated > ago({lookback_hours}h)
    | where Success == false
    | project
        TimeGenerated,
        AppRoleName,
        Name,
        Target,
        DependencyType = Type,
        ResultCode,
        DurationMs,
        OperationId
    | order by TimeGenerated desc
    | take 100
    """

    return _query_to_dict(query, lookback_hours)


def get_azure_activity(lookback_hours: int = 24) -> dict:
    """Retrieve recent Azure management operations."""

    if not 1 <= lookback_hours <= 168:
        raise ValueError("lookback_hours must be between 1 and 168")

    query = f"""
    AzureActivity
    | where TimeGenerated > ago({lookback_hours}h)
    | project
        TimeGenerated,
        OperationNameValue,
        ActivityStatusValue,
        ResourceGroup,
        ResourceId,
        Caller
    | order by TimeGenerated desc
    | take 100
    """

    return _query_to_dict(query, lookback_hours)


def get_real_azure_monitor_data(
    lookback_hours: int = 1
) -> dict:
    """Collect real telemetry for incident analysis."""

    if not 1 <= lookback_hours <= 168:
        raise ValueError("lookback_hours must be between 1 and 168")

    return {
        "source": "AZURE_LOG_ANALYTICS",
        "data_type": "REAL",
        "workspace_id": WORKSPACE_ID,
        "lookback_hours": lookback_hours,
        "application_exceptions": get_application_exceptions(lookback_hours),
        "failed_requests": get_failed_application_requests(lookback_hours),
        "failed_dependencies": get_failed_dependencies(lookback_hours),
        "azure_activity": get_azure_activity(max(lookback_hours, 24)),
    }

def get_rca_test_logs(lookback_hours: int = 24):
    query = f"""
    RCA_Test_CL_CL
    | where TimeGenerated > ago({lookback_hours}h)
    | where Scenario == "RCA_TEST"
    | project TimeGenerated, ServiceName, Environment,
              Severity, Message, CorrelationId, Scenario
    | order by TimeGenerated desc
    | take 100
    """

    return _query_to_dict(query, lookback_hours)