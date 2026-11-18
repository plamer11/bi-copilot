
from pathlib import Path
import re

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_ROOT.parent

from scripts.validate_docker import parse_dockerfile

DOCKERFILE = PROJECT_ROOT / "Dockerfile"
DOCKERIGNORE = PROJECT_ROOT / ".dockerignore"
COMPOSE = PROJECT_ROOT / "docker-compose.yml"


@pytest.fixture(scope="module")
def instrs():
    return parse_dockerfile(DOCKERFILE.read_text(encoding="utf-8"))


def test_dockerfile_exists():
    assert DOCKERFILE.exists()


def test_first_instruction_is_from(instrs):
    assert instrs[0][0] == "FROM"


def test_copy_sources_exist_in_build_context(instrs):

    missing = []
    for kind, arg in instrs:
        if kind not in ("COPY", "ADD"):
            continue
        tokens = [t for t in arg.split() if not t.startswith("--")]
        for src in tokens[:-1]:
            if not (PROJECT_ROOT / src).exists():
                missing.append(src)
    assert missing == [], f"构建上下文里找不到：{missing}"


def test_cmd_module_is_importable(instrs):

    import importlib

    cmd = next((a for k, a in instrs if k == "CMD"), "")
    m = re.search(r"([A-Za-z_][\w.]*):([A-Za-z_]\w*)", cmd)
    assert m, f"CMD 里没解析出 module:app —— {cmd}"
    mod = importlib.import_module(m.group(1))
    assert hasattr(mod, m.group(2))


def test_frontend_is_baked_into_image(instrs):

    assert any(k == "COPY" and "frontend" in a for k, a in instrs)


def test_no_torch_layer(instrs):

    joined = "\n".join(f"{k} {a}" for k, a in instrs)
    assert "torch" not in joined, "镜像引入了 torch，与默认关闭语义召回的取舍冲突"


def test_business_db_seeded_in_image(instrs):

    assert any(k == "RUN" and "app.db.seed" in a for k, a in instrs)


def test_dependencies_installed_before_code_copy(instrs):

    copy_pairs = [(i, arg) for i, (k, arg) in enumerate(instrs) if k == "COPY"]
    req_idx = next(i for i, arg in copy_pairs if "requirements.txt" in arg)
    full_idx = next(i for i, arg in copy_pairs
                    if not any(p.endswith(".txt") for p in arg.split()[:-1]))
    assert req_idx < full_idx, "依赖层必须在全量 COPY 之前"
    assert "RUN" in [k for k, _ in instrs[req_idx:full_idx]]


def test_dockerignore_excludes_secrets_and_keeps_frontend():
    text = DOCKERIGNORE.read_text(encoding="utf-8")
    assert ".env" in text, ".env 里有 API Key，绝不能进镜像"
    assert not re.search(r"^\s*frontend", text, re.M), "frontend 被排除会导致容器里没有页面"
    assert "__pycache__" in text


def test_compose_uses_named_volume_not_bind_mount():

    compose = COMPOSE.read_text(encoding="utf-8")
    assert "bicopilot-data:/app/backend/data" in compose
    assert not re.search(r"\./backend/data:/app/backend/data", compose)


def test_requirements_lines_are_valid():

    packaging = pytest.importorskip("packaging.requirements")
    bad = []
    for line in (BACKEND_ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines():
        s = line.split("#", 1)[0].strip()
        if not s:
            continue
        try:
            packaging.Requirement(s)
        except Exception as e:
            bad.append(f"{s}: {e}")
    assert bad == []


def test_expose_matches_compose_container_port(instrs):
    expose = {a.strip() for k, a in instrs if k == "EXPOSE"}
    container_side = {c for _h, c in re.findall(
        r'"(\d+):(\d+)"', COMPOSE.read_text(encoding="utf-8"))}
    assert expose & container_side, f"EXPOSE {expose} 与 compose {container_side} 对不上"


def test_healthcheck_uses_python_not_curl(instrs):

    hc = next((a for k, a in instrs if k == "HEALTHCHECK"), "")
    assert "python" in hc
    assert "curl" not in hc
