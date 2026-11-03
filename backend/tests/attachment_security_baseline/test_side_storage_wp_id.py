"""底稿 OCR 端点的底稿 ID 校验与旁路目录（spec attachment-security-baseline 需求 1.6，ADR-ASB-07）。

回归背景：26 个底稿 OCR 端点把上传文件写到 ``storage/workpapers/{wp_id}/{子目录}/``，目录段用路径参数原文。
14 个端点在 ``wp_id`` 不是 UUID 时兜底成全零 UUID 继续写盘、识别、调大模型，另有端点完全不校验；
路由级 ``dedicated_wp_gate`` 对非 UUID 路径段按设计不判定 ⇒ 任何登录用户都能借这些端点落盘、耗识别算力。

spec attachment-evidence-intake 起这些端点先经证据入口建附件再识别，旁路目录与 ``workpaper_side_storage`` 已删除：
本文件保留「非 UUID ⇒ 400 且无副作用」「生产代码不拼旁路目录、不兜底全零 UUID」两条；
建附件、写回与 26 个路由逐个覆盖见 ``tests/attachment_evidence_intake/test_ocr_intake.py``。
"""
from __future__ import annotations

import ast
import functools
import io
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient

from app.core.database import get_db
from app.deps import get_current_user
from app.models.base import UserRole
from app.routers._wp_gate import include_router_with_wp_gate
from app.routers.wp_render_strategies._d2_derecognition import router as d2_router
from app.routers.wp_render_strategies._d4_contract_ocr import router as d4_router
from app.services.workpaper_evidence_intake import parse_workpaper_id

APP_DIR = Path(__file__).resolve().parents[2] / "app"
#: 底稿 OCR 端点所在位置（全零 UUID 兜底只在这里出现过）
OCR_SOURCES = sorted((APP_DIR / "routers" / "wp_render_strategies").glob("*.py")) + [
    APP_DIR / "routers" / "n2_taxes_payable.py",
]
PDF = b"%PDF-1.4\n%side-storage\n"


# ── 底稿 ID 解析 ──

def test_parse_accepts_uuid_forms():
    wp = uuid4()
    assert parse_workpaper_id(str(wp)) == wp
    assert parse_workpaper_id(str(wp).upper()) == wp
    assert parse_workpaper_id(wp) is wp


@pytest.mark.parametrize("raw", ["test-wp-id", "..", "", " ", "00000000", "a..b", None])
def test_parse_rejects_non_uuid(raw):
    with pytest.raises(HTTPException) as exc:
        parse_workpaper_id(raw)
    assert exc.value.status_code == 400
    assert exc.value.detail == "无效的底稿 ID"


# ── AST 守卫：生产代码不拼旁路目录、不兜底全零 UUID ──

def _docstring_nodes(tree: ast.AST) -> set[int]:
    ids: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, "body", [])
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                ids.add(id(body[0].value))
    return ids


def _div_operands(node: ast.BinOp) -> list[ast.AST]:
    left = node.left
    ops = [node.right]
    while isinstance(left, ast.BinOp) and isinstance(left.op, ast.Div):
        ops.append(left.right)
        left = left.left
    ops.append(left)
    return list(reversed(ops))


def _is_path_call(node: ast.AST, literal: str) -> bool:
    if not isinstance(node, ast.Call) or not node.args:
        return False
    func = node.func
    name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
    arg = node.args[0]
    return name == "Path" and isinstance(arg, ast.Constant) and arg.value == literal


def side_path_violations(source: str) -> list[int]:
    """返回拼 ``storage/workpapers`` 旁路目录的行号（docstring 里的说明不算）。"""
    tree = ast.parse(source)
    docstrings = _docstring_nodes(tree)
    lines: list[int] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docstrings:
            if "storage/workpapers" in node.value:
                lines.append(node.lineno)
        elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
            ops = _div_operands(node)
            if (
                len(ops) >= 2
                and _is_path_call(ops[0], "storage")
                and isinstance(ops[1], ast.Constant)
                and ops[1].value == "workpapers"
            ):
                lines.append(node.lineno)
    return sorted(set(lines))


def zero_uuid_calls(source: str) -> list[int]:
    lines = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
        if name == "UUID" and any(
            k.arg == "int" and isinstance(k.value, ast.Constant) and k.value.value == 0 for k in node.keywords
        ):
            lines.append(node.lineno)
    return lines


@pytest.mark.parametrize(
    ("snippet", "expected"),
    [
        ('storage_dir = Path("storage/workpapers") / wp_id / "contracts"', 1),
        ('storage_dir = pathlib.Path("storage/workpapers") / wp_id', 1),
        ('p = f"storage/workpapers/{wp_id}/vouchers"', 1),
        ('p = os.path.join("storage/workpapers", wp_id)', 1),
        ('p = Path("storage") / "workpapers" / wp_id / "x"', 1),
        ('p = Path("storage") / "projects" / str(pid) / "workpapers"', 0),
        ('def f():\n    """写到 storage/workpapers/{wp_id}/ 下"""\n    return wp_id', 0),
    ],
)
def test_side_path_detector_is_not_vacuous(snippet, expected):
    assert len(side_path_violations(snippet)) == expected


@pytest.mark.parametrize(
    ("snippet", "expected"),
    [("wp_uuid = UUID(int=0)", 1), ("x = uuid.UUID(int=0)", 1), ("x = UUID(int=1)", 0), ("x = UUID(wp_id)", 0)],
)
def test_zero_uuid_detector_is_not_vacuous(snippet, expected):
    assert len(zero_uuid_calls(snippet)) == expected


@functools.lru_cache(maxsize=1)
def _app_sources() -> dict[Path, str]:
    # utf-8-sig：仓库里有带 BOM 的源文件，按 utf-8 读 ast.parse 会报 U+FEFF
    return {py: py.read_text(encoding="utf-8-sig") for py in sorted(APP_DIR.rglob("*.py"))}


def test_no_side_storage_path_in_app():
    """旁路目录已整体退役（文件一律经证据入口进附件存储）：生产代码里一处都不能再拼。"""
    offenders = {}
    for py, src in _app_sources().items():
        hits = side_path_violations(src)
        if hits:
            offenders[py.relative_to(APP_DIR).as_posix()] = hits
    assert offenders == {}, f"底稿文件只能经证据入口落到附件存储：{offenders}"


def test_no_zero_uuid_fallback_in_ocr_endpoints():
    assert any(p.name == "_d4_contract_ocr.py" for p in OCR_SOURCES), "扫描范围为空"
    offenders = {
        p.relative_to(APP_DIR).as_posix(): zero_uuid_calls(p.read_text(encoding="utf-8-sig"))
        for p in OCR_SOURCES
    }
    assert {k: v for k, v in offenders.items() if v} == {}


# ── 端点：非 UUID ⇒ 400，不落盘、不调识别 ──

def _app() -> FastAPI:
    app = FastAPI()
    include_router_with_wp_gate(app, d4_router)  # 与生产注册同一 helper（带路由级可见性门）
    include_router_with_wp_gate(app, d2_router)

    async def _db():
        yield AsyncMock()

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=uuid4(), role=UserRole.auditor)
    return app


def _entries(base: Path) -> list[str]:
    return sorted(p.relative_to(base).as_posix() for p in base.rglob("*"))


@pytest.mark.parametrize(
    ("path", "ocr_target"),
    [
        ("/api/workpapers/{wp}/d4/contract-ocr", "app.routers.wp_render_strategies._d4_contract_ocr.UnifiedOCRService"),
        ("/api/workpapers/{wp}/d2/derecognition-ocr", "app.routers.wp_render_strategies._d2_derecognition.UnifiedOCRService"),
    ],
)
async def test_non_uuid_wp_id_rejected_before_side_effects(tmp_path, monkeypatch, path, ocr_target):
    monkeypatch.chdir(tmp_path)  # 任何相对路径落盘都会留在这里
    with patch(ocr_target) as ocr_cls:
        ocr_cls.return_value.recognize = AsyncMock(return_value={"text": ""})
        async with AsyncClient(transport=ASGITransport(app=_app()), base_url="http://t") as client:
            resp = await client.post(
                path.format(wp="not-a-uuid"),
                files={"file": ("c.pdf", io.BytesIO(PDF), "application/pdf")},
            )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "无效的底稿 ID"
    assert _entries(tmp_path) == []
    ocr_cls.return_value.recognize.assert_not_called()


async def test_valid_uuid_reaches_ocr(tmp_path, monkeypatch):
    """正向对照：合法底稿时同一请求确实走到识别（上一条的「没调识别」不是夹具空转）。"""
    from tests.attachment_evidence_intake._helpers import ocr_world

    target = "app.routers.wp_render_strategies._d4_contract_ocr.UnifiedOCRService"
    async with ocr_world(monkeypatch, tmp_path, d4_router) as w:
        with patch(target) as ocr_cls:
            ocr_cls.return_value.recognize = AsyncMock(return_value={"text": ""})
            resp = await w.client.post(
                f"/api/workpapers/{str(w.wp.id).upper()}/d4/contract-ocr",
                files={"file": ("c.pdf", io.BytesIO(PDF), "application/pdf")},
            )
    assert resp.status_code == 200, resp.text
    ocr_cls.return_value.recognize.assert_awaited_once()
    assert not (tmp_path / "storage" / "workpapers").exists()
