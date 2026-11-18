# Docker 构建验证报告 · BI Copilot

- 通过 19｜警告 1｜失败 0｜跳过 1

| 级别 | 检查项 | 说明 |
| --- | --- | --- |
| ✓ PASS | Dockerfile 存在 | Dockerfile |
| ✓ PASS | 首条指令是 FROM | FROM |
| ✓ PASS | COPY 源路径都存在 | 全部命中构建上下文（根目录） |
| ✓ PASS | CMD 可导入 app.main:app | 模块与对象都在 |
| ✓ PASS | requirements 单独成层 | 依赖层在全量 COPY 之前 |
| ✓ PASS | frontend 已打进镜像 | — |
| ✓ PASS | 镜像未引入 torch | 语义通道默认关闭，无需 CUDA/CPU tensor 库 |
| ✓ PASS | 构建期预建业务库 | — |
| ✓ PASS | .dockerignore 存在 | — |
| ✓ PASS | .dockerignore 排除 .env | — |
| ✓ PASS | frontend 未被排除 | — |
| ✓ PASS | 排除 __pycache__ | — |
| ✓ PASS | EXPOSE 与 compose 端口一致 | EXPOSE ['8000'] / compose 容器端口 ['8000'] |
| ✓ PASS | requirements 语法合法 | 0 个包本机未装（容器内会装） |
| ✓ PASS | app.main 可导入 | （等价于 uvicorn app.main:app 启动成功） |
| ✓ PASS | GET /api/health 返回 200 | status=200 body={"status":"ok","llm_configured":true,"model":"deepseek-chat","hitl_enabled":true |
| ✓ PASS | GET /api/schema 返回 200 | status=200 |
| ✓ PASS | GET / 返回前端页面 | status=200 type=text/html; charset=utf-8 bytes=12219 |
| ✓ PASS | POST /api/ask 空问句被拒 | status=422 |
| ! WARN | 纯空格问句被拦截 | min_length=1 拦不住 '   '，空白问句会被送去调 LLM（建议加 strip 后校验） |
| - SKIP | docker 二进制可用 | 本机未安装 Docker，无法执行 build/run —— 这一层未验证 |

## ⚠️ 真机构建未执行

本机没有 Docker（WSL 也被安全策略禁用），`docker build` / `docker run` 这一层**没有真正跑过**。A+B 两层能保证的是：镜像里要 COPY 的文件都存在、入口模块能导入、HTTP 服务能响应——也就是**最容易写错的几处**已经排除。

仍然可能出问题的是**依赖安装层**：某个包的版本约束在本镜像的 Python 3.12 上是否可解。这一点只能在有 Docker 的机器上确认，命令是：

```bash
docker compose up --build        # 在项目根目录执行
docker images bicopilot-backend  # 看体积
```

把本脚本拷到有 Docker 的机器上再跑一次，它会自动多跑 C 层并把结果写进本报告。

## 为什么这个镜像没有 torch

Schema 检索有两条通道：关键词（jieba）和语义（embedding）。默认只跑关键词通道，`sentence-transformers` 被刻意留在 `requirements.txt` 的注释里——不注释掉就要连带拉 torch，镜像体积会从几百 MB 涨到 1.5GB 以上，而项目 90% 的场景并不需要它。

要启用语义召回时：把 `USE_EMBEDDING_RETRIEVAL` 设成 `true`，并在镜像里额外装 `sentence-transformers`；届时建议给 Dockerfile 补一层 `pip install torch --index-url https://download.pytorch.org/whl/cpu`，指定 CPU 源可以避免连带安装 nvidia-* 的 CUDA 运行时（SmartSupport 那边已验证）。

## 为什么 data 用 named volume 而不是目录挂载

`Dockerfile` 在构建期执行了 `python -m app.db.seed` 预建业务库。如果 compose 里写成 `./backend/data:/app/backend/data` 的目录挂载，宿主机那个（可能是空的）目录会**盖住**镜像里的同名目录，`app.db` 直接消失、服务起来就报「数据库不存在」。named volume 在首次创建时会继承镜像内的内容，所以两者兼得。