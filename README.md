# BI Copilot —— Text2SQL 多智能体数据分析平台

> 用中文问业务问题，自动翻译成 SQL、执行、自愈、给结论。
> Amazon US 家居品类运营数据，8 张表 2.2 万行，LangGraph 五 Agent 编排。

```text
你：上个月退货率最高的 3 个 SKU 是哪些？
  ↓ Supervisor 判定可直接查 → Schema 检索召回 4 张表 → 生成 SQL
  ↓ 安全守卫放行 → 只读执行 → 报错则回灌重写（最多 3 轮）
BI：5 月退货率最高的是 HN-LIG-1021(33.3%)、HN-BED-1001(31.0%)、HN-BED-1033(21.6%)。
    建议先排查前两个的退货原因，查清前暂停加投广告和补货。
```

---

## 为什么做这个项目

跟另一个项目 SmartSupport（智能客服）互补：

| 能力 | SmartSupport（客服） | **BI Copilot（本项目）** |
|---|---|---|
| 编排 | 单图多分支路由 | **多 Agent 协作 + 自愈环** |
| 数据 | 文档 RAG 检索 | **结构化数据库 Text2SQL** |
| 控制 | 意图路由 + 转人工 | **安全守卫 + 人在回路审批** |
| 评测 | ragas 主观打分 | **execution accuracy 客观比对** |



## 核心设计：五个专职 Agent

不是"一个大模型干所有事"，而是拆成职责单一的五段：

| Agent | 干什么 | 为什么必须拆开 |
|---|---|---|
| **Supervisor** | 判定 query / clarify / chitchat | 反问能力很关键——"帮我看看数据"必须追问口径，直接猜必错 |
| **Schema 检索** | 从 8 表 60+ 列里捞本次要用的子集 | 全塞 prompt 约 2500 token，且无关列会让模型挑错字段 |
| **SQL Writer** | 只拿 schema 子集生成 SQL | 职责单一，出错可定位 |
| **安全守卫 Guard** | 静态解析 AST 拦截危险语句 | 唯一不该信任 LLM 的环节，必须代码层拦 |
| **Analyst** | 结果 → 中文结论 + 图表建议 | 与查数解耦，换模型不影响上游 |

**自愈环**是灵魂：执行报错 → 把 `no such column: xxx` 原样回灌 → 重写 → 最多 3 轮 → 仍失败就诚实告知。
修复后的 SQL **必须重新过守卫**，不能因为"是重写的"就放行。

**HITL** 落在守卫上：`SELECT * FROM orders` 这类高风险语句 `interrupt()` 挂起，人工 批准/改写/拒绝 后 `Command(resume=...)` 续跑。
人工改过的 SQL **同样要再过一遍守卫**——实测过改写成 `DELETE FROM orders` 被二次拦截。

## 快速开始

```bash
cd bicopilot/backend

# 1. 装依赖（用现有 conda 环境即可）
pip install -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/

# 2. 配 Key：把 DEEPSEEK_API_KEY / LLM_BASE_URL / LLM_MODEL 写进 backend/.env

# 3. 建库（固定种子，任何机器跑出来的数据完全一致）
python -m app.db.seed --force

# 4. 起服务
uvicorn app.main:app --reload --port 8001
```

试一条：

```bash
curl -N -X POST http://127.0.0.1:8001/api/ask \
  -H "Content-Type: application/json" \
  -d '{"question":"哪些 SKU 广告费花得多但产出低，ACOS 超过 50% 的？"}'
```

SSE 会依次推 `start` → `trace`（每个 Agent 的进度）→ `sql` → `final`。

## 数据说明

固定窗口 **2026-04-01 ~ 2026-06-29**，随机种子 42，任何机器生成结果完全一致（评测才可复现）。

| 表 | 行数 | 内容 |
|---|---|---|
| products | 60 | SKU 主数据（品类/品牌/成本/售价/评分/状态） |
| orders | 4,200 | 订单头（日期/站点/区域/Prime/状态/新老客） |
| order_items | 6,221 | 订单明细（SKU/件数/成交价/折扣/运费） |
| ad_spend | 4,189 | 广告日报（曝光/点击/花费/广告销售额） |
| returns | 533 | 退货（原因/退款额/是否缺陷/可否再售） |
| inventory | 5,400 | 库存快照（可售/在途/占用/可售天数） |
| reviews | 1,600 | 评论（星级/VP/带图/点赞） |
| promotions | 200 | 促销（券/秒杀/订阅省/Prime专享） |

数据里**刻意植入了四类业务异常**，所以问出来的结论有业务含义，不是随机噪声：

| 异常 | SKU | 表现 |
|---|---|---|
| 高退货 | HN-BED-1001 / HN-BED-1057 | 退货率 22.7% / 19.1%，主因 defective |
| 广告烧钱 | HN-LIG-1053 | ACOS **528%**（第二名才 21%） |
| 断货风险 | HN-LIG-1037 / HN-BAT-1002 / HN-FUR-1038 | 可售天数 6.1 / 9.6 / 14.9 天 |

## 实测数据

`python -m app.eval.run_eval`（40 条人工标注，deepseek-chat）：

| 指标 | 数值 |
|---|---|
| **Execution Accuracy** | **87.5%（35/40）** |
| ├ easy | 100%（12/12） |
| ├ medium | 100%（18/18） |
| └ hard | 50%（5/10） |
| Schema Recall | 82.2% |
| 标注集自检 | 40/40 全部可执行且结果非空 |

准确率口径：分别执行 gold SQL 与模型生成的 SQL，比对结果集（忽略行序、浮点保留 2 位）。
不用字符串比对——换个别名、换个 JOIN 顺序就被判错没有意义。

## 安全设计

三级判定，在语句执行**之前**做静态检查：

| 级别 | 触发条件 | 处理 |
|---|---|---|
| `BLOCKED` | DML/DDL、多语句、越权表、系统表、`attach` | 直接拒绝，**不进自愈环** |
| `NEEDS_APPROVAL` | 敏感表全量导出、SELECT *、多表无过滤 | 挂起等人工确认 |
| `SAFE` | 其他 | 放行，缺 LIMIT 自动补 200 |

三道防线：守卫静态检查 → 连接层 `mode=ro` + `PRAGMA query_only` → 结果集截断 200 行。
就算守卫被绕过，数据库层面也写不进去。

## 目录结构

```text
bicopilot/
├── README.md
├── Dockerfile                # 镜像（构建上下文是项目根，前端一起打进去）
├── docker-compose.yml        # 一键起服务，data 用 named volume 持久化
├── .dockerignore
├── docs/
│   ├── prd.md                # 需求与验收标准
│   ├── tdd.md                # 技术选型与架构决策
│   ├── code-walkthrough.md   # 逐文件作用 + 全流程编排
│   └── interview.md          # 面试深挖 Q&A
└── backend/
    ├── app/
    │   ├── config.py               # 配置（读 .env）
    │   ├── llm.py                  # LLM 统一入口（屏蔽 transformers 加速启动）
    │   ├── db/
    │   │   ├── schema.sql          # 8 张表 DDL
    │   │   ├── seed.py             # 种子数据（种子固定，含业务异常植入）
    │   │   ├── catalog.py          # Schema 语义目录：中文别名 + 指标口径 + JOIN 路径
    │   │   └── schema_retriever.py # 检索：关键词+同义词打分，补 JOIN 键
    │   ├── agents/prompts.py       # 五个 Agent 的提示词
    │   ├── guard/
    │   │   ├── sql_guard.py        # SQL 静态安全检查（三级判定）
    │   │   └── audit.py            # 审计日志（JSONL）
    │   ├── tools/sqlite_tool.py    # 只读执行器（超时 + 截断）
    │   ├── graph/
    │   │   ├── state.py            # 状态定义（字段必须全声明）
    │   │   ├── nodes.py            # 各 Agent 节点
    │   │   └── build.py            # 构图：条件边 + 自愈环 + checkpointer
    │   ├── eval/
    │   │   ├── golden_set.py       # 40 条人工标注
    │   │   ├── validate_golden.py  # 标注集自检
    │   │   └── run_eval.py         # execution accuracy 评测
    │   └── main.py                 # FastAPI：SSE 问答 / 确认回调 / schema / 审计
    ├── scripts/smoke.py            # 端到端冒烟（需 Key）
    ├── scripts/validate_docker.py  # Docker 构建三层校验（静态/进程内/真机）
    ├── tests/                      # pytest（离线可跑，108 条）
    └── data/                       # app.db / audit.log（gitignore）
```

## Docker 部署

```bash
docker compose up --build        # 必须在项目根目录执行
```
起完访问 `http://127.0.0.1:8001/`（宿主机 8001 → 容器 8000，
8000 留给 SmartSupport，两个项目可以一起跑）。

三个刻意的设计：

| 决策 | 原因 |
| --- | --- |
| 构建上下文是**项目根**，不是 `backend/` | 前端目录在仓库根。只 COPY backend 的话容器里没有页面，`GET /` 拿不到东西 |
| 镜像里**没有 torch** | Schema 检索的语义通道默认关闭，`sentence-transformers` 被注释掉。装上会让镜像从几百 MB 涨到 1.5GB 以上 |
| `data` 用 **named volume**，不用目录挂载 | 构建期已经 `python -m app.db.seed` 预建了业务库；目录挂载会用宿主机（可能是空的）目录盖住它，服务直接报「数据库不存在」。named volume 首次创建会继承镜像内容 |

不想装 Docker 也能验证 Dockerfile 写得对不对：

```bash
python -m scripts.validate_docker    # 静态预检 + 进程内等价验证
python -m pytest tests/test_docker.py   # 同一批检查的离线 pytest 版（CI 会跑）
```

> ⚠️ **真机构建尚未验证**：开发机没装 Docker，上面两条只覆盖了
> 「要 COPY 的文件都在 / 入口模块能导入 / 服务能响应」这几处最容易写错的地方，
> **依赖能否在 Python 3.12 镜像里装上还没跑过**。完整报告见
> `backend/data/docker_report.md`，在有 Docker 的机器上重跑脚本会自动补上那一层。

## 命令速查

```bash
python -m app.db.seed --force          # 重建数据库
python -m app.eval.validate_golden     # 标注集自检（离线）
python -m pytest                       # 测试套件（离线，不依赖 Key）
python -m app.eval.run_eval            # 准确率评测（需 Key，约 3 分钟）
python -m app.eval.run_eval --ids 31,32 --verbose   # 单条调试，打印模型 SQL
python -m scripts.smoke "你的问题"      # 端到端跑一条（需 Key）
python -m scripts.validate_docker     # Docker 构建校验（离线，无需 docker 二进制）
```

## 踩过的坑（都在代码注释里标了出处）

1. **`from_conn_string` 返回上下文管理器**，不能直接传给 `compile(checkpointer=...)`，得自己 `aiosqlite.connect`。
2. **AsyncSqliteSaver 才能配 astream**，同步 `SqliteSaver` 一进来就抛 "does not support async methods"。
3. **aiosqlite 连接不关进程就不退出**——表现为脚本明明输出了结果却卡着不动，排查很费时间。
4. **CTE 别名被当成表名**：`WITH t AS (...)` 里的 `t` 不在白名单 → 误判越权，得先收集 CTE 名再排除。
5. **聚合查询被误判成"全量导出"**：早期把所有无 WHERE 的敏感表查询都判高风险，连"各 SKU 销量 Top10"都被卡住。加了 `_is_aggregate` 区分。
6. **指标命中靠分词会漏**：jieba 把「4 月销量」切成「月销量」，导致「销量」别名匹配不上，指标强制召回失效。改成在原始问句里找别名子串。
7. **隐式依赖表没召回**：剔取消订单要 JOIN orders，但销量公式里没出现它，模型只能靠猜列名。给指标加 `requires` 字段显式声明。
8. **口径单位没写死**：ACOS 一会儿给 0.53 一会儿给 53，同一句话两次问出两个数。在 METRICS 里写明"统一乘 100 输出百分比"。
9. **精度差异被判错**：gold 写了 `ROUND(x,2)` 模型没写，结果 4.2642 vs 4.26 判失败。比对时统一保留 2 位。
10. **rule 措辞过宽**：「统计销量时剔除 cancelled」被模型推广到所有计数，连"各站点订单量"都加了过滤。收窄为「单纯数订单量不过滤」。

## 已完成（第二轮补的）

- [x] **多轮上下文取数**（`app/db/history.py` + `rewriter` 节点）
- [x] **embedding 语义召回通道**（`app/db/embedder.py` + `app/db/embed_index.py`）
- [x] **CI 回归门禁**（`.github/workflows/regression.yml` + `app/eval/ci_gate.py`）
- [x] **前端**（`frontend/index.html`，免构建单页）

### 多轮：rewriter 必须排在 supervisor 前面

这是实测踩出来的。第一版把改写节点放在"判定为可查之后"，结果用户问「那 Kitchen 品类的呢」，
Supervisor 拿到的是一个没有谓语的残缺句子，直接判成 `clarify` 去反问"你想看哪个指标"——
而答案明明就在上一轮里。改成 `rewriter → supervisor` 后：

```
第 1 轮：上个月销量最高的 5 个 SKU 是哪些   → 独立问句，不改写
第 2 轮：那 Kitchen 品类的呢                → 上个月 Kitchen 品类销量最高的 5 个 SKU 是哪些
第 3 轮：换成退货率最高的 3 个              → 上个月 Kitchen 品类退货率最高的 3 个 SKU 是哪些
```

第 3 轮最能说明问题：指标换了、维度没换，改写得分辨"换掉什么、保留什么"。

另外两个坑：
- **history 每轮必须显式置 `None`**：同一个 thread 的 checkpoint 里残留着上一轮写入的
  `history`，不重置的话第二轮会读到空列表，追问改写**静默失效**（不报错，只是不生效）。
- **评测必须显式传 `history=[]`**：否则第二次跑评测会读到上一轮写进去的记录，结果不可复现。

演示：`cd backend && python -m scripts.demo_multiturn`

### embedding 通道：可插拔 + 默认关闭

三条后端按能力排序，`USE_EMBEDDING_RETRIEVAL=true` 后依次尝试，全不可用就退回纯关键词：

| 后端 | 说明 |
|---|---|
| `local` | sentence-transformers（BGE-small-zh），首次用要下 ~95MB |
| `api` | OpenAI 兼容 `/embeddings`（DashScope text-embedding-v4 等） |
| `hash` | 字符 n-gram 哈希，**不是语义模型**，只用于离线跑通融合链路 |

向量缓存到 `data/schema_embeddings.json`，缓存键带后端标识 —— 换个后端必须重建，
否则会读到上一个后端的向量，召回错乱且极难排查。

守住的底线：**关掉开关时检索结果与以前完全一致**（有回归测试盯着）。

### CI 门禁：宁可漏报，不可天天误报

判的是"新增失败是否超过 2 条"和"某难度档是否掉超过 10%"，
而不是"总准确率下降 X% 就拦"—— 后者跟前者完全等价（总准确率要掉，必然有原来能过的用例挂了），
判两遍还丢定位信息。基线在 `eval/baseline.json`，hard 档 5 条失败是**已知短板不是回归**，
记在基线里不被拦。

### 前端

`frontend/index.html`，单文件免构建，起服务后访问 `http://127.0.0.1:8001/`。
能看节点级执行进度、SQL 与安全判定、结果表格、追问改写后的理解，
以及 HITL 审批面板（通过 / 改写 / 取消）。

## 还没做的

- [ ] 阈值实验：把召回阈值、融合权重扫一遍看准确率怎么变（现在是拍脑袋调的）
- [ ] 图表真的画出来（Analyst 给的是 `chart_type` 建议，前端还没渲染图）
- [ ] 多轮改写本身的评测集（现在靠 `demo_multiturn` 人工看）
