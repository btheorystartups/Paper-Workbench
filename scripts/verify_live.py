"""One-shot live-provider verification (run manually; makes 1 Brave + 1 OpenAI call).

Run: python scripts/verify_live.py
"""

import sys

sys.path.insert(0, "src")

from workbench.config import get_settings  # noqa: E402
from workbench.providers.registry import (  # noqa: E402
    chat_model_name,
    get_chat_provider,
    get_search_provider,
)


def main() -> None:
    settings = get_settings()
    print(f"provider_mode={settings.provider_mode}  model={chat_model_name()}")

    search = get_search_provider()
    print(f"search provider: {type(search).__name__}")
    hits = search.search("correspondence matrix boolean logic", filters={"count": 3})
    for h in hits:
        print(f"  [{h.rank}] {h.title[:70]}  ({h.publisher})")
    if not hits:
        print("  !! no results — check Brave key")

    chat = get_chat_provider()
    print(f"chat provider: {type(chat).__name__}")
    result = chat.chat(
        system="You are a research assistant. Reply in one short sentence.",
        messages=[{"role": "user", "content": "Say 'live connection verified' and nothing else."}],
        model=chat_model_name(),
        max_output_tokens=200,
    )
    print(f"  model={result.model} request_id={result.provider_request_id}")
    print(f"  reply: {result.text.strip()[:200]}")
    print(f"  usage: {result.usage}")


if __name__ == "__main__":
    main()
