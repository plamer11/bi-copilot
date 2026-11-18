
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]
BASELINE = BACKEND_ROOT / "eval" / "baseline.json"
DEFAULT_RESULT = BACKEND_ROOT / "data" / "eval_result.json"


MAX_NEW_FAILURES = 2

MAX_DIFFICULTY_DROP = 0.10


def _load(path: Path) -> dict:
    if not path.exists():
        print(f"[ci-gate] 找不到文件: {path}", file=sys.stderr)
        sys.exit(2)
    return json.loads(path.read_text(encoding="utf-8"))


def check(result: dict, baseline: dict) -> tuple[bool, list[str]]:

    problems: list[str] = []
    notes: list[str] = []

    acc = float(result.get("accuracy", 0))
    base_acc = float(baseline.get("accuracy", 0))
    drop = base_acc - acc

    notes.append(f"准确率 {acc:.1%}（基线 {base_acc:.1%}，{'↑提升' if drop < 0 else '↓下降'} {abs(drop):.1%}）")


    base_failed = set(baseline.get("failed_ids", []))
    now_failed = set(result.get("failed_ids", []))
    regressions = sorted(now_failed - base_failed)
    if len(regressions) > MAX_NEW_FAILURES:
        problems.append(
            f"新增失败 {len(regressions)} 条 {regressions}，超过容差 {MAX_NEW_FAILURES} 条"
        )
    elif regressions:
        notes.append(f"新增失败 {regressions}（{MAX_NEW_FAILURES} 条以内，视为噪声）")


    base_by_d = baseline.get("by_difficulty", {}) or {}
    now_by_d = result.get("by_difficulty", {}) or {}
    for d, base_score in base_by_d.items():
        cur = now_by_d.get(d)
        if cur is None:
            continue
        if base_score - cur > MAX_DIFFICULTY_DROP:
            problems.append(
                f"{d} 档准确率 {cur:.1%} 较基线 {base_score:.1%} 下降超过 "
                f"{MAX_DIFFICULTY_DROP:.0%}"
            )

    fixed = sorted(base_failed - now_failed)
    if fixed:
        notes.append(f"较基线修好了 {fixed}")

    still = sorted(base_failed & now_failed)
    if still:
        notes.append(f"已知短板仍未通过 {still}（不算回归）")

    passed = not problems
    return passed, [f"  · {n}" for n in notes] + [f"  ✗ {p}" for p in problems]


def update_baseline(result_path: Path) -> None:
    result = _load(result_path)
    payload = {
        "_comment": "CI 回归基线。改 prompt / 检索 / 守卫之后，如果评测结果确实变好了，用 "
                    "`python -m app.eval.ci_gate --update-baseline` 更新这里，并把变化写进 PR 描述。",
        "source": result.get("source", "人工标注集 40 条"),
        "model": result.get("model", ""),
        "recorded_at": result.get("generated_at", "")[:10],
        "accuracy": result.get("accuracy", 0),
        "schema_recall": result.get("schema_recall", 0),
        "by_difficulty": result.get("by_difficulty", {}),
        "failed_ids": result.get("failed_ids", []),
    }
    BASELINE.parent.mkdir(parents=True, exist_ok=True)
    BASELINE.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")
    print(f"[ci-gate] 基线已更新: {BASELINE}")
    print(f"[ci-gate] 准确率 {payload['accuracy']:.1%}，失败用例 {payload['failed_ids']}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--result", default=str(DEFAULT_RESULT), help="评测结果 JSON")
    ap.add_argument("--baseline", default=str(BASELINE), help="基线 JSON")
    ap.add_argument("--update-baseline", action="store_true", help="用本次结果覆盖基线")
    args = ap.parse_args()

    if args.update_baseline:
        update_baseline(Path(args.result))
        return 0

    result = _load(Path(args.result))
    baseline = _load(Path(args.baseline))

    print("[ci-gate] 回归检查")
    ok, lines = check(result, baseline)
    for ln in lines:
        print(ln)

    if ok:
        print("[ci-gate] PASS：未发现回归")
        return 0
    print("[ci-gate] FAIL：存在回归，禁止合入", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
