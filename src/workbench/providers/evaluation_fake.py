"""Scripted offline transport for testing the evaluation adapter, never a model simulation.

One UTF-8 byte is one synthetic token unit. Costs are synthetic integer units.
There is no SDK, registry lookup, environment access, executable fixture or network.
"""

import json


def _encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


class ScriptedEvaluationProvider:
    def __init__(self, frames: list[dict]):
        self._frames = json.loads(_encoded(frames))
        self._requests = []

    @property
    def requests(self) -> list[dict]:
        return json.loads(_encoded(self._requests))

    def exchange(self, request: dict) -> dict:
        index = len(self._requests)
        self._requests.append(json.loads(_encoded(request)))
        if index >= len(self._frames):
            raise RuntimeError("synthetic fixture exhausted")
        frame = self._frames[index]
        if frame.get("fault") == "timeout":
            raise TimeoutError("synthetic uncertain dispatch")
        if frame.get("fault") == "interrupt":
            raise KeyboardInterrupt("synthetic interruption")
        if frame.get("fault"):
            raise RuntimeError("synthetic transport error")
        payload = frame.get("response", {})
        inp, out = len(_encoded(request)), len(_encoded(payload))
        usage = {
            "input_tokens": inp,
            "output_tokens": out,
            "cost_units": inp * request["input_rate"] + out * request["output_rate"],
        }
        if "usage_override" in frame:
            usage = frame["usage_override"]
        return {
            "provider": "scripted_fake",
            "model": "fake-byte-tokenizer-v1",
            "request_id": request["attempt_id"],
            "payload": payload,
            "usage": usage,
        }
