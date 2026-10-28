import os
import base64
import requests

from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv

load_dotenv()

AZDO_ORG = os.getenv("AZDO_ORG")
AZDO_PROJECT = os.getenv("AZDO_PROJECT")
AZDO_PAT = os.getenv("AZDO_PAT")

if not all([AZDO_ORG, AZDO_PROJECT, AZDO_PAT]):
    raise RuntimeError(
        "Set AZDO_ORG, AZDO_PROJECT and AZDO_PAT in your .env file"
    )

# Azure DevOps PAT authentication uses Basic authentication.
# The username is blank and the PAT is the password.
encoded = base64.b64encode(
    f":{AZDO_PAT}".encode("utf-8")
).decode("ascii")

HEADERS = {
    "Authorization": f"Basic {encoded}",
    "Accept": "application/json",
}

BASE_URL = (
    f"https://dev.azure.com/{AZDO_ORG}/"
    f"{requests.utils.quote(AZDO_PROJECT, safe='')}/_apis"
)


def get_recent_builds(lookback_hours: int = 24) -> dict:
    """Retrieve recent Azure DevOps pipeline/build runs."""

    if not 1 <= lookback_hours <= 720:
        raise ValueError("lookback_hours must be between 1 and 720")

    since = datetime.now(timezone.utc) - timedelta(
        hours=lookback_hours
    )

    url = f"{BASE_URL}/build/builds"

    params = {
        "minTime": since.isoformat(),
        "$top": 50,
        "queryOrder": "finishTimeDescending",
        "api-version": "7.1",
    }

    response = requests.get(
        url,
        headers=HEADERS,
        params=params,
        timeout=30,
    )
    response.raise_for_status()

    builds = response.json().get("value", [])

    results = []

    for build in builds:
        results.append({
            "build_id": build.get("id"),
            "build_number": build.get("buildNumber"),
            "pipeline_name": (
                build.get("definition", {}).get("name")
            ),
            "status": build.get("status"),
            "result": build.get("result"),
            "source_branch": build.get("sourceBranch"),
            "source_version": build.get("sourceVersion"),
            "requested_by": (
                build.get("requestedBy", {}).get("displayName")
            ),
            "start_time": build.get("startTime"),
            "finish_time": build.get("finishTime"),
            "url": build.get("_links", {}).get("web", {}).get("href"),
        })

    return {
        "source": "AZURE_DEVOPS_REST_API",
        "organization": AZDO_ORG,
        "project": AZDO_PROJECT,
        "lookback_hours": lookback_hours,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "build_count": len(results),
        "builds": results,
    }