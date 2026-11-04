"""Send a concise notification to a Teams Incoming Webhook."""
import os, requests

def send_teams_notification(title, message, report_url=None):
    webhook = os.getenv("TEAMS_INCOMING_WEBHOOK_URL")
    if not webhook:
        return {"sent": False, "reason": "TEAMS_INCOMING_WEBHOOK_URL is not configured"}
    text = f"**{title}**\n\n{message}"
    if report_url: text += f"\n\nReport: {report_url}"
    response = requests.post(webhook, json={"text": text}, timeout=20)
    response.raise_for_status()
    return {"sent": True, "status_code": response.status_code}
