import os
import time
import logging

from dotenv import load_dotenv
from azure.monitor.opentelemetry import configure_azure_monitor
from opentelemetry import trace
from opentelemetry.trace import SpanKind, Status, StatusCode

load_dotenv()

connection_string = os.getenv(
    "APPLICATIONINSIGHTS_CONNECTION_STRING"
)

if not connection_string:
    raise ValueError("Application Insights connection string missing")

configure_azure_monitor(
    connection_string=connection_string
)

tracer = trace.get_tracer("insurance-policy-api")
logger = logging.getLogger("insurance-policy-api")

correlation_id = "RCA-TEST-2026-004"

# 1. Simulate an incoming API request
with tracer.start_as_current_span(
    "GET /api/policies",
    kind=SpanKind.SERVER
) as request_span:

    request_span.set_attribute("service.name", "insurance-policy-api")
    request_span.set_attribute("environment", "TEST")
    request_span.set_attribute("correlation.id", correlation_id)

    # 2. Simulate SQL dependency failure
    with tracer.start_as_current_span(
        "SQL Database - GetPolicy",
        kind=SpanKind.CLIENT
    ) as dependency_span:

        dependency_span.set_attribute(
            "db.system", "mssql"
        )
        dependency_span.set_attribute(
            "db.operation.name", "SELECT"
        )
        dependency_span.set_attribute(
            "correlation.id", correlation_id
        )

        dependency_span.set_status(
            Status(StatusCode.ERROR, "SQL timeout")
        )

        logger.error(
            "SQL dependency timeout: response time 4500ms",
            extra={
                "correlation_id": correlation_id,
                "service_name": "insurance-policy-api",
                "environment": "TEST"
            }
        )

    # 3. Simulate application exception
    try:
        raise TimeoutError(
            "Database connection timed out while fetching policy"
        )
    except TimeoutError as ex:
        request_span.record_exception(ex)
        request_span.set_status(
            Status(StatusCode.ERROR, str(ex))
        )
        logger.exception(
            "Policy API failed due to database timeout"
        )

    time.sleep(0.1)

print("Synthetic Application Insights telemetry submitted.")
print("Correlation ID:", correlation_id)

# Allow telemetry exporter to flush before process exits
time.sleep(10)