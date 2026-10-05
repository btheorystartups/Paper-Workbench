"""Pinned runtime + loopback fake Responses: no credentials or model inference."""

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.metadata import version
from types import SimpleNamespace

import pytest

from workbench.manuscript_length import TOOL_NAME, tool_spec
from workbench.providers.codex_access import CodexLocalError
from workbench.providers.codex_local import runtime_overrides
from workbench.providers.codex_rpc import RUNTIME_VERSION, StdioCodexClient
from workbench.providers.research_codex_worker import CodexResearchWorker

FINAL_SCHEMA = {
    "type": "object",
    "properties": {"ok": {"type": "boolean"}},
    "required": ["ok"],
    "additionalProperties": False,
}


def tool_inventory(tools):
    return [
        {
            "name": t.get("name"),
            "type": t.get("type"),
            "counter_in_description": TOOL_NAME in t.get("description", ""),
            "nested": tool_inventory(t.get("tools", [])),
        }
        for t in tools
    ]


def flatten_inventory(rows):
    return [r for row in rows for r in [row, *flatten_inventory(row["nested"])]]


@pytest.fixture
def runtime_probe(tmp_path):
    pytest.importorskip("codex_cli_bin")
    assert version("openai-codex-cli-bin") == RUNTIME_VERSION
    captures = []
    mode = {"reply": "final"}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            assert self.path == "/v1/responses"
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            additional = [
                t
                for item in body.get("input", [])
                if item.get("type") == "additional_tools"
                for t in item["tools"]
            ]
            captures.append(
                {
                    "inventory": tool_inventory([*(body.get("tools") or []), *additional]),
                    "format": body.get("text", {}).get("format"),
                    "tool_outputs": [
                        item
                        for item in body.get("input", [])
                        if item.get("type") in {"function_call_output", "custom_tool_call_output"}
                    ],
                }
            )
            item = {
                "id": "msg_fake",
                "type": "message",
                "role": "assistant",
                "status": "completed",
                "content": [{"type": "output_text", "text": '{"ok":true}', "annotations": []}],
            }
            delta_type = "response.output_text.delta"
            delta = '{"ok":true}'
            if len(captures) == 1 and mode["reply"] == "counter":
                delta_type = "response.function_call_arguments.delta"
                delta = json.dumps({"sections": [{"id": "sec", "text": "one two three"}]})
                item = {
                    "id": "fc_fake",
                    "type": "function_call",
                    "call_id": "call_fake",
                    "name": TOOL_NAME,
                    "arguments": delta,
                }
            response = {
                "id": "resp_fake",
                "object": "response",
                "created_at": 0,
                "status": "completed",
                "output": [item],
                "usage": {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2},
            }
            events = [
                ("response.created", {"response": {**response, "status": "in_progress", "output": []}}),
                (
                    "response.output_item.added",
                    {"output_index": 0, "item": {**item, "status": "in_progress"}},
                ),
                (delta_type, {"item_id": item["id"], "output_index": 0, "content_index": 0, "delta": delta}),
                ("response.output_item.done", {"output_index": 0, "item": item}),
                ("response.completed", {"response": response}),
            ]
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            try:
                for kind, data in events:
                    self.wfile.write(
                        ("event: " + kind + "\ndata: " + json.dumps({"type": kind, **data}) + "\n\n").encode()
                    )
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    def probe(*, model, schema_on, reply="final", deferred=None, boolean_override=False):
        mode["reply"] = reply
        captures.clear()
        profile = tmp_path / "profile"
        profile.mkdir(exist_ok=True)
        settings = SimpleNamespace(
            codex_local_model=model, codex_local_reasoning_effort="low", codex_local_workspace_id=None
        )
        overrides = runtime_overrides(settings)
        # Only this synthetic fixture uses an unauthenticated custom loopback provider.
        # Production preflight still rejects custom endpoints and model catalogs.
        overrides.pop("forced_login_method")
        if boolean_override:
            overrides.pop("features.code_mode.enabled")
            overrides["features.code_mode"] = False
        overrides.update(
            {
                "model_provider": "offline_counter_probe",
                "model_providers.offline_counter_probe.name": "Offline counter probe",
                "model_providers.offline_counter_probe.base_url": f"http://127.0.0.1:{server.server_port}/v1",
                "model_providers.offline_counter_probe.wire_api": "responses",
                "model_providers.offline_counter_probe.requires_openai_auth": False,
                "model_providers.offline_counter_probe.request_max_retries": 0,
                "model_providers.offline_counter_probe.stream_max_retries": 0,
                "model_providers.offline_counter_probe.supports_websockets": False,
            }
        )
        worker = object.__new__(CodexResearchWorker)
        worker.length_tool_active = None
        worker.length_tool_receipts, worker.length_tool_events, worker.length_tool_call_ids = [], [], set()
        callbacks = []

        def callback(request):
            callbacks.append(request)
            return worker.handle_length_tool_request(request)

        client = StdioCodexClient(
            profile=str(profile),
            cwd=str(tmp_path),
            overrides=overrides,
            cancel=threading.Event(),
            server_request_handler=callback,
        )
        deadline = time.monotonic() + 15
        events = []
        try:
            client.request(
                "initialize",
                {
                    "clientInfo": {"name": "offline_counter_probe", "version": "1"},
                    "capabilities": {"experimentalApi": True},
                },
                deadline=deadline,
            )
            client.notify("initialized")
            spec = tool_spec()
            if deferred is None:
                spec.pop("deferLoading", None)  # Exercise the legacy omitted-field descriptor too.
            if deferred is not None:
                spec["deferLoading"] = deferred
            selection = client.request(
                "thread/start",
                {
                    "model": model,
                    "modelProvider": "offline_counter_probe",
                    "cwd": str(tmp_path),
                    "ephemeral": True,
                    "approvalPolicy": "never",
                    "sandbox": "read-only",
                    "dynamicTools": [spec],
                },
                deadline=deadline,
            )
            params = {
                "threadId": selection["thread"]["id"],
                "model": model,
                "effort": "low",
                "input": [{"type": "text", "text": "Synthetic counter probe. Return the requested JSON."}],
                "approvalPolicy": "never",
                "sandboxPolicy": {"type": "readOnly", "networkAccess": False},
            }
            if schema_on:
                params["outputSchema"] = FINAL_SCHEMA
            turn = client.request("turn/start", params, deadline=deadline)
            worker.length_tool_active = {
                "thread_id": selection["thread"]["id"],
                "turn_id": turn["turn"]["id"],
                "bounds": {"min_words": 3, "max_words": 5},
            }
            while time.monotonic() < deadline:
                event = client.event(deadline=deadline)
                events.append(event)
                if event.get("method") == "turn/completed":
                    assert event["params"]["turn"]["status"] == "completed"
                    break
            else:
                pytest.fail("Synthetic turn did not finish")
            return {
                "captures": list(captures),
                "events": events,
                "callbacks": callbacks,
                "receipts": worker.length_tool_receipts,
            }
        finally:
            client.close()
            assert client._proc.poll() is not None

    yield probe
    server.shutdown()
    server.server_close()
    server_thread.join(timeout=2)
    assert not server_thread.is_alive()


@pytest.mark.parametrize("schema_on", [False, True])
@pytest.mark.parametrize("deferred", [None, False])
def test_pinned_sol_exposes_counter_only_inside_unavailable_code_mode(runtime_probe, schema_on, deferred):
    result = runtime_probe(model="gpt-5.6-sol", schema_on=schema_on, deferred=deferred)
    inventory = flatten_inventory(result["captures"][0]["inventory"])
    assert not any(t["name"] == TOOL_NAME for t in inventory)
    assert any(t["name"] == "exec" and t["counter_in_description"] for t in inventory)
    warnings = [e["params"].get("message", "") for e in result["events"] if e.get("method") == "warning"]
    assert any("Code Mode is unavailable because code-mode host is disabled" in w for w in warnings)
    assert bool(result["captures"][0]["format"]) is schema_on
    assert not result["callbacks"]


@pytest.mark.parametrize("schema_on", [False, True])
def test_classic_model_direct_counter_roundtrip_keeps_final_schema(runtime_probe, schema_on):
    result = runtime_probe(model="gpt-5.5", schema_on=schema_on, reply="counter")
    assert len(result["captures"]) == 2
    for request in result["captures"]:
        assert any(t["name"] == TOOL_NAME for t in flatten_inventory(request["inventory"]))
        if schema_on:
            assert request["format"]["schema"] == FINAL_SCHEMA
        else:
            assert request["format"] is None
    assert len(result["callbacks"]) == len(result["receipts"]) == 1
    assert result["callbacks"][0]["params"]["namespace"] is None
    assert result["receipts"][0]["word_count"] == 3
    output = result["captures"][1]["tool_outputs"][0]["output"]
    assert json.loads(output)["word_count"] == 3
    assert any(e.get("params", {}).get("item", {}).get("type") == "dynamicToolCall" for e in result["events"])
    final = [
        e["params"]["item"]["text"]
        for e in result["events"]
        if e.get("method") == "item/completed" and e["params"].get("item", {}).get("type") == "agentMessage"
    ]
    assert json.loads(final[-1]) == {"ok": True}


def test_boolean_feature_override_does_not_override_sol_tool_mode(runtime_probe):
    result = runtime_probe(model="gpt-5.6-sol", schema_on=True, boolean_override=True)
    inventory = flatten_inventory(result["captures"][0]["inventory"])
    assert not any(t["name"] == TOOL_NAME for t in inventory)
    assert any(t["name"] == "exec" for t in inventory)


def test_explicit_deferred_counter_is_rejected_with_search_disabled(runtime_probe):
    with pytest.raises(CodexLocalError, match="rejected the requested operation"):
        runtime_probe(model="gpt-5.6-sol", schema_on=True, deferred=True)
