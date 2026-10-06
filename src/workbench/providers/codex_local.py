"""Opt-in local ChatGPT-account adapter, one process and fresh thread per call."""

import json
import tempfile
import threading
import time
from contextvars import ContextVar
from pathlib import Path

from .codex_access import LOCAL_NOTICE, CodexLimitError, CodexLocalError, require_access
from .codex_rpc import RUNTIME_VERSION, StdioCodexClient
from .llm import parse_action_block
from .protocols import ChatResult, validate_reasoning_effort

request_cancel: ContextVar[threading.Event | None] = ContextVar("codex_cancel", default=None)
TEXT_ONLY_PROFILE = "paper_workbench_text_only"

# Official configuration-schema feature switches. Pinning the runtime makes this
# explicit deny set reviewable; a runtime upgrade requires a capability review.
DISABLED_FEATURES = (
    "shell_tool", "unified_exec", "shell_snapshot", "shell_snapshot_v2", "shell_zsh_fork",
    "unified_exec_zsh_fork", "js_repl", "code_mode", "code_mode_host", "code_mode_only",
    "apps", "connectors", "enable_mcp_apps", "plugins", "remote_plugin", "recommended_plugins",
    "browser_use", "browser_use_external", "in_app_browser", "computer_use", "image_generation",
    "imagegenext", "view_image", "multi_agent", "multi_agent_v2", "collab", "goals",
    "hooks", "codex_hooks", "plugin_hooks", "memories", "memory_tool", "chronicle",
    "request_permissions", "request_permissions_tool", "send_async_message", "telepathy",
    "in_app_local_automation", "workspace_dependencies", "skill_search", "tool_search",
    "skill_mcp_dependency_install", "skill_env_var_dependency_prompt", "tool_suggest",
    "workspace_owner_usage_nudge", "remote_control", "standalone_web_search", "search_tool",
    "web_search", "web_search_cached", "web_search_request", "remote_compaction_v2",
    "step_model_switching", "use_agent_identity", "unbounded_connection_retries",
)


def runtime_overrides(settings, *, restrict_reads=False, counter_namespace=False):
    values = {f"features.{name}": False for name in DISABLED_FEATURES if name != "code_mode"}
    values.update({
        "features.code_mode.enabled": False,
        "forced_login_method": "chatgpt",
        "cli_auth_credentials_store": "file",
        "model_provider": "openai",
        "chatgpt_base_url": "https://chatgpt.com/backend-api/",
        "model": settings.codex_local_model,
        "model_reasoning_effort": settings.codex_local_reasoning_effort,
        "sandbox_mode": "read-only", "approval_policy": "never",
        "web_search": "disabled", "agents.enabled": False,
        "project_doc_max_bytes": 0, "analytics.enabled": False,
        "feedback.enabled": False, "check_for_update_on_startup": False,
        "history.persistence": "none", "memories.use_memories": False,
        "features.skip_host_skill_discovery": True,
        "notify": [], "mcp_servers": {}, "plugins": {},
    })
    if counter_namespace:
        values["features.code_mode.direct_only_tool_namespaces"] = ["paper_counter"]
    if settings.codex_local_workspace_id:
        values["forced_chatgpt_workspace_id"] = settings.codex_local_workspace_id
    if restrict_reads:
        values.pop("sandbox_mode")
        values.update({
            "default_permissions": TEXT_ONLY_PROFILE,
            f"permissions.{TEXT_ONLY_PROFILE}.filesystem": {},
            f"permissions.{TEXT_ONLY_PROFILE}.network.enabled": False,
        })
    return values


def _encoding():
    try:
        import tiktoken

        return tiktoken.get_encoding("o200k_base")
    except Exception:
        raise CodexLocalError("codex_local requires the optional tokenizer and its o200k_base data") from None


class CodexLocalChatAdapter:
    def __init__(self, settings, *, client_factory=StdioCodexClient, encoding_factory=_encoding):
        self.settings = settings
        self.client_factory = client_factory
        self.encoding_factory = encoding_factory

    def _preflight(self, client, deadline):
        settings = self.settings
        info = client.request("initialize", {
            "clientInfo": {"name": "paper_workbench", "version": "0.1.0"},
            "capabilities": {"experimentalApi": True},
        }, deadline=deadline)
        client.notify("initialized")
        if Path(info.get("codexHome", "")).resolve() != Path(settings.codex_local_home).resolve():
            raise CodexLocalError("codex_local runtime did not select the isolated profile")
        runtime_version = (info.get("serverInfo") or {}).get("version")
        if not runtime_version:
            agent = info.get("userAgent", "")
            runtime_version = agent.split("/", 1)[-1].split(" ", 1)[0]
        if runtime_version != RUNTIME_VERSION:
            raise CodexLocalError("codex_local runtime version is not the reviewed version")

        config = client.request("config/read", {"includeLayers": False}, deadline=deadline).get("config", {})
        # Check effective security settings, not merely requested command-line flags.
        for key, expected in runtime_overrides(settings, restrict_reads=True).items():
            current = config
            for part in key.split("."):
                current = current.get(part) if isinstance(current, dict) else None
            if key == f"permissions.{TEXT_ONLY_PROFILE}.filesystem" and isinstance(current, dict):
                # The pinned runtime serializes this optional default even when
                # the requested filesystem table has no access grants.
                current = {k: v for k, v in current.items() if k != "glob_scan_max_depth" or v is not None}
            if current != expected:
                raise CodexLocalError("codex_local could not verify the effective runtime restrictions")
        profile = (config.get("permissions") or {}).get(TEXT_ONLY_PROFILE, {})
        if profile.get("extends") or profile.get("workspace_roots"):
            raise CodexLocalError("codex_local refuses inherited filesystem permissions")
        # Inherited standalone MCP servers must be absent, not simply uncalled.
        if config.get("mcp_servers"):
            raise CodexLocalError("codex_local profile must not configure MCP servers")
        if any(config.get(key) for key in (
            "openai_base_url", "model_instructions_file", "model_catalog_json",
        )):
            raise CodexLocalError("codex_local refuses custom endpoints, instructions, or model catalogs")

        account = client.request("account/read", {"refreshToken": True}, deadline=deadline).get("account")
        if not isinstance(account, dict) or account.get("type") != "chatgpt":
            raise CodexLocalError("codex_local requires an authenticated ChatGPT-managed account")
        email = account.get("email")
        plan = account.get("planType")
        if not email or email.casefold() != settings.codex_local_account_email.strip().casefold():
            raise CodexLocalError("codex_local authenticated account does not match the expected owner")
        if plan not in {
            "free", "go", "plus", "pro", "prolite", "team", "business", "enterprise", "edu",
            "edu_plus", "edu_pro", "ent26", "self_serve_business_prolite",
            "self_serve_business_usage_based", "enterprise_cbp_automation", "enterprise_cbp_usage_based",
        }:
            raise CodexLocalError("codex_local could not establish ChatGPT plan metadata")
        limits = client.request("account/rateLimits/read", {}, deadline=deadline)
        rate = (limits.get("rateLimitsByLimitId") or {}).get("codex") or limits.get("rateLimits")
        if not isinstance(rate, dict) or not isinstance(rate.get("primary"), dict):
            raise CodexLocalError("codex_local could not confirm the ChatGPT quota source")
        percent = rate["primary"].get("usedPercent")
        if (rate.get("limitId") not in {None, "codex"}
                or type(percent) not in {float, int} or not 0 <= percent <= 100):
            raise CodexLocalError("codex_local quota metadata is ambiguous")

        cursor = None
        selected = None
        for _ in range(20):
            page = client.request("model/list", {"includeHidden": True, "cursor": cursor}, deadline=deadline)
            selected = next((m for m in page.get("data", [])
                             if m.get("model") == settings.codex_local_model), None)
            cursor = page.get("nextCursor")
            if selected or not cursor:
                break
        efforts = [e.get("reasoningEffort") for e in (selected or {}).get("supportedReasoningEfforts", [])]
        if not selected or settings.codex_local_reasoning_effort not in efforts:
            raise CodexLocalError("codex_local model or reasoning effort is unavailable")
        return {"account_email": email, "plan_type": plan, "authentication_mode": "chatgpt",
                "quota_source": "chatgpt_plan", "quota_source_available": True,
                "workspace_id": settings.codex_local_workspace_id or None}

    def account_status(self):
        return self._execute(None, None)

    def chat(self, *, system, messages, model, max_output_tokens, reasoning_effort=None):
        require_access(self.settings)
        effort = validate_reasoning_effort(reasoning_effort or self.settings.codex_local_reasoning_effort)
        if model != self.settings.codex_local_model or effort != self.settings.codex_local_reasoning_effort:
            raise CodexLocalError("codex_local model and effort must match the configured selection")
        if (isinstance(max_output_tokens, bool)
                or not isinstance(max_output_tokens, int) or max_output_tokens <= 0):
            raise CodexLimitError("codex_local output text limit must be positive")
        # Role labels and JSON syntax are included in the supplied-text count.
        if any(m.get("role") not in {"user", "assistant", "system"} or not isinstance(m.get("content"), str)
               for m in messages):
            raise CodexLocalError("codex_local accepts text messages only")
        prompt = json.dumps({"system": system, "messages": messages}, ensure_ascii=False)
        if self.settings.codex_local_gate_secret.get_secret_value() in prompt:
            raise CodexLocalError("codex_local refuses a prompt containing its access gate")
        encoding = self.encoding_factory()
        count = len(encoding.encode(prompt, disallowed_special=()))
        if count > self.settings.codex_local_max_input_tokens:
            raise CodexLimitError("codex_local supplied prompt exceeds the configured input text limit")
        maximum = min(max_output_tokens, self.settings.codex_local_max_output_tokens)
        return self._execute(prompt, (encoding, count, maximum))

    def _execute(self, prompt, text_limits):
        require_access(self.settings)
        deadline = time.monotonic() + self.settings.codex_local_timeout_seconds
        cancel = request_cancel.get() or threading.Event()
        client = None
        thread_id = turn_id = None
        try:
            with tempfile.TemporaryDirectory(prefix="workbench-codex-") as cwd:
                try:
                    client = self.client_factory(
                        profile=self.settings.codex_local_home, cwd=cwd,
                        overrides=runtime_overrides(self.settings, restrict_reads=True), cancel=cancel,
                    )
                    account = self._preflight(client, deadline)
                    if prompt is None:
                        return {**account, "provider": "codex_local", "local_only": True,
                                "model": self.settings.codex_local_model,
                                "reasoning_effort": self.settings.codex_local_reasoning_effort,
                                "notice": LOCAL_NOTICE}
                    start = client.request("thread/start", {
                        "model": self.settings.codex_local_model, "modelProvider": "openai",
                        "cwd": cwd, "permissions": TEXT_ONLY_PROFILE,
                        "approvalPolicy": "never", "ephemeral": True,
                        "baseInstructions": "Answer the supplied conversation as text. Tools are disabled.",
                    }, deadline=deadline)
                    thread_id = (start.get("thread") or {}).get("id")
                    if not thread_id or start.get("instructionSources"):
                        raise CodexLocalError("codex_local could not establish an isolated thread")
                    if (start.get("model") != self.settings.codex_local_model
                            or start.get("modelProvider") != "openai"
                            or start.get("reasoningEffort") != self.settings.codex_local_reasoning_effort
                            or start.get("approvalPolicy") != "never"
                            or (start.get("activePermissionProfile") or {}).get("id") != TEXT_ONLY_PROFILE
                            or (start.get("activePermissionProfile") or {}).get("extends")
                            or (start.get("sandbox") or {}).get("type") != "readOnly"
                            or (start.get("thread") or {}).get("ephemeral") is not True):
                        raise CodexLocalError("codex_local thread selection or sandbox could not be verified")
                    turn = client.request("turn/start", {
                        "threadId": thread_id, "input": [{"type": "text", "text": prompt}],
                        "model": self.settings.codex_local_model,
                        "effort": self.settings.codex_local_reasoning_effort,
                        "approvalPolicy": "never",
                        "permissions": TEXT_ONLY_PROFILE,
                    }, deadline=deadline)
                    turn_id = (turn.get("turn") or {}).get("id")
                    if not turn_id:
                        raise CodexLocalError("codex_local did not return a turn identifier")
                    result = self._collect(client, thread_id, turn_id, deadline, text_limits, account)
                    secret = self.settings.codex_local_gate_secret.get_secret_value()
                    if secret in json.dumps(result.__dict__):
                        raise CodexLocalError("codex_local returned protected access material")
                    return result
                finally:
                    if client is not None:
                        if thread_id and turn_id:
                            try:
                                client.send("turn/interrupt", {"threadId": thread_id, "turnId": turn_id})
                            except Exception:
                                pass
                        client.close()
        except CodexLocalError:
            raise
        except Exception:
            # SDK errors can contain prompts/account details; expose only our message.
            raise CodexLocalError("codex_local operation failed") from None

    def _collect(self, client, thread_id, turn_id, deadline, text_limits, account):
        encoding, input_count, maximum = text_limits
        chunks = []
        upper_count = 0
        usage = {}
        output = ""
        truncated = False
        for _ in range(100_000):
            event = client.event(deadline=deadline)
            method = event.get("method", "")
            params = event.get("params") or {}
            if method == "account/updated" and params.get("authMode") != "chatgpt":
                raise CodexLocalError("codex_local authentication changed during generation")
            if method in {"model/rerouted", "error"}:
                raise CodexLocalError("codex_local model changed or generation failed")
            if params.get("threadId") != thread_id:
                continue
            if method == "thread/tokenUsage/updated":
                raw = (params.get("tokenUsage") or {}).get("total") or {}
                if all(type(raw.get(k)) is int and raw[k] >= 0
                       for k in ("inputTokens", "outputTokens", "totalTokens")):
                    usage = {"input_tokens": raw["inputTokens"], "output_tokens": raw["outputTokens"],
                             "total_tokens": raw["totalTokens"]}
            elif method == "item/started":
                if (params.get("item") or {}).get("type") not in {"userMessage", "agentMessage", "reasoning"}:
                    raise CodexLocalError("codex_local attempted a capability outside text generation")
            elif method == "item/agentMessage/delta":
                delta = params.get("delta")
                if not isinstance(delta, str):
                    raise CodexLocalError("codex_local returned invalid text")
                chunks.append(delta)
                # UTF-8 bytes bound the token count, avoiding quadratic tokenization
                # of a long stream when well below the configured text ceiling.
                upper_count += len(delta.encode("utf-8"))
                if upper_count > maximum:
                    output = "".join(chunks)
                    tokens = encoding.encode(output, disallowed_special=())
                    upper_count = len(tokens)
                    if len(tokens) > maximum:
                        output = encoding.decode(tokens[:maximum])
                        # Partial Unicode tokens can change tokenization on decode.
                        while len(encoding.encode(output, disallowed_special=())) > maximum:
                            output = output[:-1]
                        truncated = True
                        break
            elif method == "turn/completed":
                if (params.get("turn") or {}).get("status") != "completed":
                    raise CodexLocalError("codex_local generation did not complete")
                break
        else:
            raise CodexLocalError("codex_local exceeded the event limit")
        if not truncated:
            output = "".join(chunks)
            tokens = encoding.encode(output, disallowed_special=())
            if len(tokens) > maximum:
                output = encoding.decode(tokens[:maximum])
                while len(encoding.encode(output, disallowed_special=())) > maximum:
                    output = output[:-1]
                truncated = True
        if self.settings.codex_local_gate_secret.get_secret_value() in output:
            raise CodexLocalError("codex_local returned protected access material")
        # Never accept structured actions from truncated output.
        prose, actions = (output, []) if truncated else parse_action_block(output)
        while len(encoding.encode(prose, disallowed_special=())) > maximum:
            prose = prose[:-1]
            truncated = True
            actions = []
        provenance = {**account, "provider": "codex_local", "local_only": True,
                      "model": self.settings.codex_local_model,
                      "reasoning_effort": self.settings.codex_local_reasoning_effort,
                      "codex_thread_id": thread_id, "codex_turn_id": turn_id,
                      "usage_available": bool(usage), "usage_final": bool(usage) and not truncated,
                      "output_truncated": truncated, "text_tokenizer": "o200k_base",
                      "supplied_input_tokens": input_count,
                      "returned_output_tokens": len(encoding.encode(prose, disallowed_special=())),
                      "account_usage_capped": False, "notice": LOCAL_NOTICE}
        return ChatResult(text=prose, model=self.settings.codex_local_model,
                          provider_request_id=turn_id, proposed_actions=actions, usage=usage,
                          provenance=provenance)
