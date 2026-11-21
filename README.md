# BI Copilot · Text2SQL 数据分析 Agent

基于 **LangGraph 多 Agent 编排** 的自然语言取数系统。用户用中文提问，系统自动改写追问、检索相关表结构、生成 SQL、做静态安全审查、只读执行，最后给出分析结论——写错的 SQL 会带着错误回到重写节点自愈，最多三轮。

## 核心能力

- **多 Agent 编排**：14 个节点的 StateGraph，Supervisor 分流到查询 / 澄清 / 闲聊三条路径，查询路径再经过改写 → Schema 检索 → SQL 生成 → 安全守卫 → 执行 → 分析
- **SQL 静态安全守卫**：用 `sqlglot` 做 AST 级检查（不是靠 prompt 约束模型），四级判定 `SAFE / NEEDS_APPROVAL / BLOCKED / UNPARSEABLE`；拦截非 SELECT、高危 token、未知表，自动补 LIMIT（默认 200，上限 2000）
- **纵深防御**：守卫之外，执行器再套 `mode=ro` + `PRAGMA query_only = ON`，会话历史写独立库不碰业务库
- **HITL 人工确认**：风险 SQL 通过 `interrupt()` 挂起，前端审批面板可选通过 / 改写 / 取消，`Command(resume=...)` 续跑
- **自愈环**：SQL 执行失败或语法错误时带错误信息回到 repair 节点重写，最多三轮，用尽则诚实失败
- **Schema 检索**：关键词 + 同义词 + 可选 embedding 双通道；embedding 默认关闭，纯关键词即可跑通全链路
- **可复现评测**：40 条人工标注金标集（easy 12 / medium 18 / hard 10），固定种子与数据时间窗，execution accuracy **87.5%**，Schema 召回 **82.2%**
- **CI 回归门禁**：基线记录准确率与失败用例 ID，只拦"原来能过、现在过不了"的回归，不拦已知的 hard 档短板

## 架构

```
接入层    Web 界面（单文件前端，SSE 流式）+ 节点级执行过程可视化
             │
服务层    FastAPI  /api/ask(SSE)  /api/approve  /api/sql  /api/schema  /api/audit  /api/history
             │
编排层    LangGraph StateGraph（AsyncSqliteSaver 持久化 checkpoint）
          rewriter → supervisor ─┬─ clarify / chitchat
                                 └─ schema_agent → sql_writer → guard
                                        ├─ SAFE ───────────→ execute
                                        ├─ NEEDS_APPROVAL → approval → execute
                                        ├─ BLOCKED ────────→ reject
                                        └─ UNPARSEABLE / 执行失败 → repair → guard（≤3 轮）
                                                              execute → analyst → persist
             │
能力层    sqlglot AST 守卫 · SQLite 只读执行器 · Schema 检索（jieba + 可选 embedding）
基础设施  DeepSeek API · Docker
```

安全是纵深的：LLM 生成的 SQL 先过 AST 守卫，执行器再套只读连接 + `query_only`，会话历史写独立库——任何一层被绕过，下一层还拦得住。

## 快速启动

```bash
cp .env.example .env              # 填入 DEEPSEEK_API_KEY
pip install -r requirements.txt
python -m app.db.seed             # 建库（固定种子，任何机器数据一致）
uvicorn app.main:app --port 8000  # 打开 http://127.0.0.1:8000/
```

Docker 一键启动：

```bash
DEEPSEEK_API_KEY=sk-xxx docker compose up --build
```

跑测试（离线，不需要 Key）：

```bash
python -m pytest                  # 106 条测试
python -m app.eval.validate_golden
```

## 实测指标

| 类别 | 指标 | 数值 |
|---|---|---|
| 准确率 | execution accuracy（结果集比对，40 条人工标注） | **87.5%** |
| 检索 | Schema 召回（相关表/列） | **82.2%** |
| 分层 | easy / medium / hard | 100% / 100% / 50% |
| 工程 | 离线测试 | 106 条 pytest，无需 Key |

hard 档的 5 条失败集中在多表交叉 + 复合条件，是已知短板；基线里记录为 `failed_ids`，CI 门禁只拦回归，不把它们当失败。

## 目录结构

```
bi-copilot/
├── app/
│   ├── main.py              # FastAPI：SSE + 审批 + 守卫/审计接口
│   ├── config.py            # 配置（.env）
│   ├── graph/               # LangGraph：state / nodes / build（条件边 + 自愈环）
│   ├── agents/prompts.py    # 各 Agent 的 prompt
│   ├── guard/               # sqlglot AST 静态守卫 + 审计
│   ├── tools/sqlite_tool.py # 只读 SQL 执行器
│   ├── db/                  # 业务库 schema / seed / Schema 检索
│   ├── eval/                # 金标集 / 评测 / CI 门禁
│   └── llm.py               # LLM 统一入口
├── frontend/index.html      # 单文件网页界面
├── tests/                   # 106 条离线测试
├── eval/baseline.json       # CI 回归基线
└── docs/                    # PRD / TDD / 代码走查 / 面试问答
```

## 技术栈

| 层 | 技术 |
|---|---|
| 服务 | FastAPI · uvicorn · SSE |
| Agent 编排 | LangGraph（StateGraph + 条件边 + interrupt HITL + AsyncSqliteSaver） |
| SQL 安全 | sqlglot AST 静态分析 · SQLite `mode=ro` + `query_only` |
| 检索 | jieba 关键词 + 同义词 · 可选 embedding（默认关闭） |
| LLM | DeepSeek（langchain-openai 兼容接口） |
| 评测 | 金标集 execution accuracy · CI 回归门禁 |
| 部署 | Docker · docker-compose |

## 环境要求

- Python 3.11+
- `DEEPSEEK_API_KEY`（见 `.env.example`）
- embedding 通道默认关闭；开启且用 local provider 时才需要安装 `sentence-transformers`（会连带拉 torch）
