"""F0 review-dialog prompt 撤回裁决守卫.

f0-confirmation-linkage-and-structural-enhancement / Task 29。

原 Task 18 往 ``review_dialog._SECTION_PROMPTS`` 加了 6 条 F0 prompt，
2026-08-03 复盘实证它们**三重无效**并已撤回：

1. **不可达**：``review-dialog/ai-generate`` 的 ``section_id`` 只来自
   ``useReviewDialog(props.sectionId)``（前端 ``GtReviewTrigger`` 一族），
   而 ``components/workpaper/confirmation/**`` 里没有任何组件传 sectionId。
2. **F0-1 段划分与源模板不符**：源模板「三、审计说明」是 5 段
   （S29/W29/S33/S34/S37），原 prompt 自造了不存在的「第三方平台评估」段、
   漏了「对误差的分析」与「针对不符事项的程序」。
3. **F0-4 无审计说明区**：源模板 F0-4 只有 9 列明细 + 合计行。

本守卫钉死两件事：
- 撤回后不得悄悄回填（否则又是 dead config）
- 若将来真要加，必须先有前端消费方（section_id 出现在前端源码里）
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

openpyxl = pytest.importorskip("openpyxl")

REPO_ROOT = Path(__file__).resolve().parents[2]
REVIEW_DIALOG_PY = REPO_ROOT / "backend" / "app" / "routers" / "review_dialog.py"
CONFIRMATION_DIR = (
    REPO_ROOT
    / "audit-platform"
    / "frontend"
    / "src"
    / "components"
    / "workpaper"
    / "confirmation"
)
F0_TEMPLATE = REPO_ROOT / "backend" / "wp_templates" / "F" / "F0 存货循环函证.xlsx"

WITHDRAWN_SECTION_IDS = (
    "f0-1-audit-note-control",
    "f0-1-audit-note-platform",
    "f0-1-audit-note-reliability",
    "f0-1-audit-note-alternative",
    "f0-4-audit-note",
    "f0-7-audit-conclusion",
)


def _prompt_keys() -> set[str]:
    """从源码抽 ``_SECTION_PROMPTS`` 的键集（不 import，避免拉起整个 app）.

    🔴 不能用 ``\\{(.*?)\\n\\}`` 截字典体 —— prompt 值本身是多行括号表达式，
    非贪婪会停在第一条 entry 的收尾括号上（实测只抽到 10 个键）。
    改用「声明处 → 下一个顶层 ``def``」切片。
    """
    src = REVIEW_DIALOG_PY.read_text(encoding="utf-8")
    start = src.find("_SECTION_PROMPTS")
    assert start > 0, "未能定位 _SECTION_PROMPTS（常量改名？）"
    end = src.find("\ndef ", start)
    assert end > start, "未能定位 _SECTION_PROMPTS 之后的顶层 def"
    body = src[start:end]
    # 只取字面键（行首缩进 4 空格的 "xxx": 形态），注释行天然被排除。
    # 注意：该字典还用 `**{...}` 推导式批量注入 I 循环/H7 的 section_id，
    # 故字面键 ≠ 全部键；F0 的可达性另由 _prompt_slice() 全文扫描兜住。
    return set(re.findall(r'^\s{4}"([a-z0-9\-]+)":', body, re.M))


def _prompt_slice() -> str:
    """``_SECTION_PROMPTS`` 声明体原文（含推导式），用于「不得出现 f0- 键」全量扫描."""
    src = REVIEW_DIALOG_PY.read_text(encoding="utf-8")
    start = src.find("_SECTION_PROMPTS")
    end = src.find("\ndef ", start)
    return src[start:end]


def _strip_py_comments(text: str) -> str:
    return re.sub(r"^\s*#.*$", "", text, flags=re.M)


def test_reverse_selfcheck_parser_reads_real_keys() -> None:
    """反向自检：解析器真读到已登记 prompt（否则后续断言全是空转）."""
    keys = _prompt_keys()
    assert len(keys) >= 8, f"解析到的字面 prompt 键过少（{len(keys)}），正则可能失效"
    # 锚点：E0 send-list 与 D1 审定表两族既有 prompt
    assert "e0-3-send-list-audit-note" in keys
    assert any(k.startswith("d1-") for k in keys)
    # 推导式注入的键不在字面键里 → 全量扫描才是 F0 可达性的裁决者
    assert "_I_CYCLE_DISCLOSURE_PROMPTS" in _prompt_slice()


def test_withdrawn_f0_prompts_not_reintroduced() -> None:
    """撤回的 6 条不得回填（回填即 dead config）."""
    keys = _prompt_keys()
    for section_id in WITHDRAWN_SECTION_IDS:
        assert section_id not in keys, (
            f"{section_id} 已于 2026-08-03 撤回（不可达 + 与源模板不符），"
            "不得只补 prompt 不接前端消费方"
        )


def test_no_f0_key_anywhere_in_prompts_declaration() -> None:
    """全量扫描（含推导式）：声明体里不得出现任何 ``f0-`` 键字面量."""
    body = _strip_py_comments(_prompt_slice())
    hits = re.findall(r'"(f0-[a-z0-9\-]*)"', body, re.I)
    assert not hits, f"F0 prompt 键回填：{hits}"
    # 反向自检：去注释后仍能读到内容
    assert "_NO_FABRICATION" in body


def test_no_f0_prompt_without_frontend_consumer() -> None:
    """凡登记 f0- 前缀 prompt，其 section_id 必须在前端源码里出现（防再造 dead config）."""
    f0_keys = {k for k in _prompt_keys() if k.startswith("f0-")}
    if not f0_keys:
        pytest.skip("当前无 f0- prompt 登记（撤回状态），本断言无对象")

    frontend_sources = "\n".join(
        p.read_text(encoding="utf-8", errors="ignore")
        for p in CONFIRMATION_DIR.rglob("*")
        if p.suffix in {".ts", ".vue"} and "__tests__" not in p.parts
    )
    for key in sorted(f0_keys):
        assert key in frontend_sources, (
            f"{key} 无前端消费方 —— review-dialog 的 section_id 来自组件 props，"
            "没有组件传它就等于永不触发"
        )


def _review_trigger_section_ids() -> dict[str, list[str]]:
    """扫 confirmation 目录里 ``GtReviewTrigger section-id="X"`` 的实际取值."""
    found: dict[str, list[str]] = {}
    for path in CONFIRMATION_DIR.rglob("*.vue"):
        if "__tests__" in path.parts:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        ids = re.findall(r'GtReviewTrigger[^>]*?section-id="([^"]+)"', text, re.S)
        if ids:
            found[str(path.relative_to(CONFIRMATION_DIR))] = ids
    return found


def test_review_trigger_pattern_exists_but_not_in_f0() -> None:
    """反向自检 + 撤回依据①的精确表述.

    2026-08-03 实测：confirmation 目录**确实**有组件走 review-dialog
    （H0-5 / K0-5 / K0-6 三个替代程序组件用 ``GtReviewTrigger section-id=...``），
    所以「confirmation 全都不接 review-dialog」是错的说法。

    精确事实是：**F0 的组件一个都没接** → 那 6 条 F0 prompt 无论内容对不对都不会触发。
    本断言同时是「模式存在」的正向锚点（防把撤回理由弱化成「平台没这条路」）。
    """
    found = _review_trigger_section_ids()
    all_ids = [sid for ids in found.values() for sid in ids]
    assert all_ids, "反向自检：应能扫到既有 GtReviewTrigger 用法（模式确实存在）"

    f0_ids = [sid for sid in all_ids if sid.lower().startswith("f0")]
    assert not f0_ids, (
        "F0 组件已接 review-dialog（section-id="
        + ", ".join(f0_ids)
        + "）→ 请按源模板段划分补回对应 prompt（见本文件 docstring 的 5 段清单）"
    )


def test_existing_confirmation_section_ids_fall_back_to_generic() -> None:
    """既有 confirmation section_id 均未登记专属 prompt → 走通用回退（记录现状）.

    这条不是缺陷断言，而是把「登记与否只影响 prompt 质量、不影响可达性」这个
    平台事实钉住：``resolve_review_ai_prompt`` 对未登记 id 回退通用 prompt，
    因此不存在「缺登记就 422/空转」的问题（那是 wp_ai 的 ``_SUPPORTED_SECTIONS`` 才有的门）。
    """
    src = REVIEW_DIALOG_PY.read_text(encoding="utf-8")
    fn = re.search(r"def resolve_review_ai_prompt\(.*?\n\n", src, re.S)
    assert fn, "未能定位 resolve_review_ai_prompt"
    assert "_SECTION_PROMPTS.get(" in fn.group(0), "应为 .get() 回退语义而非索引"
    # 不得改成硬门控（否则既有 H0-5/K0-5/K0-6 立刻 400）
    assert "raise" not in fn.group(0)


# ─── 源模板事实冻结（撤回依据 ②③ 的证据锚点） ────────────────────────────────


def test_f0_1_audit_note_has_five_segments() -> None:
    """F0-1「三、审计说明」是 5 段，且不含「第三方平台」段."""
    wb = openpyxl.load_workbook(F0_TEMPLATE, data_only=True)
    try:
        ws = wb["函证结果汇总表F0-1"]
        segments = {
            "S29": ws["S29"].value,
            "W29": ws["W29"].value,
            "S33": ws["S33"].value,
            "S34": ws["S34"].value,
            "S37": ws["S37"].value,
        }
        assert ws["S28"].value.strip() == "三、审计说明"
        texts = [str(v).strip() for v in segments.values()]
    finally:
        wb.close()

    assert len(texts) == 5
    assert texts[0].startswith("1、对询证函保持的控制的说明")
    assert texts[1].startswith("2、对误差的分析")
    assert texts[2].startswith("3、对以传真或电子邮件形式收到的回函的可靠性的考虑")
    assert texts[3].startswith("4、针对不符事项的程序")
    assert texts[4].startswith("5、针对未回函的替代程序")
    joined = "\n".join(texts)
    assert "第三方" not in joined and "平台" not in joined, (
        "源模板 F0-1 审计说明无第三方平台评估段，原 prompt 属自造"
    )


def test_f0_1_reliability_segment_references_f0_6_by_source_typo() -> None:
    """源模板笔误留证：S33 写「（F0-6）」，而可靠性验证表实为 F0-7.

    F0-6 是「应付及采购替代程序」。此处不得「顺手修正」——它是源模板事实，
    将来若要在 UI 展示该段标题，应原样保留并另加说明。
    """
    wb = openpyxl.load_workbook(F0_TEMPLATE, data_only=True)
    try:
        s33 = str(wb["函证结果汇总表F0-1"]["S33"].value).strip()
        sheet_names = set(wb.sheetnames)
    finally:
        wb.close()
    assert "（F0-6）" in s33
    assert "邮件传真回函可靠性验证F0-7" in sheet_names
    assert "应付及采购替代程序F0-6" in sheet_names


def test_f0_4_has_no_audit_note_area() -> None:
    """F0-4 只有明细 + 合计行，无审计说明/审计结论区."""
    wb = openpyxl.load_workbook(F0_TEMPLATE, data_only=True)
    try:
        ws = wb["函证差异调节表F0-4"]
        col_a = [
            str(ws.cell(r, 1).value).strip()
            for r in range(1, ws.max_row + 1)
            if ws.cell(r, 1).value is not None
        ]
    finally:
        wb.close()
    assert any(v == "合计" for v in col_a), "反向自检：应能读到合计行"
    assert not any("审计说明" in v for v in col_a), "F0-4 无审计说明区"
    assert not any("审计结论" in v for v in col_a), "F0-4 无审计结论区"
