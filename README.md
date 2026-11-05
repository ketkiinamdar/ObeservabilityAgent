# ObeservabilityAgent

# AI Engineering

AI-powered engineering operations for smarter incident resolution,
proactive technology insights, and cost optimization.

## Project files
- `agent.py` — incident RCA agent, with ServiceNow history, SonarCloud and release-feed tools added.
- `azure_devops_client.py` — supplied Azure DevOps build-history client.
- `clients/servicenow_client.py` — read-only historical incident search. Incident creation is separate and disabled by default.
- `clients/sonarcloud_client.py` — quality gate, measures and issues.
- `agents/technology_intelligence.py` — RSS/Atom release feed collector.
- `agents/daily_intelligence.py` — daily engineering intelligence JSON report.
- `scheduler.py` — optional periodic collector + Teams summary.
- `notifications/teams_notifier.py` — Teams Incoming Webhook notification.

## Safety and evidence boundaries
- ServiceNow search and SonarCloud access are read-only. Use least-privilege credentials.
- `SERVICENOW_ALLOW_CREATE` defaults to `false`; the create API is not exposed as an LLM tool. Any future incident creation should be an explicit human-approved workflow.
- Teams notifications require a webhook URL and are sent only by the scheduler.
- Release feeds are discovery signals, not proof that a release affects your estate. Compare versions against actual repository inventories before recommending an upgrade. The provided feeds are not guaranteed to cover every official release page.
- Build history is not environment deployment history. To prove a deployment, add Azure DevOps Releases/Environments deployment records and environment/resource identifiers.
- Historical incidents are precedents, not proof of current root cause. Avoid forwarding customer-identifying information or raw work notes to the LLM.
- No production remediation is performed.

## Azure DevOps credentials
Your `azure_devops_client.py` expects `AZDO_ORG`, `AZDO_PROJECT`, and `AZDO_PAT`. Keep the PAT in a secret store; do not commit `.env`.

## Architecture
<img width="1536" height="1024" alt="image" src="https://github.com/user-attachments/assets/3b88084a-ea98-4b67-a1c1-c5f21be9cd95" />


