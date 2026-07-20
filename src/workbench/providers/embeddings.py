"""Embedding providers. Fake: deterministic hash-projection vectors (offline). Live:
OpenAI text-embedding-3-small. Similarity is discovery, never evidence."""

import hashlib
import math

DIM_FAKE = 64


class FakeEmbeddingProvider:
    model = "fake-hash-64"

    def embed(self, texts: list[str]) -> list[list[float]]:
        out = []
        for text in texts:
            vec = [0.0] * DIM_FAKE
            # character-trigram hashing → stable, cheap, similarity-ish for tests
            padded = f"  {text.lower()}  "
            for i in range(len(padded) - 2):
                tri = padded[i : i + 3]
                h = int(hashlib.md5(tri.encode()).hexdigest()[:8], 16)
                vec[h % DIM_FAKE] += 1.0
            norm = math.sqrt(sum(v * v for v in vec)) or 1.0
            out.append([v / norm for v in vec])
        return out


class OpenAIEmbeddingProvider:
    model = "text-embedding-3-small"

    def __init__(self, api_key: str, *, client=None) -> None:
        self._api_key = api_key
        self._client = client

    def embed(self, texts: list[str]) -> list[list[float]]:
        if self._client is None:
            from openai import OpenAI

            self._client = OpenAI(api_key=self._api_key)
        response = self._client.embeddings.create(model=self.model, input=texts)
        return [item.embedding for item in response.data]


def get_embedding_provider():
    from ..config import openai_api_key
    from .registry import provider_mode

    if provider_mode() == "live" and openai_api_key():
        return OpenAIEmbeddingProvider(openai_api_key())
    return FakeEmbeddingProvider()


def cosine(a: list[float], b: list[float]) -> float:
    if len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(x * x for x in b)) or 1.0
    return dot / (na * nb)
