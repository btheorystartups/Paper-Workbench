"""A fast worker must survive a bounded, temporarily slower event consumer."""

import sys
import time

import pytest

from workbench.providers.research_executor import AgentProcess


@pytest.fixture()
def burst_worker(tmp_path):
    script = tmp_path / "burst_worker.py"
    script.write_text(
        "import json, sys\n"
        "for sequence in range(300):\n"
        "    print(json.dumps({'agent_id': 'burst', 'type': 'progress', "
        "'sequence': sequence}), flush=True)\n"
        "print(json.dumps({'agent_id': 'burst', 'type': 'report'}), flush=True)\n"
        "sys.stdin.readline()\n",
        encoding="utf-8",
    )
    handle = AgentProcess([sys.executable, str(script)], "burst", {})
    try:
        deadline = time.monotonic() + 10
        while handle.events.qsize() < 100 and time.monotonic() < deadline:
            time.sleep(0.01)
        assert handle.events.qsize() == 100
        yield handle
    finally:
        handle.close()


def test_burst_preserves_order_and_terminal_report(burst_worker):
    events = []
    deadline = time.monotonic() + 10
    while len(events) < 301 and time.monotonic() < deadline:
        event = burst_worker.poll()
        if event is None:
            time.sleep(0.01)
        else:
            events.append(event)
    assert [event.get("sequence") for event in events[:-1]] == list(range(300))
    assert events[-1]["type"] == "report"
    assert not burst_worker.closed.is_set()


def test_cancel_while_event_queue_is_full_stops_reader(burst_worker):
    burst_worker.close()
    assert not burst_worker.reader.is_alive()
    assert burst_worker.process.poll() is not None
