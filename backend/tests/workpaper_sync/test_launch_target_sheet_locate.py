"""「打开即定位到目标 sheet」的参数链守卫。

链路（一处装配、所有整册底稿受益）::

    前端组件 sheetKey ('d4-26-managed')
      → materialize body.sheet_key
      → MaterializeRequest.sheet_key
      → room_launch.resolve_launch_target_sheet(contract, sheet_key)  ← 契约是唯一真源
      → sign_room_contents_token(sheet='境外销售收入检查D4-26')        ← 进签名 claim
      → GET /rooms/{id}/contents → verify → claims.sheet
      → derive_bytes_with_active_sheet(artifact_bytes, claims.sheet)  ← 派生 activeTab
      → 端点回**字节流**（非 FileResponse(path)）                      ← 否则定位结果被丢

改动前该链路两处断开：`_attach_launch_urls` 签 token 时不传 `sheet`（于是 claim 恒空、
`derive_bytes_with_active_sheet` 永不触发），`get_room_contents` 又无条件
`FileResponse(resolved.path)`（于是即便有派生字节也被丢掉）。两处都有单测覆盖到"各自能跑"，
但没有任何判据看"参数有没有从头走到尾" —— 本文件就是那条判据。

🔴 为什么「多个文档」必须靠契约而不是 wp_code：`backend/wp_templates/D` 下 D4 有 9 份
xlsx，`D4-1至D4-4 …（Leap-常规程序）.xlsx` 只有 10 张 sheet、**不含** D4-26。按 wp_code
找模板会打开那一份，定位必然落空；按 entry 契约找则钉在 `D/D4 收入底稿.xlsx`（46 张
sheet / 13 张受管），文档与定位一次解析同时确定。见 `test_the_wrong_d4_document_…`。
"""

from __future__ import annotations

import ast
import io
import re
import uuid
import zipfile
from pathlib import Path

import pytest

from app.services.workpaper_sync.adapters.registry import (
    DELIVERED_PER_ENTRY_CONTRACTS,
)
from app.services.workpaper_sync.contracts import load_contract
from app.services.workpaper_sync.excel_sheet_visibility import (
    derive_bytes_with_active_sheet,
    read_sheet_entries,
)
from app.services.workpaper_sync import room_launch as RL

_BACKEND = Path(__file__).resolve().parents[2]
_TEMPLATES = _BACKEND / "wp_templates"
_ROUTER_PY = _BACKEND / "app" / "routers" / "wp_sync_router.py"

_SECRET = "launch-locate-secret"

#: 实证冻结（`scripts/_probe_*` 实跑）：D4-26 的 entry / sheet_key / 物理名 / 载体文档。
D4_ENTRY = "xlsx/gt-d4-operating-revenue"
D4_26_SHEET_KEY = "d4-26-managed"
D4_26_SHEET_NAME = "境外销售收入检查D4-26"
D4_WORKBOOK_REL = "D/D4 收入底稿.xlsx"
#: 同一 wp_code 的**另一份**文档：按 wp_code 解析主模板时会拿到它，而它没有 D4-26。
D4_WRONG_WORKBOOK_REL = "D/D4-1至D4-4 营业收入 - 审定表明细表（Leap-常规程序）.xlsx"


# ═══════════════════════════════════════════════════════════════════════════
# 辅助
# ═══════════════════════════════════════════════════════════════════════════


def _delivered_rows() -> list[tuple[str, str, str]]:
    """(entry_id, contract_id, template_relative_path) —— 已交付 per-entry 契约登记行。"""
    out: list[tuple[str, str, str]] = []
    for row in DELIVERED_PER_ENTRY_CONTRACTS:
        entry = str(row.get("entry_id") or "").strip()
        contract_id = str(row.get("contract_id") or "").strip()
        if entry and contract_id:
            out.append((entry, contract_id, str(row.get("template_relative_path") or "")))
    return out


def _active_tab(data: bytes) -> str:
    """`xl/workbook.xml` 的 `<workbookView activeTab=...>`；缺省算 "0"。"""
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        xml = zf.read("xl/workbook.xml").decode("utf-8")
    view = re.search(r"<workbookView[^>]*>", xml)
    if not view:
        return "0"
    hit = re.search(r'activeTab="(\d+)"', view.group(0))
    return hit.group(1) if hit else "0"


def _tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"))


def _func(tree: ast.Module, name: str) -> ast.AsyncFunctionDef | ast.FunctionDef:
    for node in ast.walk(tree):
        if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)) and node.name == name:
            return node
    raise AssertionError(f"找不到函数 {name!r}")


def _call_has_kwarg(fn: ast.AST, callee: str, kwarg: str) -> bool:
    """`fn` 体内是否存在 `callee(..., kwarg=...)` 调用（callee 按名或属性名匹配）。"""
    for node in ast.walk(fn):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = (
            func.id if isinstance(func, ast.Name)
            else func.attr if isinstance(func, ast.Attribute)
            else ""
        )
        if name == callee and any(kw.arg == kwarg for kw in node.keywords):
            return True
    return False


# ═══════════════════════════════════════════════════════════════════════════
# 1. sheet_key → 物理 sheet 名（契约是唯一真源）
# ═══════════════════════════════════════════════════════════════════════════


def test_d4_26_sheet_key_resolves_to_its_physical_sheet_name() -> None:
    contract = load_contract("d4.revenue_detail")
    assert RL.resolve_launch_target_sheet(
        contract=contract, sheet_key=D4_26_SHEET_KEY
    ) == D4_26_SHEET_NAME


def test_d4_entry_shares_one_workbook_across_many_managed_sheets() -> None:
    """定位必须**每次打开**算：13 张受管 sheet 共用同一份 artifact，activeTab 只能有一个值。"""
    contract = load_contract("d4.revenue_detail")
    names = {
        RL.resolve_launch_target_sheet(contract=contract, sheet_key=s.sheet_key)
        for s in contract.sheets
    }
    assert len(contract.sheets) >= 13
    assert len(names) == len(contract.sheets), "受管 sheet 的物理名必须两两不同"
    assert str(contract.template.relative_path) == D4_WORKBOOK_REL


def test_unresolvable_inputs_degrade_to_empty_not_guesswork() -> None:
    """反向自检：解析不到必须回空串（= 不定位），绝不从 sheet_key 反推名字。"""
    contract = load_contract("d4.revenue_detail")
    for bad in ("", "   ", "__definitely_not_a_sheet_key__", "d4-26", "D4-26"):
        assert RL.resolve_launch_target_sheet(contract=contract, sheet_key=bad) == "", (
            f"sheet_key={bad!r} 不该解析出任何 sheet —— 只认契约声明的键"
        )
    assert RL.resolve_launch_target_sheet(contract=None, sheet_key=D4_26_SHEET_KEY) == ""


def test_every_delivered_entry_resolves_all_declared_sheet_keys() -> None:
    """覆盖面：一处装配 ⇒ 全部已交付 entry 的每个受管 sheet 都能解析（不是只 D4 特例）。"""
    rows = _delivered_rows()
    assert len(rows) >= 10, f"已交付 per-entry 契约只有 {len(rows)} 条，覆盖面判据失效"
    for entry, contract_id, _tpl in rows:
        contract = load_contract(contract_id)
        for sheet in contract.sheets:
            got = RL.resolve_launch_target_sheet(
                contract=contract, sheet_key=sheet.sheet_key
            )
            assert got == sheet.excel_name, (
                f"{entry} 的 {sheet.sheet_key!r} 解析成 {got!r}，契约声明 {sheet.excel_name!r}"
            )


# ═══════════════════════════════════════════════════════════════════════════
# 2. 多个文档：定位目标必须落在**本 entry 自己那份**工作簿里
# ═══════════════════════════════════════════════════════════════════════════


def test_resolved_target_sheet_exists_in_the_entry_own_workbook() -> None:
    """全 entry：契约声明的 excel_name 必须真的在契约钉住的那份 workbook 里。

    这条同时是「找对文档」与「定位不落空」的判据 —— 两者由同一次契约解析确定。
    """
    checked = 0
    for entry, contract_id, tpl_rel in _delivered_rows():
        contract = load_contract(contract_id)
        rel = str(getattr(contract.template, "relative_path", "") or tpl_rel)
        workbook = _TEMPLATES / rel
        if not workbook.is_file():
            pytest.skip(f"{entry} 的权威模板不在工作树: {rel}")
        present = {e.name for e in read_sheet_entries(workbook)}
        for sheet in contract.sheets:
            target = RL.resolve_launch_target_sheet(
                contract=contract, sheet_key=sheet.sheet_key
            )
            assert target in present, (
                f"{entry}: 目标 sheet {target!r} 不在 {rel!r} 里（该文档只有 "
                f"{len(present)} 张）—— 文档与定位解析不同源"
            )
            checked += 1
    assert checked >= 13, f"只核了 {checked} 张受管 sheet，覆盖面不足"


def test_the_wrong_d4_document_does_not_contain_d4_26() -> None:
    """实证「为什么必须按 entry 契约查」：同 wp_code 的另一份文档根本没有 D4-26。

    `wp_template_finder.find_template_file_any('D4')` 按优先级阶梯返回的是「审定」那份
    （10 张 sheet）。若定位链路按 wp_code 解析文档，D4-26 必然定位落空。
    """
    right = _TEMPLATES / D4_WORKBOOK_REL
    wrong = _TEMPLATES / D4_WRONG_WORKBOOK_REL
    if not (right.is_file() and wrong.is_file()):
        pytest.skip("D4 模板文档不在工作树")
    right_names = {e.name for e in read_sheet_entries(right)}
    wrong_names = {e.name for e in read_sheet_entries(wrong)}
    assert D4_26_SHEET_NAME in right_names
    assert D4_26_SHEET_NAME not in wrong_names
    assert len(wrong_names) < len(right_names)


def test_sheet_absent_from_document_degrades_instead_of_mislocating() -> None:
    """目标 sheet 不在这本 workbook 里 ⇒ 一个字节都不动（不乱定位到别的 sheet）。"""
    wrong = _TEMPLATES / D4_WRONG_WORKBOOK_REL
    if not wrong.is_file():
        pytest.skip("D4 模板文档不在工作树")
    assert derive_bytes_with_active_sheet(wrong.read_bytes(), D4_26_SHEET_NAME) is None


# ═══════════════════════════════════════════════════════════════════════════
# 3. token claim → activeTab 派生字节
# ═══════════════════════════════════════════════════════════════════════════


def test_contents_token_carries_and_verifies_target_sheet_claim() -> None:
    room, rep = uuid.uuid4(), uuid.uuid4()
    token = RL.sign_room_contents_token(
        secret=_SECRET, room_id=room, representation_id=rep,
        artifact_sha256="ab" * 32, sheet=D4_26_SHEET_NAME,
    )
    claims = RL.verify_room_contents_token(
        token, secret=_SECRET, expected_room_id=room
    )
    assert claims.sheet == D4_26_SHEET_NAME


def test_empty_target_sheet_keeps_the_legacy_token_shape() -> None:
    """不定位时 token 形态不变（向后兼容，且 claim 空 ⇒ 不派生字节）。"""
    room, rep = uuid.uuid4(), uuid.uuid4()
    token = RL.sign_room_contents_token(
        secret=_SECRET, room_id=room, representation_id=rep,
        artifact_sha256="cd" * 32, sheet="",
    )
    claims = RL.verify_room_contents_token(token, secret=_SECRET, expected_room_id=room)
    assert claims.sheet == ""


def test_active_tab_points_at_d4_26_and_only_workbook_part_changes() -> None:
    workbook = _TEMPLATES / D4_WORKBOOK_REL
    if not workbook.is_file():
        pytest.skip("D4 整册模板不在工作树")
    entries = read_sheet_entries(workbook)
    index_of = {e.name: e.index for e in entries}
    assert D4_26_SHEET_NAME in index_of

    before = workbook.read_bytes()
    after = derive_bytes_with_active_sheet(before, D4_26_SHEET_NAME)
    assert after is not None, "D4-26 不是缺省 activeTab，必须产出派生字节"

    assert _active_tab(after) == str(index_of[D4_26_SHEET_NAME])
    assert _active_tab(before) != _active_tab(after)

    # 派生**只**改 xl/workbook.xml：canonical artifact 的其余部件逐字节不变。
    with zipfile.ZipFile(io.BytesIO(before)) as a, zipfile.ZipFile(io.BytesIO(after)) as b:
        assert a.namelist() == b.namelist()
        mutated = [
            n for n in a.namelist()
            if n != "xl/workbook.xml" and a.read(n) != b.read(n)
        ]
    assert mutated == [], f"除 workbook.xml 外还改了 {mutated}"

    # 磁盘原文件不被改写（artifact_sha256 被 descriptor 锁死）。
    assert workbook.read_bytes() == before


def test_derivation_is_idempotent_for_the_already_active_sheet() -> None:
    """已经是目标 activeTab ⇒ 返回 None（不落盘、不无谓刷新）。"""
    workbook = _TEMPLATES / D4_WORKBOOK_REL
    if not workbook.is_file():
        pytest.skip("D4 整册模板不在工作树")
    once = derive_bytes_with_active_sheet(workbook.read_bytes(), D4_26_SHEET_NAME)
    assert once is not None
    assert derive_bytes_with_active_sheet(once, D4_26_SHEET_NAME) is None


# ═══════════════════════════════════════════════════════════════════════════
# 4. 接线守卫（AST）：参数必须真的从头走到尾
# ═══════════════════════════════════════════════════════════════════════════


def _materialize_resolves_and_forwards(tree: ast.Module) -> bool:
    """`materialize` 解析目标 sheet 并把它转交唯一的启动 URL 装配点。"""
    fn = _func(tree, "materialize")
    return (
        _call_has_kwarg(fn, "resolve_launch_target_sheet", "sheet_key")
        and _call_has_kwarg(fn, "_attach_launch_urls", "target_sheet")
    )


def _launch_urls_signs_target_sheet(tree: ast.Module) -> bool:
    """`_attach_launch_urls` 把目标 sheet 签进 contents token。"""
    fn = _func(tree, "_attach_launch_urls")
    return _call_has_kwarg(fn, "sign_room_contents_token", "sheet")


def _contents_returns_derived_bytes(tree: ast.Module) -> bool:
    """`get_room_contents` 以 `resolved.data` 为判据回字节流（而不是一律 FileResponse）。"""
    fn = _func(tree, "get_room_contents")
    gated = any(
        "resolved.data" in ast.unparse(node.test)
        for node in ast.walk(fn)
        if isinstance(node, ast.If)
    )
    return gated and _call_has_kwarg(fn, "Response", "content")


_WIRING_PREDICATES = (
    ("materialize 解析并转交 target_sheet", _materialize_resolves_and_forwards),
    ("_attach_launch_urls 签入 sheet claim", _launch_urls_signs_target_sheet),
    ("contents 端点回派生字节", _contents_returns_derived_bytes),
)

#: 变异锚点：每条各删掉链路上的一个环节，对应判据必须打红。
_MUTATIONS = (
    ("svc=svc, target_sheet=target_sheet", "svc=svc"),
    ('sheet=str(target_sheet or ""),', ""),
    ("if resolved.data is not None:", "if False:"),
)


@pytest.mark.parametrize("label,predicate", _WIRING_PREDICATES, ids=lambda v: str(v)[:40])
def test_parameter_chain_is_wired_end_to_end(label: str, predicate) -> None:
    assert predicate(_tree(_ROUTER_PY)), f"参数链断在：{label}"


def test_selfcheck_wiring_guards_are_load_bearing() -> None:
    """反向自检：逐一掐断链路上的一环，必须至少有一条判据打红。

    没有这条自检，上面三个 AST 判据可能在任何源码上恒真（首版实现就是这样断了两环
    却全绿）。
    """
    text = _ROUTER_PY.read_text(encoding="utf-8")
    for needle, replacement in _MUTATIONS:
        assert needle in text, f"变异锚点未命中（源码已改形）: {needle!r}"
        mutated = ast.parse(text.replace(needle, replacement, 1))
        assert any(
            not predicate(mutated) for _label, predicate in _WIRING_PREDICATES
        ), f"掐断 {needle!r} 后判据仍全绿 —— 守卫不承重"
