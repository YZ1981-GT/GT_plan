# -*- coding: utf-8 -*-
"""G 九条单区/多区明细表四条红判据：G1R-P1 身份三族 · P3 payload 两形态 · P5 表头层级 · P6 G1≠G9。

spec: `g-cycle-single-region-detail-lanes` · Task 3
　　　Requirements 1.1 / 1.2 / 1.4 / 2.1 / 2.2 / 2.3 / 2.4

═══ 判据分两类 ═══
**A 类（本 Task 即绿）**：`EXPECTED` 期望表 ↔ 模板逐格实测 / 前端按值实测 的一致性。
　　它钉住的是 Task 2 的实测事实不漂移 —— 谁改了模板或前端，这里先红。
**B 类（本 Task 必红，Task 8~14 转绿）**：九条 provider 模块存在且声明与 `EXPECTED` 逐字段一致。

🔴 `EXPECTED` 是本 spec 声明层的**唯一真源**：Task 8~14 写 provider 时从这里取，
不得反过来让本表去迁就 provider（那样判据就成了同义反复）。表中每个值都在
`evidence/task2-geometry-and-field-probes.md` 有逐格/逐行出处。

🔴 spec 正文有六处与实测不符（G12 表头 / G8 分段 / G13 父行 / BP-7 范围 / G14 footer 布尔 /
G11 两个分母），本表按**实测**写，偏差登记在 tasks.md Task 2 注与 evidence。
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import openpyxl
import pytest

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

TPL_G = _BACKEND / "wp_templates" / "G"
COMPOSABLES = (
    _REPO / "audit-platform" / "frontend" / "src" / "components" / "workpaper" / "composables"
)

#: G9/G1 区②③ 共用的 12 列（实测三区逐行同型；G1 区① 额外多一个 T）
_C12 = ("E", "H", "I", "J", "L", "P", "Q", "R", "U", "V", "W", "Y")
_C13_WITH_T = ("E", "H", "I", "J", "L", "P", "Q", "R", "T", "U", "V", "W", "Y")
#: G3 两区共用（实测 R13-20 / R23-28 逐行同型）
_C_G3 = ("F", "M", "N", "O", "P", "T", "AA", "AB", "AC", "AD", "AE", "AF")


#: 🔴 九条的期望声明表（全部值出自 Task 2 逐格实测）。
#:   header:        (group_row, leaf_row) 两级 / (row,) 单级 / (g, mid, leaf) 三级
#:   row_segments:  ((段名, 行号元组, 该段公式列), …) —— 行级 mask 用多段表达
#:   footer_rows:   小计 + 合计（不在受管区）
EXPECTED: dict[str, dict] = {
    "G9": {
        "entry_id": "xlsx/gt-g9-other-noncurrent-financial",
        "adapter_id": "g9.other_noncurrent_detail",
        "workbook": "G9 其他非流动金融资产.xlsx",
        "managed_sheet": "明细表G9-2",
        "store_item_id": "G9-detail-rows",
        "row_identity_key": "rowId",
        "payload_json_key": "remark",
        "header": (9, 10),
        "row_segments": (
            ("r1", (12, 13, 14, 15, 16), _C12),
            ("r2", (19, 20, 21, 22, 23), _C12),
            ("r3", (26, 27, 28), _C12),
        ),
        "footer_rows": (17, 24, 29, 30),
        "effective_cols": 28,
        "composable": "useG9Detail.ts",
    },
    "G10": {
        "entry_id": "xlsx/gt-g10-trading-financial-liabilities",
        "adapter_id": "g10.trading_liabilities_detail",
        "workbook": "G10 交易性金融负债.xlsx",
        "managed_sheet": "明细表G10-2",
        "store_item_id": "G10-detail-rows",
        "row_identity_key": "rowId",
        "payload_json_key": "remark",
        "header": (9, 10),
        "row_segments": (("main", tuple(range(11, 21)), ("E", "G", "K", "L", "M", "O")),),
        "footer_rows": (21,),
        "effective_cols": 19,
        "composable": "useG10Detail.ts",
    },
    "G8": {
        "entry_id": "xlsx/gt-g8-other-equity-instruments",
        "adapter_id": "g8.other_equity_detail",
        "workbook": "G8 其他权益工具投资.xlsx",
        "managed_sheet": "明细表G8-2",
        "store_item_id": "G8-detail-rows",
        "row_identity_key": "rowId",
        "payload_json_key": "remark",
        "header": (9, 10),
        # 🔴 发现 B：三段不是两段。R12 独立（M 区间 / P 公式 / 无 T 三处都不同于 R11 与 R13+）
        "row_segments": (
            ("r11", (11,), ("E", "H", "M", "O", "P", "Q", "R", "T")),
            ("r12", (12,), ("E", "H", "M", "O", "P", "Q", "R")),
            ("r13plus", tuple(range(13, 21)), ("E", "H", "M", "O", "P", "Q", "T")),
        ),
        "footer_rows": (21,),
        "effective_cols": 23,
        "composable": "useG8Detail.ts",
    },
    "G14": {
        "entry_id": "xlsx/gt-g14-credit-impairment-loss",
        "adapter_id": "g14.credit_impairment_detail",
        "workbook": "G14 信用减值损失.xlsx",
        "managed_sheet": "明细表G14-2",
        "store_item_id": "G14-detail-rows",
        # 🔴 全 G 循环唯一 stable_template_row_key（GC-6）
        "row_identity_key": "rowKey",
        "payload_json_key": "remark",
        "header": (9, 10),
        "row_segments": (("main", tuple(range(11, 20)), ("D", "J", "K", "L")),),
        "footer_rows": (20,),
        "effective_cols": 13,
        "composable": "useG14Detail.ts",
    },
    "G11": {
        "entry_id": "xlsx/gt-g11-investment-income",
        "adapter_id": "g11.investment_income_detail",
        "workbook": "G11 投资收益.xlsx",
        "managed_sheet": "明细分析表G11-2",
        "store_item_id": "G11-detail-rows",
        "row_identity_key": "id",
        "payload_json_key": "remark",
        "header": (9,),  # 🔴 单级
        "row_segments": (("main", tuple(range(10, 31)), ("F", "G", "J", "K", "L")),),
        "footer_rows": (31,),  # R32「本年利润总额」是手填分析行，不是 footer 也不受管
        "effective_cols": 13,
        "composable": "useG11DetailAnalysis.ts",
    },
}

EXPECTED.update({
    "G13": {
        "entry_id": "xlsx/gt-g13-fair-value-changes",
        "adapter_id": "g13.fair_value_changes_detail",
        "workbook": "G13 公允价值变动收益.xlsx",
        "managed_sheet": "明细表G13-2",
        # 🔴 `store_item_id`/`row_identity_key` 记的是**工具明细**（slice 冻结口径 + 真库载荷
        #    证据的那个键），`managed_*` 记的是 **Task 12 裁决后真正受管的载体**。
        #    两者指的是不同的事，不可互相覆盖：
        #      · 模板 `明细表G13-2` R11-R20 是**固定 10 个损益表项目**；
        #      · `G13-detail-rows` 存的是动态增删的金融工具级明细（`instrumentName` 自填）
        #        ⇒ 两侧行模型不同构，按序映射会把第 N 条工具写进第 N 个损益项目行（产出错数）。
        #    ⇒ 用户拍板选项 A：把前端原有的分类骨架（`buildG13CategorySkeleton()`，原为
        #    `computed` 不落库）持久化成 `G13-detail-skeleton` 并受管它；工具明细保持
        #    HTML-only 平台增强。骨架是固定行集 ⇒ 受管行身份是业务键 `rowKey`（同 G14）。
        "store_item_id": "G13-detail-rows",
        "row_identity_key": "rowId",
        "managed_store_item_id": "G13-detail-skeleton",
        "managed_row_identity_key": "rowKey",
        "payload_json_key": "remark",
        "header": (9, 10),
        # 🔴 发现 C：父行只有 R11/R14/R17（B/C 为公式）。R19/R20 是**无子行的顶层手填行**，
        #    照 spec 把它们的 B/C 判 formula 会覆盖用户手填值。
        "row_segments": (
            ("parents", (11, 14, 17), ("B", "C", "D", "I", "J", "K")),
            ("children", (12, 13, 15, 16, 18), ("D", "I", "J", "K")),
            ("toplevel", (19, 20), ("D", "I", "J", "K")),
        ),
        "footer_rows": (21,),
        "effective_cols": 12,
        "composable": "useG13Detail.ts",
    },
    "G12": {
        "entry_id": "xlsx/gt-g12-net-hedge-gains",
        "adapter_id": "g12.net_hedge_detail",
        "workbook": "G12 净敞口套期收益.xlsx",
        "managed_sheet": "明细表G12-2",
        "store_item_id": "G12-hedge-detail-rows",
        "row_identity_key": "rowId",
        "payload_json_key": "remark",
        # 🔴 发现 A：**不是「无表头行」**。实测 R7/R8 两级表头 + R9 起数据（整册上移两行）。
        "header": (7, 8),
        # 🔴 发现 H：布尔校验列 G 只在 R9 一行 ⇒ 也是行级 mask。
        "row_segments": (
            ("r9", (9,), ("G", "I")),
            ("r10plus", (10, 11, 12, 13), ("I",)),
        ),
        "footer_rows": (14,),
        "effective_cols": 10,
        "composable": "useG12HedgeDetail.ts",
    },
    "G3": {
        "entry_id": "xlsx/gt-g3-dividend-receivable",
        "adapter_id": "g3.dividend_receivable_detail",
        "workbook": "G3 应收股利.xlsx",
        "managed_sheet": "明细表G3-2",
        "store_item_id": "G3-2-detail-rows",
        "row_identity_key": "id",
        "payload_json_key": "conclusion",  # 🔴 非 remark
        "header": (9, 10, 11),  # 🔴 三级（G 循环唯一）
        "row_segments": (
            ("r1", tuple(range(13, 21)), _C_G3),
            ("r2", tuple(range(23, 29)), _C_G3),
        ),
        "footer_rows": (21, 29, 30),
        "effective_cols": 32,  # 🔴 A..AF（spec 写 33/A-AG 偏大一列，AG 属 R3/R9 索引区）
        "composable": "useG3Detail.ts",
    },
    "G1": {
        "entry_id": "xlsx/gt-g1-trading-financial-assets",
        "adapter_id": "g1.trading_financial_assets_detail",
        "workbook": "G1 交易性金融资产.xlsx",
        "managed_sheet": "明细表G1-2",
        "store_item_id": "G1-2-rows",
        "row_identity_key": "id",
        "payload_json_key": "conclusion",  # 🔴 非 remark
        "header": (9, 10),
        # 🔴 红基线 B2：区① 含跨表 T 列（引 公允价值测试表G1-6），区②③ 不含 ⇒ 行级 mask
        "row_segments": (
            ("r1", (12, 13, 14, 15, 16), _C13_WITH_T),
            ("r2", (19, 20, 21, 22, 23), _C12),
            ("r3", (26, 27, 28), _C12),
        ),
        "footer_rows": (17, 24, 29, 30),
        "effective_cols": 27,
        "composable": "useG1Detail.ts",
    },
})

#: 接入顺序（design §Architecture，由易到难）
LANE_ORDER: tuple[str, ...] = ("G9", "G10", "G8", "G14", "G11", "G13", "G12", "G3", "G1")


@pytest.fixture(scope="module")
def sheets() -> dict[str, openpyxl.worksheet.worksheet.Worksheet]:
    """九册主受管 sheet（`data_only=False`，要看公式而非缓存值）。"""
    out = {}
    for code, spec in EXPECTED.items():
        wb = openpyxl.load_workbook(TPL_G / spec["workbook"], data_only=False)
        assert spec["managed_sheet"] in wb.sheetnames, (
            f"{code}: 模板里没有 {spec['managed_sheet']!r}（sheetnames={wb.sheetnames}）"
        )
        out[code] = wb[spec["managed_sheet"]]
    return out


def _formula_cols(ws, row: int) -> tuple[str, ...]:
    """该行所有以 `=` 开头的单元格的列字母（逐格实测，不推演）。"""
    from openpyxl.utils import get_column_letter

    return tuple(
        get_column_letter(c)
        for c in range(1, ws.max_column + 1)
        if isinstance(ws.cell(row=row, column=c).value, str)
        and str(ws.cell(row=row, column=c).value).startswith("=")
    )


def _code_lines_of(composable: str) -> str:
    """composable 源码中**剥离注释行**后的内容。

    🔴 判据若扫全文，会把「修复说明注释里逐字引用的旧写法」算成违规
    （Task 7 的注释逐字写了 `p.id ?? String(i + 1)`，那是有意的文档价值）。
    局限：只按行首标记过滤（`//` / `*` / `/*`），不解析行尾注释与字符串字面量 ——
    对本 spec 的判据足够（旧写法都在独立代码行上）。与前端
    `g1g3RowIdentityBp7.spec.ts::stripCommentLines` 同一口径。
    """
    src = (COMPOSABLES / composable).read_text(encoding="utf-8")
    kept = [
        line
        for line in src.splitlines()
        if not (
            line.strip().startswith("//")
            or line.strip().startswith("*")
            or line.strip().startswith("/*")
        )
    ]
    return "\n".join(kept)


# ════════════════════════════════════════════════════════════════════════════
# G1R-P1：三族行身份逐条按值取，`rowKey` 不被判违规
#   Validates: Requirements 1.1 / 1.2
# ════════════════════════════════════════════════════════════════════════════
class TestG1rP1RowIdentityThreeFamilies:
    """id 3 条（G1/G3/G11）· rowId 5 条（G8/G9/G10/G12/G13）· rowKey 1 条（G14）。"""

    def test_three_families_distribution_is_3_5_1(self) -> None:
        """A 类：分布必须是 3 / 5 / 1，且每族成员逐条固定（不是只数个数）。"""
        by_key: dict[str, set[str]] = {}
        for code, spec in EXPECTED.items():
            by_key.setdefault(spec["row_identity_key"], set()).add(code)
        assert by_key == {
            "id": {"G1", "G3", "G11"},
            "rowId": {"G8", "G9", "G10", "G12", "G13"},
            "rowKey": {"G14"},
        }, f"三族分布漂移：{ {k: sorted(v) for k, v in by_key.items()} }"

    @pytest.mark.parametrize("code", sorted(EXPECTED))
    def test_identity_field_is_declared_in_its_composable_by_value(self, code: str) -> None:
        """A 类：身份字段名必须在该条自己的 composable 里**按值**出现（禁按编号推演）。

        🔴 按值而非按名：`rowKey` 在 G13 也出现 1 次（L454 注释「按分类骨架 rowKey 筛选工具明细」），
        那是**跨表读取**用、不是 G13 的行身份 ⇒ 判据用「接口字段声明」而非全文计数。
        """
        spec = EXPECTED[code]
        src = (COMPOSABLES / spec["composable"]).read_text(encoding="utf-8")
        key = spec["row_identity_key"]
        # 行接口里的字段声明形如 `  rowId: string` / `  id: string` / `  rowKey: string`
        assert re.search(rf"^\s*{re.escape(key)}\??:\s*string\b", src, re.MULTILINE), (
            f"{code}: {spec['composable']} 的行接口里找不到 `{key}: string` 声明 —— "
            f"slice 冻结的 identity_field 与前端实况不一致，须重测（FC-4 禁推演）"
        )

    def test_g14_row_key_is_not_in_any_forbidden_whitelist(self) -> None:
        """🔴 变异自检（GC-6）：F 循环写死 `('rowId','id')` 白名单会把 G14 判违规。

        本判据模拟那个白名单，断言 G14 **会**被它误判 —— 这正是「不得照抄 F 守卫」的可执行证据。
        """
        f_cycle_whitelist = ("rowId", "id")
        violators = [
            c for c, s in EXPECTED.items() if s["row_identity_key"] not in f_cycle_whitelist
        ]
        assert violators == ["G14"], (
            "照抄 F 循环白名单时，本应**只有** G14 被误判；实得 "
            f"{violators} ⇒ 期望表的三族分布变了，GC-6 的论证需要重写"
        )
        # 且 G14 的 rowKey 是合法的（不在 slice 的 forbidden_identity_kinds 里）
        assert EXPECTED["G14"]["row_identity_key"] == "rowKey"

    def test_g14_row_set_comes_from_a_template_fixed_line_item_constant(self) -> None:
        """A 类：G14 的行集取 `G14_LINE_ITEMS`（源模板固定行集，用户不增删）。

        逐字判据三条：① 常量存在 ② 用它 map 出行 ③ **无** addRow（不可增行）。
        """
        src = (COMPOSABLES / "useG14Detail.ts").read_text(encoding="utf-8")
        assert "G14_LINE_ITEMS" in src, "G14_LINE_ITEMS 不在 useG14Detail.ts —— 固定行集论据失效"
        assert re.search(r"G14_LINE_ITEMS\.map\(", src), "G14 的行不是由 G14_LINE_ITEMS 生成"
        assert not re.search(r"\bfunction\s+addRow\b|\baddRow\s*[,}]", src), (
            "useG14Detail.ts 出现 addRow ⇒ 行集可增删，`stable_template_row_key` 前提被打破"
        )

    def test_map_with_index_alone_is_not_a_violation_signal(self) -> None:
        """🔴 判据设计要点（Task 2 §3.2）：`.map((r, i) =>` 在九条里**全部**出现，
        `i` 喂 `seq` 是正常业务、喂 `id`/`rowId` 才是 BP-7。

        本判据钉住这个区分：九条里「有 `.map((x, i)`」的条数 > 「有下标派生 id」的条数，
        所以任何「命中 map-index 即违规」的守卫都是错的。

        🔴 **按代码行判定，剥离注释行**：Task 7 的修复说明注释里逐字引用了旧写法
        （「原写法 `p.id ?? String(i + 1)` …」，有意的文档价值）。扫全文会把注释算成违规 ——
        本判据首版正是这样假红的。前端同源判据 `g1g3RowIdentityBp7.spec.ts` 用同一口径。
        """
        map_idx = {
            c
            for c, s in EXPECTED.items()
            if re.search(
                r"\.map\(\s*\(\s*\w+\s*,\s*(?:i|idx|index)\s*\)\s*=>",
                _code_lines_of(s["composable"]),
            )
        }
        idx_id = {
            c
            for c, s in EXPECTED.items()
            if re.search(
                r"\?\?\s*String\(\s*i\s*\+\s*1\s*\)|\|\|\s*String\(\s*i\s*\+\s*1\s*\)",
                _code_lines_of(s["composable"]),
            )
        }
        assert idx_id < map_idx, (
            f"下标派生 id 的集合 {sorted(idx_id)} 必须真包含于 map-index 集合 {sorted(map_idx)}；"
            "两者相等说明判据退化成了模式匹配"
        )
        # 🔴 Task 7 已修（`g1g3RowIdentity.resolveStableRowIds` 单点铸造）⇒ 下标派生集合为空。
        #    Task 2 实测时是 {"G1","G3"}；修复证据 `evidence/task7-bp7-and-row-identity-fix.md`。
        assert idx_id == set(), (
            f"下标派生 id 又出现了（实得 {sorted(idx_id)}）—— Task 7 的修复被回退，"
            "或新增了同型写法；前端同源判据见 "
            "`composables/__tests__/g1g3RowIdentityBp7.spec.ts` 的「源码形态防护」组"
        )


# ════════════════════════════════════════════════════════════════════════════
# G1R-P3：payload 两形态逐条断言（G1/G3 conclusion · 其余七条 remark）
#   Validates: Requirements 1.4
# ════════════════════════════════════════════════════════════════════════════
class TestG1rP3PayloadTwoShapes:
    def test_conclusion_only_is_exactly_g1_and_g3(self) -> None:
        """A 类：九条内 `conclusion` 恰为 G1/G3 两条。

        🔴 不得引 slice 的 `payload_column_mode_counts.conclusion_only=3` —— 那是**全循环**口径
        （第三条是 G6-5，归 `g4-g6` spec）。口径混用会让判据放过一条。
        """
        concl = {c for c, s in EXPECTED.items() if s["payload_json_key"] == "conclusion"}
        remark = {c for c, s in EXPECTED.items() if s["payload_json_key"] == "remark"}
        assert concl == {"G1", "G3"}, f"conclusion 两形态漂移：{sorted(concl)}"
        assert len(remark) == 7 and concl | remark == set(EXPECTED)

    def test_mutation_writing_remark_for_all_nine_breaks_g1_and_g3(self) -> None:
        """🔴 变异自检：把 payload 统一写死 `remark` ⇒ G1/G3 的投影指向恒空列。

        变异体在期望表上施加，断言它**确实**改变了 G1/G3（否则判据空转）。
        """
        mutated = {c: "remark" for c in EXPECTED}
        changed = {c for c in EXPECTED if mutated[c] != EXPECTED[c]["payload_json_key"]}
        assert changed == {"G1", "G3"}, (
            "「统一写死 remark」这个变异必须恰好打到 G1/G3 两条；"
            f"实得 {sorted(changed)} ⇒ 期望表的 payload 形态分布变了"
        )

    @pytest.mark.parametrize("code", ["G1", "G3"])
    def test_conclusion_pair_stores_main_rows_under_that_column(self, code: str) -> None:
        """A 类：G1/G3 的主表 store 键确实走 `conclusion` 列 —— 用真库裁决证据交叉验证。

        `store_payload_evidence` 里两条的 `remark_bytes` 与 `conclusion_bytes` 都是 0
        （Task 1 §3.1：它们是「键不存在」而非「空数组」）⇒ 本判据只能断言**声明一致性**，
        不能断言字节数非零。这一点如实写在断言消息里，避免将来有人以为这里验过真数据。
        """
        import json

        adj = json.loads(
            (_BACKEND / "data" / "workpaper_sync_entry_wp_code_adjudication.json").read_text(
                encoding="utf-8"
            )
        )
        rec = next(
            a for a in adj["adjudications"] if a.get("entry_id") == EXPECTED[code]["entry_id"]
        )
        ev = rec["store_payload_evidence"]
        assert ev["store_item_id"] == EXPECTED[code]["store_item_id"]
        assert ev["max_payload_bytes"] == 0 and ev["wp_count_with_payload"] == 0, (
            f"{code} 真库载荷状态变了（实得 max={ev['max_payload_bytes']} "
            f"wp={ev['wp_count_with_payload']}）—— 若已 seed，Req 4.8 的 seed 判据要同步更新"
        )


# ════════════════════════════════════════════════════════════════════════════
# G1R-P5：表头层级逐条实测（1~3 级）
#   Validates: Requirements 2.1 / 2.2 / 2.3
# ════════════════════════════════════════════════════════════════════════════
class TestG1rP5HeaderLevels:
    def test_level_distribution(self) -> None:
        """A 类：单级 1 条（G11）· 两级 7 条 · 三级 1 条（G3）。

        🔴 spec 说 G12「无表头行」—— 实测是 R7/R8 两级（Task 2 发现 A），故**零条无表头**。
        """
        by_level: dict[int, set[str]] = {}
        for code, spec in EXPECTED.items():
            by_level.setdefault(len(spec["header"]), set()).add(code)
        assert by_level == {
            1: {"G11"},
            2: {"G1", "G8", "G9", "G10", "G12", "G13", "G14"},
            3: {"G3"},
        }, f"表头层级分布漂移：{ {k: sorted(v) for k, v in by_level.items()} }"

    @pytest.mark.parametrize("code", sorted(EXPECTED))
    def test_header_rows_carry_text_and_first_data_row_does_not_start_a_header(
        self, code: str, sheets
    ) -> None:
        """A 类：每个声明的表头行都真有文本；且**表头行不得有公式**（表头是标签不是计算）。"""
        ws = sheets[code]
        spec = EXPECTED[code]
        for hrow in spec["header"]:
            vals = [
                ws.cell(row=hrow, column=c).value
                for c in range(1, ws.max_column + 1)
                if ws.cell(row=hrow, column=c).value not in (None, "")
            ]
            assert vals, f"{code}: 声明的表头行 R{hrow} 整行为空 ⇒ 不是表头"
            assert not _formula_cols(ws, hrow), (
                f"{code}: 表头行 R{hrow} 带公式 {_formula_cols(ws, hrow)} ⇒ 它不是表头行"
            )

    def test_g12_header_is_r7_r8_not_absent_and_r9_is_data(self, sheets) -> None:
        """🔴 发现 A 的可执行判据：G12 表头在 R7/R8，R9 是**第一行数据**。

        三条逐格证据：① R7 有 `项目` ② R8 有叶子标签且无公式 ③ R9 带公式（数据行才有计算列）。
        """
        ws = sheets["G12"]
        assert ws["A7"].value == "项目", f"G12 R7 的 A 列实得 {ws['A7'].value!r}，不是表头组行"
        r8 = [ws.cell(row=8, column=c).value for c in range(1, 11)]
        assert any(v not in (None, "") for v in r8), "G12 R8 整行为空 ⇒ 两级表头论据失效"
        assert not _formula_cols(ws, 8), "G12 R8 带公式 ⇒ 它不是表头叶子行"
        assert _formula_cols(ws, 9) == ("G", "I"), (
            f"G12 R9 公式列实得 {_formula_cols(ws, 9)}，期望 ('G','I') ⇒ R9 是数据行"
        )
        assert ws["A9"].value == "预期销售和预期采购的外汇净头寸"

    def test_mutation_g12_treating_r9_as_header_loses_the_first_data_row(self, sheets) -> None:
        """🔴 变异自检：把 R9 当表头 ⇒ 数据区起点变 R10 ⇒ 丢第一行数据（且丢的那行带布尔列 G）。"""
        ws = sheets["G12"]
        real_first = EXPECTED["G12"]["row_segments"][0][1][0]
        assert real_first == 9
        mutated_first = 10
        lost_cols = _formula_cols(ws, real_first)
        kept_cols = _formula_cols(ws, mutated_first)
        assert lost_cols != kept_cols and "G" in lost_cols and "G" not in kept_cols, (
            "变异「R9 当表头」必须丢掉 R9 独有的布尔校验列 G；"
            f"实得 lost={lost_cols} kept={kept_cols}"
        )

    def test_mutation_g3_two_level_header_misplaces_the_data_region_start(self, sheets) -> None:
        """🔴 变异自检：G3 按两级表头声明（R9/R10）⇒ 数据区起点会算到 R11，
        而 R11 是**第三级表头**（整行标签、无公式）⇒ 起点错位必红。
        """
        ws = sheets["G3"]
        assert len(EXPECTED["G3"]["header"]) == 3
        assert not _formula_cols(ws, 11), "G3 R11 带公式 ⇒ 三级表头论据失效"
        assert ws["A12"].value == "1、账龄一年以内的应收股利", "G3 R12 应是区标题行"
        assert _formula_cols(ws, 13) == _C_G3, (
            f"G3 真实数据首行 R13 的公式列实得 {_formula_cols(ws, 13)}"
        )


# ════════════════════════════════════════════════════════════════════════════
# G1R-P6：G1 与 G9 三区列集不等（不等点精确到唯一元素 T）
#   Validates: Requirements 2.4
# ════════════════════════════════════════════════════════════════════════════
class TestG1rP6G1IsNotG9:
    def test_g1_region1_has_t_and_g9_has_none_anywhere(self) -> None:
        """A 类：G1 区① 含 T；G1 区②③ 与 G9 三区**都不含** T。"""
        g1 = dict((name, cols) for name, _rows, cols in EXPECTED["G1"]["row_segments"])
        g9 = dict((name, cols) for name, _rows, cols in EXPECTED["G9"]["row_segments"])
        assert "T" in g1["r1"], "G1 区① 必须含跨表 T 列（红基线 B2）"
        assert "T" not in g1["r2"] and "T" not in g1["r3"], "G1 区②③ 不应含 T"
        assert all("T" not in cols for cols in g9.values()), "G9 三区均不应含 T"

    def test_the_only_difference_is_exactly_the_letter_t(self) -> None:
        """🔴 不等点精确到**唯一元素 T** —— 只断言「集合不等」会被任何无关差异蒙混过关。"""
        g1_all = set().union(*(set(c) for _n, _r, c in EXPECTED["G1"]["row_segments"]))
        g9_all = set().union(*(set(c) for _n, _r, c in EXPECTED["G9"]["row_segments"]))
        assert g1_all != g9_all, "G1 与 G9 的列集必须不等（禁「同构就复制」）"
        assert g1_all - g9_all == {"T"}, f"G1 多出的列应恰为 {{'T'}}，实得 {sorted(g1_all - g9_all)}"
        assert g9_all - g1_all == set(), f"G9 不应有 G1 没有的列，实得 {sorted(g9_all - g1_all)}"

    def test_g1_region1_t_column_is_a_cross_sheet_formula_into_g1_6(self, sheets) -> None:
        """A 类：区① 五行的 T 列逐行引 `公允价值测试表G1-6` 的 H10..H14（逐格实测，非推演）。"""
        ws = sheets["G1"]
        for offset, row in enumerate(EXPECTED["G1"]["row_segments"][0][1]):
            got = ws.cell(row=row, column=20).value  # T = 第 20 列
            expect = f"='公允价值测试表G1-6'!H{10 + offset}-'明细表G1-2'!R{row}"
            assert got == expect, f"G1 T{row} 实得 {got!r}，期望 {expect!r}"

    def test_mutation_copying_g9_columns_to_g1_drops_the_t_column(self) -> None:
        """🔴 变异自检：把 G9 的列集复制给 G1 ⇒ 区① 的 T 列漏声明 ⇒ 跨表公式被当手填格覆盖。"""
        g9_r1 = EXPECTED["G9"]["row_segments"][0][2]
        g1_r1 = EXPECTED["G1"]["row_segments"][0][2]
        assert set(g1_r1) - set(g9_r1) == {"T"}, "变异体必须恰好丢掉 T"
        assert len(g1_r1) == len(g9_r1) + 1 == 13

    @pytest.mark.parametrize("code", ["G1", "G9"])
    def test_three_regions_geometry_matches_template(self, code: str, sheets) -> None:
        """A 类：两条的三区行号 + 区标题行 + 小计/合计行逐格核（几何近同构但不得共用声明）。"""
        ws = sheets[code]
        spec = EXPECTED[code]
        assert tuple(r for _n, rows, _c in spec["row_segments"] for r in rows) == (
            12, 13, 14, 15, 16, 19, 20, 21, 22, 23, 26, 27, 28
        )
        # 区标题行（不受管）：R11 / R18 / R25 整行无公式且 A 列有分类文本
        for trow in (11, 18, 25):
            assert not _formula_cols(ws, trow), f"{code}: R{trow} 应是区标题行（无公式）"
            assert isinstance(ws.cell(row=trow, column=1).value, str)
        # 小计 R17/R24/R29 + 合计 R30（枚举相加，非 SUM 区间）
        assert ws["C17"].value == "=SUM(C12:C16)"
        assert ws["C24"].value == "=SUM(C19:C23)"
        assert ws["C29"].value == "=SUM(C26:C28)"
        assert ws["C30"].value == "=SUM(C17,C24,C29)", (
            f"{code}: 合计行应是枚举相加 =SUM(C17,C24,C29)，实得 {ws['C30'].value!r}"
        )


# ════════════════════════════════════════════════════════════════════════════
# B 类：九条 provider 尚未交付 —— 本 Task **必红**，Task 8~14 逐条转绿
# ════════════════════════════════════════════════════════════════════════════
_PROVIDER_MODULES: dict[str, str] = {
    "G9": "phase5_g9_other_noncurrent",
    "G10": "phase5_g10_trading_liabilities",
    "G8": "phase5_g8_other_equity",
    "G14": "phase5_g14_credit_impairment",
    "G11": "phase5_g11_investment_income",
    "G13": "phase5_g13_fair_value_changes",
    "G12": "phase5_g12_net_hedge_gains",
    "G3": "phase5_g3_dividend_receivable",
    "G1": "phase5_g1_trading_financial_assets",
}


class TestBClassProvidersNotYetDelivered:
    """🔴 红基线：九条 entry 层 provider 模块 + adapter 注册全未交付。

    每条在对应 Task 交付后自动转绿；**不得**用 xfail 掩盖（xfail 会让「交付了但声明错」也算过）。
    """

    @pytest.mark.parametrize("code", LANE_ORDER)
    def test_provider_module_exists_and_declares_expected_ids(self, code: str) -> None:
        import importlib

        mod_name = f"app.services.workpaper_sync.{_PROVIDER_MODULES[code]}"
        try:
            mod = importlib.import_module(mod_name)
        except ModuleNotFoundError:
            pytest.fail(
                f"{code}: provider 模块 {mod_name} 未交付（本判据在对应 Task 交付后转绿）"
            )
        assert getattr(mod, "ENTRY_ID", None) == EXPECTED[code]["entry_id"]
        assert getattr(mod, "ADAPTER_ID", None) == EXPECTED[code]["adapter_id"]

    @pytest.mark.parametrize("code", LANE_ORDER)
    def test_store_merge_plan_is_registered_with_oo_neutralization(self, code: str) -> None:
        """GC-2：九条 plan 一律带 `oo_crash_neutralization_fn`（per-file 保守策略，无例外）。"""
        from app.services.workpaper_sync.store_item_registry import STORE_MERGE_REGISTRY

        aid = EXPECTED[code]["adapter_id"]
        plan = STORE_MERGE_REGISTRY.get(aid)
        assert plan is not None, f"{code}: {aid} 未注册到 STORE_MERGE_REGISTRY"
        assert plan.oo_crash_neutralization_fn == "neutralize_oo_crash_if_formulas", (
            f"{code}: 未挂 OO 崩溃中性化 ⇒ 开 OO 会 editor_error_-82（GC-2）"
        )
        # 🔴 受管载体用 `managed_store_item_id`（只有 G13 与 `store_item_id` 不同 ——
        #    它受管的是分类骨架，不是真库里那个工具明细键；其余八条两者重合）。
        want = EXPECTED[code].get("managed_store_item_id", EXPECTED[code]["store_item_id"])
        assert any(i.item_id == want for i in plan.items), (
            f"{code}: plan.items={[i.item_id for i in plan.items]} 不含受管载体 {want!r}"
        )

    def test_only_g13_manages_a_different_store_item_than_its_legacy_table(self) -> None:
        """🔴 钉住「受管载体 ≠ 真库工具明细键」这件事**只发生在 G13**。

        别家若也出现分歧，说明有人照 G13 的样子接错了载体（或者那条也遇到了同类结构性
        错配 —— 那就该像 Task 12 一样单独裁决，而不是静默跟随）。
        """
        divergent = {
            c
            for c, s in EXPECTED.items()
            if s.get("managed_store_item_id", s["store_item_id"]) != s["store_item_id"]
        }
        assert divergent == {"G13"}, f"受管载体与工具明细键分歧的实得 {sorted(divergent)}"
        assert EXPECTED["G13"]["managed_store_item_id"] == "G13-detail-skeleton"
        assert EXPECTED["G13"]["managed_row_identity_key"] == "rowKey"
        # provider 侧两个键都要登记出来（否则「为什么不受管工具明细」不可复核）
        from app.services.workpaper_sync import phase5_g13_02_detail as m

        assert m.STORE_ITEM_ID_G1302 == EXPECTED["G13"]["managed_store_item_id"]
        assert m.LEGACY_INSTRUMENT_STORE_ITEM_ID_G1302 == EXPECTED["G13"]["store_item_id"]
        assert m.SPEC_G1302.row_identity_key == EXPECTED["G13"]["managed_row_identity_key"]
