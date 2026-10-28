from datetime import datetime, timedelta, timezone


def get_dummy_azure_monitor_signals(
    service_name: str = "insurance-policy-api",
    lookback_hours: int = 1,
) -> dict:
    """
    Generate simulated Azure Monitor signals for testing.

    No connection to Azure is required.
    """

    if not 1 <= lookback_hours <= 24:
        return {
            "status": "error",
            "message": "lookback_hours must be between 1 and 24",
        }

    now = datetime.now(timezone.utc)
    timeline = []

    for minutes_ago in range(lookback_hours * 60 - 5, -1, -5):
        incident_started = minutes_ago <= 20

        if incident_started:
            requests = 500
            failures = 75
            avg_duration_ms = 2400
            p95_duration_ms = 5200
        else:
            requests = 500
            failures = 5
            avg_duration_ms = 250
            p95_duration_ms = 600

        timeline.append({
            "timestamp": (
                now - timedelta(minutes=minutes_ago)
            ).isoformat(),
            "service": service_name,
            "request_count": requests,
            "failed_requests": failures,
            "failure_rate_percent": round(
                failures / requests * 100, 2
            ),
            "avg_duration_ms": avg_duration_ms,
            "p95_duration_ms": p95_duration_ms,
        })

    total_requests = sum(
        row["request_count"] for row in timeline
    )

    total_failures = sum(
        row["failed_requests"] for row in timeline
    )

    return {
        "status": "success",
        "source": "SIMULATED_DATA",
        "environment": "TEST",
        "service_name": service_name,
        "lookback_hours": lookback_hours,
        "summary": {
            "total_requests": total_requests,
            "failed_requests": total_failures,
            "failure_rate_percent": round(
                total_failures / total_requests * 100, 2
            ),
        },
        "request_health_timeline": timeline,
        "frequent_failure_patterns": [
            {
                "endpoint": "GET /api/policies",
                "result_code": 500,
                "failure_count": 45,
            },
            {
                "endpoint": "POST /api/claims",
                "result_code": 503,
                "failure_count": 30,
            },
        ],
        "recent_deployments": [
            {
                "service": service_name,
                "version": "v2.8.0",
                "minutes_before_now": 25,
                "status": "Succeeded",
                "change": "Updated policy processing logic",
            }
        ],
        "notice": (
            "This is simulated test data, not actual Azure telemetry."
        ),
    }