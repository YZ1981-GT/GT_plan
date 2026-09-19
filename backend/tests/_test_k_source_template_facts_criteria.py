"""test_k_source_template_facts —— 判据层（常量 / 登记表 / fixture / 纯函数 / 取证 helper）。

从 `backend/tests/test_k_source_template_facts.py` 拆出：原文件 887 行 > pre-commit 的 800 行门禁。
**不加 file_size_whitelist** —— 白名单表头写明「仅历史大文件」，新增文件
套用属滥用。

刻意与用例文件**同目录**：判据里的 `Path(__file__).parents[N]` 路径推算
移到子目录会整体错一层（实测过，会变成 fixture setup 全 ERROR）。

用例层的 import 清单由拆分脚本按其**实际引用**算出，不手写 —— 漏一个名字
就是 collection error，会让整份守卫的断言零执行而表面上「没有失败」。

原文件 docstring 原样保留在下方。

K 循环源模板事实冻结（openpyxl 直读，判据真源）。

平台铁律：披露 sheet 名 / 列头 / 行集 / 动态插行标记的**唯一裁决者是源 xlsx**，
不是记忆、不是控制台输出、不是既有常量。故本文件全部断言直读
``backend/wp_templates/K/*.xlsx``。

本文件属 Wave 1「先打红」守卫，断言分两类：

* **类 A（事实冻结 / stale 检测）** —— 现在就应全绿。绿了才证明判据基础设施有效
  （文件路径对、sheet 名对、扫描面非空），同时兑现「不拿被测代码证明自己」。
* **类 B（被测实现）** —— 现在应全红，红消息写明「尚未实现（Wave N Task M）」。

本文件**不含**类 B —— 源模板是只读事实，没有「被测实现」；对齐动作在 Task 17/18，
其守卫另建。本文件的价值是：**任何一条冻结事实变了都立刻打红**，
让「照记忆施工」在结构上不可能发生。

🔴 立项初稿的三处台账已被本文件的实测推翻（写进断言以防再犯）：

=========================  ==========================  ==================================
维度                       初稿记载                    实测（本文件冻结）
=========================  ==========================  ==================================
动态插行标记                24 处 / 3 种写法             **148 处 / 5 种**（全册）
`…`（单字符）               「未出现」                   **确有 10 处**（K6-6 / K8-5 / K9-5）
披露 sheet 括号写法          4 种                        **6 种**
K1 `#REF!` 断链             11 处                       **70 处**（listed 35 + soe 35）
=========================  ==========================  ==================================

spec: .kiro/specs/k-cycle-extraction-formula-and-disclosure-closure/
      Requirements 8.1, 8.6, 9.1, 9.7, 9.8, 10.2, 10.3, 13.6
      Property 28, 31, 33, 36, 37
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

try:  # pragma: no cover - 环境缺 openpyxl 时给出可判读的红
    from openpyxl import load_workbook
except Exception as exc:  # pragma: no cover
    load_workbook = None  # type: ignore[assignment]
    _OPENPYXL_ERR = str(exc)
else:
    _OPENPYXL_ERR = ""


# ─────────────────────────────────────────────────────────────────────────────
# 路径解析（双哨兵向上查找，禁写死回退级数）
# ─────────────────────────────────────────────────────────────────────────────


def _repo_root() -> Path:
    """靠两个**具体文件**哨兵向上找仓库根。

    单哨兵不够稳（将来子目录出现同名文件即误停）；目录做哨兵会被
    ``audit-platform/backend/app/routers`` 这类历史遗留空目录骗停。
    """
    sentinels = (
        Path("backend/app/services/four_table/k_cycle_specs.py"),
        Path(".kiro/steering/memory.md"),
    )
    here = Path(__file__).resolve()
    for cand in (here, *here.parents):
        if all((cand / s).exists() for s in sentinels):
            return cand
    raise AssertionError(
        f"未找到仓库根（哨兵 {[str(s) for s in sentinels]}），起点 {here}"
    )


ROOT = _repo_root()
TPL_DIR = ROOT / "backend" / "wp_templates" / "K"


# ─────────────────────────────────────────────────────────────────────────────
# 冻结事实（全部来自 2026-08-09 openpyxl 直读）
# ─────────────────────────────────────────────────────────────────────────────

#: 每个循环的 workbook 文件名（源模板事实，改名即打红）
WORKBOOKS: dict[str, str] = {
    "K0": "K0 管理循环函证.xlsx",
    "K1": "K1 其他应收款.xlsx",
    "K2": "K2 其他流动资产.xlsx",
    "K3": "K3 其他应付款.xlsx",
    "K4": "K4 其他流动负债.xlsx",
    "K5": "K5 预计负债.xlsx",
    "K6": "K6 持有待售资产和负债.xlsx",
    "K7": "K7 递延收益.xlsx",
    "K8": "K8 销售费用.xlsx",
    "K9": "K9 管理费用.xlsx",
    "K10": "K10 其他收益.xlsx",
    "K11": "K11 资产减值损失.xlsx",
    "K12": "K12 营业外收入.xlsx",
    "K13": "K13 营业外支出.xlsx",
}

#: 🔴 披露 sheet 名逐字冻结（Requirement 8.1 / Property 28）。
#:
#: **6 种括号写法并存**，全部是源模板事实，任何「统一括号」的改动都必须打红：
#:   1. 全全 `（上市公司）` / `（国企）` —— K2/K4/K8/K9/K10/K11/K12/K13 + K1 soe + K5 soe + K6 listed
#:   2. 前半后全 `(上市公司）` —— K1 listed
#:   3. 半半 `(上市公司)` / `(国企)` —— K3 两版
#:   4. 前全后半 `（上市公司)` —— K5 listed
#:   5. 前半后全 `(国企）` —— K6 soe
#:   6. 「国有企业」`（国有企业）` —— K7 soe（**唯一**用「国有企业」的 K 循环）
#:
#: ⚠️ 按 ``name == "附注披露信息（上市公司）"`` 精确匹配会漏 K1/K3/K5；
#:    按 ``"国企" in name`` 会漏 K7。
DISCLOSURE_SHEETS: dict[str, dict[str, str]] = {
    "K1": {"listed": "附注披露信息(上市公司）", "soe": "附注披露信息（国企）"},
    "K2": {"listed": "附注披露信息（上市公司）", "soe": "附注披露信息（国企）"},
    "K3": {"listed": "附注披露信息(上市公司)", "soe": "附注披露信息(国企)"},
    "K4": {"listed": "附注披露信息（上市公司）", "soe": "附注披露信息（国企）"},
    "K5": {"listed": "附注披露信息（上市公司)", "soe": "附注披露信息（国企）"},
    "K6": {"listed": "附注披露信息（上市公司）", "soe": "附注披露信息(国企）"},
    "K7": {"listed": "附注披露信息（上市公司）", "soe": "附注披露信息（国有企业）"},
    "K8": {"listed": "附注披露信息（上市公司）", "soe": "附注披露信息（国企）"},
    "K9": {"listed": "附注披露信息（上市公司）", "soe": "附注披露信息（国企）"},
    "K10": {"listed": "附注披露信息（上市公司）", "soe": "附注披露信息（国企）"},
    "K11": {"listed": "附注披露信息（上市公司）", "soe": "附注披露信息（国企）"},
    "K12": {"listed": "附注披露信息（上市公司）", "soe": "附注披露信息（国企）"},
    "K13": {"listed": "附注披露信息（上市公司）", "soe": "附注披露信息（国企）"},
}

#: K0 无披露 sheet（函证循环，11 个 sheet 全是函证程序/汇总/替代/舞弊评价）
CYCLES_WITHOUT_DISCLOSURE: tuple[str, ...] = ("K0",)

#: 每个 workbook 的 sheet 总数 / visible 数 / hidden 名（Requirement 8.1 配套）
#:
#: 8 个 workbook 各有一个 hidden ``GT_Custom``（平台自定义占位，不属底稿集合）；
#: K4/K5/K6/K8/K9/K11 无 hidden sheet。
SHEET_COUNTS: dict[str, tuple[int, int, tuple[str, ...]]] = {
    "K0": (11, 10, ("GT_Custom",)),
    "K1": (17, 16, ("GT_Custom",)),
    "K2": (11, 10, ("GT_Custom",)),
    "K3": (12, 11, ("GT_Custom",)),
    "K4": (8, 8, ()),
    "K5": (11, 11, ()),
    "K6": (11, 11, ()),
    "K7": (11, 10, ("GT_Custom",)),
    "K8": (12, 12, ()),
    "K9": (12, 12, ()),
    "K10": (11, 10, ("GT_Custom",)),
    "K11": (7, 7, ()),
    "K12": (9, 8, ("GT_Custom",)),
    "K13": (9, 8, ("GT_Custom",)),
}

#: 全册 visible sheet 合计（覆盖面判据的分母）
TOTAL_VISIBLE_SHEETS = 144

#: 披露 sheet 合计
TOTAL_DISCLOSURE_SHEETS = 26

#: 🔴 动态插行标记的 **5 种写法**（Requirement 9.7 / Property 34）。
#:
#: 立项初稿写「3 种、`…` 未出现」，实测 **4 种**且 `…` 确有 9 处 ⇒ 判据必须覆盖全 4 种，
#: 否则会把真实可扩位（K6-6 的三处 `…`）排除在外。
MARKER_FORMS: dict[str, int] = {
    # 逐写法计数按守卫口径实测（最长写法优先互斥归类，全 sheet 扫描）
    "……": 147,  # U+2026 ×2
    "…": 9,  # U+2026 ×1（**确实存在**：K6-6 三处 / K8·K9 合同检查表各两处 / K0-3 两处）
    "......": 4,  # ASCII 点 ×6（K11 四处，均带前导空格 " ......"）
    "可无限量添加行": 4,  # K1 上市 A27/A109 + K3 两版 A16
}

#: 全册动态标记总数（**164 处**，推翻初稿的 24 处）
#: 🔴 初稿与首轮探针记的 `?` 41 处是 **GBK 控制台显示假象** —— U+003F 真实只有 2 处
#: 且都是 K0 的链接提示文字（见 `NON_MARKER_QUESTION_MARKS`），不属于动态标记。
TOTAL_MARKERS = 164

#: 在 K 类**零命中**的写法 —— 不得加入 K 类判据（会产生永不触发的空转分支）
MARKER_FORMS_ABSENT_IN_K: tuple[str, ...] = ("预留", "可改名")

#: 披露 sheet 内的动态标记（Task 18 的作业面；全册 164 处里只有这 29 处落在披露 sheet）
#:
#: 格式：``{wp_code: {variant: ((coord, marker_form, text), ...)}}``
DISCLOSURE_MARKERS: dict[str, dict[str, tuple[tuple[str, str], ...]]] = {
    "K1": {
        "listed": (("A27", "可无限量添加行"), ("A109", "可无限量添加行")),
        "soe": (("A24", "……"), ("A33", "……")),
    },
    "K3": {
        "listed": (("A16", "可无限量添加行"),),
        "soe": (("A16", "可无限量添加行"),),
    },
    "K6": {
        "listed": (
            ("A15", "……"),
            ("A37", "……"),
            ("A41", "……"),
            ("A58", "……"),
            ("A64", "……"),
            ("A71", "……"),
            ("A77", "……"),
        ),
        "soe": (
            ("A14", "……"),
            ("A18", "……"),
            ("A27", "……"),
            ("A31", "……"),
            ("A54", "……"),
        ),
    },
    "K13": {"soe": (("A14", "……"),)},
    # 🔴 以下 5 组落在披露 sheet 的表尾，且**标记格是公式格** —— 缓存值是 `……`，
    #    公式串里没有。故读取必须 `data_only=True`，这正是 `_load` docstring 里
    #    写明的坑（「用 False 扫会漏掉它们，实测 148 vs 164，差的 16 处全在这批」）。
    #    `test_disclosure_sheet_markers_frozen` 曾用 `_ws()` 的默认 `False`，
    #    于是这 5 条参数化恒红 —— 是读取方式错，不是登记表错。
    "K10": {"listed": (("A13", "……"),), "soe": (("A13", "……"),)},
    "K11": {"listed": (("A25", "......"),), "soe": (("A25", "......"),)},
    "K12": {"listed": (("A13", "……"),), "soe": (("A13", "……"),)},
    "K8": {"listed": (("A16", "……"),), "soe": (("A16", "……"),)},
    "K9": {"listed": (("A24", "……"),), "soe": (("A24", "……"),)},
}

#: 🔴 U+003F 问号在 K 类只有 2 处，且**都不是动态标记**（是链接提示文字）。
#:
#: 立项初稿与首轮探针都记「`?` 41 处」并把它当第 5 种写法 —— 那是 **GBK 控制台把
#: 无法显示的字符统一打成 `?`** 造成的假象。守卫据本表反向锁死：U+003F 命中必须恰为
#: 这 2 处，且不得进 `MARKER_FORMS`（否则会把叙述文字标成可扩位）。
NON_MARKER_QUESTION_MARKS: tuple[tuple[str, str, str], ...] = (
    ("K0", "函证程序表K0A", "G13"),
    ("K0", "邮件传真回函可靠性验证K0-7", "D28"),
)

#: 披露 sheet 内动态标记总数 **29 处**（Task 18 逐处判定的对象；全册 164 处里只有这些）
TOTAL_DISCLOSURE_MARKERS = 29

#: 🔴 有跨列合并父表头（两级表头）的披露 sheet（Requirement 8.3 / Property 29）。
#:
#: 只登记**数据区**的父表头（排除 r1/r2 的标题行与 `【提示：` 说明段）。
#: 格式：``{wp_code: {variant: ((range_str, row, col_from, col_to, text), ...)}}``
TWO_LEVEL_HEADERS: dict[str, dict[str, tuple[tuple[str, int, int, int, str], ...]]] = {
    "K1": {
        "listed": (
            ("B22:D22", 22, 2, 4, "期末数"),
            ("E22:G22", 22, 5, 7, "上年年末数"),
        ),
        "soe": (
            ("B19:F19", 19, 2, 6, "期末余额"),
            ("B20:C20", 20, 2, 3, "账面余额"),
            ("D20:E20", 20, 4, 5, "坏账准备"),
            ("B28:F28", 28, 2, 6, "期初余额"),
            ("B29:C29", 29, 2, 3, "账面余额"),
            ("D29:E29", 29, 4, 5, "坏账准备"),
            ("B38:E38", 38, 2, 5, "期末余额"),
            ("B46:D46", 46, 2, 4, "期末数"),
            ("B47:C47", 47, 2, 3, "账面余额"),
            ("E46:G46", 46, 5, 7, "期初数"),
            ("E47:F47", 47, 5, 6, "账面余额"),
            ("B57:D57", 57, 2, 4, "期末数"),
        ),
    },
    "K6": {
        "listed": (
            ("B6:D6", 6, 2, 4, "期末数"),
            ("E6:G6", 6, 5, 7, "上年年末数"),
            ("D32:E32", 32, 4, 5, "本期减少"),
        ),
        "soe": (
            ("B9:D9", 9, 2, 4, "期末数"),
            ("E9:G9", 9, 5, 7, "期初数"),
            ("D22:E22", 22, 4, 5, "本期减少"),
        ),
    },
}

#: 有两级表头的循环（其余 11 循环的披露表是单级 ⇒ 必须显式标 `flat`）
TWO_LEVEL_CYCLES: tuple[str, ...] = ("K1", "K6")

#: 🔴 账龄字面两版不同（Requirement 10.2 / Property 36）
AGING_FIRST_BAND_LISTED = "1年以内"
AGING_FIRST_BAND_SOE = "1年以内（含1年）"

#: 账龄作**行**维度的位置（K1 两版主表 + K1 soe 账龄组合表 + K3 两版「账龄超过1年」段）
AGING_ROW_ANCHORS: dict[str, dict[str, tuple[str, ...]]] = {
    "K1": {
        "listed": ("A8", "A13", "A14", "A17"),
        "soe": ("A7", "A8", "A9", "A12", "A49", "A50", "A51", "A54"),
    },
}

#: 🔴 账龄作**列**维度的位置（Requirement 10.3 / Property 37）—— 必须保持为列
AGING_COLUMN_ANCHORS: dict[str, dict[str, tuple[str, ...]]] = {
    "K1": {
        "listed": ("D124", "D137"),
        "soe": ("D103", "D126"),
    },
}

#: K1 listed 的月度细分行（源模板事实，Requirement 10.4 —— 必须保留）
K1_MONTHLY_DETAIL_ANCHORS: tuple[tuple[str, str], ...] = (
    ("A9", "其中：0-X个月"),
    ("A10", "X-Y个月"),
)

#: 🔴 源模板自身缺陷登记（Requirement 8.6 / Property 31）——
#: 按意图实现、不照抄；配 stale 检测（源模板修好后打红提醒移出）

#: K1 两版的 `#REF!` 断链数（**推翻初稿记的 11 处**）
K1_REF_ERROR_COUNTS: dict[str, int] = {"listed": 35, "soe": 35}

#: K6 合计行「账面价值」列是说明文字而非公式 —— 载荷层须按「账面余额 − 减值准备」派生
K6_TOTAL_ROW_TEXT_CELLS: dict[str, tuple[str, str]] = {
    "listed": ("D16", "C=A+B=报表数"),
    "soe": ("D19", "A+B=报表数"),
}

#: K3 soe 按性质表标签列列头是 `账  龄`（listed 侧 `项 目` 才对）—— 按 listed 字面
K3_NATURE_LABEL_HEADER: dict[str, str] = {"listed": "A18", "soe": "A18"}


# ─────────────────────────────────────────────────────────────────────────────
# 加载（模块级缓存，键含 mtime 防变异检验假绿）
# ─────────────────────────────────────────────────────────────────────────────

_WB_CACHE: dict[tuple[str, int, int, bool], object] = {}


def _load(wp_code: str, *, data_only: bool = False):
    """加载 workbook。

    🔴 **`data_only` 必须按用途分**（2026-08-09 实测，两个口径差 16 处标记）：

    - ``data_only=False``（默认）→ 读**公式字符串**。`#REF!` 断链断言必须用它
      （`data_only=True` 下 `#REF!` 格返回 ``None``，判据会静默归零）。
    - ``data_only=True`` → 读**缓存值** = 审计师在 Excel 里**看到的内容**。
      动态插行标记判定必须用它 —— K8/K9/K10/K11/K12 五个循环的 listed 披露
      sheet 里那批 `……` 标记格是**公式格**（缓存值是 `……`、公式串不是），
      用 `False` 扫会漏掉它们（实测 148 vs 164，差的 16 处全在这批）。

    缓存键含 ``(path, mtime_ns, size)`` —— **纯路径键会让变异检验静默假绿**
    （变异脚本的工作方式是「改文件 → 跑测试 → 还原」）。
    """
    if load_workbook is None:  # pragma: no cover
        pytest.fail(f"openpyxl 不可用：{_OPENPYXL_ERR}")
    fn = WORKBOOKS.get(wp_code)
    assert fn, f"{wp_code} 未登记 workbook 文件名"
    p = TPL_DIR / fn
    assert p.exists(), f"源模板不存在：{p}"
    st = p.stat()
    key = (str(p), st.st_mtime_ns, st.st_size, data_only)
    if key not in _WB_CACHE:
        _WB_CACHE[key] = load_workbook(p, data_only=data_only, read_only=False)
    return _WB_CACHE[key]


def _ws(wp_code: str, variant: str, *, data_only: bool = False):
    """取披露 sheet（按冻结的逐字 sheet 名）。

    ``data_only`` 语义同 :func:`_load` —— 判「用户看到的文字」（列头 / 动态标记 /
    账龄字面）传 ``True``；判「公式是否已坏」（``#REF!``）传 ``False``。
    """
    wb = _load(wp_code, data_only=data_only)
    name = DISCLOSURE_SHEETS[wp_code][variant]
    assert name in wb.sheetnames, (
        f"{wp_code} 源模板无 sheet「{name}」；实际 sheetnames={wb.sheetnames}"
    )
    return wb[name]


def _text(ws, coord: str) -> str:
    v = ws[coord].value
    return "" if v is None else str(v)


# ─────────────────────────────────────────────────────────────────────────────
# 判据基础设施自检（应全绿；不绿说明整组断言在空转）
# ─────────────────────────────────────────────────────────────────────────────


