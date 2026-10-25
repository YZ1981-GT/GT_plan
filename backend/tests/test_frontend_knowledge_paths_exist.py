"""前端知识库 API 路径 ↔ 后端真实路由 —— 存在性守卫

spec: knowledge-upload-robustness-and-consumer-wiring（Requirement 7.2）

═══ 缘起 ═══

附注 / 审计报告编辑器的「📚 知识库」选择器调 ``/api/knowledge/search``：后端**从未有过**这条
路由，404 被 ``catch`` 吞成空列表，界面恒显示「未找到匹配的文档」。同表另有 3 个路径
（``/api/knowledge/{分类}``、``…/upload``、``…/{id}``）同样不存在。路径是**字符串字面量**：
vue-tsc / eslint / vitest 都不校验它指向的后端路由是否存在，只有真点一下才知道。

═══ 判据 ═══

前端生产源码里每个含 ``knowledge*`` 路径段的 ``/api/…`` 字面量，都必须命中运行期
``app.routes`` 的某条路由（段数相等；后端 ``{参数}`` 段匹配任意，前端 ``${…}`` 只能匹配
后端 ``{参数}``）。范围只到知识库命名空间：全前端现算 3825 个 ``/api/`` 字面量中 361 个
不可解析，横跨几十个业务域，超出本 spec（见 requirements §三）。

已知死代码链（``KnowledgeBasePanel.vue`` 无任何挂载点）的 5 个路径登记在
``_KNOWN_DEAD_PATHS``，且**可伪证**：一旦有人挂载该组件或在别处使用这些路径，
``test_dead_chain_is_still_unmounted`` 打红，逼迫先修路径再上线。
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_SRC = _ROOT / "audit-platform" / "frontend" / "src"

_LITERAL = re.compile(r"""(['"`])(/api/[^'"`\s]*)\1""")
_PLACEHOLDER = re.compile(r"\$\{[^}]*\}")
# 注释剥离：只认「行首 / 空白 / 标点」之后的 // 与 /*，字符串里的 https:// 与 /api/* 不受影响
_LINE_COMMENT = re.compile(r"(^|[\s;{}(),])//[^\n]*")
_BLOCK_COMMENT = re.compile(r"(^|[\s;{}(),])/\*.*?\*/", re.S)
_HTML_COMMENT = re.compile(r"<!--.*?-->", re.S)

#: 已知死代码链的不可达路径（前端占位 ``*`` = 模板插值段）。🔴 只许删除，不许新增。
#: 链：``apiPaths/system.ts`` 的 ``ai.chat.knowledge`` / ``aiProject.knowledgeIndex``
#: → 仅 ``aiApi.ts`` 的 ``knowledgeBase`` 使用 → 仅 ``components/ai/KnowledgeBasePanel.vue`` 使用
#: → 该组件零挂载（只被死 barrel ``components/ai/index.js`` 与自动生成的 ``components.d.ts`` 提及）。
_KNOWN_DEAD_PATHS: dict[str, str] = {
    "/api/ai/chat/knowledge/search": "KnowledgeBasePanel 死链（零挂载）",
    "/api/ai/chat/knowledge": "KnowledgeBasePanel 死链（零挂载）",
    "/api/ai/chat/knowledge/*": "KnowledgeBasePanel 死链（零挂载）",
    "/api/projects/*/knowledge/index/build": "KnowledgeBasePanel 死链（零挂载）",
    "/api/projects/*/knowledge/index/status": "KnowledgeBasePanel 死链（零挂载）",
}

#: 本 spec 删除的路径：不得回到前端源码
_REMOVED_PATHS = frozenset({
    "/api/knowledge/search",
    "/api/knowledge/*",
    "/api/knowledge/*/upload",
    "/api/knowledge/*/*",
    "/api/projects/*/knowledge",
})


def strip_comments(text: str) -> str:
    return _LINE_COMMENT.sub(r"\1", _BLOCK_COMMENT.sub(r"\1", _HTML_COMMENT.sub("", text)))


def normalize(raw: str) -> str | None:
    """``${…}`` → ``*``，去 query / hash；段内拼接（``prefix${x}``）无法静态判定 → None。"""
    path = _PLACEHOLDER.sub("*", raw).split("?")[0].split("#")[0].rstrip("/")
    if any("*" in seg and seg != "*" for seg in path.split("/")):
        return None
    return path or None


def is_knowledge_path(path: str) -> bool:
    return any(seg.startswith("knowledge") for seg in path.split("/"))


def _is_production_source(f: Path) -> bool:
    return (
        f.suffix in (".ts", ".vue")
        and "__tests__" not in f.parts
        and not f.name.endswith((".spec.ts", ".test.ts", ".stories.ts", ".d.ts"))
    )


def knowledge_literals(src_root: Path = _SRC) -> list[tuple[str, str]]:
    """``[(相对文件, 规范化路径)]``：前端生产源码中含 knowledge 段的 ``/api/`` 字面量。"""
    out: list[tuple[str, str]] = []
    for f in sorted(src_root.rglob("*")):
        if not _is_production_source(f):
            continue
        text = strip_comments(f.read_text(encoding="utf-8", errors="replace"))
        for m in _LITERAL.finditer(text):
            path = normalize(m.group(2))
            if path and is_knowledge_path(path):
                out.append((f.relative_to(src_root).as_posix(), path))
    return out


def resolves(frontend_path: str, backend_paths: list[str]) -> bool:
    fe = [s for s in frontend_path.split("/") if s]
    for bp in backend_paths:
        be = [s for s in bp.split("/") if s]
        if len(be) != len(fe):
            continue
        if all(b.startswith("{") or (f != "*" and f == b) for b, f in zip(be, fe)):
            return True
    return False


@pytest.fixture(scope="module")
def backend_paths() -> list[str]:
    from app.main import app  # 延迟 import：构建 app 较重

    return sorted({p for p in (getattr(r, "path", "") for r in app.routes) if p})


@pytest.fixture(scope="module")
def literals() -> list[tuple[str, str]]:
    return knowledge_literals()


def test_scan_surface_is_not_empty(backend_paths, literals):
    """防空转：路由表或扫描面异常小时，下面的断言会全体假绿。"""
    assert len(backend_paths) >= 2000, len(backend_paths)
    assert len(literals) >= 15, literals
    assert any(p.startswith("/api/knowledge-library/") for _, p in literals)


def test_every_frontend_knowledge_path_resolves(backend_paths, literals):
    missing = sorted(
        {(f, p) for f, p in literals if p not in _KNOWN_DEAD_PATHS and not resolves(p, backend_paths)}
    )
    assert not missing, (
        "前端引用了后端不存在的知识库路由（请求恒 404，调用方多半把失败吞成「无结果」）：\n"
        + "\n".join(f"  {p}    <- {f}" for f, p in missing)
    )


def test_removed_paths_do_not_come_back(literals):
    back = sorted({(f, p) for f, p in literals if p in _REMOVED_PATHS})
    assert not back, f"已删除的不存在路由又回到了前端源码：{back}"


def test_known_dead_paths_have_no_stale_entries(backend_paths, literals):
    """登记只许向下：死链路径已不在前端、或后端已补上路由 → 必须从 ``_KNOWN_DEAD_PATHS`` 删除。"""
    present = {p for _, p in literals}
    stale = sorted(p for p in _KNOWN_DEAD_PATHS if p not in present or resolves(p, backend_paths))
    assert not stale, f"请从 _KNOWN_DEAD_PATHS 删除：{stale}"


def test_dead_chain_is_still_unmounted():
    """``_KNOWN_DEAD_PATHS`` 的豁免前提是「死链零挂载」—— 这里把前提本身钉死（可伪证）。"""
    mounts: list[str] = []
    users: list[str] = []
    for f in sorted(_SRC.rglob("*")):
        if not _is_production_source(f):
            continue
        rel = f.relative_to(_SRC).as_posix()
        text = strip_comments(f.read_text(encoding="utf-8", errors="replace"))
        if rel != "components/ai/KnowledgeBasePanel.vue" and re.search(
            r"<KnowledgeBasePanel\b|<knowledge-base-panel\b|import\s+KnowledgeBasePanel\b|KnowledgeBasePanel\.vue", text
        ):
            mounts.append(rel)
        if rel not in ("components/ai/KnowledgeBasePanel.vue", "services/aiApi.ts") and re.search(
            r"\bknowledgeBase\.|aiApi\.knowledgeBase|\{[^}]*\bknowledgeBase\b[^}]*\}\s*from\s*['\"]@/services/aiApi", text
        ):
            users.append(rel)
    assert not mounts, f"KnowledgeBasePanel 被挂载/引用了，它调用的 5 个路径在后端不存在，须先修：{mounts}"
    assert not users, f"aiApi.knowledgeBase 有了新调用方，它的路径在后端不存在，须先修：{users}"


def test_matcher_and_scanner_self_check(tmp_path):
    """双向自检：不存在的路径必须报、存在的必须放行、注释里的不算、``*`` 不得匹配字面段。"""
    backend = [
        "/api/knowledge-library/folders/{folder_id}/documents",
        "/api/knowledge/libraries",
        "/api/knowledge/tsj/{cycle_name}",
    ]
    assert resolves("/api/knowledge-library/folders/*/documents", backend)
    assert resolves("/api/knowledge/tsj/*", backend)
    assert not resolves("/api/knowledge/search", backend)
    assert not resolves("/api/knowledge/*", backend), "* 只能匹配后端 {参数} 段，不得匹配字面段 libraries"
    assert not resolves("/api/knowledge-library/folders/*", backend), "段数不等不得匹配"

    (tmp_path / "a.ts").write_text(
        "const ok = `/api/knowledge-library/folders/${id}/documents?x=1`\n"
        "// const dead = '/api/knowledge/commented'\n"
        "/* const dead2 = '/api/knowledge/block' */\n"
        "const url = 'https://example.com/api/knowledge/not-a-path'\n"
        "const bad = '/api/knowledge/search'\n"
        "const mixed = `/api/knowledge/pre${x}`\n",
        encoding="utf-8",
    )
    (tmp_path / "b.vue").write_text(
        "<template><!-- <a href=\"/api/knowledge/html-comment\" /> --></template>\n"
        "<script setup lang=\"ts\">const u = \"/api/projects/${pid}/knowledge/index/build\"</script>\n",
        encoding="utf-8",
    )
    (tmp_path / "__tests__").mkdir()
    (tmp_path / "__tests__" / "c.ts").write_text("const t = '/api/knowledge/test-only'", encoding="utf-8")
    found = sorted(p for _, p in knowledge_literals(tmp_path))
    assert found == [
        "/api/knowledge-library/folders/*/documents",
        "/api/knowledge/search",
        "/api/projects/*/knowledge/index/build",
    ], found
