from datetime import datetime, timedelta, timezone


def get_dummy_application_insights_signals(
    service_name: str = "insurance-policy-api",
    lookback_hours: int = 1,
) -> dict:
    """Return simulated Application Insights telemetry."""

    if not 1 <= lookback_hours <= 24:
        return {
            "status": "error",
            "message": "lookback_hours must be between 1 and 24",
        }

    now = datetime.now(timezone.utc)
    incident_time = now - timedelta(minutes=20)

    return {
        "status": "success",
        "source": "SIMULATED_APPLICATION_INSIGHTS",
        "environment": "TEST",
        "service_name": service_name,
        "lookback_hours": lookback_hours,
        "request_telemetry": {
            "total_requests": 3000,
            "failed_requests": 450,
            "failure_rate_percent": 15.0,
            "average_duration_ms": 2400,
            "p95_duration_ms": 5200,
        },
        "exceptions": [
            {
                "timestamp": (
                    incident_time + timedelta(minutes=2)
                ).isoformat(),
                "type": "SqlException",
                "message": (
                    "Execution timeout expired while retrieving policy data"
                ),
                "count": 85,
                "operation": "GET /api/policies",
                "correlation_id": "test-operation-1001",
            },
            {
                "timestamp": (
                    incident_time + timedelta(minutes=4)
                ).isoformat(),
                "type": "InvalidOperationException",
                "message": "Policy processing failed",
                "count": 35,
                "operation": "POST /api/claims",
                "correlation_id": "test-operation-1002",
            },
        ],
        "dependencies": [
            {
                "dependency_type": "SQL",
                "target": "insurance-policy-db",
                "calls": 500,
                "failed_calls": 100,
                "average_duration_ms": 1800,
                "failure_rate_percent": 20.0,
            },
            {
                "dependency_type": "HTTP",
                "target": "customer-profile-service",
                "calls": 200,
                "failed_calls": 10,
                "average_duration_ms": 350,
                "failure_rate_percent": 5.0,
            },
        ],
        "observations": [
            "SQL dependency latency is elevated.",
            "Policy retrieval exceptions increased during the incident.",
            "Request failures and dependency timeouts overlap in time.",
        ],
        "data_notice": (
            "All telemetry is simulated. No production Application "
            "Insights resource was queried."
        ),
    }
