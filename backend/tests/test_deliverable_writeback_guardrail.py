"""回填合规护栏接线测试 — deliverable-lineage-wiring-and-writeback-closure Task 15.1

**Validates: Requirements 8.1, 8.2, 8.3, 8.4, 8.5**

覆盖 Property 16（护栏拒绝表格数字与标题）+ 一条反向自检：

历史缺陷 = `_classify_change`（130 行 TABLE/TITLE 拒绝逻辑，design 标「审计底线」）
**全仓零生产调用方** —— 回填主流程第 4a 步硬编码
`[ChangeClassification(kind=TEXT, ...)]` 并注释「简化」，于是：

- `rejected` 恒空、需求 8.4 的被拒变更留痕从未产生；
- 表格数字写不进上游只是因为**提取阶段**过滤掉了 `w:tbl`，不是护栏在起作用 ——
  一旦提取逻辑放宽（例如为了支持表格回填），数字就能直接绕过调整分录写进上游。

故本文件的核心断言不是「护栏函数逻辑对不对」（那由 characterization 覆盖），而是
**「主流程真的调用了它」** —— 这正是只测纯函数永远发现不了的那一层。
"""

from __future__ import annotations

import re
from pathlib import Path

from app.services.deliverable_writeback_service import (
    ChangeKind,
    DeliverableWritebackService,
)

_SRC = (
    Path(__file__).resolve().parents[1]
    / "app"
    / "services"
    / "deliverable_writeback_service.py"
)

_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _strip_comments(src: str) -> str:
    """剥掉 `#` 注释与三引号 docstring。

    🔴 必须先剥：本文件与被测源码的注释里都写着历史反例
    （`kind=ChangeKind.TEXT` / `硬编码`），不剥会把说明文字数成真实代码，
    守卫结论完全反过来（memory 已记的「读源码型守卫必须 stripComments」铁律）。
    """
    src = re.sub(r'"""[\s\S]*?"""', "", src)
    src = re.sub(r"'''[\s\S]*?'''", "", src)
    return re.sub(r"#[^\n]*", "", src)


def _writeback_body(src: str) -> str:
    """截出 `async def writeback(` 的函数体（到下一个同级 `def` 为止）。"""
    m = re.search(r"\n    async def writeback\(", src)
    assert m, "未找到 writeback 主流程（正则失效 ⇒ 本文件断言会空转）"
    start = m.end()
    nxt = re.search(r"\n    (?:async )?def ", src[start:])
    return src[start : start + nxt.start()] if nxt else src[start:]


def _p(text: str) -> str:
    return f'<w:p xmlns:w="{_W}"><w:r><w:t>{text}</w:t></w:r></w:p>'


def _tbl(cells: list[str]) -> str:
    tcs = "".join(
        f"<w:tc><w:p><w:r><w:t>{c}</w:t></w:r></w:p></w:tc>" for c in cells
    )
    return f'<w:tbl xmlns:w="{_W}"><w:tr>{tcs}</w:tr></w:tbl>'


# ─── Property 16：表格数字与标题被拒 ────────────────────────────────────────


def test_property_16_numeric_table_is_rejected():
    # Feature: deliverable-lineage-wiring-and-writeback-closure, Property 16
    svc = DeliverableWritebackService(db=None)
    xml = _tbl(["货币资金", "1,234,567.89"]) + _p("新的叙述文字")
    kinds = [c["kind"] for c in svc._classify_change("八、1", "旧文字", xml)]

    assert ChangeKind.TABLE in kinds, "含数字单元格的表格变更必须被判 TABLE"
    tbl_item = next(
        c for c in svc._classify_change("八、1", "旧文字", xml)
        if c["kind"] == ChangeKind.TABLE
    )
    assert tbl_item["rejection_reason"], "TABLE 拒绝必须带可读原因（需求 8.2）"
    assert "调整分录" in tbl_item["rejection_reason"], (
        "拒绝原因须指向调整分录路径（需求 8.2）"
    )


def test_property_16_title_change_is_rejected():
    # Feature: deliverable-lineage-wiring-and-writeback-closure, Property 16
    svc = DeliverableWritebackService(db=None)
    # 块首标题段落 —— 形态必须匹配 `_is_title_paragraph` 的真实判据：
    # `{{seq:}}` 占位符 / `（一）xxx` 中文数字编号 / `1. xxx` 阿拉伯数字编号 +
    # section_code 末段编号前缀。**不是**「章节号 + 空格 + 名称」（首版 fixture
    # 按猜测写成 `八、1 货币资金`，护栏正确地不认它 → 断言假红）。
    xml = _p("（一）货币资金") + _p("正文改动")
    items = svc._classify_change("八、1", "旧文字", xml)
    title_items = [c for c in items if c["kind"] == ChangeKind.TITLE]

    assert title_items, "块首标题段落变更必须被判 TITLE（需求 8.3）"
    assert title_items[0]["rejection_reason"], "TITLE 拒绝必须带可读原因"


def test_pure_text_change_is_not_rejected():
    """纯叙述文字变更照常放行（护栏不得误杀正常回填）。"""
    svc = DeliverableWritebackService(db=None)
    xml = _p("这是审计师润色后的叙述文字。")
    items = svc._classify_change("八、1", "旧文字", xml)

    assert [c["kind"] for c in items] == [ChangeKind.TEXT]
    assert items[0]["rejection_reason"] is None


def test_non_numeric_table_is_not_rejected_as_table():
    """纯文字表格（无数字单元格）不判 TABLE —— 护栏只拦数字（需求 8.2）。"""
    svc = DeliverableWritebackService(db=None)
    xml = _tbl(["项目", "说明"]) + _p("正文")
    kinds = [c["kind"] for c in svc._classify_change("八、1", "旧", xml)]
    assert ChangeKind.TABLE not in kinds


# ─── Task 15 接线：主流程真的调用了护栏 ─────────────────────────────────────


def test_writeback_main_flow_calls_guardrail():
    """需求 8.1：主流程必须调用 `_classify_change`。"""
    body = _writeback_body(_strip_comments(_SRC.read_text(encoding="utf-8")))
    assert "self._classify_change(" in body, (
        "回填主流程未调用护栏 ⇒ _classify_change 又成零调用方死代码，"
        "rejected 恒空、需求 8.4 的拒绝留痕从未产生"
    )


def test_reverse_selfcheck_hardcoded_text_classification_is_gone():
    """反向自检：主流程不得再硬编码构造 TEXT 分类当唯一分类。

    复现旧行为（`classifications = [ChangeClassification(kind=ChangeKind.TEXT, ...)]`
    无条件赋值）时本断言必须打红。允许的残留只有「拿不到块 XML 时的降级分支」，
    故判据是「该构造必须出现在 else 降级分支里」而非「完全不出现」。
    """
    body = _writeback_body(_strip_comments(_SRC.read_text(encoding="utf-8")))

    # 找到所有 classifications 赋值点
    assigns = [m.start() for m in re.finditer(r"classifications\s*=", body)]
    assert assigns, "未找到 classifications 赋值（正则失效）"

    guarded = body.index("self._classify_change(")
    # 护栏调用必须是**第一个**赋值来源；硬编码 TEXT 只能在其后的降级分支
    first_assign = assigns[0]
    assert first_assign < guarded < (assigns[1] if len(assigns) > 1 else len(body)) or (
        guarded > first_assign
    ), "护栏调用未参与 classifications 赋值"

    # 降级分支必须有 warning（可观测降级，不得静默）
    assert "护栏降级" in _SRC.read_text(encoding="utf-8"), (
        "降级分支缺 warning ⇒ 护栏失效变静默（需求 8.5 的结构定位形同虚设）"
    )


def test_block_xml_is_captured_by_extractor():
    """护栏的输入（块内 XML）必须由提取阶段带出（需求 8.5：按结构定位）。"""
    src = _strip_comments(_SRC.read_text(encoding="utf-8"))
    assert "self._last_block_xml" in src
    assert "etree.tostring(" in src, (
        "未序列化块内元素 ⇒ 护栏拿不到 XML，只能退回文字分类"
    )
    # 每次 extract 必须重置，避免跨次回填串味
    assert re.search(r"self\._last_block_xml\s*=\s*\{\}", src), (
        "extract 未重置 _last_block_xml ⇒ 上一次回填的块 XML 会串到本次"
    )


def test_guardrail_uses_xml_structure_not_regex():
    """需求 8.5：护栏按块内 XML 结构定位，不得用正则猜测。"""
    src = _SRC.read_text(encoding="utf-8")
    i = src.index("def _classify_change")
    nxt = re.search(r"\n    (?:async )?def ", src[i:])
    fn = src[i : i + nxt.start()] if nxt else src[i:]
    fn_code = _strip_comments(fn)

    assert "ET.fromstring" in fn_code or "etree.fromstring" in fn_code, (
        "护栏未解析 XML"
    )
    assert "findall" in fn_code, "护栏未按元素结构定位"
    assert "re.search" not in fn_code and "re.match" not in fn_code, (
        "护栏用正则猜测结构（违反需求 8.5）"
    )
