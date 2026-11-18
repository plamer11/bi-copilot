# BI Copilot 代码走查：每个文件的作用与全流程编排

## 0. 一句话总览

一次提问经过 **5 个 Agent + 1 个守卫**，中间可能插入 **自愈循环** 和 **人工确认**，最终输出结论 + 数据 + 图表建议。

```text
supervisor ─┬─ clarify ─→ clarify_node ─→ END
            ├─ chitchat → chitchat_node → END
            └─ query ──→ schema_agent → sql_writer ─→ guard ─┬─ BLOCKED ─→ reject
                                                              ├─ NEEDS_APPROVAL → approval ─→ execute
                                                              └─ SAFE ─────────→ execute
                                    ↑                                                  │
                                    │      ┌─ 失败且未超轮次 ─ repair ────────────────┘
                                    └──────┘        └─ 失败且已用尽 ─→ exhausted
                                             └─ 成功 ─→ analyst ─→ END
```

## 1. 文件作用一览

| 文件 | 作用 |
|---|---|
| `app/config.py` | 配置：LLM、数据库路径、自愈轮次、HITL 开关、阈值 |
| `app/llm.py` | LLM 统一入口。屏蔽 transformers 加速启动；DeepSeek 只认 `function_calling` 结构化 |
| `app/db/schema.sql` | 8 张表 DDL + 索引 |
| `app/db/seed.py` | 种子数据。固定种子 42，植入 4 类业务异常 |
| `app/db/catalog.py` | **Schema 语义目录**：表/列的中文别名、指标口径、JOIN 路径、业务规则、敏感表定义 |
| `app/db/schema_retriever.py` | Schema 检索：关键词+同义词打分 → 选表 → 选列 → 补 JOIN 键 → 渲染 prompt |
| `app/agents/prompts.py` | 五个 Agent 的系统提示词（含少样本与常见错误清单） |
| `app/guard/sql_guard.py` | SQL 静态安全检查，三级判定 + 自动补 LIMIT |
| `app/guard/audit.py` | 审计日志（JSONL），记录每次提问的 SQL 与决策 |
| `app/tools/sqlite_tool.py` | 只读执行器：只读连接 + 超时中断 + 结果截断 |
| `app/graph/state.py` | 状态定义（**字段必须全部声明**，否则被 LangGraph 静默丢弃） |
| `app/graph/nodes.py` | 各 Agent 节点实现，返回状态增量 |
| `app/graph/build.py` | 构图：条件边 + 自愈环 + checkpointer |
| `app/eval/golden_set.py` | 40 条人工标注（NL → gold SQL），分 easy/medium/hard |
| `app/eval/validate_golden.py` | 标注集自检 |
| `app/eval/run_eval.py` | execution accuracy 评测（并发 5） |
| `app/main.py` | FastAPI：SSE 问答、确认回调、schema 浏览、SQL 调试、审计查询 |
| `scripts/smoke.py` | 端到端冒烟测试 |

## 2. 节点职责与状态产出

| 节点 | 产出字段 | 说明 |
|---|---|---|
| `supervisor_node` | `decision`, `clarify_question` | 判定 query/clarify/chitchat，越界标签兜底为 query |
| `schema_node` | `recalled_tables`, `schema_text` | 检索并渲染 DDL + JOIN + 口径 + 规则 |
| `write_sql_node` | `sql`, `attempts` | 首轮生成，清洗 markdown 代码块与多余前缀 |
| `guard_node` | `guard_level`, `guard_sql`, `guard_reasons` | 静态检查，UNPARSEABLE 时把报错塞进 `result_error` 交自愈 |
| `approval_node` | `approval_action`, `edited_sql` | `interrupt()` 挂起；改写后**二次过守卫** |
| `execute_node` | `result_ok`, `result_*` | 只读执行，失败不抛异常 |
| `repair_node` | `sql`, `repair_round` | 报错回灌重写，error 留空等 execute 回填 |
| `analyst_node` | `answer`, `chart_type` | 结论 + 图表建议，结构化输出失败降级裸文本 |
| `reject_node` / `exhausted_node` | `answer`, `error` | 拦截与轮次用尽的诚实失败说明 |

## 3. 一次请求的完整时序

1. **`POST /api/ask`** → 生成 `session_id`，`astream` 逐节点推送 SSE `trace` 事件
2. **Supervisor** 判定；clarify/chitchat 直接结束
3. **Schema 检索** 召回表与列，渲染进 prompt
4. **Writer** 生成 SQL（清洗后）
5. **Guard** 判定：
   - BLOCKED → 返回拦截说明，结束
   - NEEDS_APPROVAL → `interrupt()` 挂起，推 `approval_required` 事件，**流结束**
   - SAFE → 继续
6. **Execute** 执行：失败 → 未超轮次进 repair，超了进 exhausted
7. **Repair** 重写 → **回到 Guard**（不直连执行）
8. **Analyst** 生成结论 → 推 `final` 事件

人工确认场景：客户端收到 `approval_required` → 调 `POST /api/approve` 带 `action`（approve/edit/reject）→
服务端 `Command(resume=...)` 恢复同一个 thread → 继续执行。

## 4. 关键设计点（代码注释里都有出处）

- **修复后重新过守卫**（`build.py`）：`g.add_edge("repair", "guard")`，不能直连 `execute`。
- **JOIN 键强制带上**（`schema_retriever._always_columns`）：召回表却不给 `sku`/`order_id`，模型拼不出关联。
- **指标强制召回**（`_forced_tables_by_metrics`）：问 ACOS 必须召回 `ad_spend`；`requires` 声明隐式依赖（如销量需要 `orders`）。
- **相对阈值**（`RELATIVE_THRESHOLD=0.05`）：低于最高分 5% 的表丢弃，避免 top_k 硬截断放进噪声。
- **维度表加权**（`DIMENSION_BOOST`，products +4）：取品名/品类几乎总需要它。
- **聚合不算全量导出**（`_is_aggregate`）：否则常规分析全被审批卡死。
- **CTE 别名排除**（`_extract_tables`）：`WITH t AS (...)` 里的 `t` 不是表。
- **连接必须关闭**（`aclose_graph`）：不关进程不退出。

## 5. 存储层

| 文件 | 内容 |
|---|---|
| `data/app.db` | 业务数据（8 张表，2.2 万行），只读访问 |
| `data/checkpoints.db` | LangGraph 状态（HITL 挂起现场） |
| `data/audit.log` | 审计事件（JSONL） |
| `data/eval_report.md` | 评测报告（脚本生成） |

## 6. 接口一览

| 接口 | 用途 |
|---|---|
| `POST /api/ask` | 提问，SSE 流式返回 |
| `POST /api/approve` | 人工确认回调（恢复挂起的会话） |
| `GET /api/schema` | 浏览表/列/指标口径 |
| `POST /api/sql` | 单独检查并执行一条 SQL（调试用，同样过守卫） |
| `GET /api/audit` | 审计日志与统计 |
| `GET /api/health` | 健康检查与当前配置 |

---

## 7. 第二轮新增的文件

| 文件 | 作用 |
|---|---|
| `app/db/history.py` | 会话历史存储（独立 `history.db`，不写业务库，避免破坏只读防线） |
| `app/graph/nodes.py::rewrite_node` | 追问改写，把「那 Kitchen 呢？」补成完整问句 |
| `app/graph/nodes.py::persist_node` | 只落成功轮次，失败 SQL 进了历史会把错误固化到下一轮 |
| `app/db/embedder.py` | 三条可插拔向量后端 + 探活 + 静默降级 |
| `app/db/embed_index.py` | 表/列向量索引、带后端标识的磁盘缓存、双通道融合 |
| `app/eval/ci_gate.py` | 回归门禁判定（新增失败数 + 分档跌幅） |
| `eval/baseline.json` | 基线（hard 档 5 条失败是已知短板，不算回归） |
| `.github/workflows/regression.yml` | 两层 CI：离线 pytest + 有 Key 时跑准确率门禁 |
| `frontend/index.html` | 免构建单页前端（SSE 进度 / SQL / 结果 / HITL 面板） |
| `scripts/demo_multiturn.py` | 多轮端到端演示（真实 LLM，三连问） |

### 图结构的变化

```
rewriter → supervisor ─┬─ clarify ─→ clarify_node ─→ END
                       ├─ chitchat → chitchat_node → END
                       └─ query ──→ schema_agent → sql_writer → guard ─┬─ BLOCKED → reject
                                                                        ├─ NEEDS_APPROVAL → approval → execute
                                                                        └─ SAFE ─────────→ execute
                                        ↑                                            │
                                        │      ┌─ 失败未超轮次 ─ repair ───────────────┘
                                        └──────┘      └─ 用尽 ─→ exhausted
                                                 └─ 成功 ─→ analyst ─→ persist ─→ END
```

**为什么 rewriter 在最前面**：Supervisor 判的是"这句话信息够不够"。
给它残缺原句，它会把「那 Kitchen 品类的呢」判成 clarify 去反问，而答案就在上一轮里。
