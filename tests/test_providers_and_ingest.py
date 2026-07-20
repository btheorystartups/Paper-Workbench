"""Provider registry defaults, Brave adapter cache/fail-soft (no network), SSRF guard."""

import pytest

from workbench.ingest.safe_fetch import UnsafeUrlError, assert_safe_url, parse_html
from workbench.providers.brave import BraveSearchAdapter
from workbench.providers.fakes import FakeChatProvider, FakeSearchProvider
from workbench.providers.llm import parse_action_block
from workbench.providers.registry import get_chat_provider, get_search_provider


def test_registry_defaults_to_fakes(session):
    assert isinstance(get_search_provider(), FakeSearchProvider)
    assert isinstance(get_chat_provider(), FakeChatProvider)


def test_brave_without_key_returns_empty():
    adapter = BraveSearchAdapter("")
    assert adapter.search("anything") == []


def test_brave_parses_and_caches(tmp_path):
    calls = []

    class _Resp:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {
                "web": {
                    "results": [
                        {"url": "https://www.example.com/a", "title": "T", "description": "D"}
                    ]
                }
            }

    class _Session:
        def get(self, url, params=None, timeout=None):
            calls.append(params["q"])
            return _Resp()

    adapter = BraveSearchAdapter(
        "key", session=_Session(), cache_dir=str(tmp_path), sleep=lambda _s: None
    )
    first = adapter.search("cm boolean")
    assert first[0].publisher == "example.com"
    assert first[0].provider_payload["provider"] == "brave"
    adapter.search("cm boolean")  # second call served from cache
    assert calls == ["cm boolean"]


def test_ssrf_guard_blocks_private_and_bad_schemes():
    with pytest.raises(UnsafeUrlError):
        assert_safe_url("file:///etc/passwd")
    with pytest.raises(UnsafeUrlError):
        assert_safe_url("http://127.0.0.1/admin", resolve=False)
    with pytest.raises(UnsafeUrlError):
        assert_safe_url("http://169.254.169.254/latest/meta-data", resolve=False)
    assert assert_safe_url("HTTPS://Example.com:443/p#frag", resolve=False) == (
        "https://example.com/p"
    )


def test_parse_html_extracts_metadata():
    html = (
        "<html><head><title>Fallback</title>"
        '<meta property="og:title" content="Real Title"/>'
        '<meta name="author" content="A. Author"/></head>'
        "<body><script>bad()</script><p>Hello &amp; welcome</p></body></html>"
    )
    parsed = parse_html(html)
    assert parsed.title == "Real Title"
    assert parsed.author == "A. Author"
    assert "Hello & welcome" in parsed.text
    assert "bad()" not in parsed.text


def test_action_block_parsing_is_defensive():
    prose, actions = parse_action_block(
        'Before.\n```wb-actions\n[{"kind": "create_object", "payload": {"kind": "task", '
        '"title": "T"}}]\n```'
    )
    assert prose == "Before."
    assert actions[0]["kind"] == "create_object"

    prose2, actions2 = parse_action_block("Text\n```wb-actions\nnot json\n```")
    assert actions2 == []
    assert prose2 == "Text"

    # entries missing required fields are dropped, valid ones kept
    _, actions3 = parse_action_block(
        '```wb-actions\n[{"kind": "x", "payload": {}}, {"nope": 1}]\n```'
    )
    assert len(actions3) == 1
