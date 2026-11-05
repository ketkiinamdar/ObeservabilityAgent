"""Run periodic intelligence collection. Start as a separate long-running process."""
import os
from apscheduler.schedulers.blocking import BlockingScheduler
from dotenv import load_dotenv
from agents.daily_intelligence import run_daily_intelligence
from notifications.teams_notifier import send_teams_notification
load_dotenv()

def scheduled_job():
    report = run_daily_intelligence()
    counts = {
        "ServiceNow incidents": len(report.get("servicenow", {}).get("recent_incidents", [])),
        "SonarCloud projects": len(report.get("sonarcloud", {})),
        "technology release entries": len(report.get("technology_releases", {}).get("items", [])),
        "collection errors": len(report.get("errors", [])),
    }
    message = "\n".join(f"- {key}: {value}" for key, value in counts.items())
    send_teams_notification("Engineering intelligence summary", message, report.get("report_file"))

if __name__ == "__main__":
    minutes = max(15, int(os.getenv("INTELLIGENCE_INTERVAL_MINUTES", "360")))
    scheduler = BlockingScheduler(timezone="UTC")
    scheduler.add_job(scheduled_job, "interval", minutes=minutes, id="engineering-intelligence", max_instances=1, coalesce=True)
    print(f"Scheduler started; first run now, then every {minutes} minutes")
    scheduled_job()
    scheduler.start()
