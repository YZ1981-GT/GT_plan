# -*- coding: utf-8 -*-
"""产出工作簿级行变更传播的**可达性清册**，并让 design.md 的分母表可被 CI 复算。

spec: excel-workbook-wide-row-change-propagation / Wave 0 Task 24
Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 8.5
Properties: **P24** / **P25** / **P36**

═══ 为什么这条能在门前做（原本排在 Wave 5）═══

原 rationale 是「清册要登记真实状态，需等传播能力落地才知道哪些 `blocked`」。
**Wave 0 Gate 1 的裁决把这条依赖消掉了**：`blocked` 的判定依据变成「该 entry 有没有已审核
per-entry 契约」——今天就完全可判定，与传播能力无关。唯一要等传播落地的只是「有契约且有
传播需求的那些」从 `blocked/pending_implementation` 翻成 `propagated`，今天只有 **D2** 一条
（Task 29 复核该翻转）。

清册本体只读，零文件冲突 ⇒ 不受 Task 101 阻断。

═══ 宿主模板怎么定位（AC 6.5 禁止按 sheet 名）═══

🔴 实测：`附注披露信息（国企）` 这个 sheet 名在 **39 份**模板里都存在，且被引用情况完全不同
⇒ 按 sheet 名找宿主会取到错的模板。

也**不能**用 manifest 的 `wp_match.wp_code_patterns` —— 实测那是从**组件名**派生的
（`D2A` / `G7L` / `H1F`），不是真 wp_code，`_index.json` 里查不到。

可靠链条只有一条，且是**内容寻址**的：

    DELIVERED_PER_ENTRY_CONTRACTS(entry_id, contract_id)
      → load_contract(contract_id).template.relative_path + .sha256
      → backend/wp_templates/<relative_path>，并**逐份校验 sha256**

顺带得到一个免费的漂移判据：契约冻结的 `template_sha256` 与磁盘现算不符即模板已漂移。

═══ 确定性 ═══

产物**不含任何计时**。计时会让 `--check` 每次都报差异。Gate 3 的实测耗时是冻结常量
（`GATE3_MEASURED_MS`），不在本脚本里重测。

用法::

    python backend/scripts/gen/generate_row_change_reachability.py --check
    python backend/scripts/gen/generate_row_change_reachability.py --apply
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import zipfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
if str(_BACKEND) not in sys.path:  # pragma: no cover - import 环境自举
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

from app.services.excel_structure_fingerprint import (  # noqa: E402
    _normalise_part,
    _parse_workbook_xml,
)
from app.services.workpaper_sync.excel_row_shift import (  # noqa: E402
    _F_RE,
    _QUALIFIED_PREFIX_RE,
    _REF_TOKEN_RE,
    _STRING_LITERAL_RE,
    _left_boundary_ok,
)

TEMPLATE_ROOT: Path = _BACKEND / "wp_templates"
INVENTORY_PATH: Path = _BACKEND / "data" / "workpaper_row_change_reachability.json"

#: Gate 3 冻结的实测数据（design.md「Gate 3」表）。本脚本不重测，保持产物确定性。
GATE3_MEASURED_MS: dict[str, int] = {
    "C/C24 会计分录 - 细节测试.xlsx": 1158,
    "A/A2-1、A2-2单体报表试算.xlsx": 201,
    "A/A3-4 合并报表试算（含金融企业报表项目）-清洁版-2019.xlsx": 181,
    "A/A3-1、-2 合并报表试算-2019.xlsx": 163,
}
PERF_THRESHOLD_MS: int = 2000
EXTREME_SITE_THRESHOLD: int = 1000

#: R6.2 限定的三态。
STATES: tuple[str, ...] = ("propagated", "blocked", "out_of_scope")

#: 三态各自的封闭原因词表（R6.2 要求写明原因）。
#:
#: ✅ Wave 5 Task 29 新增 `implemented` —— `propagated` 状态的原因。在此之前
#: `propagated` 是个**从未被使用**的状态值（词表里有、实际取不到），Task 24 的守卫
#: 只能验「词表没漂移」而验不到「这个状态真的可达」。
REASONS: tuple[str, ...] = (
    "no_projection_contract",
    "pending_implementation",
    "no_propagation_demand",
    # ✅ Wave 5 Task 29 新增：`propagated` 的原因。
    #
    # ⚠ `pending_implementation` **保留在词表里**而不是删掉：它仍然是一个合法状态 ——
    #    将来若有新契约进来而传播链路对它尚未验证，那一行就该是它。删掉等于让未来的
    #    「已有契约但还没验过」无处表达，只能被迫写成 `propagated`（假绿）。
    "implemented",
)

#: 占位标记 —— 与 design.md「占位标记集」表的 `key` 列逐字对应（单一真源双向锁死）。
PLACEHOLDER_MARKERS: dict[str, re.Pattern[str]] = {
    "ellipsis_single": re.compile("…"),
    "ellipsis_double": re.compile("……"),
    "xx_placeholder": re.compile(r"[×xX]{2,}"),
    "self_fill": re.compile("自行"),
    "add_row": re.compile(r"[增加]行"),
    "item_n": re.compile(r"项目\s*[0-9NnＮ]"),
    "dots_ascii": re.compile(r"\.\.\."),
    "insert_row": re.compile("插入行"),
    "fillable": re.compile("可填"),
    "reserved": re.compile("预留"),
    "continued": re.compile("续表"),
    "renameable": re.compile("可改名"),
}

_A1_LIKE_RE = re.compile(r"(?<![A-Za-z0-9])\$?[A-Z]{1,3}\$?\d+(?![A-Za-z0-9])")
_CELL_RE = re.compile(r"<c\b(?P<attrs>[^>]*?)(?:/>|>(?P<body>.*?)</c>)", re.S)
_V_RE = re.compile(r"<v[^>]*>(.*?)</v>", re.S)
_T_RE = re.compile(r"<t[^>]*>(.*?)</t>", re.S)
_SI_RE = re.compile(r"<si\b.*?</si>|<si\b[^>]*/>", re.S)
_ROW_NUM_RE = re.compile(r"\$?([A-Z]{1,3})\$?(\d+)")
_CF_SQREF_RE = re.compile(r'<conditionalFormatting\b[^>]*\bsqref="([^"]*)"')
_DV_SQREF_RE = re.compile(r'<dataValidation\b[^>]*\bsqref="([^"]*)"')
_MERGE_REF_RE = re.compile(r'<mergeCell\b[^>]*\bref="([^"]*)"')
_HYPERLINK_RE = re.compile(r"<hyperlink\b(?P<attrs>[^>]*)/?>")
_DV_FORMULA_RE = re.compile(r"<formula[12]\b[^>]*>(.*?)</formula[12]>", re.S)
_CF_FORMULA_RE = re.compile(r"<formula\b[^>]*>(.*?)</formula>", re.S)
_BUILTIN_NAMES = ("_xlnm.Print_Titles", "_xlnm.Print_Area", "_xlnm._FilterDatabase", "_xlnm.Criteria")


def _unescape(raw: str) -> str:
    return (
        raw.replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"')
        .replace("&apos;", "'").replace("&amp;", "&")
    )


def qualified_hits(text: str) -> list[tuple[str, str, str]]:
    """`[(kind, sheet_name, token)]` —— 分支顺序与生产 `_rewrite_formula_refs` 逐一对应。"""
    out: list[tuple[str, str, str]] = []
    index, length = 0, len(text)
    while index < length:
        if text[index] == '"':
            literal = _STRING_LITERAL_RE.match(text, index)
            index = literal.end() if literal else index + 1
            continue
        if _left_boundary_ok(text, index):
            prefix = _QUALIFIED_PREFIX_RE.match(text, index)
            if prefix is not None:
                index = prefix.end()
                target = _REF_TOKEN_RE.match(text, index)
                token = ""
                if target is not None:
                    token = target.group(0)
                    index = target.end()
                kind = (
                    "external" if prefix.group("book")
                    else "three_d" if prefix.group("span")
                    else "sheet"
                )
                raw = prefix.group("first")
                if len(raw) >= 2 and raw.startswith("'") and raw.endswith("'"):
                    raw = raw[1:-1].replace("''", "'")
                out.append((kind, raw, token))
                continue
        index += 1
    return out


def _shared_strings(zf: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in zf.namelist():
        return []
    xml = zf.read("xl/sharedStrings.xml").decode("utf-8", "replace")
    return [
        "".join(_unescape(t) for t in _T_RE.findall(si.group(0)))
        for si in _SI_RE.finditer(xml)
    ]


def _sheet_strings(xml: str, sst: list[str]) -> str:
    parts: list[str] = []
    for cell in _CELL_RE.finditer(xml):
        attrs, body = cell.group("attrs") or "", cell.group("body") or ""
        if 't="s"' in attrs:
            hit = _V_RE.search(body)
            if hit is not None:
                try:
                    parts.append(sst[int(hit.group(1))])
                except (ValueError, IndexError):
                    pass
        elif 't="inlineStr"' in attrs:
            parts.append("".join(_unescape(t) for t in _T_RE.findall(body)))
        elif 't="str"' in attrs:
            hit = _V_RE.search(body)
            if hit is not None:
                parts.append(_unescape(hit.group(1)))
    return "\n".join(parts)


# ═══════════════════════════════════════════════════════════════════════════
# 逐模板扫描
# ═══════════════════════════════════════════════════════════════════════════


def scan_template(path: Path) -> dict[str, Any]:
    rel = str(path.relative_to(TEMPLATE_ROOT)).replace("\\", "/")
    rec: dict[str, Any] = {"rel_path": rel}
    with zipfile.ZipFile(path) as zf:
        names = set(zf.namelist())
        sheets, defined = _parse_workbook_xml(zf)
        sheet_names = {s["name"] for s in sheets}
        sst = _shared_strings(zf)

        # referenced_sheet -> {"sites", "from": {sheet: n}, "rows": {row}}
        cross: dict[str, dict[str, Any]] = {}
        markers: dict[str, set[str]] = defaultdict(set)   # marker key -> sheet names
        carriers = Counter()
        three_d = external = cross_formulas = looks_a1 = 0
        all_qualified_sites = resolvable_formulas = 0
        unresolvable_targets: set[str] = set()

        for sheet in sheets:
            part = _normalise_part(sheet["rel_target"])
            if part not in names:
                continue
            xml = zf.read(part).decode("utf-8", "replace")
            name = sheet["name"]

            joined = _sheet_strings(xml, sst)
            for key, pattern in PLACEHOLDER_MARKERS.items():
                if pattern.search(joined):
                    markers[key].add(name)

            for fm in _F_RE.finditer(xml):
                text = _unescape(fm.group("text") or "")
                if not text:
                    continue
                hits = qualified_hits(text)
                has_cross = has_resolvable = False
                for kind, target, token in hits:
                    if kind == "three_d":
                        three_d += 1
                        continue
                    if kind == "external":
                        external += 1
                        continue
                    if target == name:
                        continue
                    # 🔴 两个**不同**口径，都要算，不能混：
                    #   all_qualified  —— 指向任何别的名字（含本工作簿里**不存在**的 sheet）。
                    #     这是零回归基线的口径：`_rewrite_formula_refs` 不知道哪些 sheet 存在，
                    #     对任何限定前缀一视同仁，所以行为冻结必须按这个分母。
                    #   resolvable     —— 目标 sheet 在本工作簿里**真实存在**。
                    #     这是传播/可达性的口径：指向不存在 sheet 的引用本就是坏引用，
                    #     不可能成为传播目标。
                    all_qualified_sites += 1
                    has_cross = True
                    if _A1_LIKE_RE.search(target):
                        looks_a1 += 1
                    if target not in sheet_names:
                        unresolvable_targets.add(target)
                        continue
                    has_resolvable = True
                    slot = cross.setdefault(
                        target, {"sites": 0, "from": Counter(), "rows": set()}
                    )
                    slot["sites"] += 1
                    slot["from"][name] += 1
                    slot["rows"].update(
                        int(m.group(2)) for m in _ROW_NUM_RE.finditer(token)
                    )
                if has_cross:
                    cross_formulas += 1
                if has_resolvable:
                    resolvable_formulas += 1

            for key, pattern in (
                ("cf_sqref", _CF_SQREF_RE), ("dv_sqref", _DV_SQREF_RE),
                ("merge_ref", _MERGE_REF_RE),
            ):
                for m in pattern.finditer(xml):
                    if any(k == "sheet" for k, _s, _t in qualified_hits(_unescape(m.group(1)))):
                        carriers["sqref_ref_cross"] += 1
            for m in _HYPERLINK_RE.finditer(xml):
                attrs = m.group("attrs")
                ref = re.search(r'\bref="([^"]*)"', attrs)
                if ref and any(
                    k == "sheet" for k, _s, _t in qualified_hits(_unescape(ref.group(1)))
                ):
                    carriers["sqref_ref_cross"] += 1
                loc = re.search(r'\blocation="([^"]*)"', attrs)
                if loc:
                    val = _unescape(loc.group(1))
                    hits = [h for h in qualified_hits(val) if h[0] == "sheet"]
                    if hits:
                        carriers["hyperlink_location_cross"] += 1
                        targets = {h[1] for h in hits}
                        if targets == {name}:
                            carriers["hyperlink_location_same_sheet"] += 1
                        elif targets & sheet_names:
                            carriers["hyperlink_location_in_workbook"] += 1
                        else:
                            carriers["hyperlink_location_not_in_workbook"] += 1
            for key, pattern in (("dv_formula_cross", _DV_FORMULA_RE),
                                 ("cf_formula_cross", _CF_FORMULA_RE)):
                for m in pattern.finditer(xml):
                    if any(k == "sheet" for k, _s, _t in qualified_hits(_unescape(m.group(1)))):
                        carriers[key] += 1

        for dn in defined:
            ref = dn.get("ref") or ""
            hits = [h for h in qualified_hits(ref) if h[0] == "sheet"]
            if not hits:
                continue
            carriers["defined_name_cross"] += 1
            name, scope = dn.get("name") or "", dn.get("scope")
            targets = {h[1] for h in hits}
            builtin = any(name.startswith(b) for b in _BUILTIN_NAMES)
            if builtin and scope is not None and targets == {scope}:
                carriers["defined_name_builtin_self_scope"] += 1
            elif builtin and not (targets & sheet_names):
                carriers["defined_name_target_not_in_workbook"] += 1
            elif builtin:
                carriers["defined_name_builtin_other_sheet"] += 1
            elif not (targets & sheet_names):
                carriers["defined_name_target_not_in_workbook"] += 1
            elif scope is not None and targets == {scope}:
                carriers["defined_name_user_self_scope"] += 1
            else:
                carriers["defined_name_user_cross_sheet"] += 1

        rec["sheets"] = sorted(sheet_names)
        rec["cross"] = {
            k: {"sites": v["sites"], "from": dict(sorted(v["from"].items())),
                "rows": sorted(v["rows"])}
            for k, v in sorted(cross.items())
        }
        rec["markers"] = {k: sorted(v) for k, v in sorted(markers.items())}
        rec["carriers"] = dict(sorted(carriers.items()))
        rec["three_d_sites"] = three_d
        rec["external_sites"] = external
        rec["cross_sheet_formulas"] = cross_formulas
        rec["resolvable_formulas"] = resolvable_formulas
        rec["all_qualified_sites"] = all_qualified_sites
        rec["unresolvable_targets"] = sorted(unresolvable_targets)
        rec["sheet_name_looks_like_a1_sites"] = looks_a1
        rec["chart_parts"] = sum(1 for n in names if n.startswith("xl/charts/"))
        rec["pivot_parts"] = sum(
            1 for n in names
            if n.startswith("xl/pivotCache/") or n.startswith("xl/pivotTables/")
        )
        rec["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    return rec


# ═══════════════════════════════════════════════════════════════════════════
# 契约侧：entry → 模板（内容寻址，AC 6.5）
# ═══════════════════════════════════════════════════════════════════════════


def contracted_entries(scans: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    from app.services.workpaper_sync.adapters.registry import (
        DELIVERED_PER_ENTRY_CONTRACTS,
    )
    from app.services.workpaper_sync.contracts import load_contract

    rows: list[dict[str, Any]] = []
    for reg in DELIVERED_PER_ENTRY_CONTRACTS:
        entry_id = str(reg.get("entry_id") or "").strip()
        contract_id = str(reg.get("contract_id") or "").strip()
        contract = load_contract(contract_id)
        ref = contract.template
        rel = ref.relative_path.replace("\\", "/")
        scan = scans.get(rel)

        managed: list[dict[str, Any]] = []
        for sheet in contract.sheets:
            excel_name = sheet.excel_name
            slot = (scan or {}).get("cross", {}).get(excel_name) or {}
            anchors = sorted({t.anchor for t in sheet.tables})
            managed.append(
                {
                    "excel_name": excel_name,
                    "anchors": anchors,
                    "has_dynamic_rows": any(t.has_dynamic_rows for t in sheet.tables),
                    "referencing_sites": slot.get("sites", 0),
                    "referencing_sheets": sorted(slot.get("from", {})),
                    "referenced_rows": slot.get("rows", []),
                }
            )
        demand = sum(m["referencing_sites"] for m in managed)
        rows.append(
            {
                "entry_id": entry_id,
                "contract_id": contract_id,
                "template_relative_path": rel,
                "template_present": scan is not None,
                "template_sha256_matches": bool(
                    scan and scan["sha256"] == ref.sha256
                ),
                "managed_sheets": managed,
                "propagation_demand_sites": demand,
                # ✅ Wave 5 Task 29：传播能力已交付 ⇒ 有传播需求的 entry 从
                #    `blocked/pending_implementation` 翻成 `propagated/implemented`。
                #    今天只有 D2 一条有需求（52 处），其余三份需求为 0 ⇒ 仍 `out_of_scope`。
                "state": "propagated" if demand else "out_of_scope",
                "reason": "implemented" if demand else "no_propagation_demand",
            }
        )
    return sorted(rows, key=lambda r: r["entry_id"])


def host_ambiguity(
    contracted: list[dict[str, Any]], scans: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    """量化「按 sheet 名定位宿主」会有多歧义（AC 6.5 的反证数据）。

    对每个契约声明的受管 sheet 名，数全库有多少份模板含同名 sheet。>1 即按名定位歧义。
    把它登记进清册而不是留给判据现算 —— 判据现算等于在守卫里复制一份扫描逻辑。
    """
    out: dict[str, Any] = {}
    for row in contracted:
        for managed in row["managed_sheets"]:
            name = managed["excel_name"]
            hosts = sorted(rel for rel, rec in scans.items() if name in rec["sheets"])
            out[name] = {
                "templates_containing": len(hosts),
                "bound_host": row["template_relative_path"],
                "bound_host_is_among_them": row["template_relative_path"] in hosts,
                "other_hosts_sample": [
                    h for h in hosts if h != row["template_relative_path"]
                ][:5],
            }
    return dict(sorted(out.items()))


# ═══════════════════════════════════════════════════════════════════════════
# 组装
# ═══════════════════════════════════════════════════════════════════════════


def build_inventory() -> dict[str, Any]:
    xlsx = sorted(
        p for p in TEMPLATE_ROOT.rglob("*.xlsx") if not p.name.startswith("~$")
    )
    scans = {}
    for path in xlsx:
        rec = scan_template(path)
        scans[rec["rel_path"]] = rec

    contracted = contracted_entries(scans)
    contracted_templates = {r["template_relative_path"] for r in contracted}
    ambiguity = host_ambiguity(contracted, scans)

    # ── 受影响模板：被引用的 sheet 自身含占位标记 ──────────────────
    affected: list[dict[str, Any]] = []
    for rel, rec in scans.items():
        marker_sheets = {s for names in rec["markers"].values() for s in names}
        hit = [
            (target, slot)
            for target, slot in rec["cross"].items()
            if slot["sites"] > 0 and target in marker_sheets
        ]
        if not hit:
            continue
        in_contract = rel in contracted_templates
        affected.append(
            {
                "rel_path": rel,
                # ✅ Wave 5 Task 29：有已审契约的模板翻成 `propagated/implemented`
                #    （今天只有 D2 一份）；其余 135 份**仍 blocked**，原因不是「传播没做」
                #    而是「没有 projection 契约」—— 那与传播能力无关，做完也不会变。
                #
                # 🔴 首版这里写的是 `"blocked" if not in_contract else "blocked"`
                #    —— 两个分支**完全相同**的死三元。它当时不影响结果（那时两类都该是
                #    blocked），但把「这一维本该随契约分叉」这件事藏了起来。Task 29 要
                #    翻转的正是这个分叉，于是它必须先被写出来。
                "state": "propagated" if in_contract else "blocked",
                "reason": ("implemented" if in_contract else "no_projection_contract"),
                "managed_sheet_candidates": sorted(t for t, _s in hit),
                "referencing_sheets": sorted(
                    {f for _t, slot in hit for f in slot["from"]}
                ),
                "referencing_sites": sum(slot["sites"] for _t, slot in hit),
                "marker_keys": sorted(rec["markers"]),
            }
        )
    affected.sort(key=lambda r: r["rel_path"])

    # ── 极端规模组合 ─────────────────────────────────────────────
    extremes = [
        {
            "rel_path": rel,
            "sheet": target,
            "sites": slot["sites"],
            "gate3_measured_ms": GATE3_MEASURED_MS.get(rel),
            "perf_threshold_ms": PERF_THRESHOLD_MS,
        }
        for rel, rec in scans.items()
        for target, slot in rec["cross"].items()
        if slot["sites"] > EXTREME_SITE_THRESHOLD
    ]
    extremes.sort(key=lambda r: (-r["sites"], r["rel_path"], r["sheet"]))

    # ── 分母 ─────────────────────────────────────────────────────
    carrier_total = Counter()
    for rec in scans.values():
        carrier_total.update(rec["carriers"])

    d2 = next((r for r in contracted if r["contract_id"] == "d2.receivable_detail"), None)
    k11 = scans.get("K/K11 资产减值损失.xlsx", {}).get("cross", {}).get("审定表K11-1", {})

    resolvable_sites = sum(
        s["sites"] for r in scans.values() for s in r["cross"].values()
    )
    all_qualified = sum(r["all_qualified_sites"] for r in scans.values())
    denominators = {
        "xlsx_total": len(xlsx),
        # 口径一：任何指向别的名字的限定引用（零回归基线用）
        "templates_with_cross_sheet": sum(
            1 for r in scans.values() if r["all_qualified_sites"]
        ),
        "cross_sheet_sites": all_qualified,
        "cross_sheet_formulas": sum(r["cross_sheet_formulas"] for r in scans.values()),
        # 口径二：目标 sheet 在本工作簿里真实存在（传播/可达性用）
        "templates_with_resolvable_cross_sheet": sum(
            1 for r in scans.values() if any(s["sites"] for s in r["cross"].values())
        ),
        "resolvable_cross_sheet_sites": resolvable_sites,
        "resolvable_cross_sheet_formulas": sum(
            r["resolvable_formulas"] for r in scans.values()
        ),
        # 两个口径之差 = 指向**本工作簿里不存在**的 sheet 的引用（已坏的引用）
        "unresolvable_cross_sheet_sites": all_qualified - resolvable_sites,
        "templates_with_unresolvable_targets": sum(
            1 for r in scans.values() if r["unresolvable_targets"]
        ),
        "sheet_name_looks_like_a1_sites": sum(
            r["sheet_name_looks_like_a1_sites"] for r in scans.values()
        ),
        "external_sites": sum(r["external_sites"] for r in scans.values()),
        "three_d_sites": sum(r["three_d_sites"] for r in scans.values()),
        "affected_templates": len(affected),
        "delivered_contract_entries": len(contracted),
        "d2_managed_sheet_sites": (
            d2["propagation_demand_sites"] if d2 else 0
        ),
        "k11_managed_sheet_sites": k11.get("sites", 0),
        "k11_managed_sheet_rows": len(k11.get("rows", [])),
        "extreme_combinations": len(extremes),
        "extreme_max_sites": extremes[0]["sites"] if extremes else 0,
        "defined_name_cross": carrier_total["defined_name_cross"],
        "defined_name_builtin_self_scope": carrier_total["defined_name_builtin_self_scope"],
        "defined_name_target_not_in_workbook": carrier_total["defined_name_target_not_in_workbook"],
        "defined_name_user_self_scope": carrier_total["defined_name_user_self_scope"],
        "defined_name_user_cross_sheet": carrier_total["defined_name_user_cross_sheet"],
        "hyperlink_location_cross": carrier_total["hyperlink_location_cross"],
        "hyperlink_location_in_workbook": carrier_total["hyperlink_location_in_workbook"],
        "hyperlink_location_not_in_workbook": carrier_total["hyperlink_location_not_in_workbook"],
        "dv_formula_cross": carrier_total["dv_formula_cross"],
        "cf_formula_cross": carrier_total["cf_formula_cross"],
        "sqref_ref_cross": carrier_total["sqref_ref_cross"],
        "chart_parts": sum(r["chart_parts"] for r in scans.values()),
        "pivot_parts": sum(r["pivot_parts"] for r in scans.values()),
        "max_host_name_collisions": max(
            (v["templates_containing"] for v in ambiguity.values()), default=0
        ),
    }

    marker_stats = {}
    for key in PLACEHOLDER_MARKERS:
        sheets = sum(len(r["markers"].get(key, ())) for r in scans.values())
        templates = sum(1 for r in scans.values() if r["markers"].get(key))
        marker_stats[key] = {"sheets": sheets, "templates": templates}

    return {
        "spec": "excel-workbook-wide-row-change-propagation",
        "task": "Wave 0 Task 24 (Requirements 6.1~6.5, 8.5)",
        "states": list(STATES),
        "reasons": list(REASONS),
        "host_resolution": (
            "contract.template.relative_path + template_sha256（内容寻址）—— "
            "禁止按 sheet 名或 manifest 的 wp_code_patterns 定位（AC 6.5）"
        ),
        "denominators": denominators,
        "placeholder_markers": marker_stats,
        "host_ambiguity": ambiguity,
        "contracted_entries": contracted,
        "extremes": extremes,
        "affected_templates": affected,
    }


def diff_inventory(current: dict[str, Any], stored: dict[str, Any]) -> list[str]:
    problems: list[str] = []
    for key in ("states", "reasons", "denominators", "placeholder_markers",
                "host_ambiguity", "contracted_entries", "extremes", "host_resolution"):
        if current.get(key) != stored.get(key):
            if key == "denominators":
                for name in sorted(set(current[key]) | set(stored.get(key, {}))):
                    if current[key].get(name) != stored.get(key, {}).get(name):
                        problems.append(
                            f"分母 {name}：清册 {stored.get(key, {}).get(name)!r}"
                            f" → 现算 {current[key].get(name)!r}"
                        )
            else:
                problems.append(f"{key} 变了")
    cur_a = {r["rel_path"]: r for r in current.get("affected_templates", ())}
    old_a = {r["rel_path"]: r for r in stored.get("affected_templates", ())}
    for rel in sorted(set(cur_a) ^ set(old_a)):
        problems.append(f"受影响模板集合变了：{rel}")
    for rel in sorted(set(cur_a) & set(old_a)):
        if cur_a[rel] != old_a[rel]:
            problems.append(f"{rel} 的登记内容变了")
    return problems


def load_inventory() -> dict[str, Any]:
    return json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true")
    group.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)

    current = build_inventory()
    d = current["denominators"]
    summary = (
        f"xlsx {d['xlsx_total']} / 含跨 sheet {d['templates_with_cross_sheet']} / "
        f"引用 {d['cross_sheet_sites']} 处 / 受影响 {d['affected_templates']} 份 / "
        f"已发契约 entry {d['delivered_contract_entries']} / "
        f"极端组合 {d['extreme_combinations']}（最大 {d['extreme_max_sites']}）"
    )

    if args.apply:
        INVENTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
        INVENTORY_PATH.write_text(
            json.dumps(current, ensure_ascii=False, indent=1, sort_keys=True),
            encoding="utf-8",
        )
        print(f"[apply] 清册已写入 {INVENTORY_PATH.relative_to(_REPO)}")
        print(f"        {summary}")
        return 0

    if not INVENTORY_PATH.is_file():
        print(f"[check] 🔴 清册不存在：{INVENTORY_PATH.relative_to(_REPO)} —— 先跑 --apply")
        return 1
    problems = diff_inventory(current, load_inventory())
    print(f"[check] {summary}")
    if problems:
        print(f"[check] 🔴 与清册有 {len(problems)} 处差异：")
        for p in problems[:40]:
            print(f"  - {p}")
        return 1
    print("[check] ✅ 与清册逐字相同")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
