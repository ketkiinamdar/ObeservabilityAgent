import os
from datetime import datetime, timezone
from dotenv import load_dotenv
from azure.identity import DefaultAzureCredential
from azure.monitor.ingestion import LogsIngestionClient
from azure.core.exceptions import HttpResponseError

load_dotenv()

ENDPOINT = os.getenv("AZURE_MONITOR_INGESTION_ENDPOINT")
DCR_ID = os.getenv("AZURE_MONITOR_DCR_IMMUTABLE_ID")
STREAM_NAME = os.getenv("AZURE_MONITOR_STREAM_NAME")

if not all([ENDPOINT, DCR_ID, STREAM_NAME]):
    raise ValueError("Missing Azure Monitor ingestion configuration in .env")

# Create sample records
now = datetime.now(timezone.utc)

logs = [
    {
        "TimeGenerated": now.isoformat(),
        "ServiceName": "insurance-policy-api",
        "Environment": "TEST",
        "Severity": "Error",
        "Message": "SQL connection timeout while fetching policy details",
        "CorrelationId": "RCA-TEST-2026-002",
        "Scenario": "RCA_TEST"
    },
    {
        "TimeGenerated": now.isoformat(),
        "ServiceName": "insurance-policy-api",
        "Environment": "TEST",
        "Severity": "Warning",
        "Message": "SQL dependency response time exceeded 4 seconds",
        "CorrelationId": "RCA-TEST-2026-002",
        "Scenario": "RCA_TEST"
    },
    {
        "TimeGenerated": now.isoformat(),
        "ServiceName": "insurance-policy-api",
        "Environment": "TEST",
        "Severity": "Information",
        "Message": "Application restarted after configuration update",
        "CorrelationId": "RCA-TEST-2026-002",
        "Scenario": "RCA_TEST"
    }
]

credential = DefaultAzureCredential()

try:
    client = LogsIngestionClient(
        endpoint=ENDPOINT,
        credential=credential
    )

    client.upload(
        rule_id=DCR_ID,
        stream_name=STREAM_NAME,
        logs=logs
    )

    print(f"Successfully submitted {len(logs)} records.")

except HttpResponseError as e:
    print(f"Azure ingestion failed: {e}")

finally:
    if "client" in locals():
        client.close()
    credential.close()