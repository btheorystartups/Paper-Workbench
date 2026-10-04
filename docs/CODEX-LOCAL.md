# Local Codex chat provider

`codex_local` is explicitly opt-in and disabled by default. It uses a locally
authenticated ChatGPT account through the official Codex app-server. It has no API-key
or fake fallback. Other providers retain their existing behavior.

**One OS user, one local instance, one isolated Codex profile.** This release does not
support shared or hosted servers. Every person who wants to use their own plan or
credits must run and authenticate their own instance. The gate grants access to this
adapter; it does not select, prove, or change the billed account. Usage belongs to the
ChatGPT account authenticated in that instance's Codex profile.

## Setup (PowerShell)

1. From the Paper-Workbench project, install the optional dependencies into its venv:

   ```powershell
   uv sync --extra codex-local
   ```

   The lockfile pins `openai-codex` and its runtime to `0.154.0`. Upgrades require a new
   capability review. The adapter uses the documented stdio JSON-RPC API with the
   SDK's bundled executable, and starts a fresh process and ephemeral thread for
   each generation. It never reads Codex credential files or OS credential stores.

2. Choose a new, dedicated directory outside the repository and the default `.codex`
   profile. Authenticate interactively with the bundled Codex login command:

   ```powershell
   $env:CODEX_HOME = Join-Path $env:USERPROFILE '.paper-workbench-codex'
   New-Item -ItemType Directory -Force -Path $env:CODEX_HOME | Out-Null
   $workbenchCodex = & .venv/Scripts/python.exe -c "from codex_cli_bin import bundled_codex_path; print(bundled_codex_path())"
   & $workbenchCodex --config 'cli_auth_credentials_store="file"' --config 'forced_login_method="chatgpt"' login
   ```

   Complete the supported browser sign-in as yourself. Codex owns credential storage
   and refresh. Do not copy tokens. Keep this dedicated profile private to your OS user
   and free of plugins, MCP servers, hooks, custom endpoints, and extra configuration.

3. Independently generate a gate with at least 32 random characters, for example with
   your password manager or Python's `secrets.token_urlsafe(32)`. Put it in your
   uncommitted `.env`, along with these settings (replace the placeholders):

   ```dotenv
   WB_LLM_PROVIDER=codex_local
   WB_CODEX_LOCAL_ENABLED=true
   WB_CODEX_LOCAL_GATE_SECRET=<independently-generated-secret>
   WB_CODEX_LOCAL_HOME=C:/Users/<you>/.paper-workbench-codex
   WB_CODEX_LOCAL_ACCOUNT_EMAIL=<your-ChatGPT-email>
   WB_CODEX_LOCAL_MODEL=gpt-5.6-sol
   WB_CODEX_LOCAL_REASONING_EFFORT=xhigh
   WB_CODEX_LOCAL_MAX_INPUT_TOKENS=200000
   WB_CODEX_LOCAL_MAX_OUTPUT_TOKENS=1000000
   WB_CODEX_LOCAL_TIMEOUT_SECONDS=120
   WB_DEPLOYMENT_MODE=local
   WB_AUTH_REQUIRED=false
   WB_AUTH_ALLOW_REGISTRATION=false
   WB_AUTH_COOKIE_SESSIONS_ENABLED=false
   WB_OIDC_MODE=disabled
   ```

   An optional `WB_CODEX_LOCAL_WORKSPACE_ID` UUID applies Codex's supported workspace
   restriction when an administrator provides that ID. Account/read currently exposes
   email and plan metadata, not a stable account/workspace UUID; the expected email
   is mandatory. Provenance records a workspace ID only when explicitly restricted.

4. Prepare the application tokenizer once (may download public tokenizer data):

   ```powershell
   .venv/Scripts/python.exe -c "import tiktoken; tiktoken.get_encoding('o200k_base')"
   ```

5. Launch with the dedicated loopback launcher:

   ```powershell
   .venv/Scripts/python.exe -m workbench.codex_local_server --port 8000
   ```

   This binds its own socket to `127.0.0.1`, uses one worker, disables proxy-header
   trust and access logs, and performs normal application startup/migrations. Back up
   your database before a schema upgrade. Arbitrary uvicorn launchers cannot activate
   this provider because their socket binding cannot be established by the adapter.

6. Open `http://127.0.0.1:8000`. Enter the gate in **Local gate secret**, then choose
   **Verify account**. Review the returned email, ChatGPT authentication mode, plan,
   model and reasoning effort before generation. Access stays in memory and clears
   on reload or **Clear access**. Never place the gate in prompts, URLs, project data,
   browser storage, or artifacts. API clients send it only in
   `X-Workbench-Codex-Gate`; `/providers/codex-local/account` performs the same checks.

## Limits and provenance

The input limit counts the JSON-serialized system text and messages supplied by
Paper-Workbench using `o200k_base`. Oversized input is rejected before a Codex process
starts. The output limit caps returned text using that same application tokenizer.
The effective output limit is the smaller of the configured ceiling and the workflow's
requested limit (existing workflows commonly request 1,024 or 4,096 tokens).
Truncated output carries `output_truncated=true` and contains no proposed actions.

These are application text limits, **not account-usage ceilings**. Codex may add
instructions, reasoning, retries and internal work. Native model limits also apply;
configuring 1M does not make a model support a 1M response. Timeout, disconnect and
output-limit cancellation request `turn/interrupt` and terminate the local process;
upstream cancellation is best effort and tokens already consumed cannot be recovered.

Every generation verifies the profile, effective restrictions, account email and plan,
ChatGPT quota metadata, available model and reasoning effort. Unknown or unavailable
metadata causes refusal. Tools are disabled through the pinned runtime's feature
controls; a named permission profile with no filesystem grants and network disabled,
denied approval requests and an empty temporary working directory provide additional
restrictions. The adapter checks the effective profile and rejects inherited grants.
The pinned runtime requires this profile instead of the obsolete `readOnly.access`
turn field. The child receives neither the gate nor API
keys. Unexpected tool activity, model rerouting, authentication changes and malformed
responses fail closed with application-owned error messages.

Usage events carry provider, authentication/quota source, model/effort, thread/turn IDs,
reported token usage and availability/completeness flags. Missing usage remains unknown,
even though legacy integer database columns store zero. ChatGPT-plan totals are reported
separately from API tokens and do not count toward existing API token budgets. Failed
requests can still consume account usage; when no result is returned, no completed
usage event is committed. Do not treat the local ledger as an authoritative account bill.

Official references: [Codex SDK](https://learn.chatgpt.com/docs/codex-sdk),
[app-server](https://learn.chatgpt.com/docs/app-server),
[authentication](https://learn.chatgpt.com/docs/auth), and
[configuration schema](https://learn.chatgpt.com/docs/config-schema.json).
