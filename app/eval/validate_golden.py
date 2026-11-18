
from __future__ import annotations

from app.eval.golden_set import GOLDEN, summary
from app.tools.sqlite_tool import run_sql


def main() -> int:
    print(f"标注集规模: {summary()}\n")
    failed, empty, ok = [], [], 0
    for g in GOLDEN:
        res = run_sql(g["sql"])
        if not res.ok:
            failed.append((g["id"], res.error))
            print(f"  [FAIL] #{g['id']:<3} {g['question'][:34]:<36} {res.error[:60]}")
        elif res.row_count == 0:
            empty.append(g["id"])
            print(f"  [EMPTY] #{g['id']:<3} {g['question'][:34]:<36} 返回 0 行")
        else:
            ok += 1
    print(f"\n通过 {ok}/{len(GOLDEN)}")
    if failed:
        print(f"执行失败: {[i for i, _ in failed]}")
    if empty:
        print(f"结果为空: {empty}")
    return 0 if not failed and not empty else 1


if __name__ == "__main__":
    raise SystemExit(main())
