# JBF Cloud Agent

Remote JBF agent hosted on Cloudflare Workers. `jbf agent <task>` sends work to this Worker; the phone is only the task entry point and per-action approval surface. Planning, model inference, and connected-service work run in the cloud. It uses Cloudflare Workers AI `@cf/zai-org/glm-4.7-flash` first. On free-quota/capacity errors, it can use the owner-approved OpenRouter `openrouter/free` router. The model ID is fixed to the free router; paid model IDs and credit purchases are not used.

The agent supports GitHub, Cloudflare, and Supabase remote MCP. Explicitly read-only tools may run automatically. Other external calls pause for one exact approval in the local JBF terminal; after approval, the cloud agent resumes the same task. Supabase starts in read-only mode. Sensitive input fields are redacted in approval summaries.

Run `jbf agent providers` to see which provider paths are connected, approval-based, or unavailable without manual setup. JBF reuses the existing GitHub and Cloudflare credentials and can open a dynamic OAuth consent flow for Supabase; it must not ask for pasted API keys, create OAuth apps, or start paid plans. Cloudflare exposes hosting, D1/KV/R2, and Workers AI through the existing account. GitHub Actions is temporary compute, not a persistent VPS. Supabase remains read-only unless a future project-scoped write connection is explicitly approved. Gmail/WhatsApp paths that require manual app registration are skipped. GitHub Models is retired.

Deployment creates a separate Worker named `jbf-cloud-agent` and leaves the existing Steadfast Worker untouched. GitHub Actions uses the existing Cloudflare deployment secrets plus a separate generated `JBF_OWNER_TOKEN` secret. The application code has no provider credentials.

Free quotas and model availability can change. If both free inference providers fail, the task stops without a paid fallback. OpenRouter's free model limits apply. Gmail, WhatsApp, and SnapDeploy are not in this first cloud release.

The agent compares product opportunities—including game-studio tools, image/video generation, and other SaaS ideas—by verifiable buyer demand and the fastest free route to revenue. It can build through connected GitHub and Cloudflare tools; writes and deployments are held for owner approval. Owner-provided email and WhatsApp contact values are installed as Worker secrets and used only in owner-approved outreach or a specifically approved public listing. Gmail and WhatsApp sending connectors are not connected.
