"""L 类公式预设纠错与补齐。

改造前 L2~L7 审定表块**整块错位一位**：
  L2 块（wp_code=L2）写的是「长期借款审定表」+ codes=['2501']（实为 L3 内容）
  L3 块重复第二次写 L3 内容
  L4 块写「租赁负债审定表」+ codes=['2601']（实为 H8/H9 循环）
  L5 块写「应付债券审定表」+ codes=['2502']（实为 L4 内容）
  L6 块写「长期应付款审定表」+ codes=['2701']（实为 L5 内容）
  L7 块写「预计负债审定表」+ codes=['2801']（K5 循环）

根因：手工编辑时从 L3 开始连续错位，使 _l6.py render 照抄预设得到 '2601'，_l7 得到 '2801'。

本脚本纠正上述 6 个审定表块的 wp_name/account_codes/cells，并为缺失的循环补齐条目。

🔴 2026-08-09 补齐 cells 判据（本脚本此前的判据盲区）
--------------------------------------------------------
改造前 `build_plan()` **只校验 wp_name / account_codes / sheet 三个字段**，
而 `_build_adjudication_cells()` 虽已定义却**从未被调用**（死代码）
⇒ `--check` 长期 rc=0（报「0 项欠账」），而真正错的 `cells[].formula` 实参
与 `cells[].description` 科目中文名一处未改。

这正是平台已记的缺陷模式「守卫判据没覆盖真正会错的那一维」：
wp_name 与 account_codes 已被某一轮修对，剩下的错只在 cells 里，
于是脚本自报全绿、守卫 test_l_preset_account_coherence 的类 B 断言全红，
两者结论互相矛盾。

本次把 cells 纳入判据（逐 cell 比对 formula 与 description），
并保持 L1/L3/L8 三块逐字节不变（脚本内 assert 钉死，见 UNTOUCHED_BLOCKS）。

🔴 2026-08-12 增补类 B：明细表整块迁移 + 幽灵块删除（Task 5）
---------------------------------------------------------------
除审定表外还有三处**块级**错位（不是字段错位，是整块贴错位置）：

  L5 / 明细表L5-2      内容全是应付债券（TB('2502')×4 + TB('2502.02')）⇒ 实为 L4 的明细表
  L6 / 明细表L6-2      内容全是长期应付款（AUX('2701')×5）           ⇒ 实为 L5 的明细表
  L1 / 分析程序L1-3    sheet 在源 xlsx 不存在（真实 tab 是 调整分录汇总L1-3）
                       且 TB_SUM('2001~2501') 横跨 L1/L2/L3 三个循环，
                       会把 2231（L2 应付利息）一起扫进「债务合计」⇒ 跨循环双算

修法：前两块**原地改 wp_code + sheet**（cells 逐字不动 —— 它们对新归属是正确的），
第三块整块删除。三处都不新建块，故块顺序与 JSON 其余部分零扰动。

用法：
    python backend/scripts/fix/fix_l_cycle_prefill_presets.py --dry-run   # 只输出改动计划
    python backend/scripts/fix/fix_l_cycle_prefill_presets.py --check     # 校验改动已落地
    python backend/scripts/fix/fix_l_cycle_prefill_presets.py --apply     # 执行并写盘

spec: .kiro/specs/l-cycle-extraction-formula-and-disclosure-completion/ R1, R2
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # → backend/
PREFILL_PATH = ROOT / "data" / "prefill_formula_mapping.json"

#: 抽「首实参是科目码」的函数实参（TB/ADJ）。PREV 首实参是 wp_code、
#: PLACEHOLDER 首实参是自由文本，故都不在此列。
#: 🔴 仅供审定表块使用（那些块只有 TB/ADJ/PREV/PLACEHOLDER 四种）。
#: 明细表块含 AUX/LEDGER_DETAIL，必须用下面那条更宽的 _ANY_CODE_ARG_RE ——
#: 拿这条窄正则去扫 AUX 块会抽出空集合，让「父码校验」恒过（或恒判不符）= 假绿。
_CODE_ARG_RE = re.compile(r"\b(?:TB|ADJ)\s*\(\s*'([^']*)'")

#: 抽全部「首实参是科目码」的函数实参，覆盖明细表用的 AUX/LEDGER_DETAIL。
#: 与守卫 test_l_preset_account_coherence._CODE_RE 的函数名清单保持一致。
_ANY_CODE_ARG_RE = re.compile(
    r"\b(?:TB|ADJ|AUX|LEDGER_DETAIL|LEDGER)\s*\(\s*'([^']*)'"
)
#: 科目码形态（四位数字 + 可选点号子级）。区间形态 '2001~2501' 与自由文本会被排除。
_CODE_SHAPE_RE = re.compile(r"^\d{4}(?:\.\d+)*$")

# ─── 正确的 L 循环审定表定义 ─────────────────────────────────────────────────

L_ADJUDICATION_BLOCKS: dict[str, dict] = {
    "L1": {
        "wp_name": "短期借款审定表",
        "sheet": "审定表L1-1",
        "account_codes": ["2001"],
        "subject": "短期借款",
        "kind": "balance",
    },
    "L2": {
        "wp_name": "应付利息审定表",
        "sheet": "审定表L2-1",
        "account_codes": ["2231"],
        "subject": "应付利息",
        "kind": "balance",
    },
    "L3": {
        "wp_name": "长期借款审定表",
        "sheet": "审定表L3-1",
        "account_codes": ["2501"],
        "subject": "长期借款",
        "kind": "balance",
    },
    "L4": {
        "wp_name": "应付债券审定表",
        "sheet": "审定表L4-1",
        "account_codes": ["2502"],
        "subject": "应付债券",
        "kind": "balance",
    },
    "L5": {
        "wp_name": "长期应付款审定表",
        "sheet": "审定表L5-1",
        "account_codes": ["2701"],
        "subject": "长期应付款",
        "kind": "balance",
    },
    "L6": {
        "wp_name": "专项应付款审定表",
        "sheet": "审定表L6-1",
        "account_codes": ["2711"],
        "subject": "专项应付款",
        "kind": "balance",
    },
    "L7": {
        "wp_name": "其他非流动负债审定表",
        "sheet": "审定表L7-1",
        "account_codes": [],  # 宁缺勿造：CAS 无专属科目 + report_config 撞码
        "subject": "其他非流动负债",
        "kind": "placeholder",
    },
    "L8": {
        "wp_name": "财务费用审定表",
        "sheet": "审定表L8-1",
        "account_codes": ["6603"],
        "subject": "财务费用",
        "kind": "balance",
    },
}

# 🔴 零回归钉死：这三块在本次改动中必须逐字节不变。
# L1/L3/L8 的 cells 实参与 description 本就正确（L1→2001 / L3→2501 / L8→6603），
# 错位只发生在 L2/L4/L5/L6/L7 五块。
UNTOUCHED_BLOCKS = ("L1", "L3", "L8")

# L7 宁缺勿造的依据（写进 description，供审计师溯源）
L7_PLACEHOLDER_REASON = (
    "其他非流动负债在 CAS 会计科目表中无专属科目，本项目需按实际情况手工填列。"
    "不得采用 2801（预计负债，归 K5 循环）或 2901（递延所得税负债，归 N 循环）—— "
    "report_config 的 BS-071/BS-097 引用的 2901 与 BS-070/BS-096 撞码，"
    "故 L7 的 fallback_codes 为空元组、报表公式解析成功也不采用（宁缺勿造）。"
)


# ─── 类 B：明细表整块迁移 + 幽灵块删除 ────────────────────────────────────────
#
# 判据形态说明：这里用 (旧 wp_code, 旧 sheet) 定位块，而不是用 wp_name ——
# 因为 wp_name 本身就是错的那一维（`L5 / 明细表L5-2` 的 wp_name 写着「应付债券明细表」），
# 拿错值当定位键会让 --check 在改完后再也找不到块、恒报「已对齐」= 假绿。


@dataclass(frozen=True)
class BlockRelocation:
    """整块迁移：原地改 wp_code / sheet / wp_name，cells 逐字不动。

    cells 不动是本类修法的核心 —— 那些公式对**新**归属是正确的
    （`TB('2502')` 对 L4 应付债券正确、`AUX('2701')` 对 L5 长期应付款正确），
    错的只是这堆 cells 被挂在了哪个 wp_code / sheet 底下。
    """

    old_wp_code: str
    old_sheet: str
    new_wp_code: str
    new_sheet: str
    new_wp_name: str
    #: 迁移后该块所有公式实参的父码必须恰为这些（防迁到又一个错位置）
    expect_parent_codes: frozenset[str]
    evidence: str


BLOCK_RELOCATIONS: tuple[BlockRelocation, ...] = (
    BlockRelocation(
        old_wp_code="L5",
        old_sheet="明细表L5-2",
        new_wp_code="L4",
        new_sheet="应付债券明细表L4-2",
        new_wp_name="应付债券明细表",
        expect_parent_codes=frozenset({"2502"}),
        evidence=(
            "该块五个 cells 全是 TB('2502',...) 与 TB('2502.02','期末余额')，"
            "2502 是应付债券（L4）、2502.02 是应付债券-利息调整，"
            "与 L5 长期应付款（2701）无关。"
            "目标 sheet 名取 L4 源 xlsx 的真实 visible tab「应付债券明细表L4-2」"
            "（openpyxl 直读实证；L4 源模板的明细表 tab 名带科目前缀，"
            "不是 L1/L5/L6 那种「明细表LN-2」形态）。"
        ),
    ),
    BlockRelocation(
        old_wp_code="L6",
        old_sheet="明细表L6-2",
        new_wp_code="L5",
        new_sheet="明细表L5-2",
        new_wp_name="长期应付款明细表",
        expect_parent_codes=frozenset({"2701"}),
        evidence=(
            "该块五个 cells 全是 AUX('2701',...)，2701 是长期应付款（L5），"
            "与 L6 专项应付款（2711）无关。"
            "目标 sheet 名「明细表L5-2」经 openpyxl 实证存在于 L5 源 xlsx。"
            "注意本条与上一条构成一次「腾挪」：L5/明细表L5-2 先迁往 L4，"
            "该键位才空出来给本条落位（apply 顺序无关，因两条各自按旧键定位）。"
        ),
    ),
)

#: 迁移后 L6 明细表无预设 —— 显式登记「无预设」及理由（R2.3）。
#: 专项应付款（2711）在 tb_balance 的辅助维度覆盖率未经实证，
#: 按「宁缺勿造」不凭空造 AUX 预设；待有实证再补。
NO_PRESET_REGISTRY: dict[tuple[str, str], str] = {
    ("L6", "明细表L6-2"): (
        "L6 专项应付款明细表迁移后无预设。理由：原块内容是长期应付款（2701）已迁往 L5；"
        "专项应付款（2711）的辅助核算维度（项目名称 / 拨款来源）在客户账套中的覆盖率"
        "未经实证，按宁缺勿造不凭空造 AUX 预设。源模板「明细表L6-2」r08 列头为"
        "序号/项目/未审数/期初调整/账项调整/重分类调整，其取数由 render 侧"
        "adjudication_prefill 分类桶承载，不依赖 Tier A 公式预设。"
    ),
}


@dataclass(frozen=True)
class BlockDeletion:
    """幽灵块删除。"""

    wp_code: str
    sheet: str
    evidence: str


BLOCK_DELETIONS: tuple[BlockDeletion, ...] = (
    BlockDeletion(
        wp_code="L1",
        sheet="分析程序L1-3",
        evidence=(
            "两条独立依据，任一条都足以删除："
            "①sheet 名 '分析程序L1-3' 不在 L1 源 xlsx 的 13 张 visible tab 内"
            "（openpyxl 直读实证；该索引号的真实 tab 是 '调整分录汇总L1-3'）"
            "⇒ 预设永远匹配不到任何底稿 sheet，是死配置；"
            "②公式 TB_SUM('2001~2501','期末余额') 是病态区间 —— "
            "区间横跨 L1(2001)/L2(2231)/L3(2501) 三个循环，"
            "会把 2201~2241 整段流动负债（含应付账款、预收款项、应付职工薪酬、"
            "应交税费、应付利息）全扫进「债务合计」，"
            "其中 2231 应付利息恰是 L2 自己的科目 ⇒ 跨循环双算。"
            "不改成离散 TB() 而直接删块的理由：该 sheet 不存在，"
            "改对公式也没有落点（宁缺勿造）。"
        ),
    ),
)


def _block_parent_codes(block: dict) -> set[str]:
    """抽一个块内所有公式实参的父级科目码（PREV/PLACEHOLDER 首实参不是科目码）。

    🔴 必须用 _ANY_CODE_ARG_RE（含 AUX/LEDGER_DETAIL）——
    明细表块的取数全是 AUX('2701','成本中心',...)，用只认 TB/ADJ 的窄正则
    会抽出空集合、让父码校验退化成「与空集比较」这类假信号。
    形态过滤同时挡掉区间实参（'2001~2501' 不是单一科目码）。
    """
    found: set[str] = set()
    for cell in block.get("cells") or []:
        if cell.get("formula_type") in ("PREV", "PLACEHOLDER"):
            continue
        for raw in _ANY_CODE_ARG_RE.findall(str(cell.get("formula") or "")):
            code = raw.strip()
            if not _CODE_SHAPE_RE.match(code):
                continue
            found.add(code.split(".")[0])
    return found


def _find_block(mappings: list, wp_code: str, sheet: str) -> dict | None:
    for block in mappings:
        if block.get("wp_code") == wp_code and block.get("sheet") == sheet:
            return block
    return None


def _build_adjudication_cells(wp_code: str, correct: dict) -> list[dict]:
    """生成审定表块的 cells 期望值。

    🔴 `sheet` 与 `wp_code` 一律取 correct 声明值，禁从科目码反推
    （原实现写 `审定表{code[0:2].upper()}{code[2:]}-1`，用科目码 `2001` 拼出
    `审定表20-01-1` 这类不存在的 tab 名）。
    """
    sheet = correct["sheet"]
    subject = correct["subject"]

    prev_cell = {
        "cell_ref": "上年审定数",
        "formula": f"=PREV('{wp_code}','{sheet}','审定数')",
        "formula_type": "PREV",
        "description": "上年同底稿审定数",
    }

    if correct["kind"] == "placeholder":
        # L7 宁缺勿造：四个取数格改 PLACEHOLDER，只保留 PREV
        return [
            {
                "cell_ref": ref,
                "formula": f"=PLACEHOLDER('{subject}{label}')",
                "formula_type": "PLACEHOLDER",
                "description": f"{subject}{label}需手工填列。{L7_PLACEHOLDER_REASON}",
            }
            for ref, label in (
                ("期初余额", "期初余额"),
                ("未审数", "期末余额（未审）"),
                ("AJE调整", "审计调整分录净额"),
                ("RJE调整", "重分类调整分录净额"),
            )
        ] + [prev_cell]

    code = correct["account_codes"][0]
    return [
        {
            "cell_ref": "期初余额",
            "formula": f"=TB('{code}','期初余额')",
            "formula_type": "TB",
            "description": f"从试算表取{subject}期初余额",
        },
        {
            "cell_ref": "未审数",
            "formula": f"=TB('{code}','期末余额')",
            "formula_type": "TB",
            "description": f"从试算表取{subject}期末余额（未审）",
        },
        {
            "cell_ref": "AJE调整",
            "formula": f"=ADJ('{code}','aje_net')",
            "formula_type": "ADJ",
            "description": f"{subject}审计调整分录净额",
        },
        {
            "cell_ref": "RJE调整",
            "formula": f"=ADJ('{code}','rje_net')",
            "formula_type": "ADJ",
            "description": f"{subject}重分类调整分录净额",
        },
        prev_cell,
    ]


def build_plan(data: dict) -> list[dict]:
    """构建改动计划：[{action, wp_code, field, old, new}, ...]

    校验四个维度：wp_name / account_codes / sheet / **cells**。
    🔴 cells 是本脚本改造前的判据盲区 —— 原实现定义了 `_build_adjudication_cells`
    却从未在此调用，导致 `--check` rc=0 而 5 个块的公式实参与 description 全错位。
    """
    mappings = data["mappings"]
    plan = []

    for block in mappings:
        wc = block.get("wp_code", "")
        sh = block.get("sheet", "")
        if not wc.startswith("L"):
            continue
        # 只处理审定表块
        if "审定表" not in sh:
            continue
        correct = L_ADJUDICATION_BLOCKS.get(wc)
        if correct is None:
            continue

        # 🔴 L1/L3/L8 三块本就正确（cells 实参与 description 均已对齐各自科目），
        # 本 spec 要求它们逐字节不变 ⇒ 不参与期望值比对。
        # 它们的正确性由 assert_untouched_blocks_are_healthy() 独立断言
        # （只校验「公式实参恰为本块 account_codes」这一不变量，不比对 description 措辞）。
        if wc in UNTOUCHED_BLOCKS:
            continue

        for field in ("wp_name", "account_codes", "sheet"):
            if block.get(field) != correct[field]:
                plan.append({
                    "action": "fix",
                    "wp_code": wc,
                    "field": field,
                    "old": block.get(field),
                    "new": correct[field],
                })

        want_cells = _build_adjudication_cells(wc, correct)
        if block.get("cells") != want_cells:
            plan.append({
                "action": "fix",
                "wp_code": wc,
                "field": "cells",
                "old": _cells_digest(block.get("cells")),
                "new": _cells_digest(want_cells),
                "_cells": want_cells,
            })

    plan.extend(build_class_b_plan(data))
    return plan


def build_class_b_plan(data: dict) -> list[dict]:
    """类 B 计划：明细表整块迁移 + 幽灵块删除。

    🔴 定位一律用 (旧 wp_code, 旧 sheet) 二元组，且**迁移后该二元组必然消失** ——
    这是 --check 幂等性的结构性保证：迁移完成后 `_find_block(old)` 返 None，
    本函数产出空计划；不像「按 wp_name 定位」那样会在改完后仍匹配到同一块、
    反复重排（或反过来恒报已对齐 = 假绿）。
    """
    mappings = data["mappings"]
    plan: list[dict] = []

    for rel in BLOCK_RELOCATIONS:
        src = _find_block(mappings, rel.old_wp_code, rel.old_sheet)
        if src is None:
            # 已迁移：确认目标位置真的在，否则是「两头都没有」的丢块事故
            dst = _find_block(mappings, rel.new_wp_code, rel.new_sheet)
            if dst is None:
                plan.append({
                    "action": "ERROR",
                    "wp_code": rel.old_wp_code,
                    "field": "relocate",
                    "old": f"{rel.old_wp_code} / {rel.old_sheet} 不存在",
                    "new": (
                        f"{rel.new_wp_code} / {rel.new_sheet} 也不存在"
                        " ⇒ 该块两头都找不到，疑似被并发会话删除"
                    ),
                })
            continue

        got_codes = _block_parent_codes(src)
        if got_codes != set(rel.expect_parent_codes):
            # 🔴 链式腾挪兼容：两次迁移共用同一个 sheet 名时，迁移后旧键被另一次
            # 迁移的产物占据（L5/明细表L5-2 既是第一次迁移的源、又是第二次迁移的目标）。
            # 此时旧键位上的块是正确的（属于后续迁移），只要目标位置存在即视为「已迁移」。
            dst = _find_block(mappings, rel.new_wp_code, rel.new_sheet)
            if dst is not None:
                dst_codes = _block_parent_codes(dst)
                if dst_codes == set(rel.expect_parent_codes):
                    # 目标位置内容正确 ⇒ 确认已迁移，跳过
                    continue
            plan.append({
                "action": "ERROR",
                "wp_code": rel.old_wp_code,
                "field": "relocate",
                "old": f"块内公式父码实测 {sorted(got_codes)}",
                "new": (
                    f"期望恰为 {sorted(rel.expect_parent_codes)}；"
                    "父码不符说明该块内容已被并发会话改动，拒绝盲目迁移"
                ),
            })
            continue

        plan.append({
            "action": "relocate",
            "wp_code": rel.old_wp_code,
            "field": "relocate",
            "old": f"{rel.old_wp_code} / {rel.old_sheet} / {src.get('wp_name')}",
            "new": f"{rel.new_wp_code} / {rel.new_sheet} / {rel.new_wp_name}",
            "_rel": rel,
        })

    for dele in BLOCK_DELETIONS:
        if _find_block(mappings, dele.wp_code, dele.sheet) is not None:
            plan.append({
                "action": "drop",
                "wp_code": dele.wp_code,
                "field": "drop_block",
                "old": f"{dele.wp_code} / {dele.sheet}",
                "new": "<删除>",
                "_del": dele,
            })

    return plan


def assert_untouched_blocks_are_healthy(data: dict) -> list[str]:
    """对 L1/L3/L8 三块做独立不变量断言（它们不参与期望值比对）。

    判据只取「公式实参恰为本块 account_codes」这一维，**不比对 description 措辞** ——
    那三块的 description 写作「从试算表取短期借款审定表期初余额」（含「审定表」二字），
    与本脚本为 L2/L4/L5/L6 生成的措辞不同，属既有形态，改它会破坏「逐字节不变」。

    返回问题清单（空 = 健康）。
    """
    problems: list[str] = []
    for block in data["mappings"]:
        wc = block.get("wp_code", "")
        if wc not in UNTOUCHED_BLOCKS or "审定表" not in block.get("sheet", ""):
            continue
        want_code = L_ADJUDICATION_BLOCKS[wc]["account_codes"][0]
        for cell in block.get("cells") or []:
            ftype = cell.get("formula_type")
            if ftype not in ("TB", "ADJ"):
                continue  # PREV 首实参是 wp_code 不是科目码
            got = _CODE_ARG_RE.findall(str(cell.get("formula") or ""))
            bad = [c for c in got if c.split(".")[0] != want_code]
            if bad:
                problems.append(
                    f"{wc}.{cell.get('cell_ref')}: 公式实参 {bad} 不属于本块科目 {want_code}"
                )
    return problems


def _cells_digest(cells) -> str:
    """cells 的可读摘要（供 --check/--dry-run 输出，避免打印整块 JSON）。"""
    if not cells:
        return "<空>"
    parts = []
    for c in cells:
        f = c.get("formula", "")
        parts.append(f"{c.get('cell_ref', '?')}={f}")
    return " | ".join(parts)


def _retarget_prev_cells(block: dict, old_sheet: str, new_sheet: str) -> int:
    """把块内 PREV('LN','<旧 sheet>',...) 的第二实参改成新 sheet 名（R2.5）。

    不改这一处会让 --check 假绿：块的 sheet 字段已是新值、守卫的 sheet 存在性判据
    过关，而 PREV 第二实参仍指向旧 tab 名 ⇒ 上年数取不到且无人报错。
    同时把 PREV 首实参（wp_code）也一起换 —— 迁移改了归属循环，
    PREV 再指旧 wp_code 会跨循环取上年数。
    """
    touched = 0
    for cell in block.get("cells") or []:
        if cell.get("formula_type") != "PREV":
            continue
        formula = str(cell.get("formula") or "")
        if old_sheet not in formula:
            continue
        cell["formula"] = formula.replace(f"'{old_sheet}'", f"'{new_sheet}'")
        touched += 1
    return touched


def apply_plan(data: dict, plan: list[dict]) -> int:
    """应用改动计划到 data，返回改动数。"""
    mappings = data["mappings"]
    changes = 0
    for item in plan:
        action = item.get("action")

        if action == "ERROR":
            # build 阶段已判为不可自动处置，apply 不得静默跳过
            print(
                f"[ERR] {item['wp_code']}.{item['field']}: {item['new']}",
                file=sys.stderr,
            )
            sys.exit(2)

        if action == "relocate":
            rel: BlockRelocation = item["_rel"]
            block = _find_block(mappings, rel.old_wp_code, rel.old_sheet)
            if block is None:
                continue
            old_wp, old_sheet = rel.old_wp_code, rel.old_sheet
            block["wp_code"] = rel.new_wp_code
            block["sheet"] = rel.new_sheet
            block["wp_name"] = rel.new_wp_name
            _retarget_prev_cells(block, old_sheet, rel.new_sheet)
            for cell in block.get("cells") or []:
                if cell.get("formula_type") == "PREV":
                    cell["formula"] = str(cell.get("formula") or "").replace(
                        f"PREV('{old_wp}'", f"PREV('{rel.new_wp_code}'"
                    )
            changes += 1
            continue

        if action == "drop":
            dele: BlockDeletion = item["_del"]
            block = _find_block(mappings, dele.wp_code, dele.sheet)
            if block is None:
                continue
            mappings.remove(block)
            changes += 1
            continue

        wc = item["wp_code"]
        field = item["field"]
        new_val = item["_cells"] if field == "cells" else item["new"]
        for block in mappings:
            if block.get("wp_code") == wc and "审定表" in block.get("sheet", ""):
                if block.get(field) != new_val:
                    block[field] = new_val
                    changes += 1
                break
    return changes


def snapshot_untouched(data: dict) -> dict[str, str]:
    """抓 L1/L3/L8 三块的逐字节快照（零回归钉死用）。"""
    out = {}
    for block in data.get("mappings", []):
        wc = block.get("wp_code", "")
        if wc in UNTOUCHED_BLOCKS and "审定表" in block.get("sheet", ""):
            out[wc] = json.dumps(block, ensure_ascii=False, sort_keys=True)
    return out


def assert_no_preset_registry_is_honest(data: dict) -> list[str]:
    """核验「无预设」登记表与实际状态一致（R2.3）。

    登记表声明某 (wp_code, sheet) 无预设 —— 若实际却存在该块，说明登记表过期
    （某轮补了预设却没撤登记），必须报出来。这条判据防的是
    「登记表写着无预设、实际有预设」这类文档与实现分叉。
    """
    problems: list[str] = []
    for (wp_code, sheet), reason in NO_PRESET_REGISTRY.items():
        block = _find_block(data["mappings"], wp_code, sheet)
        if block is not None:
            problems.append(
                f"{wp_code} / {sheet}: NO_PRESET_REGISTRY 声明无预设，"
                f"但实际存在该预设块（cells={len(block.get('cells') or [])} 个）"
                " ⇒ 登记表已过期，需撤销登记或删除该块"
            )
        if len(reason) < 40:
            problems.append(
                f"{wp_code} / {sheet}: 无预设理由过短（{len(reason)} 字），"
                "登记必须写明依据"
            )
    return problems


def check_mode(data: dict) -> int:
    """--check 模式：返回剩余欠账数（含 L1/L3/L8 三块的独立不变量）。"""
    plan = build_plan(data)
    untouched_problems = assert_untouched_blocks_are_healthy(data)
    registry_problems = assert_no_preset_registry_is_honest(data)

    if plan:
        print(f"[FAIL] {len(plan)} 项欠账:")
        for p in plan:
            print(f"  [{p['action']}] {p['wp_code']}.{p['field']}:")
            print(f"    old = {p['old']}")
            print(f"    new = {p['new']}")
    if untouched_problems:
        print(
            f"[FAIL] {len(untouched_problems)} 项零回归块异常"
            f"（{'/'.join(sorted(UNTOUCHED_BLOCKS))} 本应始终健康）:"
        )
        for msg in untouched_problems:
            print(f"  {msg}")
    if registry_problems:
        print(f"[FAIL] {len(registry_problems)} 项「无预设」登记不诚实:")
        for msg in registry_problems:
            print(f"  {msg}")
    if not plan and not untouched_problems and not registry_problems:
        print("[OK] L 类公式预设审定表块全部对齐（含 cells），0 项欠账")
        print(
            f"[OK] 零回归块 {'/'.join(sorted(UNTOUCHED_BLOCKS))} "
            "公式实参与自身 account_codes 一致"
        )
        print(
            f"[OK] 类 B 迁移 {len(BLOCK_RELOCATIONS)} 块 / "
            f"删除 {len(BLOCK_DELETIONS)} 块已落地，"
            f"「无预设」登记 {len(NO_PRESET_REGISTRY)} 项诚实"
        )
    return len(plan) + len(untouched_problems) + len(registry_problems)


def _assert_round_trip(raw: str, data: dict) -> None:
    """round-trip 硬闸：序列化必须逐字复现原文，否则拒绝写盘。

    该 JSON 被多个并发 spec 共享，若 json.dumps 的格式与原文不符，
    --apply 会重排整个文件并与并发会话互相回退。
    """
    reproduced = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    if reproduced != raw:
        print(
            "[ERR] round-trip 自检失败：json.dumps 无法逐字复现原文。\n"
            "      直接写盘会重排整个文件并与并发 spec 互相回退。\n"
            f"      原文 {len(raw)} 字节 / 复现 {len(reproduced)} 字节",
            file=sys.stderr,
        )
        sys.exit(2)


def main():
    parser = argparse.ArgumentParser(description="L 类公式预设纠错")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true", help="只输出改动计划")
    group.add_argument("--check", action="store_true", help="校验改动已落地")
    group.add_argument("--apply", action="store_true", help="执行并写盘")
    args = parser.parse_args()

    raw = PREFILL_PATH.read_text(encoding="utf-8")
    data = json.loads(raw)

    if args.check:
        remaining = check_mode(data)
        sys.exit(0 if remaining == 0 else 1)

    before_untouched = snapshot_untouched(data)
    plan = build_plan(data)
    if not plan:
        print("[OK] 无需改动")
        sys.exit(0)

    print(f"改动计划：{len(plan)} 项")
    for p in plan:
        print(f"  [{p['action']}] {p['wp_code']}.{p['field']}:")
        print(f"      old = {p['old']}")
        print(f"      new = {p['new']}")

    if args.dry_run:
        print("\n(dry-run 模式，未写盘)")
        sys.exit(0)

    # --apply：先过 round-trip 闸，再写盘
    _assert_round_trip(raw, json.loads(raw))
    changes = apply_plan(data, plan)

    # 零回归钉死：L1/L3/L8 三块逐字节不变
    after_untouched = snapshot_untouched(data)
    for wc in sorted(UNTOUCHED_BLOCKS):
        if before_untouched.get(wc) != after_untouched.get(wc):
            print(
                f"[ERR] 零回归断言失败：{wc} 审定表块被改动，但它本应逐字节不变。",
                file=sys.stderr,
            )
            sys.exit(2)

    PREFILL_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"\n[OK] 已写盘 {changes} 项改动 → {PREFILL_PATH}")
    print(f"[OK] 零回归核验通过：{'/'.join(sorted(UNTOUCHED_BLOCKS))} 三块逐字节不变")


if __name__ == "__main__":
    main()
