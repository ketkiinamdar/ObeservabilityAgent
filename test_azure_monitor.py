import json

from azure_monitor_client import get_real_azure_monitor_data

if __name__ == "__main__":
    data = get_real_azure_monitor_data(lookback_hours=1)
    print(json.dumps(data, indent=2, default=str))