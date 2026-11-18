
from __future__ import annotations

import asyncio
import sys

from app.graph.build import aclose_graph, aget_graph, new_thread_config
from app.guard.audit import stats as audit_stats

SAMPLES = [
    "4 月 Kitchen 品类的销售额是多少？",
    "上个月退货率最高的 3 个 SKU 是哪些？",
    "哪些 SKU 广告费花得多但产出低，ACOS 超过 50% 的？",
    "哪些商品快断货了，还能卖几天？",
    "最近一个月一星二星差评集中在哪些商品？",
]


async def run_one(graph, question: str, idx: int) -> None:
    tid = f"smoke-{idx}"
    cfg = new_thread_config(tid)
    out = await graph.ainvoke({"session_id": tid, "question": question}, cfg)
    snapshot = await graph.aget_state(cfg)

    print(f"\n{'=' * 72}\n问：{question}\n{'-' * 72}")
    for t in out.get("trace", []):
        print(f"  · {t['node']:<13} {t['detail'][:70]}")

    if snapshot.next:
        print(f"  [HITL] 挂起等待人工确认于 {snapshot.next}，待确认 SQL 未执行")
        return

    print(f"\n  SQL: {(out.get('guard_sql') or '').strip()}")
    preview = (out.get("result_preview") or "").strip()
    if preview:
        print("  结果:")
        for line in preview.splitlines()[:8]:
            print("    " + line)
    print(f"\n  结论({out.get('chart_type', 'table')}): {(out.get('answer') or '').strip()[:200]}")


async def main() -> None:
    graph = await aget_graph()
    questions = sys.argv[1:] or SAMPLES
    try:
        for i, q in enumerate(questions, 1):
            await run_one(graph, q, i)
        print(f"\n{'=' * 72}\n审计统计: {audit_stats()}")
    finally:
        await aclose_graph()


if __name__ == "__main__":
    asyncio.run(main())
