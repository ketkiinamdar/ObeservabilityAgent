"""Read-only SonarCloud project quality/security collectors."""
import os, requests
from dotenv import load_dotenv
load_dotenv()
BASE = "https://sonarcloud.io/api"

def _get(path, params):
    token = os.getenv("SONARCLOUD_TOKEN")
    if not token:
        raise RuntimeError("SONARCLOUD_TOKEN is not configured")
    response = requests.get(f"{BASE}/{path}", params=params, auth=(token, ""), timeout=30)
    response.raise_for_status()
    return response.json()

def quality_gate(project): return _get("qualitygates/project_status", {"projectKey": project})
def measures(project):
    metrics = "alert_status,bugs,vulnerabilities,security_hotspots,code_smells,coverage,duplicated_lines_density,sqale_index"
    return _get("measures/component", {"component": project, "metricKeys": metrics})
def issues(project):
    return _get("issues/search", {"projectKeys": project, "types": "BUG,VULNERABILITY,CODE_SMELL", "ps": 100, "s": "CREATION_DATE", "asc": "false"})
