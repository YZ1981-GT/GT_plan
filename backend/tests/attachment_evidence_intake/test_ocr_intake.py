"""底稿 OCR 端点先建附件再识别（spec attachment-evidence-intake 需求 2，ADR-AEI-05）。

回归背景：26 个底稿 OCR 路由把文件写到 ``storage/workpapers/{wp}/…`` 旁路目录，附件表没有记录（只有 E1 的 4 个
先建附件，建失败时退回临时 id）；带 ``attachment_id`` 时不校项目与关联，能读走任意项目附件的识别全文；8 个路由
识别结果不写回任何地方；一批路由识别失败时直接返回，附件会停在「识别中」。
识别引擎与大模型在被测路由模块的下一层打桩（``UnifiedOCRService`` / ``chat_completion``），入口与写回走生产代码。
"""
from __future__ import annotations

import ast
import importlib
import uuid
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import sqlalchemy as sa

from app.models.attachment_models import Attachment
from app.models.core import ProjectStatus
from app.services import workpaper_evidence_intake
from tests.attachment_evidence_intake._helpers import count, links_of, ocr_world, pdf, unwrap
from tests.attachment_security_baseline._world import add_attachment

OCR_TEXT = "识别全文：合同编号 HT-2026-001，金额 1000 元"
APP = Path(__file__).resolve().parents[2] / "app"

#: (模块, URL 尾段, 底稿编码, 缺省证据类型)
ROUTES = [
    ("_d4_contract_ocr", "d4/contract-ocr", "D4-2", "contract"),
    ("_d2_derecognition", "d2/derecognition-ocr", "D2-3", "contract"),
    ("_e1_account_list_ocr", "e1/account-list-ocr", "E1-10", "support"),
    ("_e1_commit_ocr", "e1/commit-ocr", "E1-11", "support"),
    ("_e1_credit_ocr", "e1/credit-ocr", "E1-18", "support"),
    ("_e1_statement_ocr", "e1/statement-ocr", "E1-31", "bank_statement"),
    ("_e1_cutoff_ocr", "e1/cutoff-ocr", "E1-21", "voucher"),
    ("_e1_large_check_ocr", "e1/large-check-ocr", "E1-23", "voucher"),
    ("_f2_contract_ocr", "f2/contract-ocr", "F2-30", "contract"),
    ("_f2_special_contract_ocr", "f2-spe/contract-ocr", "F2-56", "contract"),
    ("_f2_stocktake_contract_ocr", "f2-st/contract-ocr?sheet=F2-25", "F2-25", "stocktake"),
    ("_f2_valuation_contract_ocr", "f2-val/contract-ocr", "F2-47", "evidence"),
    ("_f3_contract_ocr", "f3/contract-ocr", "F3-5", "note"),
    ("_f4_contract_ocr", "f4/contract-ocr", "F4-5", "evidence"),
    ("_f5_contract_ocr", "f5/contract-ocr", "F5-6", "voucher"),
    ("_g1_contract_ocr", "g1/contract-ocr", "G1-14", "contract"),
    ("_g8_contract_ocr", "g8/contract-ocr", "G8-3", "voucher"),
    ("_g9_contract_ocr", "g9/contract-ocr", "G9-3", "voucher"),
    ("_g10_contract_ocr", "g10/contract-ocr", "G10-3", "voucher"),
    ("_g11_contract_ocr", "g11/contract-ocr", "G11-3", "voucher"),
    ("_h1_property_ocr", "h1/property-title-ocr", "H1-16", "contract"),
    ("_h1_property_ocr", "h1/vehicle-title-ocr", "H1-17", "contract"),
    ("_h1_stocktake_summary_ocr", "h1/stocktake-summary-ocr", "H1-11", "stocktake"),
    ("_h3_contract_ocr", "h3/contract-ocr", "H3-5", "contract"),
    ("_h3_property_ocr", "h3/real-estate-title-ocr", "H3-12", "contract"),
    ("n2_taxes_payable", "N2", "N2-3", "voucher"),
]
IDS = [route[1].split("?")[0] for route in ROUTES]
#: 三类改造形态各取一个（复用+旁路 / 先建附件再写旁路 / 原来不写回）+ N2
SAMPLE = [ROUTES[0], ROUTES[4], ROUTES[20], ROUTES[25]]


def _url(tail: str, wp_id) -> str:
    if tail == "N2":
        return f"/api/n2-taxes-payable/{wp_id}/contract-ocr"
    return f"/api/workpapers/{wp_id}/{tail}"


def _module(name: str):
    return importlib.import_module(("app.routers." if name == "n2_taxes_payable" else "app.routers.wp_render_strategies.") + name)


@contextmanager
def _engines(module, *, text: str = OCR_TEXT, ocr_error: Exception | None = None):
    ocr = MagicMock()
    ocr.return_value.recognize = AsyncMock(return_value={"text": text}, side_effect=ocr_error)
    with patch.object(module, "UnifiedOCRService", ocr), patch.object(
        module, "chat_completion", AsyncMock(return_value="{}"),
    ):
        yield ocr.return_value.recognize


async def _only_attachment(db) -> Attachment:
    rows = (await db.execute(sa.select(Attachment))).scalars().all()
    assert len(rows) == 1, [r.file_name for r in rows]
    await db.refresh(rows[0])
    return rows[0]


@pytest.mark.parametrize(("module_name", "tail", "wp_code", "etype"), ROUTES, ids=IDS)
async def test_upload_creates_linked_attachment_and_writes_back(monkeypatch, tmp_path, module_name, tail, wp_code, etype):
    module = _module(module_name)
    async with ocr_world(monkeypatch, tmp_path, module.router, wp_code=wp_code) as w:
        with _engines(module) as recognize:
            resp = await w.client.post(_url(tail, w.wp.id), files=pdf("证据.pdf"))
        assert resp.status_code == 200, resp.text
        att = await _only_attachment(w.db)
        assert (att.attachment_type, att.reference_type, att.reference_id, att.created_by) == (
            etype, "working_paper", w.wp.id, w.user.id,
        )
        assert (att.ocr_text, att.ocr_status, att.version) == (OCR_TEXT, "completed", 1)
        wp_links, ev_links = await links_of(w.db, att.id)
        assert [(link.wp_id, link.association_type) for link in wp_links] == [(w.wp.id, etype)]
        assert ev_links == []
        assert unwrap(resp.json()).get("attachment_id") == str(att.id)
        recognize.assert_awaited_once()
        assert Path(recognize.await_args.args[0]).resolve() == Path(att.file_path).resolve()  # 识别的就是附件原件
    assert not (tmp_path / "storage" / "workpapers").exists()


@pytest.mark.parametrize(("module_name", "tail", "wp_code", "etype"), ROUTES, ids=IDS)
async def test_ocr_failure_marks_attachment_failed(monkeypatch, tmp_path, module_name, tail, wp_code, etype):
    module = _module(module_name)
    async with ocr_world(monkeypatch, tmp_path, module.router, wp_code=wp_code) as w:
        with _engines(module, ocr_error=RuntimeError("识别服务不可用")):
            resp = await w.client.post(_url(tail, w.wp.id), files=pdf("证据.pdf"))
        assert resp.status_code == 200, resp.text
        att = await _only_attachment(w.db)
        assert att.ocr_status == "failed"  # 文件已留档，状态如实为失败，不停在「识别中」
        assert unwrap(resp.json()).get("attachment_id") == str(att.id)


@pytest.mark.parametrize(("module_name", "tail", "wp_code", "etype"), SAMPLE, ids=[r[1] for r in SAMPLE])
async def test_foreign_or_unlinked_attachment_is_404(monkeypatch, tmp_path, module_name, tail, wp_code, etype):
    module = _module(module_name)
    async with ocr_world(monkeypatch, tmp_path, module.router, wp_code=wp_code) as w:
        other = await w.world.project(name="【测试】他项目")
        foreign = await add_attachment(w.world, other, ocr_text="他项目机密识别文本", ocr_status="completed")
        loose = await add_attachment(w.world, w.world.target, ocr_text="未关联本底稿的识别文本", ocr_status="completed")
        for att in (foreign, loose):
            with _engines(module) as recognize:
                resp = await w.client.post(_url(tail, w.wp.id), files=pdf(), data={"attachment_id": str(att.id)})
            assert resp.status_code == 404, resp.text
            assert "识别文本" not in resp.text
            recognize.assert_not_awaited()
        assert await count(w.db, Attachment) == 2  # 没有因此新建附件


async def test_reuse_and_force_reocr_read_stored_original(monkeypatch, tmp_path):
    module = _module("_d4_contract_ocr")
    async with ocr_world(monkeypatch, tmp_path, module.router, wp_code="D4-2") as w:
        url = _url("d4/contract-ocr", w.wp.id)
        with _engines(module):
            first = await w.client.post(url, files=pdf("合同.pdf"))
        att_id = unwrap(first.json())["attachment_id"]
        other_file = pdf("另一个文件.pdf", b"%PDF-1.4 other")
        with _engines(module, text="不该被用到") as recognize:
            reused = unwrap((await w.client.post(url, files=other_file, data={"attachment_id": att_id})).json())
        assert (reused["reused"], reused["ocr_text"]) == (True, OCR_TEXT)
        recognize.assert_not_awaited()
        with _engines(module, text="重新识别的全文") as recognize:
            forced = await w.client.post(
                url, files=pdf("另一个文件.pdf", b"%PDF-1.4 other"), data={"attachment_id": att_id, "force_reocr": "true"},
            )
        assert forced.status_code == 200, forced.text
        att = await _only_attachment(w.db)
        assert Path(recognize.await_args.args[0]).resolve() == Path(att.file_path).resolve()
        assert att.ocr_text == "重新识别的全文"


async def test_borrowed_endpoint_uses_declaration_default(monkeypatch, tmp_path):
    """``d4/contract-ocr`` 被 C 类当通用识别口时不再一律记成合同。"""
    module = _module("_d4_contract_ocr")
    async with ocr_world(monkeypatch, tmp_path, module.router, wp_code="C23-2") as w:
        with _engines(module):
            resp = await w.client.post(_url("d4/contract-ocr", w.wp.id), files=pdf())
        assert resp.status_code == 200, resp.text
        assert (await _only_attachment(w.db)).attachment_type == "evidence"


async def test_row_position_writes_evidence_link_only(monkeypatch, tmp_path):
    module = _module("_f3_contract_ocr")
    async with ocr_world(monkeypatch, tmp_path, module.router, wp_code="F3-5") as w:
        with _engines(module):
            resp = await w.client.post(
                _url("f3/contract-ocr", w.wp.id), files=pdf(),
                data={"evidence_sheet": "F3-5", "evidence_cell": "item:3", "evidence_type": "voucher"},
            )
        assert resp.status_code == 200, resp.text
        att = await _only_attachment(w.db)
        wp_links, ev_links = await links_of(w.db, att.id)
        assert wp_links == []
        assert [(e.sheet_name, e.cell_ref, e.evidence_type) for e in ev_links] == [("F3-5", "item:3", "voucher")]
        assert (att.attachment_type, att.reference_type, att.ocr_text) == ("voucher", "workpaper_item", OCR_TEXT)


@pytest.mark.parametrize("case", ["too_large", "unsafe", "archived", "missing_wp", "bad_wp"])
async def test_rejections_write_nothing(monkeypatch, tmp_path, case):
    module = _module("_d4_contract_ocr")
    async with ocr_world(monkeypatch, tmp_path, module.router, wp_code="D4-2") as w:
        wp_id, files, expected = w.wp.id, pdf(), {
            "too_large": 413, "unsafe": 422, "archived": 423, "missing_wp": 404, "bad_wp": 400,
        }[case]
        if case == "too_large":
            monkeypatch.setattr(workpaper_evidence_intake, "max_upload_bytes", lambda: 4)
        elif case == "unsafe":
            files = pdf("看着像合同.pdf", b"MZ\x90\x00\x03\x00\x00\x00")
        elif case == "archived":
            w.world.target.status = ProjectStatus.archived
            await w.db.flush()
        elif case == "missing_wp":
            wp_id = uuid.uuid4()
        elif case == "bad_wp":
            wp_id = "not-a-uuid"
        with _engines(module) as recognize:
            resp = await w.client.post(_url("d4/contract-ocr", wp_id), files=files)
        assert resp.status_code == expected, resp.text
        assert await count(w.db, Attachment) == 0
        recognize.assert_not_awaited()


# ── 静态守卫 ──


def _route_modules() -> list[Path]:
    return sorted((APP / "routers" / "wp_render_strategies").glob("_*.py")) + [APP / "routers" / "n2_taxes_payable.py"]


def _docstring_ids(tree: ast.AST) -> set[int]:
    """模块 / 类 / 函数的文档字符串节点（说明改造前做法的文字不算代码）。"""
    ids: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
                ids.add(id(first.value))
    return ids


def _side_storage_offenders(source: str, rel: str) -> list[str]:
    tree = ast.parse(source)
    docs = _docstring_ids(tree)  # tree 存活期间节点不回收，id 不会复用
    found = []
    for node in ast.walk(tree):
        if id(node) in docs:
            continue
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and "storage/workpapers" in node.value:
            found.append(f"{rel}:{node.lineno}")
        if isinstance(node, ast.Name) and node.id in {"side_storage_dir", "provision_wp_linked_attachment"}:
            found.append(f"{rel}:{node.lineno}:{node.id}")
    return found


def test_side_storage_scanner_ignores_docstrings_only():
    """双向：代码里的旁路路径与旧函数名必须报出，文档字符串里的说明不报。"""
    code = 'def f():\n    """改造前写 storage/workpapers/x"""\n    return "storage/workpapers/" + side_storage_dir()\n'
    assert _side_storage_offenders(code, "x.py") == ["x.py:3", "x.py:3:side_storage_dir"]
    assert _side_storage_offenders('"""旧做法 storage/workpapers/{wp}"""\n', "y.py") == []


def test_no_side_storage_left_in_app():
    assert not (APP / "services" / "workpaper_side_storage.py").exists()
    offenders = []
    for py in sorted(APP.rglob("*.py")):
        # 仓库里有带 BOM 的源文件
        offenders += _side_storage_offenders(py.read_text(encoding="utf-8-sig"), py.relative_to(APP).as_posix())
    assert offenders == []


def test_every_ocr_route_goes_through_intake():
    """防空转：本文件参数化覆盖的 26 个路由 = 源码里调用 ``intake_ocr_upload`` 的路由。"""
    calls = 0
    for py in _route_modules():
        for node in ast.walk(ast.parse(py.read_text(encoding="utf-8-sig"))):
            if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "intake_ocr_upload":
                calls += 1
    assert calls == len(ROUTES) == 26
