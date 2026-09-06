# -*- coding: utf-8 -*-
"""Task 24 可达性清册守卫 —— design.md 分母表 ↔ 清册 JSON ↔ 现算，三向锁死。

spec: excel-workbook-wide-row-change-propagation / Wave 0 Task 24
Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 8.5
Properties: **P24** / **P25** / **P36**

═══ 为什么是「三向」而不是把数字写进守卫 ═══

把期望值硬编码进守卫，等于**在守卫里复制一份真源** —— 改真源不改守卫（或反过来）都不会红，
那是本平台反复出现的假绿形态。本文件改成：

    design.md「分母断言」表（人读的真源，带 `key` 列）
        ↕ 解析比对
    backend/data/workpaper_row_change_reachability.json（机器可读清册）
        ↕ 现算比对
    generate_row_change_reachability.build_inventory()（真实执行）

三边任一处被单独改动都会打红。这一层锁在首次运行时就抓出了两处真源缺陷：
① 分母表把「全部限定引用」与「目标真实存在的引用」两个口径混成一行（182/144,154 vs
174/140,726）；② definedNames 的 `builtin_other_sheet` 类名与它自己的样本自相矛盾
（样本本身就是「目标不在本工作簿」），归并后 `target_not_in_workbook` 由 1,991 改为 2,001。

═══ AC 6.5：宿主模板不按 sheet 名定位 ═══

判据落在**行为**上而不是「代码里没有某个字符串」：
`test_host_binding_is_content_addressed` 断言 4 份契约的 `template_sha256` 与磁盘现算逐份相符
（只有内容寻址才可能成立），并同时断言「G7 契约声明的 sheet 名在全库出现在 >1 份模板里」——
即按名定位本会歧义，而实际绑定唯一。
"""

from __future__ import annotations

import copy
import json
import os
import re
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
for _p in (str(_BACKEND), str(_BACKEND / "scripts" / "gen")):
    if _p not in sys.path:  # pragma: no cover - import 环境自举
        sys.path.insert(0, _p)
os.environ.setdefault("DB_DISABLE_SSL", "True")

import generate_row_change_reachability as G  # noqa: E402

DESIGN_MD: Path = (
    _REPO / ".kiro" / "specs" / "excel-workbook-wide-row-change-propagation" / "design.md"
)

_DENOMINATOR_HEADER = "| key | 分母 | 值 | 定义（判据必须按此口径复算） |"
_MARKER_HEADER = "| key | 标记 | 命中 sheet | 命中模板 |"
_KEY_CELL = re.compile(r"^\|\s*`([A-Za-z0-9_]+)`\s*\|")
_NUM = re.compile(r"\*{0,2}([\d,]+)\*{0,2}")
#: Markdown 表格列分隔符 —— 只认**未转义**的 `|`。
_CELL_SPLIT = re.compile(r"(?<!\\)\|")


def _parse_table(header: str) -> list[list[str]]:
    """取 `header` 之后连续的表格数据行，逐行拆成单元格列表。"""
    lines = DESIGN_MD.read_text(encoding="utf-8").splitlines()
    try:
        start = lines.index(header)
    except ValueError as exc:  # pragma: no cover - 真源被改名
        raise AssertionError(
            f"design.md 里找不到表头 {header!r} —— 分母真源被改动过，"
            "本守卫的解析基础失效，必须人工复核"
        ) from exc
    rows: list[list[str]] = []
    for line in lines[start + 1:]:
        if not line.startswith("|"):
            break
        if set(line.replace("|", "").replace(" ", "")) <= {"-", ":"}:
            continue  # 分隔行
        # 🔴 只按**未转义**的 `|` 拆列。表里有 `` `dataValidation/formula1\|2` `` 这种
        # Markdown 转义竖线，裸 split("|") 会把它当列分隔符，导致该行的值列错位。
        rows.append([c.strip() for c in _CELL_SPLIT.split(line.strip().strip("|"))])
    return rows


def design_denominators() -> dict[str, int]:
    out: dict[str, int] = {}
    for cells in _parse_table(_DENOMINATOR_HEADER):
        key = _KEY_CELL.match("|" + cells[0] + "|")
        if key is None:
            continue
        hit = _NUM.fullmatch(cells[2])
        assert hit is not None, f"分母 {key.group(1)} 的值不是纯数字: {cells[2]!r}"
        out[key.group(1)] = int(hit.group(1).replace(",", ""))
    return out


def design_markers() -> dict[str, dict[str, int]]:
    out: dict[str, dict[str, int]] = {}
    for cells in _parse_table(_MARKER_HEADER):
        key = _KEY_CELL.match("|" + cells[0] + "|")
        if key is None:
            continue
        sheets = _NUM.fullmatch(cells[2])
        templates = _NUM.fullmatch(cells[3])
        assert sheets and templates, f"标记 {key.group(1)} 的计数不是纯数字: {cells!r}"
        out[key.group(1)] = {
            "sheets": int(sheets.group(1).replace(",", "")),
            "templates": int(templates.group(1).replace(",", "")),
        }
    return out


def verify_contract_template_binding(
    load: Any = None,
) -> tuple[list[str], int]:
    """独立校验 4 份契约的「宿主 = contract.template.relative_path + sha256」绑定。

    刻意**不读**生成器写下的 `template_sha256_matches` —— 那等于让守卫核对自己写的数字。
    这里自己 hash 磁盘文件，与契约冻结的 digest 逐份比。

    Returns:
        `(问题清单, 校验过的契约数)`
    """
    import hashlib

    from app.services.workpaper_sync.adapters.registry import (
        DELIVERED_PER_ENTRY_CONTRACTS,
    )
    from app.services.workpaper_sync.contracts import load_contract

    loader = load or load_contract
    problems: list[str] = []
    checked = 0
    for reg in DELIVERED_PER_ENTRY_CONTRACTS:
        entry_id = str(reg.get("entry_id") or "").strip()
        contract = loader(str(reg.get("contract_id") or "").strip())
        ref = contract.template
        rel = ref.relative_path.replace("\\", "/")
        path = G.TEMPLATE_ROOT / rel
        checked += 1
        if not path.is_file():
            problems.append(
                f"{entry_id} / {contract.contract_id}: 契约模板 {rel!r} 不在模板库里"
                " —— 契约与权威目录脱节"
            )
            continue
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != ref.sha256:
            problems.append(
                f"{entry_id} / {contract.contract_id}: 契约冻结 "
                f"template_sha256={ref.sha256[:12]}… 与磁盘现算 {actual[:12]}… 不符 "
                f"—— 权威模板 {rel!r} 已漂移，或绑定取错了模板"
            )
    return problems, checked


@pytest.fixture(scope="module")
def stored() -> dict[str, Any]:
    assert G.INVENTORY_PATH.is_file(), (
        f"可达性清册缺失：{G.INVENTORY_PATH.relative_to(_REPO)} —— 它必须入库"
        "（规则 7 第 3 项），否则干净 checkout 下本守卫无从比对"
    )
    return G.load_inventory()


@pytest.fixture(scope="module")
def current() -> dict[str, Any]:
    """现算一次，全模块共用（全库 351 份实测约 10 秒）。"""
    return G.build_inventory()


# ═══════════════════════════════════════════════════════════════════════════
# 1. 三向锁
# ═══════════════════════════════════════════════════════════════════════════


def test_inventory_matches_current_computation(
    current: dict[str, Any], stored: dict[str, Any]
) -> None:
    """清册 ↔ 现算：逐字相同（`--check` 的等价判据）。"""
    problems = G.diff_inventory(current, stored)
    assert not problems, (
        f"清册与现算有 {len(problems)} 处差异 —— 需重跑生成器 --apply 并复核：\n  "
        + "\n  ".join(problems[:20])
    )


def test_design_denominator_table_matches_inventory(stored: dict[str, Any]) -> None:
    """🔴 design.md 分母表 ↔ 清册：逐键相等。

    这是「真源与守卫双向锁死」的那一半 —— 改 design.md 不改代码、或改代码不改 design.md，
    本条都会红。
    """
    design = design_denominators()
    inventory = stored["denominators"]
    assert design, "design.md 分母表解析出 0 行 —— 解析器坏了或真源被改动"

    missing_in_inventory = sorted(set(design) - set(inventory))
    missing_in_design = sorted(set(inventory) - set(design))
    assert not missing_in_inventory, (
        f"design.md 声明了但清册没产出的分母：{missing_in_inventory}"
    )
    assert not missing_in_design, (
        f"清册产出了但 design.md 没登记的分母：{missing_in_design} —— "
        "分母必须在真源里有一行，否则它不受任何人复核"
    )
    mismatched = {
        k: (design[k], inventory[k]) for k in design if design[k] != inventory[k]
    }
    assert not mismatched, (
        "design.md 分母表与清册不一致（键: (design.md, 清册)）：\n  "
        + "\n  ".join(f"{k}: {v}" for k, v in sorted(mismatched.items()))
    )


def test_design_marker_table_matches_inventory(stored: dict[str, Any]) -> None:
    """占位标记表 ↔ 清册：逐键逐列相等。它决定 `affected_templates` 那个分母。"""
    design = design_markers()
    inventory = stored["placeholder_markers"]
    assert set(design) == set(inventory), (
        f"标记集合不一致：仅 design.md {sorted(set(design) - set(inventory))}，"
        f"仅清册 {sorted(set(inventory) - set(design))}"
    )
    mismatched = {k: (design[k], inventory[k]) for k in design if design[k] != inventory[k]}
    assert not mismatched, (
        "占位标记表与清册不一致：\n  "
        + "\n  ".join(f"{k}: design.md={v[0]} 清册={v[1]}" for k, v in sorted(mismatched.items()))
    )


def test_declared_marker_set_matches_generator(stored: dict[str, Any]) -> None:
    """生成器的标记正则集合与 design.md 的 `key` 列逐字一致 —— 第三边。"""
    assert set(G.PLACEHOLDER_MARKERS) == set(design_markers()), (
        "生成器的 PLACEHOLDER_MARKERS 与 design.md 标记表的 key 列不一致"
    )
    assert set(stored["placeholder_markers"]) == set(G.PLACEHOLDER_MARKERS)


def test_renameable_marker_is_zero_in_xlsx(stored: dict[str, Any]) -> None:
    """`可改名` 在全库 xlsx 里命中 0 —— requirements.md 曾把它列为主要占位标记。

    这条把「原登记的六标记算出 101 份、扩到 12 类才算出 136 份」这个事实锁住：
    若哪天它不再是 0，说明模板库变了，`affected_templates` 的分母要重新裁定。
    """
    assert stored["placeholder_markers"]["renameable"] == {"sheets": 0, "templates": 0}


# ═══════════════════════════════════════════════════════════════════════════
# 2. 清册内容（R6.1 / R6.2 / R6.3）
# ═══════════════════════════════════════════════════════════════════════════


def test_states_and_reasons_are_closed_vocabulary(stored: dict[str, Any]) -> None:
    """状态限定三态；`blocked` / `out_of_scope` 必须带封闭词表里的原因（R6.2）。"""
    assert stored["states"] == list(G.STATES) == ["propagated", "blocked", "out_of_scope"]
    rows = list(stored["affected_templates"]) + list(stored["contracted_entries"])
    assert rows, "清册两侧都空 —— 判据会在空集上恒真"
    for row in rows:
        assert row["state"] in G.STATES, f"非法状态 {row['state']!r}"
        if row["state"] == "propagated":
            continue
        assert row.get("reason") in G.REASONS, (
            f"{row.get('rel_path') or row.get('entry_id')} 的 state={row['state']} "
            f"缺合法 reason（实得 {row.get('reason')!r}）—— R6.2 要求写明阻塞原因"
        )


def test_affected_inventory_covers_declared_denominator(stored: dict[str, Any]) -> None:
    """受影响模板逐份登记，条数 == `affected_templates` 分母（R6.1）。"""
    rows = stored["affected_templates"]
    assert len(rows) == stored["denominators"]["affected_templates"]
    assert len(rows) > 0
    for row in rows:
        assert row["managed_sheet_candidates"], f"{row['rel_path']} 没有受管 sheet 候选"
        assert row["referencing_sheets"], f"{row['rel_path']} 没有引用侧 sheet"
        assert row["referencing_sites"] > 0, f"{row['rel_path']} 引用处数为 0 却被判受影响"


def test_uncontracted_templates_are_blocked_with_gate1_reason(
    stored: dict[str, Any],
) -> None:
    """🔴 Gate 1 裁决：无契约的一律 `blocked` + `no_projection_contract`。

    分母断言：这类必须占绝大多数（今天只有 4 个 entry 有契约）。若某天大部分受影响模板
    都不是这个原因，说明契约覆盖面变了，Gate 1 的裁决需要重新审。
    """
    rows = stored["affected_templates"]
    no_contract = [r for r in rows if r["reason"] == "no_projection_contract"]
    assert len(no_contract) > len(rows) * 0.9, (
        f"仅 {len(no_contract)}/{len(rows)} 份受影响模板以 no_projection_contract 阻塞 —— "
        "与 Gate 1 的裁决（覆盖面 = 4 个已发契约 entry）不符，需重新审裁决"
    )


def test_extremes_are_registered_with_perf_data(stored: dict[str, Any]) -> None:
    """极端规模组合单独登记，且最极端那几份带 Gate 3 的实测耗时与阈值（R6.3 / 8.5）。"""
    extremes = stored["extremes"]
    assert len(extremes) == stored["denominators"]["extreme_combinations"]
    assert len(extremes) >= 4, f"引用处数 > 1000 的组合只有 {len(extremes)} 个，分母偏少"
    assert extremes == sorted(extremes, key=lambda r: (-r["sites"], r["rel_path"], r["sheet"]))
    top = extremes[0]
    assert top["sites"] == stored["denominators"]["extreme_max_sites"]
    assert top["rel_path"] == "C/C24 会计分录 - 细节测试.xlsx"
    assert top["sheet"] == "2025假期清单"

    measured = [r for r in extremes if r["gate3_measured_ms"] is not None]
    assert len(measured) >= 4, (
        f"只有 {len(measured)} 个极端组合带 Gate 3 实测耗时 —— R6.3 要求给出性能实测数据"
    )
    for row in measured:
        assert row["perf_threshold_ms"] == G.PERF_THRESHOLD_MS == 2000
        assert row["gate3_measured_ms"] < row["perf_threshold_ms"], (
            f"{row['rel_path']} 的实测耗时 {row['gate3_measured_ms']}ms 已超阈值 —— "
            "Gate 3 的『不异步化』裁决需重新审"
        )


# ═══════════════════════════════════════════════════════════════════════════
# 3. AC 6.5：宿主绑定是内容寻址的
# ═══════════════════════════════════════════════════════════════════════════


def test_host_binding_is_content_addressed(stored: dict[str, Any]) -> None:
    """🔴 4 份契约的 `template_sha256` 与磁盘现算逐份相符。

    只有沿 `contract.template.relative_path` + `template_sha256` 绑定才可能全部成立；
    按 sheet 名或 manifest 的 `wp_code_patterns` 猜出来的宿主不会恰好都对上 digest。
    顺带这也是一条**模板漂移**判据：权威模板被改了字节，本条立刻红。

    🔴 **本条不读生成器写下的 `template_sha256_matches` 布尔值**，而是**独立重算**：
    从 `DELIVERED_PER_ENTRY_CONTRACTS` → `load_contract` → `contract.template` 取冻结
    digest，再自己 hash 磁盘文件。变异检验实测过 —— 把生成器里那个比对短路成恒 `True`
    时，读布尔值的写法判 GREEN（守卫在核对自己写的数字，假绿第②源）。
    """
    rows = {r["entry_id"]: r for r in stored["contracted_entries"]}
    assert len(rows) == stored["denominators"]["delivered_contract_entries"] == 4

    problems, checked = verify_contract_template_binding()
    assert checked == 4, f"只独立校验了 {checked} 份契约，应为 4（防空集恒真）"
    assert not problems, "契约 ↔ 权威模板的内容寻址绑定不成立：\n  " + "\n  ".join(problems)

    for entry_id, row in rows.items():
        assert row["template_present"] is True
        assert row["template_sha256_matches"] is True, (
            f"{entry_id} 的清册登记说 digest 不符 —— 与独立重算矛盾"
        )


def test_binding_verifier_detects_injected_digest_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """🔴 反向自检：注入一个错的 `template_sha256` ⇒ 校验器必须报出漂移。

    没有这条，上面那条判据在「校验器真的在 hash」与「校验器压根没在比」之间无法区分 ——
    变异检验实测过：把生成器里的比对短路成恒 `True` 时，只读那个布尔值的写法判 GREEN。
    （顺带说明那条变异本身也是**无效用例**：短路成 `True` 在「本来就全部匹配」的状态下
    不改变任何可观测结果，敏感的做法是注入一个**不匹配**的 digest。）
    """
    from app.services.workpaper_sync import contracts as C

    real_load = C.load_contract

    def _drifted(adapter_id: str):
        contract = real_load(adapter_id)
        if adapter_id != "d2.receivable_detail":
            return contract
        bogus = replace(contract.template, sha256="0" * 64)
        return replace(contract, template=bogus)

    monkeypatch.setattr(
        "generate_row_change_reachability.load_contract", _drifted, raising=False
    )
    problems, checked = verify_contract_template_binding(load=_drifted)
    assert checked == 4
    assert any("d2.receivable_detail" in p or "gt-d2" in p for p in problems), (
        f"注入的 digest 漂移没被报出来 —— 校验器没在真的 hash。实得 {problems}"
    )


@pytest.mark.parametrize("side", ["stored", "current"])
def test_sheet_name_lookup_would_have_been_ambiguous(
    side: str, stored: dict[str, Any], current: dict[str, Any]
) -> None:
    """反证 AC 6.5 的必要性：契约声明的 sheet 名在全库**不唯一**。

    实测 `附注披露信息（国企）` 出现在多份模板里 ⇒ 若按 sheet 名定位宿主必然歧义；
    而 G7 entry 的实际绑定唯一且指向 `G/G7 长期股权投资.xlsx`。
    两条合起来才说明「内容寻址」不是多余的谨慎。
    """
    payload = stored if side == "stored" else current
    g7 = next(
        r for r in payload["contracted_entries"]
        if r["contract_id"] == "g7.soe_subsidiary_disclosure"
    )
    assert g7["template_relative_path"] == "G/G7 长期股权投资.xlsx"

    ambiguity = payload["host_ambiguity"]
    assert ambiguity, "host_ambiguity 为空 —— AC 6.5 的反证数据没被登记"
    for name, info in ambiguity.items():
        assert info["bound_host_is_among_them"], (
            f"契约声明的 sheet 名 {name!r} 竟不在其绑定宿主里 —— 绑定或扫描有一处错了"
        )

    collided = {n: i for n, i in ambiguity.items() if i["templates_containing"] > 1}
    assert collided, (
        "契约声明的受管 sheet 名在全库都唯一 —— 那样按名定位不会歧义，本反证不成立。"
        "若模板库真变成这样，AC 6.5 的必要性论证需要换证据"
    )
    worst = max(i["templates_containing"] for i in ambiguity.values())
    assert worst == payload["denominators"]["max_host_name_collisions"] >= 2, (
        f"[{side}] 最大同名冲突数 {worst} 与分母不一致或不足以证明歧义"
    )
    # G7 那张受管 sheet 是实测冲突最严重的样本
    g7_sheet = g7["managed_sheets"][0]["excel_name"]
    assert ambiguity[g7_sheet]["templates_containing"] > 1, (
        f"{g7_sheet!r} 在全库唯一 —— 换一个冲突样本"
    )
    assert ambiguity[g7_sheet]["other_hosts_sample"], "冲突样本里应能列出别的宿主"


def test_d2_is_the_only_entry_with_propagation_demand(stored: dict[str, Any]) -> None:
    """Gate 1 的核心结论：4 个契约 entry 里只有 D2 有真实传播需求。

    这条决定了 Wave 2 的首要判据载体。若哪天不止 D2，Task 10 / 11 的载体选择要重审。
    """
    rows = {r["contract_id"]: r for r in stored["contracted_entries"]}
    with_demand = {
        cid: r["propagation_demand_sites"]
        for cid, r in rows.items() if r["propagation_demand_sites"] > 0
    }
    assert with_demand == {"d2.receivable_detail": 52}, (
        f"有传播需求的契约 entry 集合变了：{with_demand} —— "
        "Wave 2 的首要判据载体（D2）需重新裁定"
    )
    for cid, row in rows.items():
        if cid == "d2.receivable_detail":
            # 🔴 **不写死具体状态值**：D2 的状态随传播能力落地而合法翻转
            #    （Task 29：`blocked/pending_implementation` → `propagated/implemented`）。
            #    首版这里硬写了 `blocked`，Task 29 翻转后本条漏改而打红 —— 那是判据
            #    与「会随进度变的事实」耦合。改为只断言「有需求 ⇒ 落在两个合法态之一」，
            #    「恰好是哪一态」由 `test_only_d2_flipped_to_propagated` 单独钉死。
            assert (row["state"], row["reason"]) in {
                ("blocked", "pending_implementation"),
                ("propagated", "implemented"),
            }, f"D2 有传播需求却落在意外状态: {row['state']}/{row['reason']}"
        else:
            assert row["state"] == "out_of_scope"
            assert row["reason"] == "no_propagation_demand"


def test_two_denominator_conventions_are_both_registered(stored: dict[str, Any]) -> None:
    """🔴 两个引用口径必须各自有分母，且差值自洽。

    `cross_sheet_sites`（全部限定引用，零回归基线用）与 `resolvable_cross_sheet_sites`
    （目标真实存在，传播用）**不是同一个数**。首次三向锁死时正是这两者被混成一行，
    导致分母表的定义与数值互相矛盾。
    """
    d = stored["denominators"]
    assert d["cross_sheet_sites"] > d["resolvable_cross_sheet_sites"] > 0
    assert (
        d["cross_sheet_sites"] - d["resolvable_cross_sheet_sites"]
        == d["unresolvable_cross_sheet_sites"]
    )
    assert d["templates_with_cross_sheet"] >= d["templates_with_resolvable_cross_sheet"]
    assert d["unresolvable_cross_sheet_sites"] > 0, (
        "权威模板里已坏的跨 sheet 引用为 0 —— 若真如此，两个口径就没必要分开，"
        "但实测是 3,428 处；这里为 0 说明存在性过滤没生效"
    )


def test_defined_name_classes_sum_to_total(stored: dict[str, Any]) -> None:
    """definedNames 四分类之和 == 总数 —— 防某一类被静默漏掉（AC 4.7）。"""
    d = stored["denominators"]
    parts = (
        d["defined_name_builtin_self_scope"],
        d["defined_name_target_not_in_workbook"],
        d["defined_name_user_self_scope"],
        d["defined_name_user_cross_sheet"],
    )
    assert sum(parts) == d["defined_name_cross"], (
        f"四分类之和 {sum(parts)} ≠ 总数 {d['defined_name_cross']} —— "
        "有一类没被登记，它会被静默漏改"
    )
    assert all(p > 0 for p in parts), f"某一类为 0，判据会在空集上恒真: {parts}"


def test_hyperlink_location_classes_sum_to_total(stored: dict[str, Any]) -> None:
    """`hyperlink@location` 三分类之和 == 总数（同 21 条 same_sheet）。"""
    d = stored["denominators"]
    assert (
        d["hyperlink_location_in_workbook"] + d["hyperlink_location_not_in_workbook"]
        <= d["hyperlink_location_cross"]
    )
    assert d["hyperlink_location_in_workbook"] > 0
    assert d["hyperlink_location_not_in_workbook"] > 0


# ═══════════════════════════════════════════════════════════════════════════
# 4. 反向自检
# ═══════════════════════════════════════════════════════════════════════════


def test_diff_detects_denominator_change(
    current: dict[str, Any], stored: dict[str, Any]
) -> None:
    mutated = copy.deepcopy(current)
    mutated["denominators"]["affected_templates"] += 1
    problems = G.diff_inventory(mutated, stored)
    assert any("affected_templates" in p for p in problems)


def test_diff_detects_affected_row_change(
    current: dict[str, Any], stored: dict[str, Any]
) -> None:
    mutated = copy.deepcopy(current)
    mutated["affected_templates"][0]["referencing_sites"] += 1
    problems = G.diff_inventory(mutated, stored)
    assert any("登记内容变了" in p for p in problems)


def test_diff_detects_dropped_affected_row(
    current: dict[str, Any], stored: dict[str, Any]
) -> None:
    mutated = copy.deepcopy(current)
    dropped = mutated["affected_templates"].pop()["rel_path"]
    problems = G.diff_inventory(mutated, stored)
    assert any(dropped in p for p in problems)


def test_design_table_parser_rejects_missing_header() -> None:
    """解析器找不到表头时必须抛，不得静默返回空表（空表会让三向锁恒真）。"""
    with pytest.raises(AssertionError, match="找不到表头"):
        _parse_table("| 这个表头不存在 |")


def test_design_table_parser_yields_expected_shape() -> None:
    """分母表与标记表各自解析出合理条数 —— 防解析器只抓到一两行。"""
    assert len(design_denominators()) >= 25
    assert len(design_markers()) == 12
