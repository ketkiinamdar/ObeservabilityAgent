from datetime import datetime, timedelta, timezone


def get_dummy_azure_devops_deployments(
    service_name: str = "insurance-policy-api",
    lookback_hours: int = 24,
) -> dict:
    """Return simulated Azure DevOps pipeline and deployment history."""

    if not 1 <= lookback_hours <= 168:
        return {
            "status": "error",
            "message": "lookback_hours must be between 1 and 168",
        }

    now = datetime.now(timezone.utc)

    return {
        "status": "success",
        "source": "SIMULATED_AZURE_DEVOPS",
        "environment": "TEST",
        "service_name": service_name,
        "lookback_hours": lookback_hours,
        "deployments": [
            {
                "deployment_id": "TEST-DEP-2048",
                "pipeline": "insurance-policy-api-cicd",
                "build_id": "TEST-BUILD-9821",
                "version": "v2.8.0",
                "commit": "test-commit-a91f",
                "status": "Succeeded",
                "environment_name": "Production-Simulation",
                "deployed_at": (
                    now - timedelta(minutes=25)
                ).isoformat(),
                "change_summary": (
                    "Updated policy processing and database access logic"
                ),
            },
            {
                "deployment_id": "TEST-DEP-2047",
                "pipeline": "insurance-policy-api-cicd",
                "build_id": "TEST-BUILD-9814",
                "version": "v2.7.4",
                "commit": "test-commit-7bc2",
                "status": "Succeeded",
                "environment_name": "Production-Simulation",
                "deployed_at": (
                    now - timedelta(hours=6)
                ).isoformat(),
                "change_summary": "Previous stable release",
            },
        ],
        "pipeline_runs": [
            {
                "build_id": "TEST-BUILD-9821",
                "result": "Succeeded",
                "tests_passed": 245,
                "tests_failed": 0,
                "duration_minutes": 12,
            }
        ],
        "observations": [
            "Version v2.8.0 was deployed shortly before the simulated incident.",
            "The simulated pipeline reported successful completion.",
            "The available deployment record does not prove causation.",
        ],
        "data_notice": (
            "All deployment information is simulated. No Azure DevOps "
            "organization or project was queried."
        ),
    }
