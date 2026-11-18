
from __future__ import annotations

import json

import pytest

from app.eval.ci_gate import MAX_DIFFICULTY_DROP, MAX_NEW_FAILURES, check

BASELINE = {
    "accuracy": 0.875,
    "by_difficulty": {"easy": 1.0, "medium": 1.0, "hard": 0.5},
    "failed_ids": [31, 32, 36, 37, 40],
}


def _result(acc: float, failed: list[int], by_difficulty: dict | None = None) -> dict:
    return {"accuracy": acc, "failed_ids": failed, "passed_ids": [],
            "by_difficulty": by_difficulty or {}, "schema_recall": 0.8}


def test_identical_to_baseline_passes():
    ok, _ = check(_result(0.875, [31, 32, 36, 37, 40]), BASELINE)
    assert ok is True


def test_one_or_two_new_failures_are_treated_as_noise():

    ok, lines = check(_result(0.85, [31, 32, 33, 36, 37, 40]), BASELINE)
    assert ok, f"容差是 {MAX_NEW_FAILURES} 条，新增 1 条应当放行"
    assert any("视为噪声" in ln for ln in lines)


def test_more_new_failures_than_tolerance_fails():
    ok, lines = check(_result(0.70, [1, 2, 3, 4, 31, 32, 36, 37, 40]), BASELINE)
    assert ok is False
    assert any("新增失败" in ln and "超过容差" in ln for ln in lines)


def test_difficulty_bucket_drop_is_caught_even_within_case_tolerance():

    ok, lines = check(
        _result(0.825, [1, 2, 31, 32, 36, 37, 40],
                {"easy": 0.833, "medium": 1.0, "hard": 0.5}),
        BASELINE,
    )
    assert ok is False
    assert any("easy" in ln and "下降" in ln for ln in lines)


def test_difficulty_bucket_within_tolerance_passes():
    ok, _ = check(
        _result(0.85, [33, 31, 32, 36, 37, 40],
                {"easy": 1.0, "medium": 0.944, "hard": 0.5}),
        BASELINE,
    )
    assert ok, f"分档容差 {MAX_DIFFICULTY_DROP:.0%}，medium 掉 5.6% 应当放行"


def test_known_failures_still_failing_is_not_regression():
    ok, lines = check(_result(0.875, [31, 32, 36, 37, 40]), BASELINE)
    assert ok
    assert any("已知短板" in ln for ln in lines)


def test_improvement_passes_and_is_reported():
    ok, lines = check(_result(0.925, [36, 37, 40]), BASELINE)
    assert ok
    assert any("修好了" in ln for ln in lines)


def test_accuracy_up_while_many_new_cases_fail_still_fails():

    ok, lines = check(_result(0.90, [7, 8, 9, 31]), BASELINE)
    assert ok is False
    assert any("新增失败" in ln for ln in lines)


def test_missing_fields_do_not_crash():
    ok, lines = check({}, {})
    assert isinstance(ok, bool) and lines


def test_update_baseline_writes_file(tmp_path, monkeypatch):
    from app.eval import ci_gate

    result = tmp_path / "res.json"
    result.write_text(json.dumps({
        "accuracy": 0.9, "schema_recall": 0.85,
        "by_difficulty": {"easy": 1.0}, "failed_ids": [31],
        "model": "deepseek-chat", "generated_at": "2026-10-08T23:00:00",
    }), encoding="utf-8")

    baseline = tmp_path / "baseline.json"
    monkeypatch.setattr(ci_gate, "BASELINE", baseline)
    ci_gate.update_baseline(result)

    saved = json.loads(baseline.read_text(encoding="utf-8"))
    assert saved["accuracy"] == 0.9 and saved["failed_ids"] == [31]
