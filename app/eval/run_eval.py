
from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime
from pathlib import Path

from app.config import settings
from app.db.schema_retriever import build_context, schema_recall
from app.eval.golden_set import GOLDEN
from app.graph.build import aclose_graph, aget_graph, new_thread_config
from app.tools.sqlite_tool import run_sql

CONCURRENCY = 5
BACKEND_ROOT = Path(__file__).resolve().parents[2]
REPORT = BACKEND_ROOT / "data" / "eval_report.md"
RESULT_JSON = BACKEND_ROOT / "data" / "eval_result.json"
GOLD_SQL_BY_ID = {g["id"]: g["sql"] for g in GOLDEN}


def _canon(res) -> list[tuple] | None:

    if not res.ok:
        return None
    out = []
    for row in res.rows:
        cells = []
        for v in row:
            if isinstance(v, float):
                cells.append(round(v, 2))
            elif isinstance(v, int) and not isinstance(v, bool):
                cells.append(v)
            else:
                cells.append(str(v))
        out.append(tuple(cells))
    return sorted(out, key=lambda r: str(r))


async def run_case(graph, case: dict, idx: int) -> dict:
    tid = f"eval-{case['id']}"
    cfg = new_thread_config(tid)
    question = case["question"]

    ctx = build_context(question)
    recall = schema_recall(case["sql"], ctx)

    gold_res = run_sql(case["sql"])
    gold_canon = _canon(gold_res)

    try:


        out = await graph.ainvoke(
            {"session_id": tid, "question": question, "history": []}, cfg
        )
    except Exception as e:
        return {"id": case["id"], "question": question, "difficulty": case["difficulty"],
                "ok": False, "pred_sql": "", "error": f"图执行异常: {e}", "schema_recall": recall,
                "repairs": 0}

    pred_sql = out.get("guard_sql") or out.get("sql", "")
    pred_res = run_sql(pred_sql) if pred_sql else None
    pred_canon = _canon(pred_res) if pred_res else None

    attempts = out.get("attempts", [])
    return {
        "id": case["id"],
        "question": question,
        "difficulty": case["difficulty"],
        "ok": bool(pred_canon is not None and gold_canon is not None and pred_canon == gold_canon),
        "pred_sql": pred_sql,
        "error": "" if (pred_res and pred_res.ok) else (pred_res.error if pred_res else "未生成 SQL"),
        "gold_error": "" if gold_res.ok else gold_res.error,
        "schema_recall": recall,
        "repairs": max(0, len(attempts) - 1),
        "guarded": out.get("guard_level", ""),
    }


async def run_all(cases: list[dict]) -> list[dict]:
    graph = await aget_graph()
    sem = asyncio.Semaphore(CONCURRENCY)

    async def wrapped(case, i):
        async with sem:
            r = await run_case(graph, case, i)
            flag = "OK  " if r["ok"] else "FAIL"
            print(f"  [{flag}] #{r['id']:<3} {r['difficulty']:<7} {r['question'][:38]:<40}", flush=True)
            return r

    try:
        return list(await asyncio.gather(*(wrapped(c, i) for i, c in enumerate(cases, 1))))
    finally:
        await aclose_graph()


def summarize(results: list[dict]) -> dict:

    total = len(results) or 1
    correct = [r["id"] for r in results if r["ok"]]
    by_difficulty = {}
    for d in ("easy", "medium", "hard"):
        sub = [r for r in results if r["difficulty"] == d]
        if sub:
            by_difficulty[d] = round(sum(1 for r in sub if r["ok"]) / len(sub), 4)
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "model": settings.llm_model,
        "total": len(results),
        "correct": len(correct),
        "accuracy": round(len(correct) / total, 4),
        "schema_recall": round(sum(r["schema_recall"] for r in results) / total, 4),
        "by_difficulty": by_difficulty,
        "passed_ids": sorted(correct),
        "failed_ids": sorted(r["id"] for r in results if not r["ok"]),
    }


def build_report(results: list[dict]) -> str:
    total = len(results)
    correct = sum(1 for r in results if r["ok"])
    acc = correct / total if total else 0

    lines = [
        "# BI Copilot 评测报告",
        "",
        f"- 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"- 模型：{settings.llm_model}",
        f"- 标注集：{total} 条（easy/medium/hard 分层）",
        "",
        "## 总体指标",
        "",
        "| 指标 | 数值 | 说明 |",
        "|---|---|---|",
        f"| Execution Accuracy | **{acc:.1%}** | 执行结果与 gold 完全一致 |",
        f"| Schema Recall | **{sum(r['schema_recall'] for r in results) / total:.1%}** | gold 用到的列被召回了多少 |",
        f"| 触发自愈的用例 | {sum(1 for r in results if r['repairs'] > 0)} | 首轮 SQL 执行失败后重试 |",
        f"| 修复后成功 | {sum(1 for r in results if r['repairs'] > 0 and r['ok'])} | 自愈环的实际贡献 |",
        "",
        "## 分层准确率",
        "",
        "| 难度 | 用例数 | 正确 | 准确率 |",
        "|---|---|---|---|",
    ]
    for d in ("easy", "medium", "hard"):
        sub = [r for r in results if r["difficulty"] == d]
        if not sub:
            continue
        c = sum(1 for r in sub if r["ok"])
        lines.append(f"| {d} | {len(sub)} | {c} | {c / len(sub):.1%} |")

    failed = [r for r in results if not r["ok"]]
    if failed:
        lines += ["", "## 失败案例归因", "", "| ID | 难度 | 问题 | schema召回 | 报错 |", "|---|---|---|---|---|"]
        for r in failed:
            err = (r.get("error") or "")[:60].replace("|", "/")
            lines.append(f"| {r['id']} | {r['difficulty']} | {r['question'][:30]} | "
                         f"{r['schema_recall']:.0%} | {err} |")
    return "\n".join(lines)


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="只跑前 N 条")
    ap.add_argument("--ids", type=str, default="", help="只跑指定 id，逗号分隔")
    ap.add_argument("--verbose", action="store_true", help="打印每条的模型 SQL 与 gold 结果差异")
    ap.add_argument("--json", dest="json_path", default=str(RESULT_JSON),
                    help="机器可读结果的落盘路径（CI 门禁读这个）")
    args = ap.parse_args()

    cases = GOLDEN
    if args.ids:
        wanted = {int(x) for x in args.ids.split(",") if x.strip()}
        cases = [c for c in GOLDEN if c["id"] in wanted]
    elif args.limit:
        cases = GOLDEN[: args.limit]

    settings.enable_hitl = False
    print(f"开始评测 {len(cases)} 条（并发 {CONCURRENCY}，HITL 已关闭）...\n")

    results = await run_all(cases)
    if args.verbose:
        for r in results:
            if r["ok"]:
                continue
            print(f"\n--- #{r['id']} [{r['difficulty']}] {r['question']}")
            print(f"  gold  : {' '.join(GOLD_SQL_BY_ID[r['id']].split())}")
            print(f"  model : {' '.join((r['pred_sql'] or '(空)').split())}")
            print(f"  报错  : {r['error'] or '无（结果不一致）'}")
    report = build_report(results)
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(report, encoding="utf-8")

    summary = summarize(results)
    json_path = Path(args.json_path)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    correct = sum(1 for r in results if r["ok"])
    print(f"\n执行准确率: {correct}/{len(results)} = {correct / len(results):.1%}")
    print(f"报告已写入: {REPORT}")


if __name__ == "__main__":
    asyncio.run(main())
