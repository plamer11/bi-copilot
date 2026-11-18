
from __future__ import annotations

import importlib
import re
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_ROOT.parent
CONTEXT_ROOT = PROJECT_ROOT
DOCKERFILE = PROJECT_ROOT / "Dockerfile"
DOCKERIGNORE = PROJECT_ROOT / ".dockerignore"
COMPOSE = PROJECT_ROOT / "docker-compose.yml"
REPORT = BACKEND_ROOT / "data" / "docker_report.md"
EXPOSE_PORT = 8000

if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

PASS, WARN, FAIL, SKIP = "PASS", "WARN", "FAIL", "SKIP"
ICON = {PASS: "✓", WARN: "!", FAIL: "✗", SKIP: "-"}

results: list[tuple[str, str, str]] = []


def record(level: str, name: str, detail: str = ""):
    results.append((level, name, detail))
    print(f"  [{ICON[level]}] {name}" + (f" — {detail}" if detail else ""))


def parse_dockerfile(text: str) -> list[tuple[str, str]]:

    out, buf = [], ""
    for line in text.splitlines():
        line = line.rstrip()
        if buf:
            line = buf + " " + line.strip()
            buf = ""
        if line.endswith("\\"):
            buf = line[:-1].strip()
            continue
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        parts = s.split(None, 1)
        out.append((parts[0].upper(), parts[1] if len(parts) > 1 else ""))
    return out


def check_dockerfile():
    print("\n[A] 静态预检")
    if not DOCKERFILE.exists():
        record(FAIL, "Dockerfile 存在", str(DOCKERFILE))
        return None
    record(PASS, "Dockerfile 存在", DOCKERFILE.name)

    instrs = parse_dockerfile(DOCKERFILE.read_text(encoding="utf-8"))
    kinds = [k for k, _ in instrs]
    record(PASS if kinds and kinds[0] == "FROM" else FAIL,
           "首条指令是 FROM", kinds[0] if kinds else "(空)")

    missing = []
    for k, arg in instrs:
        if k not in ("COPY", "ADD"):
            continue
        tokens = [t for t in arg.split() if not t.startswith("--")]
        for src in tokens[:-1]:
            if src.startswith(("http://", "https://")):
                continue
            if not (CONTEXT_ROOT / src).exists():
                missing.append(src)
    record(FAIL if missing else PASS, "COPY 源路径都存在",
           f"缺失：{missing}" if missing else "全部命中构建上下文（根目录）")

    cmd = next((arg for k, arg in instrs if k == "CMD"), "")
    m = re.search(r"([A-Za-z_][\w.]*):([A-Za-z_]\w*)", cmd)
    if not m:
        record(WARN, "CMD 模块路径可解析", f"未识别出 module:app —— {cmd}")
        return instrs
    mod_name, attr = m.group(1), m.group(2)
    try:
        mod = importlib.import_module(mod_name)
        ok = hasattr(mod, attr)
        record(PASS if ok else FAIL, f"CMD 可导入 {mod_name}:{attr}",
               "模块与对象都在" if ok else f"{mod_name} 里没有 {attr}")
    except Exception as e:
        record(FAIL, f"CMD 可导入 {mod_name}:{attr}", f"{type(e).__name__}: {e}")


    copy_pairs = [(i, arg) for i, (k, arg) in enumerate(instrs) if k == "COPY"]
    req_idx = next((i for i, arg in copy_pairs if "requirements.txt" in arg), None)
    full_idx = next((i for i, arg in copy_pairs
                     if not any(p.endswith(".txt") for p in arg.split()[:-1])), None)
    if req_idx is None:
        record(FAIL, "requirements 单独成层", "未找到 requirements.txt 的 COPY")
    elif full_idx is None or req_idx > full_idx:
        record(FAIL, "requirements 单独成层", "依赖层必须在全量 COPY 之前")
    elif "RUN" not in [k for k, _ in instrs[req_idx:full_idx]]:
        record(FAIL, "requirements 单独成层", "两层之间没有 RUN pip install")
    else:
        record(PASS, "requirements 单独成层", "依赖层在全量 COPY 之前")


    frontend_copied = any(k == "COPY" and "frontend" in arg for k, arg in instrs)
    record(PASS if frontend_copied else FAIL, "frontend 已打进镜像",
           "" if frontend_copied else "容器里 GET / 会拿不到页面")


    joined = "\n".join(f"{k} {a}" for k, a in instrs)
    if "torch" in joined:
        record(WARN, "镜像未引入 torch", "Dockerfile 里出现 torch，体积会从 ~300MB 涨到 ~1.5GB")
    else:
        record(PASS, "镜像未引入 torch", "语义通道默认关闭，无需 CUDA/CPU tensor 库")

    seed_built = any(k == "RUN" and "app.db.seed" in arg for k, arg in instrs)
    record(PASS if seed_built else WARN, "构建期预建业务库",
           "" if seed_built else "未在镜像里 seed，容器首启会报数据库不存在")
    return instrs


def check_dockerignore():
    if not DOCKERIGNORE.exists():
        record(WARN, ".dockerignore 存在", "缺失（构建上下文会带上 .env 与 __pycache__）")
        return
    text = DOCKERIGNORE.read_text(encoding="utf-8")
    record(PASS, ".dockerignore 存在", "")
    record(PASS if ".env" in text else FAIL, ".dockerignore 排除 .env",
           "" if ".env" in text else "密钥会被打进镜像")
    excluded_frontend = re.search(r"^\s*frontend", text, re.M)
    record(FAIL if excluded_frontend else PASS, "frontend 未被排除",
           "frontend 被排除会导致容器里没有页面" if excluded_frontend else "")
    record(PASS if "__pycache__" in text else WARN, "排除 __pycache__", "")


def check_ports(instrs):
    expose = [arg.strip() for k, arg in (instrs or []) if k == "EXPOSE"]
    if not expose:
        record(WARN, "EXPOSE 声明端口", "未声明")
        return
    if COMPOSE.exists():
        compose = COMPOSE.read_text(encoding="utf-8")
        container_side = {c for _h, c in re.findall(r'"(\d+):(\d+)"', compose)}
        ok = set(expose) & container_side
        record(PASS if ok else FAIL, "EXPOSE 与 compose 端口一致",
               f"EXPOSE {expose} / compose 容器端口 {sorted(container_side)}")
    else:
        record(WARN, "EXPOSE 与 compose 端口一致", "未找到 docker-compose.yml")


def check_requirements():
    req = BACKEND_ROOT / "requirements.txt"
    if not req.exists():
        record(FAIL, "requirements.txt 存在", "")
        return
    try:
        from importlib import metadata

        from packaging.requirements import Requirement
    except ImportError:
        record(SKIP, "requirements 语法校验", "未装 packaging，跳过")
        return

    bad, missing = [], []
    for line in req.read_text(encoding="utf-8").splitlines():
        s = line.split("#", 1)[0].strip()
        if not s:
            continue
        try:
            r = Requirement(s)
        except Exception as e:
            bad.append(f"{s} ({e})")
            continue
        try:
            metadata.version(r.name)
        except Exception:
            missing.append(r.name)
    record(FAIL if bad else PASS, "requirements 语法合法",
           f"非法行：{bad}" if bad else f"{len(missing)} 个包本机未装（容器内会装）")
    if missing:
        record(WARN, "requirements 本机已安装",
               f"未装：{', '.join(missing[:6])}" + (" …" if len(missing) > 6 else ""))


def check_inprocess():

    print("\n[B] 进程内等价验证（不需要 docker）")
    try:
        from fastapi.testclient import TestClient
    except ImportError:
        record(SKIP, "TestClient 可用", "未装 httpx")
        return
    try:
        from app.main import app
    except Exception as e:
        record(FAIL, "app.main 可导入", f"{type(e).__name__}: {e}")
        return
    record(PASS, "app.main 可导入", "（等价于 uvicorn app.main:app 启动成功）")

    client = TestClient(app)
    try:
        r = client.get("/api/health")
        ok = r.status_code == 200 and r.json().get("status") == "ok"
        record(PASS if ok else FAIL, "GET /api/health 返回 200",
               f"status={r.status_code} body={r.text[:80]}")
    except Exception as e:
        record(FAIL, "GET /api/health 返回 200", f"{type(e).__name__}: {e}")

    try:
        r = client.get("/api/schema")
        record(PASS if r.status_code == 200 else FAIL,
               "GET /api/schema 返回 200", f"status={r.status_code}")
    except Exception as e:
        record(WARN, "GET /api/schema 返回 200", f"{type(e).__name__}: {e}")


    try:
        r = client.get("/")
        html_ok = r.status_code == 200 and "text/html" in r.headers.get("content-type", "")
        record(PASS if html_ok else FAIL, "GET / 返回前端页面",
               f"status={r.status_code} type={r.headers.get('content-type')} bytes={len(r.content)}")
    except Exception as e:
        record(FAIL, "GET / 返回前端页面", f"{type(e).__name__}: {e}")


    try:
        r = client.post("/api/ask", json={"question": ""})
        record(PASS if r.status_code in (400, 422) else FAIL,
               "POST /api/ask 空问句被拒", f"status={r.status_code}")
    except Exception as e:
        record(WARN, "POST /api/ask 空问句被拒", f"{type(e).__name__}: {e}")


    from pydantic import ValidationError

    try:
        from app.main import AskRequest

        AskRequest(question="   ")
        record(WARN, "纯空格问句被拦截",
               "min_length=1 拦不住 '   '，空白问句会被送去调 LLM（建议加 strip 后校验）")
    except (ImportError, ValidationError):
        record(PASS, "纯空格问句被拦截", "")


def check_real_docker():
    print("\n[C] 真机 docker 验证")
    docker = shutil.which("docker")
    if not docker:
        record(SKIP, "docker 二进制可用",
               "本机未安装 Docker，无法执行 build/run —— 这一层未验证")
        return None

    tag = "bicopilot:validate"
    print("      执行 docker build（会在项目根构建，含 frontend）……")
    build = subprocess.run(
        [docker, "build", "-t", tag, "."],
        cwd=str(PROJECT_ROOT), capture_output=True, text=True,
    )
    if build.returncode != 0:
        record(FAIL, "docker build 成功", (build.stderr.strip().splitlines() or [""])[-1][:160])
        return None
    record(PASS, "docker build 成功", tag)

    size = subprocess.run([docker, "images", tag, "--format", "{{.Size}}"],
                          capture_output=True, text=True).stdout.strip()
    record(PASS, "镜像体积", size)

    run = subprocess.run(
        [docker, "run", "-d", "--rm", "-p", f"8124:{EXPOSE_PORT}",
         "-e", f"DEEPSEEK_API_KEY={_key()}", "--name", "bicopilot-validate", tag],
        capture_output=True, text=True,
    )
    if run.returncode != 0:
        record(FAIL, "docker run 启动", run.stderr.strip()[:160])
        return size

    healthy = False
    for _ in range(20):
        time.sleep(2)
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:8124/api/health", timeout=3) as resp:
                if resp.status == 200:
                    healthy = True
                    break
        except Exception:
            pass
    record(PASS if healthy else FAIL, "容器内 /api/health 通过",
           "容器起来并可响应" if healthy else "多次探测均未通过")

    subprocess.run([docker, "stop", "bicopilot-validate"], capture_output=True, text=True)
    return size


def _key() -> str:
    import os

    return os.getenv("DEEPSEEK_API_KEY", "")


def write_report(docker_skipped: bool, size: str | None):
    counts = {lv: sum(1 for l, _, _ in results if l == lv) for lv in (PASS, WARN, FAIL, SKIP)}
    lines = [
        "# Docker 构建验证报告 · BI Copilot",
        "",
        f"- 通过 {counts[PASS]}｜警告 {counts[WARN]}｜失败 {counts[FAIL]}｜跳过 {counts[SKIP]}",
        "",
        "| 级别 | 检查项 | 说明 |",
        "| --- | --- | --- |",
    ]
    for lv, name, detail in results:
        lines.append(f"| {ICON[lv]} {lv} | {name} | {detail or '—'} |")

    if docker_skipped:
        lines += [
            "",
            "## ⚠️ 真机构建未执行",
            "",
            "本机没有 Docker（WSL 也被安全策略禁用），`docker build` / `docker run` "
            "这一层**没有真正跑过**。A+B 两层能保证的是：镜像里要 COPY 的文件都存在、"
            "入口模块能导入、HTTP 服务能响应——也就是**最容易写错的几处**已经排除。",
            "",
            "仍然可能出问题的是**依赖安装层**：某个包的版本约束在本镜像的 Python 3.12 上"
            "是否可解。这一点只能在有 Docker 的机器上确认，命令是：",
            "",
            "```bash",
            "docker compose up --build        # 在项目根目录执行",
            "docker images bicopilot-backend  # 看体积",
            "```",
            "",
            "把本脚本拷到有 Docker 的机器上再跑一次，"
            "它会自动多跑 C 层并把结果写进本报告。",
        ]
    else:
        lines += ["", "## 真机验证已执行", "", f"镜像体积：**{size or '未知'}**"]

    lines += [
        "",
        "## 为什么这个镜像没有 torch",
        "",
        "Schema 检索有两条通道：关键词（jieba）和语义（embedding）。"
        "默认只跑关键词通道，`sentence-transformers` 被刻意留在 `requirements.txt` 的"
        "注释里——不注释掉就要连带拉 torch，镜像体积会从几百 MB 涨到 1.5GB 以上，"
        "而项目 90% 的场景并不需要它。",
        "",
        "要启用语义召回时：把 `USE_EMBEDDING_RETRIEVAL` 设成 `true`，"
        "并在镜像里额外装 `sentence-transformers`；届时建议给 Dockerfile 补一层 "
        "`pip install torch --index-url https://download.pytorch.org/whl/cpu`，"
        "指定 CPU 源可以避免连带安装 nvidia-* 的 CUDA 运行时（SmartSupport 那边已验证）。",
        "",
        "## 为什么 data 用 named volume 而不是目录挂载",
        "",
        "`Dockerfile` 在构建期执行了 `python -m app.db.seed` 预建业务库。"
        "如果 compose 里写成 `./backend/data:/app/backend/data` 的目录挂载，"
        "宿主机那个（可能是空的）目录会**盖住**镜像里的同名目录，"
        "`app.db` 直接消失、服务起来就报「数据库不存在」。"
        "named volume 在首次创建时会继承镜像内的内容，所以两者兼得。",
    ]
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    print("=== BI Copilot Docker 构建验证 ===")
    instrs = check_dockerfile()
    check_dockerignore()
    check_ports(instrs)
    check_requirements()
    check_inprocess()
    size = check_real_docker()

    docker_skipped = any(l == SKIP and "docker 二进制" in n for l, n, _ in results)
    write_report(docker_skipped, size)

    failed = [n for l, n, _ in results if l == FAIL]
    print(f"\n报告 → {REPORT}")
    if failed:
        print(f"结论：失败 {len(failed)} 项 → {failed}")
        return 1
    if docker_skipped:
        print("结论：静态 + 进程内检查全部通过；真机构建未执行（本机无 Docker）")
    else:
        print("结论：全部通过（含真机 docker build + run）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
