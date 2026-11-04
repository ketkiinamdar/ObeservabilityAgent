"""Scheduled read-only engineering intelligence collector."""
import json, os
from pathlib import Path
from datetime import datetime, timezone
from dotenv import load_dotenv
from clients.servicenow_client import search_incidents
from clients.sonarcloud_client import quality_gate, measures, issues
from agents.technology_intelligence import collect
load_dotenv()

def run_daily_intelligence():
    report = {"generated_utc": datetime.now(timezone.utc).isoformat(), "servicenow": {}, "sonarcloud": {}, "technology_releases": {}, "errors": []}
    try:
        report["servicenow"]["recent_incidents"] = search_incidents(days=int(os.getenv("SERVICENOW_LOOKBACK_DAYS", "90")))
    except Exception as exc: report["errors"].append({"source": "ServiceNow", "error": str(exc)})
    keys = [x.strip() for x in os.getenv("SONARCLOUD_PROJECT_KEYS", "").split(",") if x.strip()]
    for key in keys:
        try: report["sonarcloud"][key] = {"quality_gate": quality_gate(key), "measures": measures(key), "issues": issues(key)}
        except Exception as exc: report["errors"].append({"source": f"SonarCloud:{key}", "error": str(exc)})
    try: report["technology_releases"] = collect()
    except Exception as exc: report["errors"].append({"source": "Technology release feeds", "error": str(exc)})
    output_dir = Path(os.getenv("REPORT_DIR", "reports")); output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_file = output_dir / f"engineering_intelligence_{stamp}.json"
    output_file.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    report["report_file"] = str(output_file.resolve())
    return report

if __name__ == "__main__":
    result = run_daily_intelligence()
    print(json.dumps({"report_file": result["report_file"], "errors": result["errors"]}, indent=2))
