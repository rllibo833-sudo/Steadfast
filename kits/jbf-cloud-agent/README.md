# JBF Cloud Agent

Remote JBF agent hosted on Cloudflare Workers. `jbf agent <task>` sends work to this Worker; the phone is only the task entry point and per-action approval surface. Planning, model inference, and connected-service work run in the cloud. The model is Cloudflare Workers AI free binding `@cf/zai-org/glm-4.7-flash`; there is no paid fallback.

The agent supports GitHub, Cloudflare, and Supabase remote MCP. Explicitly read-only tools may run automatically. Other external calls pause for one exact approval in the local JBF terminal; after approval, the cloud agent resumes the same task. Supabase starts in read-only mode. Sensitive input fields are redacted in approval summaries.

Deployment creates a separate Worker named `jbf-cloud-agent` and leaves the existing Steadfast Worker untouched. GitHub Actions uses the existing Cloudflare deployment secrets plus a separate generated `JBF_OWNER_TOKEN` secret. The application code has no provider credentials.

Free quotas can change. When Cloudflare AI's free quota is exhausted, the task stops without a paid fallback. Gmail, WhatsApp, and SnapDeploy are not in this first cloud release.
