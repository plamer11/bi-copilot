
from __future__ import annotations

import sys
from functools import lru_cache
from typing import Any

from langchain_openai import ChatOpenAI

from app.config import settings


class _BlockTransformers:


    def find_spec(self, name: str, path=None, target=None):
        if name == "transformers" or name.startswith("transformers."):
            raise ImportError("transformers disabled for faster startup")
        return None


if not any(isinstance(f, _BlockTransformers) for f in sys.meta_path):
    sys.meta_path.insert(0, _BlockTransformers())


@lru_cache(maxsize=None)
def get_llm(temperature: float = 0.0) -> ChatOpenAI:

    if not settings.api_key:
        raise RuntimeError(
            "未配置 DEEPSEEK_API_KEY，请在 backend/.env 中填写后再启动服务"
        )
    return ChatOpenAI(
        model=settings.llm_model,
        api_key=settings.api_key,
        base_url=settings.llm_base_url,
        temperature=temperature,
        timeout=settings.llm_timeout,
        max_retries=settings.llm_max_retries,
    )


def get_structured_llm(schema: Any, temperature: float = 0.0):

    return get_llm(temperature).with_structured_output(schema, method="function_calling")
