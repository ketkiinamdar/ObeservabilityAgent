"""Read-only ServiceNow incident search plus explicitly gated incident creation."""
import os
import requests
from requests.auth import HTTPBasicAuth
from dotenv import load_dotenv
load_dotenv()

FIELDS = "number,short_description,description,priority,state,assignment_group,opened_at,closed_at,close_code,close_notes,cmdb_ci,sys_created_on"

def _base():
    instance = os.getenv("SERVICENOW_INSTANCE", "").rstrip("/")
    if not instance:
        raise RuntimeError("SERVICENOW_INSTANCE is not configured")
    return instance

def _auth():
    user, password = os.getenv("SERVICENOW_USER"), os.getenv("SERVICENOW_PASSWORD")
    if not user or not password:
        raise RuntimeError("SERVICENOW_USER and SERVICENOW_PASSWORD are required")
    return HTTPBasicAuth(user, password)

def search_incidents(text="", days=90, limit=100):
    """Read recent incidents. Do not pass customer PII in the search text."""
    days = max(1, min(int(days), 3650))
    params = {
        "sysparm_limit": min(max(int(limit), 1), 500),
        "sysparm_fields": FIELDS,
        "sysparm_query": f"sys_created_on>=javascript:gs.daysAgoStart({days})^ORDERBYDESCsys_created_on",
    }
    # Escape ServiceNow encoded-query control characters to avoid query injection.
    term = str(text or "").replace("^", "").replace("\\", "")[:100]
    if term:
        params["sysparm_query"] += f"^short_descriptionLIKE{term}"
    url = f"{_base()}/api/now/table/{os.getenv('SERVICENOW_TABLE', 'incident')}"
    response = requests.get(url, params=params, auth=_auth(), timeout=30)
    response.raise_for_status()
    return response.json().get("result", [])

def create_incident(summary, description, category="software", urgency="3"):
    """Create only when explicitly enabled; keep this out of autonomous agent tools."""
    if os.getenv("SERVICENOW_ALLOW_CREATE", "false").lower() != "true":
        raise PermissionError("ServiceNow incident creation is disabled. Set SERVICENOW_ALLOW_CREATE=true after approval.")
    payload = {"short_description": str(summary)[:160], "description": str(description),
               "category": category, "urgency": str(urgency)}
    url = f"{_base()}/api/now/table/{os.getenv('SERVICENOW_TABLE', 'incident')}"
    response = requests.post(url, json=payload, auth=_auth(), headers={"Accept":"application/json"}, timeout=30)
    response.raise_for_status()
    return response.json().get("result", {})
