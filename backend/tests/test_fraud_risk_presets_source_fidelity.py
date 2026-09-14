"""函证舞弊风险迹象预置文字 ↔ 源模板交叉锁死守卫.

f0-confirmation-linkage-and-structural-enhancement / Task 27。

背景（2026-08-03 实证）：
    ``fraudRiskPresets.PRESET_FRAUD_ITEMS`` 原 19 条描述与任何源模板都不一致
    （原第 1 条「被审计单位管理层凌驾于内部控制之上」vs 源模板「管理层不允许寄发询证函」），
    属自造内容；而 ``composables/f0FraudRiskPush.ts`` 另抄了一份文字不同的
    ``F0_FRAUD_INDICATORS`` → 双真源。该模块已于 2026-08-04（Task 32）整体重写为
    ``composables/confirmationRiskPush.ts``（旧名带 ``f0`` 前缀但消费方是七枢纽共享组件）。

本守卫以 **源 xlsx 为唯一裁决者**（openpyxl 直读），钉死：
    1. 六张 fraud-risk sheet 的 19 条内容互相全等（共用一份常量的事实前提）
    2. 前端预置的 19 条 description 与源模板 A6:A24 逐字相同
    3. 两条 tooltip 举例与源模板 J18/J19 逐字相同，且不得增补第三条
    4. 整个 ``confirmation/`` 目录都不得再声明 ``F0_FRAUD_INDICATORS``（双真源已删）
    5. 反向自检：解析器确实读到了内容（防正则/路径失效导致断言空转）
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

openpyxl = pytest.importorskip("openpyxl")

REPO_ROOT = Path(__file__).resolve().parents[2]
WP_TEMPLATES = REPO_ROOT / "backend" / "wp_templates"
PRESETS_TS = (
    REPO_ROOT
    / "audit-platform"
    / "frontend"
    / "src"
    / "components"
    / "workpaper"
    / "confirmation"
    / "fraudRisk"
    / "fraudRiskPresets.ts"
)
CONFIRMATION_DIR = (
    REPO_ROOT
    / "audit-platform"
    / "frontend"
    / "src"
    / "components"
    / "workpaper"
    / "confirmation"
)
#: 推送载荷构建模块（Task 32 由 `composables/f0FraudRiskPush.ts` 改名而来 —— 消费方是七枢纽共享组件）
PUSH_TS = CONFIRMATION_DIR / "composables" / "confirmationRiskPush.ts"

#: 六张函证舞弊风险评价表（sheet 名 → 所在模板目录前缀）
FRAUD_SHEETS = {
    "函证程序舞弊风险评价表D0-8": "D",
    "函证程序舞弊风险评价表E0-8": "E",
    "函证程序舞弊风险评价表F0-8": "F",
    "函证程序舞弊风险评价表H0-7": "H",
    "函证程序舞弊风险评价表K0-8": "K",
    "函证程序舞弊风险评价表L0-7": "L",
}

#: 源模板迹象行范围（A6:A24 = 19 条；A25 是可扩行 `……`）
ITEM_ROW_RANGE = range(6, 25)


def _strip_ts_comments(src: str) -> str:
    """去 TS 注释（防说明文字被数成真实声明）."""
    out = re.sub(r"/\*[\s\S]*?\*/", "", src)
    return re.sub(r"(^|[^:])//.*$", r"\1", out, flags=re.M)


def _normalize(text: str) -> str:
    """去序号前缀与尾部标点（源模板部分条目带 `；`/`。` 部分不带）."""
    t = re.sub(r"^\d+\.", "", str(text).strip())
    return t.rstrip("；;。")


def _load_sheet_items(sheet_name: str, dir_prefix: str) -> list[str]:
    matches = sorted(
        p
        for p in (WP_TEMPLATES / dir_prefix).glob("*.xlsx")
        if not p.name.startswith("~$")
    )
    for path in matches:
        wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
        try:
            if sheet_name not in wb.sheetnames:
                continue
            ws = wb[sheet_name]
            items: list[str] = []
            for row in ws.iter_rows(
                min_row=ITEM_ROW_RANGE.start,
                max_row=ITEM_ROW_RANGE.stop - 1,
                min_col=1,
                max_col=1,
            ):
                value = row[0].value
                if value is None or not str(value).strip():
                    continue
                items.append(_normalize(value))
            return items
        finally:
            wb.close()
    raise AssertionError(f"源模板未找到 sheet {sheet_name}（目录 {dir_prefix}）")


@pytest.fixture(scope="module")
def source_items() -> list[str]:
    """F0-8 的 19 条（作为基准；其余五张由 test_all_six_sheets_identical 锁死全等）."""
    return _load_sheet_items("函证程序舞弊风险评价表F0-8", "F")


@pytest.fixture(scope="module")
def preset_descriptions() -> list[str]:
    src = PRESETS_TS.read_text(encoding="utf-8")
    block = re.search(
        r"export const PRESET_FRAUD_ITEMS: FraudRiskItem\[\] = \[(.*?)\n\]", src, re.S
    )
    assert block, "未能定位 PRESET_FRAUD_ITEMS 数组（正则失效或常量改名）"
    return [
        m.group(1)
        for m in re.finditer(r"description:\s*'([^']*)'", block.group(1))
    ]


# ─── 前提：六张表内容全等 ────────────────────────────────────────────────────


def test_all_six_sheets_identical(source_items: list[str]) -> None:
    """跨循环共用一份常量的事实前提：六张 sheet 的 19 条完全一致."""
    for sheet_name, dir_prefix in FRAUD_SHEETS.items():
        items = _load_sheet_items(sheet_name, dir_prefix)
        assert items == source_items, f"{sheet_name} 与 F0-8 内容不一致，不能共用一份预置"


def test_source_has_exactly_19_items(source_items: list[str]) -> None:
    """反向自检：解析器真读到 19 条（防路径/范围错导致后续断言空转）."""
    assert len(source_items) == 19, f"源模板迹象条数应为 19，实为 {len(source_items)}"
    assert source_items[0] == "管理层不允许寄发询证函"
    assert source_items[-1].startswith("第三方对函证信息有误的询证函")


# ─── 预置文字逐字对齐 ────────────────────────────────────────────────────────


def test_preset_count_matches_source(
    preset_descriptions: list[str], source_items: list[str]
) -> None:
    assert len(preset_descriptions) == len(source_items)


def test_preset_descriptions_verbatim(
    preset_descriptions: list[str], source_items: list[str]
) -> None:
    """逐条比对（不做归一化以外的任何加工）."""
    for idx, (preset, source) in enumerate(zip(preset_descriptions, source_items), 1):
        assert preset == source, (
            f"第 {idx} 条与源模板不一致：\n  预置={preset!r}\n  源模板={source!r}"
        )


def test_fabricated_text_not_resurrected(preset_descriptions: list[str]) -> None:
    """原自造文字不得复活（每条都是源模板里不存在的措辞）."""
    fabricated = [
        "被审计单位管理层凌驾于内部控制之上",
        "被审计单位近期频繁更换会计师事务所",
        "被审计单位存在大量现金交易或非正常结算方式",
        "其他可能表明存在舞弊风险的情况",
    ]
    joined = "\n".join(preset_descriptions)
    for bad in fabricated:
        assert bad not in joined, f"自造文字复活：{bad}"


# ─── tooltip 举例 ────────────────────────────────────────────────────────────


def test_tooltips_verbatim_from_source() -> None:
    """两条举例逐字取自 J18/J19，且不得增补第三条."""
    wb = openpyxl.load_workbook(
        WP_TEMPLATES / "F" / "F0 存货循环函证.xlsx", data_only=True
    )
    try:
        ws = wb["函证程序舞弊风险评价表F0-8"]
        j18 = str(ws["J18"].value).strip()
        j19 = str(ws["J19"].value).strip()
    finally:
        wb.close()

    src = PRESETS_TS.read_text(encoding="utf-8")
    block = re.search(
        r"export const ITEM_TOOLTIPS_D08: Record<string, string> = \{(.*?)\n\}", src, re.S
    )
    assert block, "未能定位 ITEM_TOOLTIPS_D08"
    body = block.group(1)

    keys = re.findall(r"^\s{2}(\w+):", body, re.M)
    assert keys == ["item_14_reply_rate", "item_15_independence"], (
        f"tooltip 键集应恰为源模板 J18/J19 两条，实为 {keys}"
    )
    assert j18 in body, "第 14 条 tooltip 与源模板 J18 不一致"
    assert j19 in body, "第 15 条 tooltip 与源模板 J19 不一致"
    # 🔴 必须去注释后再断言 —— 本文件与被守卫文件的「更正记录」注释里都会提到
    #    被禁的键名，直接扫全文会把说明文字数成真实声明（memory 铁律同款坑）。
    code = _strip_ts_comments(src)
    assert "item_18_19_examples" not in code, "源模板无第 18/19 条举例，不得自造"
    # 反向自检：去注释函数没把内容清空
    assert "item_14_reply_rate" in code


def test_tooltip_keys_are_wired_to_right_items() -> None:
    """J18 讲回函率 → 第 14 条；J19 讲独立性 → 第 15 条（源模板注写在上一行属排版偏移）."""
    src = PRESETS_TS.read_text(encoding="utf-8")
    block = re.search(
        r"export const PRESET_FRAUD_ITEMS: FraudRiskItem\[\] = \[(.*?)\n\]", src, re.S
    )
    assert block
    entries = re.findall(r"\{\s*seq:\s*(\d+),(.*?)\n  \}", block.group(1), re.S)
    by_seq = {int(seq): body for seq, body in entries}
    assert "item_14_reply_rate" in by_seq[14]
    assert "item_15_independence" in by_seq[15]
    # 其余条目不得挂 tooltip
    for seq, body in by_seq.items():
        if seq not in (14, 15):
            assert "tooltip_key" not in body, f"第 {seq} 条不应有 tooltip（源模板无举例）"


# ─── 双真源已删 ──────────────────────────────────────────────────────────────


def test_f0_duplicate_constant_removed() -> None:
    """整个 confirmation 目录都不得再出现第二份迹象文字常量.

    🔴 2026-08-04（Task 32）判据由「单文件扫描」改为「目录级扫描」：
    原断言只读 ``composables/f0FraudRiskPush.ts`` 一个路径，模块一改名/迹象常量一搬家
    就变成**恒绿的空断言**（文件不存在时 ``read_text`` 直接报错反而还好，
    真正危险的是搬到同目录别的文件里 —— 原守卫查不出）。
    现在扫全目录，任何 ``.ts``/``.vue`` 里出现 ``F0_FRAUD_INDICATORS`` 即打红。
    """
    ts_files = sorted(CONFIRMATION_DIR.rglob("*.ts")) + sorted(
        CONFIRMATION_DIR.rglob("*.vue")
    )
    # 反向自检①：目录确实被扫到（防路径写错导致断言空转）
    assert len(ts_files) > 100, f"confirmation 目录只扫到 {len(ts_files)} 个文件，路径可疑"

    offenders = []
    for path in ts_files:
        if "__tests__" in path.parts:
            continue  # 守卫自身/测试可以提到这个名字
        if "F0_FRAUD_INDICATORS" in _strip_ts_comments(path.read_text(encoding="utf-8")):
            offenders.append(path.relative_to(CONFIRMATION_DIR).as_posix())
    assert not offenders, (
        f"以下文件仍声明 F0_FRAUD_INDICATORS（与 PRESET_FRAUD_ITEMS 构成双真源）：{offenders}"
    )

    # 旧模块整体已删（它同时还带着发明的事件名 `fraud-risk:push-to-b50`，零消费方）
    assert not (CONFIRMATION_DIR / "composables" / "f0FraudRiskPush.ts").exists(), (
        "f0FraudRiskPush.ts 已由 confirmationRiskPush.ts 取代，不得复活"
    )

    # 反向自检②：确认 _strip_ts_comments 没把整份源码清空
    code = _strip_ts_comments(PUSH_TS.read_text(encoding="utf-8"))
    assert "buildB50RiskFactorPayload" in code
    assert "buildDiffMisstatementPayload" in code


def test_preset_descriptions_are_read_only_source_of_truth() -> None:
    """预置行 description 在 UI 只读 → 合并时必须以预置为准，否则更正传不到既有项目."""
    merge_ts = (
        REPO_ROOT
        / "audit-platform"
        / "frontend"
        / "src"
        / "components"
        / "workpaper"
        / "confirmation"
        / "fraudRisk"
        / "composables"
        / "useFraudRiskData.ts"
    )
    src = merge_ts.read_text(encoding="utf-8")
    merge_fn = re.search(
        r"function mergePresetWithExisting\(.*?\n  \}", src, re.S
    )
    assert merge_fn, "未能定位 mergePresetWithExisting"
    body = merge_fn.group(0)
    assert "description: preset.description" in body, (
        "合并时预置行的 description 必须取预置值（UI 上只读，不是用户数据）"
    )
    # 用户数据三项不得被预置覆盖
    for user_field in ("is_exist", "source_ref", "countermeasure"):
        assert f"{user_field}: preset" not in body, f"{user_field} 是用户数据，不得被预置覆盖"
