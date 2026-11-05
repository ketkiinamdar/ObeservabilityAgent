# ObeservabilityAgent

# AI Engineering

AI-powered engineering operations for smarter incident resolution,
proactive technology insights, and cost optimization.

# Insurance AI Engineering Intelligence + RCA

This package keeps the existing Azure Monitor / Application Insights / Azure DevOps RCA investigation and adds separate read-only engineering-intelligence collectors.

## Project files
- `agent.py` — incident RCA agent, with ServiceNow history, SonarCloud and release-feed tools added.
- `azure_devops_client.py` — supplied Azure DevOps build-history client.
- `clients/servicenow_client.py` — read-only historical incident search. Incident creation is separate and disabled by default.
- `clients/sonarcloud_client.py` — quality gate, measures and issues.
- `agents/technology_intelligence.py` — RSS/Atom release feed collector.
- `agents/daily_intelligence.py` — daily engineering intelligence JSON report.
- `scheduler.py` — optional periodic collector + Teams summary.
- `notifications/teams_notifier.py` — Teams Incoming Webhook notification.

## Setup
1. Copy your existing `dummy_data.py`, `dummy_application_insights.py`, and `azure_monitor_client.py` into this project folder (these were referenced by your submitted `agent.py` but were not included in the uploads).
2. Create/activate a virtual environment and install `pip install -r requirements.txt`.
3. Copy `.env.example` to `.env` and fill in only the integrations you intend to use.
4. Set Azure authentication for `DefaultAzureCredential` (for example `az login` locally or Managed Identity when hosted).
5. Ensure `AZDO_PAT` is set. The submitted Azure DevOps client reads `AZDO_PAT`; `AZDO_TOKEN` in the submitted agent is unused.
6. Run an interactive RCA: `python agent.py`.
7. Run a one-off intelligence collection: `python -m agents.daily_intelligence`.
8. Run scheduled intelligence: `python scheduler.py`.

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


