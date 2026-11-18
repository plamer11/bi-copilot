
from __future__ import annotations

import pytest

from app.graph.nodes import AnalystOutput, RewriteOutput, SupervisorDecision


class FakeLLM:


    def __init__(self, result):
        self.result = result

    def invoke(self, messages=None, **kwargs):
        return self.result


class EchoRewriter:


    def invoke(self, messages=None, **kwargs):
        content = (messages[0].content if messages else "") or ""
        tail = content.split("## 本轮用户说的")[-1]
        question = next((ln.strip() for ln in tail.splitlines() if ln.strip()), "")
        return RewriteOutput(is_followup=False, standalone_question=question, reason="echo")


@pytest.fixture
def fake_structured(monkeypatch):


    def _factory(schema=None, temperature: float = 0.0, **kwargs):
        if schema is SupervisorDecision:
            return FakeLLM(SupervisorDecision(decision="query", reason="stub"))
        if schema is AnalystOutput:
            return FakeLLM(AnalystOutput(answer="（打桩结论）", chart_type="bar"))
        if schema is RewriteOutput:
            return EchoRewriter()
        return FakeLLM(None)

    monkeypatch.setattr("app.graph.nodes.get_structured_llm", _factory)
    return _factory


@pytest.fixture
def structured_map(monkeypatch):

    mapping: dict = {}

    def _factory(schema=None, temperature: float = 0.0, **kwargs):
        if schema in mapping:
            return FakeLLM(mapping[schema])
        if schema is RewriteOutput:
            return EchoRewriter()
        return FakeLLM(None)

    monkeypatch.setattr("app.graph.nodes.get_structured_llm", _factory)
    return mapping


@pytest.fixture
def fake_text(monkeypatch):


    def _install(responses: list[str]):
        it = iter(responses)

        def _fake(prompt: str) -> str:
            try:
                return next(it)
            except StopIteration:
                raise AssertionError("LLM 打桩调用次数超出预期，检查测试里的 responses 列表")

        monkeypatch.setattr("app.graph.nodes._llm_text", _fake)
        return _fake

    return _install
