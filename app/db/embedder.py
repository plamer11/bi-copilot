
from __future__ import annotations

import hashlib
import logging
import math
import re
from typing import Protocol

from app.config import settings

logger = logging.getLogger(__name__)


class Embedder(Protocol):


    dim: int

    def embed(self, texts: list[str]) -> list[list[float]]:
        ...


def cosine(a: list[float], b: list[float]) -> float:

    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


def _l2(vec: list[float]) -> list[float]:
    n = math.sqrt(sum(x * x for x in vec))
    return [x / n for x in vec] if n else vec


class HashEmbedder:


    dim = 512

    def __init__(self, ngram: int = 2):
        self.ngram = ngram

    def _grams(self, text: str) -> list[str]:
        t = re.sub(r"\s+", "", (text or "").lower())
        if len(t) < self.ngram:
            return [t] if t else []
        return [t[i:i + self.ngram] for i in range(len(t) - self.ngram + 1)]

    def embed(self, texts: list[str]) -> list[list[float]]:
        out = []
        for text in texts:
            vec = [0.0] * self.dim
            for g in self._grams(text):

                idx = int(hashlib.md5(g.encode("utf-8")).hexdigest()[:4], 16) % self.dim
                vec[idx] += 1.0
            out.append(_l2(vec))
        return out


class LocalEmbedder:


    def __init__(self, model_name: str | None = None):
        self.model_name = model_name or settings.embedding_model
        self._model = None
        self.dim = 0

    def _load(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self.model_name)
            self.dim = int(self._model.get_sentence_embedding_dimension())
        return self._model

    def embed(self, texts: list[str]) -> list[list[float]]:
        model = self._load()
        vecs = model.encode(list(texts), normalize_embeddings=True)
        return [list(map(float, v)) for v in vecs]


class ApiEmbedder:


    def __init__(self, base_url: str = "", api_key: str = "", model: str = ""):
        self.base_url = base_url or settings.embedding_base_url
        self.api_key = api_key or settings.embedding_api_key
        self.model = model or settings.embedding_model
        self.dim = 0
        self._client = None

    def _load(self):
        if self._client is None:
            if not (self.base_url and self.api_key):
                raise RuntimeError("未配置 EMBEDDING_BASE_URL / EMBEDDING_API_KEY")
            from langchain_openai import OpenAIEmbeddings

            self._client = OpenAIEmbeddings(
                model=self.model, base_url=self.base_url, api_key=self.api_key
            )
        return self._client

    def embed(self, texts: list[str]) -> list[list[float]]:
        client = self._load()
        vecs = client.embed_documents(list(texts))
        self.dim = len(vecs[0]) if vecs else 0
        return [_l2(list(map(float, v))) for v in vecs]


def _usable(embedder) -> bool:

    try:
        vecs = embedder.embed(["连通性测试"])
        return bool(vecs) and bool(vecs[0]) and any(v != 0.0 for v in vecs[0])
    except Exception as e:
        logger.info("embedding 后端不可用，已跳过: %s", e)
        return False


_EMBEDDER = None
_EMBEDDER_PROBED = False


def resolve_embedder():

    global _EMBEDDER, _EMBEDDER_PROBED
    if not _EMBEDDER_PROBED:
        _EMBEDDER = get_embedder()
        _EMBEDDER_PROBED = True
    return _EMBEDDER


def reset_embedder_cache() -> None:

    global _EMBEDDER, _EMBEDDER_PROBED
    _EMBEDDER = None
    _EMBEDDER_PROBED = False


def get_embedder():

    if not settings.use_embedding_retrieval:
        return None

    provider = (settings.embedding_provider or "auto").lower()
    candidates: dict[str, list] = {
        "local": [lambda: LocalEmbedder()],
        "api": [lambda: ApiEmbedder()],
        "hash": [lambda: HashEmbedder()],
    }
    order = candidates.get(provider) or (
        candidates["local"] + candidates["api"] + candidates["hash"]
    )

    for factory in order:
        try:
            emb = factory()
        except Exception as e:
            logger.info("embedding 后端初始化失败: %s", e)
            continue
        if _usable(emb):
            return emb
    return None
