import json
from azure_devops_client import get_recent_builds

data = get_recent_builds(lookback_hours=24)

print(json.dumps(data, indent=2))