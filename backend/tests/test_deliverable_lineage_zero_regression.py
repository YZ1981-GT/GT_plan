"""正向输出零回归守卫 — deliverable-lineage-wiring-and-writeback-closure Task 10

Property 24（需求 12.4）分两档，本文件覆盖**未注入的那一档**与**不可见性**：

- 报表 xlsx：本 spec 不往 xlsx 注入任何元素 ⇒ 与改动前**逐字节等价**。
  判据取「源码级不引用注入模块」而非跑一次导出比字节 —— 后者需要真实项目数据且
  xlsx 内嵌时间戳，逐字节比对天然不稳定；而"没有任何注入代码路径"是更强的结论。
- 报告正文 docx：Wave 3 前同样不注入（Wave 3 起才写段落锚点）。届时本文件的
  `test_report_body_not_yet_injected` 会打红 —— 那是**预期信号**，改为可见文字比对即可。
- 附注 docx：注入锚点与内容控件，故只要求**可见段落文字序列逐字相等**。
  该档由 `test_note_export_anchor_wiring.py` 的 Property 2 / Property 6 覆盖
  （两处都做了开/关两次导出并逐字比对），此处补一条「注入的元素确实不可见」的
  底层断言，防「可见文字比对通过但其实是两侧都被污染」。

反向自检：把 `_INJECTION_SYMBOLS` 清空则守卫恒绿 ⇒ 断言集合非空。
"""

from __future__ import annotations

import re
from pathlib import Path

from docx import Document
from docx.oxml.ns import qn

from app.services.section_anchor_utils import (
    SectionBlock,
    anchor_name,
    write_section_anchors,
)

SERVICES = Path(__file__).resolve().parent.parent / "app" / "services"

#: 本 spec 引入的「会往文档注入元素」的符号。任一出现在下游导出器中即意味着
#: 该产物不再逐字节等价，必须改用可见文字比对档。
_INJECTION_SYMBOLS = (
    "write_section_anchors",
    "section_anchor_utils",
    "inject_content_controls_for_blocks",
    "content_control_injector",
    "wrap_all_sections",
)


def _strip_comments(src: str) -> str:
    """剥掉 # 行注释与三引号 docstring。

    必要性：踩坑说明/设计注释里会**原样写出**被禁符号名（本文件自己就是例子），
    不剥离会把说明文字数成真实引用 → 守卫假红。
    """
    src = re.sub(r'"""[\s\S]*?"""', "", src)
    src = re.sub(r"'''[\s\S]*?'''", "", src)
    return re.sub(r"(?m)#.*$", "", src)


def _referenced_symbols(rel: str) -> list[str]:
    src = _strip_comments((SERVICES / rel).read_text(encoding="utf-8"))
    return [s for s in _INJECTION_SYMBOLS if s in src]


# ─── Property 24 档 1：xlsx 逐字节等价（无注入路径） ─────────────────────────


def test_property_24_financial_report_exporter_has_no_injection():
    # Feature: deliverable-lineage-wiring-and-writeback-closure, Property 24
    """报表 xlsx 导出器不引用任何注入符号 ⇒ 输出逐字节等价（需求 12.4 档 1）。

    这同时是需求 10.1「xlsx 不提供单元格级回写」的结构性保障：没有锚点就无法
    做章节定位，也就不存在把 xlsx 编辑结果写回上游的通路。
    """
    found = _referenced_symbols("report_excel_exporter.py")
    assert found == [], (
        f"report_excel_exporter.py 引用了注入符号 {found} —— "
        "报表 xlsx 一旦被注入元素，需求 12.4 的「逐字节等价」判据即不再成立，"
        "且意味着有人在给报表加章节定位（违反需求 10.1：报表数字只能由调整分录派生）"
    )


def test_report_body_visible_text_unchanged_by_anchor_injection():
    """报告正文自 Wave 3 起注入锚点 ⇒ 判据从「逐字节等价」转为
    **可见段落文字序列逐字相等**（需求 12.4 档 2）。

    这是 Wave 1 时留下的**预期信号**：`test_report_body_not_yet_injected` 断言
    `template_fill_service.py` 不引用注入符号，Task 17 接线后它必然打红 ——
    当时的注释已写明「届时改为可见文字比对档，不要简单删掉」。

    本条对**真实源模板**做端到端验证（不是合成 docx）：扫章节 → 写锚点 →
    比对可见段落文字序列，并断言锚点确实写进了 XML（防上一句空转）。
    """
    from docx import Document

    from app.services.report_body_section_blocks import (
        report_body_anchor_name,
        scan_report_body_sections,
    )

    tpl_dir = (
        Path(__file__).resolve().parents[1]
        / "data"
        / "audit_report_templates"
        / "report_body"
    )
    if not tpl_dir.exists():
        import pytest

        pytest.skip("报告正文源模板目录不存在（精简部署）")

    templates = sorted(tpl_dir.glob("*.docx"))[:3]
    assert templates, "源模板目录为空 —— 本断言会空转"

    for tpl in templates:
        doc = Document(str(tpl))
        before = _visible_texts(doc)
        sections = scan_report_body_sections(doc)
        assert sections, f"{tpl.name} 未扫出任何章节（定位器失效）"

        mapping = write_section_anchors(
            doc,
            [s.to_section_block() for s in sections],
            namer=report_body_anchor_name,
        )
        assert _visible_texts(doc) == before, (
            f"{tpl.name}: 锚点注入改变了可见段落文字序列（需求 12.4 档 2）"
        )
        # 锚点确实写入（否则上一条断言是空转）
        assert len(list(doc.element.body.iter(qn("w:bookmarkStart")))) >= len(mapping)
        assert all(a.startswith("sec_rb_") for a in mapping.values()), (
            "报告正文锚点必须用 sec_rb_ 命名空间，沿用附注 sec_ 会撞章节码域"
        )


def test_report_body_anchors_invisible_to_note_writeback():
    """报告正文锚点必须对**附注**回填的扫描器不可见（命名空间隔离）。

    反向自检意义：若用默认命名器写，`scan_anchor_blocks` 实测会看见 4 个块，
    且把 `cpa_responsibility` 反解成伪章节码 `cpa、responsibility` —— 那会让
    附注回填拿报告正文的文字去 `disclosure_notes` 找章节（最坏情况写错表）。
    """
    from docx import Document

    from app.services.report_body_section_blocks import (
        report_body_anchor_name,
        scan_report_body_sections,
    )
    from app.services.section_anchor_utils import scan_anchor_blocks

    tpl_dir = (
        Path(__file__).resolve().parents[1]
        / "data"
        / "audit_report_templates"
        / "report_body"
    )
    if not tpl_dir.exists():
        import pytest

        pytest.skip("报告正文源模板目录不存在（精简部署）")
    tpl = sorted(tpl_dir.glob("*.docx"))[0]

    doc = Document(str(tpl))
    secs = scan_report_body_sections(doc)
    write_section_anchors(
        doc, [s.to_section_block() for s in secs], namer=report_body_anchor_name
    )
    assert scan_anchor_blocks(doc) == [], (
        "附注回填的扫描器看见了报告正文锚点 ⇒ 命名空间隔离失效"
    )

    # 反向自检：默认命名器时**必须**泄漏，证明隔离不是空转
    doc2 = Document(str(tpl))
    secs2 = scan_report_body_sections(doc2)
    write_section_anchors(doc2, [s.to_section_block() for s in secs2])
    assert scan_anchor_blocks(doc2), (
        "反向自检失效：默认命名器下也没泄漏 ⇒ 上一条断言证明不了隔离有效"
    )


def test_report_body_injection_is_wired_in_confirm():
    """Task 17 接线正向断言：`confirm_report_body` 真的写了锚点。

    与档 1 的「不引用注入符号」相反 —— 报告正文现在**必须**引用，
    若被回退则章节溯源/回填/刷新在报告正文侧全部恒空。
    """
    src = _strip_comments(
        (SERVICES / "template_fill_service.py").read_text(encoding="utf-8")
    )
    assert "write_section_anchors(" in src, "confirm_report_body 未写入锚点"
    assert "report_body_anchor_name" in src, "未使用 sec_rb_ 命名空间"
    assert "persist_report_body_section_states(" in src, "章节状态未落库"
    assert "sections=rb_sections_payload" in src, (
        "report_body_json 未落 sections ⇒ 回填无目标字段、重新生成必丢人工文字"
    )


def test_reverse_selfcheck_injection_symbol_set_is_not_empty():
    """反向自检：符号集合为空则上面两条恒绿（守卫空转）。"""
    assert len(_INJECTION_SYMBOLS) >= 3
    # 且这些符号必须真实存在于本 spec 的模块中，否则是拼错的死字符串
    anchor_src = (SERVICES / "section_anchor_utils.py").read_text(encoding="utf-8")
    cc_src = (SERVICES / "content_control_injector.py").read_text(encoding="utf-8")
    assert "def write_section_anchors" in anchor_src
    assert "def inject_content_controls_for_blocks" in cc_src


def test_note_exporter_does_inject_so_byte_equivalence_is_not_claimed():
    """反向自检：附注导出器**确实**引用注入符号。

    若某次重构让附注侧也不注入了，说明锚点接线被回退（历史假绿的形态），
    此时应立即打红而不是让「零回归」看起来更好达标。
    """
    found = _referenced_symbols("note_word_exporter.py")
    assert "write_section_anchors" in found, (
        "note_word_exporter.py 不再调用 write_section_anchors —— "
        "锚点接线被回退，溯源/回填/刷新三条链将全部恒空"
    )


# ─── Property 24 档 2 底层保障：注入元素不可见 ───────────────────────────────


def _visible_texts(doc: Document) -> list[str]:
    ns_w = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    return [
        "".join(t.text or "" for t in p.iter(f"{{{ns_w}}}t"))
        for p in doc.element.body.iter(qn("w:p"))
    ]


def test_anchor_elements_are_invisible():
    """`w:bookmarkStart/End` 不产生可见文字 ⇒ 可见文字序列比对档成立的前提。"""
    doc = Document()
    blocks = []
    for code in ("八、1", "八、2"):
        open_p = doc.add_paragraph(f"##SECTION:{code}##")
        doc.add_paragraph(f"{code} 正文")
        close_p = doc.add_paragraph(f"##/SECTION:{code}##")
        blocks.append(
            SectionBlock(
                section_code=code, open_el=open_p._p, close_el=close_p._p
            )
        )
    before = _visible_texts(doc)

    mapping = write_section_anchors(doc, blocks)

    assert mapping == {c: anchor_name(c) for c in ("八、1", "八、2")}
    assert _visible_texts(doc) == before, "锚点元素产生了可见文字"
    # 锚点确实写进了 XML（否则上一条断言是空转）
    assert len(list(doc.element.body.iter(qn("w:bookmarkStart")))) >= 2
