# Setup Guide

## 1. Create a Foundry Project

1. Sign in to [Microsoft Foundry](https://ai.azure.com/).
2. Create a new project or open an existing one.
3. Note your **project endpoint** from the Overview page (look for the "Endpoint" field at the top):
   ```
   https://<account_name>.services.ai.azure.com/api/projects/<project_name>
   ```

> **Tip:** You can also find it via CLI: `az cognitiveservices account show --name <account> --resource-group <rg> --query properties.endpoint`

## 2. Deploy an AI Model

1. In your Foundry project, go to **Build → Models**.
2. Deploy a model (e.g., `gpt-4o-mini`).
3. Note the **deployment name** from the "Name" column in the Deployments table.

## 3. Connect Application Insights (for cloud tracing)

1. In Foundry, go to **Agents → Traces**.
2. Click **Connect** and either:
   - Connect an existing Application Insights resource, or
   - Create a new one.
3. A confirmation message appears when the connection succeeds.

> **Permissions:** You need the `Log Analytics Reader` role to query telemetry. See [Assign Azure roles](https://learn.microsoft.com/azure/role-based-access-control/role-assignments-portal).

## 4. Install Dependencies

```bash
pip install -r requirements.txt
```

This installs:

| Package | Purpose |
|---------|---------|
| `azure-ai-projects` | Core SDK — agents, evaluations, telemetry |
| `azure-identity` | Authentication (DefaultAzureCredential) |
| `python-dotenv` | Load `.env` files |
| `opentelemetry-sdk` | OpenTelemetry core |
| `azure-core-tracing-opentelemetry` | Azure SDK tracing bridge |
| `azure-monitor-opentelemetry` | Export to Application Insights |
| `opentelemetry-exporter-otlp` | Export via OTLP (for Aspire Dashboard) |
| `azure-monitor-query` | Query Application Insights logs (for trace-based evals) |
| `aiohttp` | Async HTTP — required for async examples only |

## 5. Configure Environment Variables

```bash
cp .env.example .env
```

Edit `.env` with your values. At minimum:

```env
AZURE_AI_PROJECT_ENDPOINT="https://<account>.services.ai.azure.com/api/projects/<project>"
AZURE_AI_MODEL_DEPLOYMENT_NAME="gpt-4o-mini"
AZURE_EXPERIMENTAL_ENABLE_GENAI_TRACING=true
```

See [.env.example](../.env.example) for a full list of variables with descriptions.

## 6. Set Up Aspire Dashboard (Local Trace Viewer)

The [Aspire Dashboard](https://aspire.dev/dashboard/standalone/) gives you a local UI to view OpenTelemetry traces without needing Azure resources.

### Using the DevContainer (recommended)

If you open this repo in VS Code with the DevContainer, the Aspire Dashboard **starts automatically**. Just open http://localhost:18888.

### Manual setup

```bash
docker compose up -d
```

This starts:
- **Dashboard UI** → http://localhost:18888
- **OTLP gRPC endpoint** → http://localhost:4317

To stop:
```bash
docker compose down
```

## 7. Azure CLI Login

```bash
az login
```

The SDK uses `DefaultAzureCredential`, which picks up your Azure CLI credentials.

## 8. RBAC Roles Reference

| Role | When needed | Where to assign |
|------|-------------|-----------------|
| `Log Analytics Reader` | Querying traces in Application Insights | Application Insights resource |
| `Cognitive Services User` | Eval runs (project MI calls RAI/content-safety service) | AI Services account |
| `Storage Blob Data Contributor` | Eval runs (project MI reads/writes eval data) | Project storage account |
| `Azure AI User` | Scheduled evaluations (managed identity) | Foundry project resource |
| `Contributor` or `Owner` | Creating/managing resources | Resource group level |

Assign roles via: Azure portal → Resource → Access Control (IAM) → Add role assignment.

### Storage Network Configuration for Evaluations

Eval runs use the project's Managed Identity to access the linked storage account via the Responsible AI (RAI) backend service. If your storage account has a firewall enabled:

- **`publicNetworkAccess: Disabled`** → Eval runs will fail with `AuthorizationFailure`. The RAI service cannot reach storage through private endpoints alone unless explicitly configured.
- **`publicNetworkAccess: Enabled` + `defaultAction: Allow`** → Works. Security is maintained via `allowSharedKeyAccess: false` (Entra ID + RBAC only).
- **`publicNetworkAccess: Enabled` + `defaultAction: Deny`** → May fail because the RAI service accesses storage through a delegated identity path that is not covered by the `bypass: AzureServices` exception or resource instance rules.

Recommended configuration for the project's linked storage account:

```bash
az storage account update \
  --name <storage-account-name> \
  --resource-group <resource-group> \
  --public-network-access Enabled \
  --default-action Allow \
  --allow-shared-key-access false
```

## 9. Verify Everything Works

```bash
# 1. Check that dependencies installed
python -c "import azure.ai.projects; print(azure.ai.projects.__version__)"

# 2. Check Aspire Dashboard is running
curl -s http://localhost:18888 > /dev/null && echo "Aspire Dashboard is running" || echo "Not running"

# 3. Run the simplest tracing example
python examples/01_tracing_console/tracing_console.py
```

If you see span output in the console, you're ready to go!

## 10. Troubleshooting Common Errors

These are the most common issues we've seen when running the examples:

### `ProjectMIUnauthorized` / `AuthorizationFailure` on eval runs

**Symptom:** `evals.create()` succeeds but `evals.runs.create()` fails with a 401/403 mentioning `ProjectMIUnauthorized` and component `raisvc`.

**Root cause:** Eval runs execute server-side using the project's **Managed Identity (MI)**. The MI needs both RBAC roles AND network access to the storage account.

**Fix — check in this order:**

1. **Is the MI enabled?** Azure Portal → Your AI project → Identity → System assigned → Status: **On**.
2. **Does the MI have the right roles?** Check with:
   ```bash
   # Get your project MI's principal ID
   az resource show \
     --ids "/subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.CognitiveServices/accounts/<account>/projects/<project>" \
     --query identity.principalId -o tsv
   
   # List its roles
   az role assignment list --assignee <principal-id> --all -o table
   ```
   You need at minimum: `Cognitive Services User` on the AI Services account, and `Storage Blob Data Contributor` on the storage account.
3. **Is the storage firewall blocking?** This is the most common gotcha. See [Storage Network Configuration](#storage-network-configuration-for-evaluations) above.

### `Log Analytics Reader` 403 when querying traces

**Symptom:** Example 07 (eval_traces) fails to query Application Insights.

**Fix:** Your user identity needs the `Log Analytics Reader` role on the Application Insights resource. Assign it in Azure Portal → Application Insights → Access Control (IAM).

### `AGENT_ID` empty — no traces found

**Symptom:** Example 07 (eval_traces) prints "No trace IDs found".

**Fix:** Set `AGENT_ID` in your `.env` to the agent ID you used when running tracing examples (e.g., `ObservabilityDemoAgent:1`). You can discover available agent IDs by querying App Insights — see the example's docstring for the Kusto query.

---

**Next:** [Tracing Deep-Dive →](03-tracing.md)
