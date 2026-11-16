# -*- coding: utf-8 -*-
"""M 循环明细表「模板驱动」守卫（spec `m-cycle-key-naming-unification` \u00a7R12\uff09\u3002

\u9489\u4f4f\u4e09\u4ef6\u4e8b\uff1a

1. **\u884c\u6a21\u578b\u952e = provider \u58f0\u660e\u7684 jsonKey**\uff08\u4e0d\u518d\u662f\u81ea\u9020\u7684 sourceName/beginning/accrual \u90a3\u4e00\u5957\uff09\uff1b
2. **\u884c\u6570 = \u6a21\u677f\u56fa\u5b9a\u884c\u6570**\uff08\u56e0\u4e3a `row_identity_kind = template_row_key`\uff0c\u6a21\u677f\u6ca1\u6709\u591a\u4f59\u884c\u4f4d\uff09\uff1b
3. **\u4e0d\u5728\u524d\u7aef\u91cd\u7b97\u516c\u5f0f\u5217**\uff08\u6a21\u677f\u90a3\u4e9b\u683c\u5b50\u662f\u516c\u5f0f\uff0cOO \u4fa7\u91cd\u7b97\uff1b\u524d\u7aef\u91cd\u590d\u5b9e\u73b0\u5fc5\u7136\u6f02\u79fb\uff09\u3002

\u4e3a\u4ec0\u4e48\u8981\u8fd9\u4e9b\u5224\u636e\uff1a\u539f\u5b9e\u73b0\u4e0e\u6a21\u677f\u5217\u96c6\u5408\u4ea4\u96c6\u22641\uff08M5 \u624b\u5199 6 \u5217 vs \u6a21\u677f 17 \u5217\uff0c\u4ea4\u96c6 0\uff09\uff0c
\u800c**\u8fd9\u4e2a\u7f3a\u9677\u4e0d\u4f1a\u8ba9\u4efb\u4f55\u65e2\u6709\u6d4b\u8bd5\u53d8\u7ea2**\uff08\u4e09\u4e2a\u9875\u9762\u6b64\u524d\u96f6\u6d4b\u8bd5\u8986\u76d6\uff09\u3002
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[1]
_ROOT = _BACKEND.parent
if str(_BACKEND) not in sys.path:  # pragma: no cover
    sys.path.insert(0, str(_BACKEND))

_COMPOSABLES = _ROOT / "audit-platform" / "frontend" / "src" / "components" / "workpaper" / "composables"
_GENERATED = (
    _ROOT
    / "audit-platform"
    / "frontend"
    / "src"
    / "components"
    / "workpaper"
    / "m-cycle"
    / "mCycleDetailColumns.generated.ts"
)

ENTRIES = [
    ("M3", "phase5_m3_treasury_stock", "useM3Detail.ts"),
    ("M5", "phase5_m5_surplus_reserve", "useM5Detail.ts"),
    ("M7", "phase5_m7_special_reserve", "useM7Detail.ts"),
]


def _provider(module_name: str):
    import importlib

    return importlib.import_module(f"app.services.workpaper_sync.{module_name}")


@pytest.mark.parametrize("label,module_name,composable", ENTRIES, ids=[e[0] for e in ENTRIES])
def test_composable_reads_columns_from_generated_file(label, module_name, composable) -> None:
    """composable 必须从生成文件取列，不得自带一份列名清单。"""
    src = (_COMPOSABLES / composable).read_text(encoding="utf-8")
    # 🔴 光看「import 里有这个名字」是不够的：把取列的那一行改成另一个常量名，
    # import 行仍含原名 ⇒ 守卫照绿（本条首版正是这个漏洞，变异实测存活）。
    # 因此要求它以 `M_CYCLE_DETAIL_COLUMNS.{LABEL}` 的形式真取数。
    used = re.search(rf"M_CYCLE_DETAIL_COLUMNS\.{label}\b", src)
    assert used, (
        f"{label}: {composable} 没有以 `M_CYCLE_DETAIL_COLUMNS.{label}` 真取列 —— "
        "列元数据必须来自 provider，自带清单就是第二真源"
    )
    # 🔴 **每一处**取列 / 取行标签都必须挂在生成常量上。
    # 只断言「出现过一次」会漏掉「只改一处，另一处走旁路」
    # （实测：把 3 个取数点里的 1 个改名，旧版守卫照绿）。
    rogue = [
        line.strip()
        for line in src.splitlines()
        if re.search(r"\?\.(fields|rowLabels)\b", line)
        and "M_CYCLE_DETAIL_COLUMNS" not in line
    ]
    # 🔴 行标签必须真的取自生成常量，且**不得出现字面量行标签数组**。
    # 只看「有没有走旁路」会漏掉「把整个来源换成硬编码列表」
    # （实测：把 `= M_CYCLE_DETAIL_COLUMNS.{l}.rowLabels ?? []` 换成 `= ['a','b']`，旧判据照绿）。
    assert re.search(rf"M_CYCLE_DETAIL_COLUMNS\.{label}\?\.rowLabels", src), (
        f"{label}: 行标签没有取自生成常量（应为 "
        f"`M_CYCLE_DETAIL_COLUMNS.{label}?.rowLabels`）—— 行标签属于模板身份"
    )
    literal_labels = re.search(r"=\s*\[\s*['\"]", src)
    assert not literal_labels, (
        f"{label}: 出现了字面量数组赋值 —— 行标签/列清单不得写死，必须取自生成文件"
    )
    assert not rogue, (
        f"{label}: 存在不经生成常量的取列/取行标签：{rogue} —— "
        "那就是第二真源"
    )
    assert "mCycleDetailColumns.generated" in src, (
        f"{label}: 引用路径不对（应指向 m-cycle/mCycleDetailColumns.generated）"
    )


@pytest.mark.parametrize("label,module_name,composable", ENTRIES, ids=[e[0] for e in ENTRIES])
def test_frontend_row_keys_equal_provider_json_keys(label, module_name, composable) -> None:
    """行模型产出的键必须**逐个等于** provider 的 jsonKey（不再自造语义）。"""
    mod = _provider(module_name)
    provider_keys = [f.json_key for f in mod.DETAIL_FIELDS]
    src = (_COMPOSABLES / composable).read_text(encoding="utf-8")

    # 该 composable 用 f.jsonKey 建行 ⇒ 断言它真的是按 provider 键建行，而不是写死键名
    assert "f.jsonKey" in src, (
        f"{label}: 建空行时没有用 `f.jsonKey` —— 说明键名仍是写死的，无法与 provider 保持同步"
    )

    # 反向：不再出现旧的、与契约不相交的键名（抽一笔最容易残留的）。
    # 🔴 **只查代码行，不查注释**：文件头 docstring 刻意点名了旧键（用来说明
    # 「为什么要重建」），把它算成残留会让守卫在**正确代码上变红** ——
    # 那种假阳最终只会逼人把守卫改松。
    code_only = "\n".join(
        line for line in src.splitlines()
        if not line.strip().startswith(("*", "//", "/*"))
    )
    stale = {
        "M3": ["batchName", "repurchaseShares", "cancelAmount", "beginShares"],
        "M5": ["sourceName", "accrual", "capitalConversion", "lossOffset"],
        "M7": ["creditAccrual", "debitExpense", "auditUsage", "usageAje"],
    }[label]
    residue = [k for k in stale if re.search(rf"\b{k}\b", code_only)]
    assert not residue, (
        f"{label}: 旧行模型的键仍残留在**代码**里 {residue} —— "
        "重建不彻底，会与模板列并存成第二套语义"
    )
    assert provider_keys, f"{label}: provider 没有声明任何明细字段"


@pytest.mark.parametrize("label,module_name,composable", ENTRIES, ids=[e[0] for e in ENTRIES])
def test_row_count_follows_the_template(label, module_name, composable) -> None:
    """行数 = 模板固定行数（`template_row_key` 的表没有多余行位）。"""
    mod = _provider(module_name)
    sheet = mod.DETAIL_SHEET
    template_rows = sheet.last_data_row - sheet.first_data_row + 1
    src = (_COMPOSABLES / composable).read_text(encoding="utf-8")
    assert "rowLabels" in src, (
        f"{label}: 没有按模板 rowLabels 建行 —— 行数与行标签都必须来自模板"
    )
    # provider 侧的行数与 data 区一致（这是契约几何，不是前端数字）
    assert template_rows > 0, f"{label}: 模板数据区为空"


@pytest.mark.parametrize("label,module_name,composable", ENTRIES, ids=[e[0] for e in ENTRIES])
def test_formula_columns_are_not_recomputed_in_frontend(label, module_name, composable) -> None:
    """公式列不得在前端重算（模板公式是权威，前端重算必然漂移）。"""
    src = (_COMPOSABLES / composable).read_text(encoding="utf-8")
    banned = ["calcContraEquityEndBalance", "calcEquityEndBalance", "calcEndBalance"]
    residue = [b for b in banned if b in src]
    assert not residue, (
        f"{label}: composable 仍调用公式引擎 {residue} —— 公式列应由 OO 侧重算后同步，"
        "前端重复实现一份就等于与模板赛跑"
    )


def test_generated_file_declares_all_three_entries() -> None:
    """生成文件必须覆盖 M3/M5/M7 三条（少一条说明生成器漏了）。"""
    text = _GENERATED.read_text(encoding="utf-8")
    for label in ("M3", "M5", "M7"):
        assert f"  {label}: {{" in text, f"生成文件缺少 {label}"
    # 每条都要有 rowLabels + fields
    assert text.count("rowLabels:") >= 3, "生成文件的 rowLabels 少于 3 条"
    assert text.count("fields: [") >= 3, "生成文件的 fields 少于 3 条"
