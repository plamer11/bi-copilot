
from __future__ import annotations

import asyncio
import sys

from app.config import settings
from app.db.history import clear_session, load_recent
from app.graph.build import aclose_graph, aget_graph, new_thread_config
from app.main import _fresh_state

SESSION = "demo-multiturn"

TURNS = [
    "上个月销量最高的 5 个 SKU 是哪些",
    "那 Kitchen 品类的呢",
    "换成退货率最高的 3 个",
]


async def ask_once(graph, question: str) -> dict:

    return await graph.ainvoke(_fresh_state(SESSION, question), new_thread_config(SESSION))


async def main() -> int:
    if not settings.api_key:
        print("没配 DEEPSEEK_API_KEY，跑不了真实链路。")
        return 2

    settings.enable_hitl = False
    graph = await aget_graph()
    clear_session(SESSION)

    try:
        for i, q in enumerate(TURNS, 1):
            print(f"\n{'=' * 68}\n第 {i} 轮：{q}\n{'=' * 68}")
            out = await ask_once(graph, q)

            is_follow = out.get("is_followup", False)
            standalone = out.get("standalone_question") or q
            if is_follow:
                print(f"追问改写：{q}  →  {standalone}")
            else:
                print("判定：独立问句（未改写）")

            print(f"SQL：{' '.join((out.get('guard_sql') or out.get('sql') or '(空)').split())}")
            if out.get("result_ok"):
                print(f"结果：{out.get('row_count')} 行")
            else:
                print(f"执行失败：{out.get('result_error') or out.get('error')}")
            print(f"结论：{(out.get('answer') or '')[:160]}")
    finally:
        await aclose_graph()

    print(f"\n{'=' * 68}\n会话历史（追问改写的依据）\n{'=' * 68}")
    for t in load_recent(SESSION, limit=5):
        print(f"- 问：{t['question']}\n  理解成：{t['standalone_question']}\n  行数为：{t['row_count']}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
