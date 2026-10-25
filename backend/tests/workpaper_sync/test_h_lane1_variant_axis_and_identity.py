# -*- coding: utf-8 -*-
r"""lane1（H3/H5/H7）变体轴 + 动态列范式 + 族 C 身份的收口判据。

spec: `h3-h5-h7-variant-axis-and-dynamic-column-paradigm`

═══ 与 foundation 守卫的分工 ═══════════════════════════════════════════════════

foundation 的 `test_h_foundation_hc_guards.py` 守 HC-5/HC-7 的**清册**（几组变体轴、
族 C 命中几处）；本文件守 lane1 的**实例化结果**（契约里坐标怎么写的、那 3 处族 C 改成
什么形态、旧身份靠什么机制不丢）。

🔴 **族 C 命中数不会因为修好而变少**：`FAMILY_C_RE` 判的是「身份模板里插了语义值」，
它允许后面再跟随机后缀 —— 所以 foundation 那条「族 C 7 处」判据修完仍是 7，**不是没修**。
本文件补的正是「这 7 处里属 lane1 的 3 处已带唯一化后缀」这一层。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from tests.workpaper_sync import h_cycle_facts as F

CONTRACTS = F.CONTRACTS_DIR
COMP = F.COMPOSABLES
WORKPAPER = COMP.parent

#: 唯一化后缀（与 `h_cycle_facts.FAMILY_A_SUFFIX_RE` 同域，独立写一份是为了本文件自洽）
UNIQ_RE = re.compile(r"Math\.random|Date\.now|randomUUID")


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="replace")


# ════════════════════════════════════════════════════════════════════════════
# HV-P1 / HV-P2　变体轴：契约坐标写法与消歧
# ════════════════════════════════════════════════════════════════════════════

#: 三条 entry 的契约 → 期望的 (sheet_key, excel_name 关键片段) 组。
#: 🔴 字段名是 `excel_name` 而**不是** `sheet_name` —— 后者在契约里根本不存在，
#:    按名字推字段会得到一串 None（方法论㉑：字段路径必须现算验证）。
LANE1_CONTRACTS: dict[str, tuple[tuple[str, str], ...]] = {
    "h3.investment_property_detail": (
        ("h302cost-managed", "成本模式"),
        ("h302fair-managed", "公允价值模式"),
    ),
    "h5.oil_gas_assets_detail": (("h502-managed", "H5-2"),),
    "h7.biological_assets_detail": (
        ("h702cost-managed", "成本"),
        ("h702fair-managed", "公允价值"),
    ),
}


@pytest.mark.parametrize("cid", sorted(LANE1_CONTRACTS))
def test_variant_sheets_use_full_excel_name_not_bare_sheet_code(cid: str) -> None:
    """HV-P1：坐标写**全名**（`excel_name`），变体轴只作查询索引 —— 不靠 sheet_code 定位。"""
    data = json.loads((CONTRACTS / f"{cid}.json").read_text(encoding="utf-8"))
    sheets = data.get("sheets") or []
    got = {str(s.get("sheet_key")): str(s.get("excel_name") or "") for s in sheets}
    for key, needle in LANE1_CONTRACTS[cid]:
        assert key in got, f"{cid}: 缺 sheet_key {key}，实测 {sorted(got)}"
        assert got[key], f"{cid}/{key}: `excel_name` 为空 ⇒ 只能靠 sheet_code 定位，会撞变体"
        assert needle in got[key], f"{cid}/{key}: excel_name {got[key]!r} 里没有 {needle!r}"


@pytest.mark.parametrize("cid", sorted(LANE1_CONTRACTS))
def test_two_measurement_models_have_independent_keys_and_names(cid: str) -> None:
    """HV-P2：同一 `sheet_code` 的两个计量模式必须**各有独立键与独立全名**。

    🔴 反向断言不可省：只查「两个键都在」的话，两个键指向同一个 `excel_name`
    （复制粘贴漏改）也能过 —— 而那正是「静默取首张」的等价缺陷。
    """
    expected = LANE1_CONTRACTS[cid]
    if len(expected) < 2:
        pytest.skip(f"{cid} 只有单张受管 sheet，无变体轴")
    data = json.loads((CONTRACTS / f"{cid}.json").read_text(encoding="utf-8"))
    sheets = data.get("sheets") or []
    keys = [str(s.get("sheet_key")) for s in sheets]
    names = [str(s.get("excel_name") or "") for s in sheets]
    assert len(set(keys)) == len(keys), f"{cid}: sheet_key 有重复 {keys}"
    assert len(set(names)) == len(names), f"{cid}: excel_name 有重复 {names} ⇒ 两个变体指向同一张"


# ════════════════════════════════════════════════════════════════════════════
# HV-P11　族 C 三处：形态已对齐族 A + 旧身份靠 preserve-on-read 不丢
# ════════════════════════════════════════════════════════════════════════════

#: (文件, 该处身份模板的定位正则)
LANE1_FAMILY_C_SITES: tuple[tuple[str, str], ...] = (
    ("useH3Adjustment.ts", r"`\$\{kind\}-\$\{cat\}[^`]*`"),
    ("useH3RentalIncome.ts", r"`subtotal-\$\{cat\}[^`]*`"),
    ("useH5Adjudication.ts", r"`row-\$\{prefix\}-\$\{cat\}[^`]*`"),
)


@pytest.mark.parametrize(("fname", "pattern"), LANE1_FAMILY_C_SITES)
def test_family_c_sites_now_carry_a_uniqueness_suffix(fname: str, pattern: str) -> None:
    """HV-P11：三处必须带唯一化后缀，否则同名类别会共用一个身份。"""
    text = _read(COMP / fname)
    hits = re.findall(pattern, text)
    assert hits, f"{fname}: 找不到该族 C 身份模板（正则 {pattern}）"
    for frag in hits:
        assert UNIQ_RE.search(frag), (
            f"{fname}: 身份模板 {frag!r} 没有唯一化后缀 ⇒ 同名类别撞身份"
        )


#: 每个 normalize 函数里「先用库里已有 rowId」的形态（`raw.rowId ?? <生成>`）。
PRESERVE_ON_READ_FILES: tuple[str, ...] = (
    "useH3Adjustment.ts",
    "useH3AdjudicationCost.ts",
    "useH5Adjudication.ts",
    "useH5Detail.ts",
)


def _normalize_function_bodies(text: str) -> list[tuple[str, str]]:
    r"""取出每个 `function _normalize*` 的函数体（花括号配平定界）。

    🔴 **必须按函数体取，不能整文件 `re.search`**：本文件首版就是整文件搜
    `rowId: raw.rowId ??`，而这些文件里**同时存在**「读库 normalize」与「新建行 builder」
    两类站点 —— builder 本来就该直接生成身份。于是我把 `useH5Detail._normalizeRow`
    的 `raw.rowId ??` 整个删掉做变异时，守卫**照样 18 passed**（它搜到的是 L166 那个
    builder）。这就是一条恒绿判据。

    🔴 **第二版又改成花括号配平**：第一版按 `^{indent}\}` 猜闭合，实测把函数体取成
    98~364 行（远超真实长度）⇒ 整段仍把后面的 builder 包进来，变异**照样不红**。
    按缩进猜闭合在嵌套对象字面量面前不成立 —— 与「`split(')')` 遇嵌套括号提前截断」同源。
    ⇒ 一条判据连踩两次假绿，根因都是「边界靠猜」。
    """
    out: list[tuple[str, str]] = []
    for m in re.finditer(r"\bfunction\s+(_normalize\w*)\s*\(", text):
        name = m.group(1)
        i = text.find("{", m.end())
        if i < 0:
            continue
        depth = 0
        end = len(text)
        for j in range(i, len(text)):
            ch = text[j]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end = j
                    break
        out.append((name, text[i : end + 1]))
    return out


@pytest.mark.parametrize("fname", PRESERVE_ON_READ_FILES)
def test_legacy_identities_survive_via_preserve_on_read(fname: str) -> None:
    """🔴 spec 原文要求「必须带旧身份迁移映射」，实现用的是**等效更强**的手法：读库时
    优先沿用 `raw.rowId`，只有库里没有才生成新身份。

    真库实证（本轮现算）：`H5-1-cost-rows` 1059 B 里是 `"rowId":"row-c-油井资产"`、
    `H5-1-depletion-rows` 是 `row-d-油井资产`，H1 侧还有 `row-c-房屋及建筑物` 等。
    只要读路径沿用它们，就不存在「既有行全部变新行、历史金额串位」 —— 也就不需要一张
    显式映射表（映射表反而多一处会漂的真源）。

    ⇒ 这条判据守的就是那个 `??`：谁把它「清理」成无条件生成，真库历史行当场全部错位。
    """
    text = _read(COMP / fname)
    bodies = _normalize_function_bodies(text)
    assert bodies, f"{fname}: 找不到任何 `function _normalize*` ⇒ 读路径形态变了，判据失效"
    for name, body in bodies:
        assert re.search(r"rowId:\s*raw\.rowId\s*\?\?", body), (
            f"{fname}::{name} 里没有 `rowId: raw.rowId ??` ⇒ 读库时不再沿用已有身份，"
            "真库里 row-c-* / row-d-* 那批历史行会全部被当成新行、历史金额串位"
        )


# ════════════════════════════════════════════════════════════════════════════
# HV-P12　H5 小计行不落库（契约无需排除）
# ════════════════════════════════════════════════════════════════════════════


class TestH5SubtotalRowsAreNeverPersisted:
    """HV-P12：小计行是 computed，存库前被 filter 掉 ⇒ 契约**不需要**把它们写进排除列表。"""

    def test_subtotal_rows_are_filtered_before_persist(self) -> None:
        text = _read(COMP / "useH5Adjudication.ts")
        hits = re.findall(r"filter\(\(?\w+\)?\s*=>\s*!\w+\.isSubtotal\)", text)
        assert len(hits) >= 3, (
            f"`filter(r => !r.isSubtotal)` 命中 {len(hits)} 处（预期 ≥3：成本/折耗/减值三块）"
        )

    def test_subtotal_identity_is_stable_and_that_is_correct(self) -> None:
        """🔴 小计行用稳定串 `row-{c|d|i}-subtotal`（**无**随机后缀）—— 这不是族 C 漏修。

        它压根不入库（上一条判据），身份只用于前端 `:key`；给它加随机后缀反而会让
        每次重算都换 key、整行重绘。故此处显式断言「就该是稳定串」，防后人误改。
        """
        text = _read(COMP / "useH5Adjudication.ts")
        m = re.search(r"rowId:\s*`row-\$\{prefix\}-subtotal`", text)
        assert m, "小计行身份不再是稳定串 `row-${prefix}-subtotal`"
        assert not UNIQ_RE.search(m.group(0))


# ════════════════════════════════════════════════════════════════════════════
# HV-P5 / HV-P6 / HV-P7　三条载体接线与 legacy 处置
# ════════════════════════════════════════════════════════════════════════════


class TestLane1Carriers:
    def test_h7_carrier_is_the_tab_not_the_stub_composable(self) -> None:
        """HV-P6：H7 的载体是 Tab（内联 api + 主表键），`useH7DetailCost.ts` 是取值 stub。

        🔴 接到 stub 上是假绿典型：文件改了、桥也建了，但那个 composable 没有写路径，
        双向永远不通。故两侧都断言。
        """
        tab = next(WORKPAPER.rglob("H7TabDetailCost.vue"))
        tab_text = _read(tab)
        assert "H7-2-cost-rows" in tab_text, "主表键不在 Tab 里 ⇒ 载体判定错了"
        assert re.search(r"from ['\"]@/services/apiProxy['\"]", tab_text), "Tab 未内联 api"

        stub = next(WORKPAPER.rglob("useH7DetailCost.ts"))
        stub_text = _read(stub)
        assert len(stub_text.splitlines()) < 80, "stub 变大了 —— 写路径可能被搬了进去"
        assert "useWorkpaperSyncBridge" not in stub_text, (
            "取值 stub 里出现了双向桥 ⇒ 接错载体（假绿典型）"
        )

    def test_h7_formdata_is_on_the_do_not_delete_list(self) -> None:
        """HV-P7：`useH7FormData` 是 H7 唯一 TB 发布门，slice 把它列进删除名单是**错的**。"""
        p = COMP / "useH7FormData.ts"
        assert p.exists(), "useH7FormData.ts 被删了 —— H7 的 TB 发布门随之消失"
        text = _read(p)
        assert text.count("publishToTb") >= 2, (
            f"`publishToTb` 命中 {text.count('publishToTb')} 处（预期 ≥2）⇒ 发布门不完整"
        )

    def test_deleted_dual_modes_stay_deleted_and_take_the_fourth_store_with_them(self) -> None:
        """HV-P7 + HC-10：两个 dual-mode 已删；删掉它们同时消除第四处存储前缀。"""
        for name in ("useH5DualMode.ts", "useH7DualMode.ts"):
            assert not (COMP / name).exists(), f"{name} 又回来了"
        residue = [
            p.relative_to(F.FRONTEND_SRC).as_posix()
            for p in F.FRONTEND_SRC.rglob("*")
            if p.is_file() and p.suffix in {".ts", ".vue"} and "h5-dual-mode:" in _read(p)
        ]
        assert residue == [], f"第四处存储前缀 `h5-dual-mode:` 仍在 {residue}"

    def test_h5_per_tab_instances_are_enumerated_not_assumed(self) -> None:
        """HV-P5：H5 是 `per_tab_formdata_instance` —— 实例化点**现算**，不写死个数。

        判据形态：每个 `h5/**` 下的 Tab 只要用到 `useH5FormData`，就必须是**直接调用**
        （而不是从别处接一个实例进来）；漏任一点 = 那个 Tab 双向不通但文件已改（假绿）。
        """
        sites = []
        for p in list(F.FRONTEND_SRC.rglob("*.vue")) + list(F.FRONTEND_SRC.rglob("*.ts")):
            rel = p.relative_to(F.FRONTEND_SRC).as_posix()
            if "__tests__" in rel or rel.endswith(".spec.ts"):
                continue
            if "useH5FormData(" in _read(p):
                sites.append(rel)
        tabs = [s for s in sites if "/h5/" in s]
        assert len(tabs) >= 15, f"H5 Tab 侧实例化点只有 {len(tabs)} 个，疑似漏接：{tabs}"
        # 每个 h5 Tab 目录下的站点都必须是 .vue（Tab 自持一份实例）
        assert all(s.endswith(".vue") for s in tabs), [s for s in tabs if not s.endswith(".vue")]
