"""Pinned local-only sentence embeddings. Never download or select an API at runtime."""

import hashlib
import os
import threading
from functools import lru_cache
from pathlib import Path

REVISION = "1110a243fdf4706b3f48f1d95db1a4f5529b4d41"
REPOSITORY = "sentence-transformers/all-MiniLM-L6-v2"
MODEL = "minilm-l6-v2-1110a243-quint8-window-mean-v1"
FILES = {
    "model.onnx": ("onnx/model_quint8_avx2.onnx",
                   "b941bf19f1f1283680f449fa6a7336bb5600bdcd5f84d10ddc5cd72218a0fd21"),
    "tokenizer.json": ("tokenizer.json",
                       "be50c3628f2bf5bb5e3a7f17b1f74611b2561a3a27eeab05e5aa30f411572037"),
}
MAX_TEXT_CHARS = 4096
SPECS = {
    "minilm": {"repository": REPOSITORY, "revision": REVISION, "files": FILES,
               "model": MODEL, "dimensions": 384, "window": 256},
    "mpnet": {"repository": "sentence-transformers/all-mpnet-base-v2",
              "revision": "e8c3b32edf5434bc2275fc9bab85f82640a19130",
              "model": "mpnet-base-v2-e8c3b32e-quint8-window-mean-v1", "dimensions": 768, "window": 384,
              "files": {
                  "model.onnx": ("onnx/model_quint8_avx2.onnx",
                     "aa5c27172d77bbd1cbae3628cbac4b26d7c12adabff25d2d4285d0f29159b237"),
                  "tokenizer.json": ("tokenizer.json",
                     "b8be2c30ba5dd723a6d5ee26d013da103d5408d92ddcb23747622f9e48f1d842"),
              }},
}


class SemanticUnavailable(ValueError):
    pass


def model_directory():
    return Path(os.environ.get("WB_RESEARCH_SEMANTIC_MODEL_DIR") or
                Path(__file__).resolve().parents[3] / "output" / f"research-semantic-{model_name()}-v1")


def model_name():
    name = os.environ.get("WB_RESEARCH_SEMANTIC_MODEL", "minilm")
    if name not in SPECS:
        raise SemanticUnavailable("Unknown local semantic model selection")
    return name


class LocalResearchEmbeddings:
    model = MODEL
    dimensions = 384

    def __init__(self, directory, name="minilm"):
        try:
            import onnxruntime as ort
            from tokenizers import Tokenizer
        except ImportError as exc:
            raise SemanticUnavailable("Install the research-semantic optional dependencies") from exc
        spec = SPECS[name]
        self.model, self.dimensions = spec["model"], spec["dimensions"]
        for filename, (_, digest) in spec["files"].items():
            path = Path(directory) / filename
            if (not path.is_file() or path.stat().st_size > 160_000_000
                    or hashlib.sha256(path.read_bytes()).hexdigest() != digest):
                raise SemanticUnavailable(
                    "Pinned local model missing or corrupt; run setup_research_semantic.py")
        self._tokenizer = Tokenizer.from_file(str(Path(directory) / "tokenizer.json"))
        self._tokenizer.enable_truncation(max_length=spec["window"], stride=0)
        self._tokenizer.enable_padding(pad_id=0, pad_token="[PAD]")
        options = ort.SessionOptions()
        options.intra_op_num_threads = 2
        options.inter_op_num_threads = 1
        self._session = ort.InferenceSession(str(Path(directory) / "model.onnx"),
                                            sess_options=options, providers=["CPUExecutionProvider"])
        self._lock = threading.Lock()

    def embed(self, texts):
        import numpy as np

        if any(len(text) > MAX_TEXT_CHARS for text in texts):
            raise ValueError("Semantic input exceeds the recorded character bound")
        with self._lock:
            # Include every overflow window; do not silently discard later wordpieces.
            windows, owners = [], []
            for index, text in enumerate(texts):
                encoded = self._tokenizer.encode(text)
                pieces = [encoded, *encoded.overflowing]
                if len(pieces) > 32:
                    raise ValueError("Semantic input exceeds the bounded window count")
                windows.extend(pieces)
                owners.extend([index] * len(pieces))
            sums = np.zeros((len(texts), self.dimensions), dtype=np.float64)
            for start in range(0, len(windows), 16):
                batch = windows[start:start + 16]
                width = max(len(e.ids) for e in batch)
                inputs = {"input_ids": [], "attention_mask": [], "token_type_ids": []}
                for encoded in batch:
                    padding = [0] * (width - len(encoded.ids))
                    inputs["input_ids"].append(encoded.ids + padding)
                    inputs["attention_mask"].append(encoded.attention_mask + padding)
                    inputs["token_type_ids"].append(encoded.type_ids + padding)
                arrays = {key: np.asarray(value, dtype=np.int64) for key, value in inputs.items()}
                hidden = self._session.run(None, {i.name: arrays[i.name]
                                                 for i in self._session.get_inputs()})[0]
                pooled = (hidden * arrays["attention_mask"][..., None]).sum(axis=1)
                for index, vector in enumerate(pooled):
                    sums[owners[start + index]] += vector
            norms = np.linalg.norm(sums, axis=1, keepdims=True)
            vectors = sums / np.maximum(norms, 1e-12)
            if not np.isfinite(vectors).all():
                raise ValueError("Embedding model returned non-finite values")
            return vectors.tolist()


@lru_cache(maxsize=2)
def _load(directory, name):
    return LocalResearchEmbeddings(directory, name)


def get_local_provider():
    return _load(str(model_directory().resolve()), model_name())
