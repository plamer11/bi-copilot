# BI Copilot · Text2SQL 数据分析 Agent 后端镜像
#
# 构建上下文必须是**项目根目录**（不是 backend/），因为前端目录在仓库根：
#   docker build -t bicopilot .
#   docker compose up --build
#
# 和 SmartSupport 那个 Dockerfile 最大的区别：**这里没有 torch 层**。
# Schema 检索的语义通道默认关闭（走关键词 + jieba），
# sentence-transformers 被刻意留在 requirements.txt 的注释里，
# 所以镜像里不会出现 490MB 的 torch —— 这也是它能几十秒构建完的原因。
FROM python:3.12-slim

ARG PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_ENDPOINT=https://hf-mirror.com

# 镜像内目录结构与仓库保持一致：
#   /app/backend/   ← bicopilot/backend
#   /app/frontend/  ← bicopilot/frontend
#
# 这样两处硬编码的相对路径都不用改：
#   app/main.py           FRONTEND_DIR = parents[2] / "frontend"  → /app/frontend
#   app/tools/sqlite_tool DB_PATH      = parents[2] / "data"      → /app/backend/data
WORKDIR /app

# ---- 依赖层：单独一层，改业务代码不会触发重装 ----
# 只先复制 requirements.txt，让 Docker 缓存住这一层。
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install -r backend/requirements.txt -i ${PIP_INDEX_URL}

COPY backend/ ./backend/
COPY frontend/ ./frontend/

# ---- 预建业务库 ----
# 放在构建期而不是启动期：容器每次 docker run 都要重新 seed 一遍纯属浪费。
# seed.py 幂等（库已存在就跳过），所以重复构建也没副作用。
RUN cd /app/backend && python -m app.db.seed

WORKDIR /app/backend

EXPOSE 8000

# 健康检查用 python 而不是 curl：slim 镜像里没有 curl。
# start-period 20s 足够 —— 这里没有 embedding 模型要加载，
# 冷启动只是 import langgraph/sqlglot 的时间。
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
