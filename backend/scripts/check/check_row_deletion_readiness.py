"""删物理行「开表准入」体检 —— 逐表算可删行比例与锁死原因。

为什么需要这个工具
==================

spec ``workpaper-sync-row-deletion-multi-region-propagation`` 把多区位移联动接成了真
双向，但**全库 62 份契约里声明 ``row_convergence=delete`` 的是 0 张** —— 删行链路目前
生产零消费方。要给某张表开表（把 ``clear`` 改成 ``delete``），先得知道：

* 这张表的受管行里，**有多少行现在就删得下去**？
* 删不下去的那些，**卡在什么上**？

反例是「先改契约再看会不会炸」：``row_convergence=delete`` 打开后，删行是**不可逆的
数据丢失**，而 fail-closed 会在用户点保存时才报错。本工具把这件事挪到开表**之前**。

判据口径（全部现算，禁写死）
============================

分母三层，逐层现算：

1. **契约层** —— ``contracts.CONTRACTS_DIR`` 下全部 ``*.json``；不可解析的**分类登记**
   而不是跳过（照 ``test_row_deletion_contract_gate`` 的普查口径）。
2. **表层** —— 只看**有 ``row_identity``** 的表：没有行身份就谈不上按身份删行
   （CS-21），那些表连准入资格都没有。
3. **行层** —— 受管区 ``anchor.first_row..footer_anchor`` 之间的每一行，用生产的
   :func:`excel_workbook_row_change.find_undeletable_rows` 判它删不删得动。

🔴 **不复刻任何判定逻辑**：可删性一律问生产的 ``find_undeletable_rows`` /
``find_dangling_sites``。测试侧与工具侧各写一份「怎么算悬空」就是第二真源，
两份一漂，体检结论就成了安慰剂。

🔴 本工具**测的不是**什么（口径声明，防止与别处的数字混为一谈）
================================================================

2026-09-29 实测对账：同一个「可删行比例」有**两个口径**，数值不同且**都对** ——

============  =========================================  ================
口径           受管区从哪来                                 G3-2 实测
============  =========================================  ================
本工具         **原始模板**的 ``anchor`` → footer marker 现搜   12 行 / 可删 4
spec 期普查     **已插桩**工作簿里 ``GT_*_ROWS`` 的运行时区      14 行 / **全锁**
============  =========================================  ================

差异来源：① 区间边界不同（插桩后 footer 会被冻结成 ``GT_FOOTER_ROW_*``，与模板里按
marker 搜到的那一行并不总是同一行）；② 插桩工作簿多出 ``_GT_SYNC`` 等载体，跨 sheet
引用面更大 ⇒ 锁死更多。

⇒ **两个数不可互相「纠正」**（铁律㉗）。要论证某张表该不该开表，必须说清用的是哪个
口径；本工具只回答「**原始模板**上删 ``--count`` 行会不会坏引用」。上线前的最终判定
仍须在**插桩后的真实工作簿**上跑一遍。

用法
====

    python backend/scripts/check/check_row_deletion_readiness.py
    python backend/scripts/check/check_row_deletion_readiness.py --json
    python backend/scripts/check/check_row_deletion_readiness.py --table endorse_discount_rows
    python backend/scripts/check/check_row_deletion_readiness.py --count 3

退出码：``0`` 体检跑通；``2`` 语料自身坏了（契约目录空 / 模板全缺 —— 那是环境问题，
不是「没有可删的表」）。**「某表 0 行可删」不是失败**，那正是本工具要报告的事实。

🔴 本工具**不是 CI 门禁**，是按需跑的报告
==========================================

刻意**不**接进任何 workflow。理由：它输出的是**事实**（「89.7% 可删」），做成门禁就必须
拍一个阈值（「可删率须 ≥ 80%」），而那种数字是拍脑袋来的、允许静默退化，正是本仓反复
登记过的反模式。

防腐由它的**守卫测试**承担：``backend/tests/scripts/test_check_row_deletion_readiness.py``
在常规测试里跑，锁住分母现算、逐行账闭合、`--count` 真接线、语料坏了 fail-closed。
⇒ 工具手动跑、守卫自动跑。不要把这里的退出码改成「可删率不达标就红」。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

os.environ.setdefault("DB_DISABLE_SSL", "True")

from app.services.workpaper_sync import contracts as C  # noqa: E402
from app.services.workpaper_sync import excel_workbook_row_change as W  # noqa: E402

TEMPLATE_ROOT: Path = _REPO / "wp_templates"


@dataclass
class TableReadiness:
    """一张受管行表的体检结论。"""

    contract_id: str
    contract_file: str
    excel_name: str
    table_key: str
    template: str
    row_convergence: str
    region_first_row: int
    region_last_row: int
    managed_rows: int = 0
    deletable: tuple[int, ...] = ()
    locked: tuple[int, ...] = ()
    lock_reasons: dict[str, int] = field(default_factory=dict)
    blocked_by: str | None = None

    @property
    def deletable_ratio(self) -> float:
        return (len(self.deletable) / self.managed_rows) if self.managed_rows else 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "contract_id": self.contract_id,
            "contract_file": self.contract_file,
            "excel_name": self.excel_name,
            "table_key": self.table_key,
            "template": self.template,
            "row_convergence": self.row_convergence,
            "region": [self.region_first_row, self.region_last_row],
            "managed_rows": self.managed_rows,
            "deletable_count": len(self.deletable),
            "deletable_rows": list(self.deletable),
            "locked_count": len(self.locked),
            "locked_rows": list(self.locked),
            "lock_reasons": dict(sorted(self.lock_reasons.items())),
            "deletable_ratio": round(self.deletable_ratio, 4),
            "blocked_by": self.blocked_by,
        }


def _sheet_parts(zf: zipfile.ZipFile) -> tuple[dict[str, str], list[Any]]:
    """sheet 显示名 → zip part 名，外加 defined names。

    🔴 **复用生产的 `_parse_workbook_xml` / `_normalise_part`**，不自己写正则：
    `d2_bidirectional_bridge._sheet_part_by_name` 的注释里已经实测记过两个坑 ——
    正则会被属性顺序与命名空间前缀差异打败（`rId8` 匹配不到），按 `sheetnames`
    次序回推对隐藏表（`_GT_SYNC`）不成立。本工具与
    `excel_workbook_row_change._scan_from_entries` 走**同一条**解析路径。
    """
    from app.services.excel_structure_fingerprint import (
        _normalise_part,
        _parse_workbook_xml,
    )

    sheets, defined = _parse_workbook_xml(zf)
    parts = {s["name"]: _normalise_part(s["rel_target"]) for s in sheets}
    return parts, list(defined)


def _anchor_first_row(anchor: Any) -> int | None:
    """``anchor`` 是 A1 串（实测 `'A12'`），取它的行号。"""
    import re

    m = re.fullmatch(r"\$?([A-Z]{1,3})\$?(\d+)", str(anchor or "").strip())
    return int(m.group(2)) if m else None


def _footer_row_by_marker(
    zf: zipfile.ZipFile, *, part: str, footer: Any, from_row: int
) -> int | None:
    """按 ``footer_anchor.marker`` 在 ``search_column`` 现搜 footer 行。

    🔴 契约里**没有** footer 行号（`FooterAnchorSpec` 只有
    `marker`/`search_column`/`carries_total_formula`）—— 行号必须在工作簿里找。
    这与引擎的 `assert_footer_anchor_stable` 同一判据（按 marker 找，不信固定行号），
    照 `d2_bidirectional_bridge._find_footer_row` 的口径，但列取契约声明的那一列
    而不是硬写 A。
    """
    import re
    import xml.etree.ElementTree as ET

    marker = str(getattr(footer, "marker", "") or "").strip()
    column = str(getattr(footer, "search_column", "") or "A").strip()
    if not marker:
        return None

    ns = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    try:
        root = ET.fromstring(zf.read(part))
    except (KeyError, ET.ParseError):
        return None

    # 共享字符串表：marker 多半以 `t="s"` 索引形式存放。
    shared: list[str] = []
    try:
        ss = ET.fromstring(zf.read("xl/sharedStrings.xml"))
        shared = ["".join(t.text or "" for t in si.iter(f"{ns}t")) for si in ss]
    except (KeyError, ET.ParseError):
        shared = []

    for cell in root.iter(f"{ns}c"):
        ref = cell.get("r") or ""
        m = re.fullmatch(r"([A-Z]{1,3})(\d+)", ref)
        if not m or m.group(1) != column:
            continue
        row = int(m.group(2))
        if row <= from_row:
            continue
        value_node = cell.find(f"{ns}v")
        text = ""
        if cell.get("t") == "s" and value_node is not None:
            try:
                text = shared[int(value_node.text or "-1")]
            except (ValueError, IndexError):
                text = ""
        elif cell.get("t") == "inlineStr":
            text = "".join(t.text or "" for t in cell.iter(f"{ns}t"))
        elif value_node is not None:
            text = value_node.text or ""
        cell_text = text.strip()
        if cell_text == marker:
            return row
        # 🔴 模板里的 footer 标签常带尾随冒号而契约 marker 不带（实测 G4-7：模板
        #    `三、审计说明：`（全角冒号）vs 契约 `三、审计说明`）⇒ 精确 `==` 搜不到，
        #    该表被误报成 `footer_marker_not_found`。
        #    只放宽**尾随标点**这一种差异，不做模糊匹配 —— 模糊匹配会让「合计」命中
        #    「合计（不含税）」之类的别的行，那是静默错答，比找不到更坏。
        if cell_text.rstrip("：:、。 ") == marker.rstrip("：:、。 "):
            return row
    return None


def audit_table(
    *, contract: Any, contract_file: str, sheet: Any, table: Any, count: int = 1
) -> TableReadiness:
    """单表体检：受管区每一行问一次生产的可删性判定。

    Args:
        count: 一次删几行。生产的 ``find_undeletable_rows`` 本就带这个参数 ——
            「删 1 行没事」不代表「删 3 行没事」（连续段会跨过更多引用）。
    """
    template_rel = getattr(contract.template, "relative_path", "") or ""
    result = TableReadiness(
        contract_id=contract.contract_id,
        contract_file=contract_file,
        excel_name=getattr(sheet, "excel_name", "") or "",
        table_key=getattr(table, "table_key", "") or "",
        template=template_rel,
        row_convergence=table.row_convergence.value,
        region_first_row=0,
        region_last_row=0,
    )

    anchor_row = _anchor_first_row(getattr(table, "anchor", None))
    if anchor_row is None:
        result.blocked_by = f"bad_anchor: {getattr(table, 'anchor', None)!r} 不是 A1 引用"
        return result
    # 🔴 `anchor` 指的是**表头**起始行，不是第一个数据行：受管数据区从
    #    `anchor + header_rows` 开始（D1-8 实测 anchor=A12 / header_rows=2 ⇒ 数据行 14..21，
    #    而不是 12..21）。把表头行算进去会让本工具去问「能不能删表头行」——
    #    那不是一个真问题，而且会把分母整体抬高 `header_rows` 行。
    first = anchor_row + int(getattr(table, "header_rows", 0) or 0)

    path = TEMPLATE_ROOT / template_rel
    if not path.is_file():
        result.blocked_by = f"template_missing: {template_rel}"
        return result

    try:
        with zipfile.ZipFile(path) as zf:
            parts, defined = _sheet_parts(zf)
            target = parts.get(result.excel_name)
            if target is None:
                result.blocked_by = (
                    f"sheet_not_in_template: {result.excel_name!r}"
                    f"（模板有 {len(parts)} 个 sheet）"
                )
                return result
            footer = getattr(table, "footer_anchor", None)
            # 🔴 `footer_anchor` 为 None 是**合法形态**，不是缺陷：引擎的
            #    `assert_footer_anchor_stable` 对不含 footer_anchor 的 table 直接跳过。
            #    实测 3 张这样的表（D4-29 客户信息检查表 / D4-12 合同检查表 /
            #    J1-6 计提情况检查表）。它们的受管区末行契约里没有，得另找来源：
            #    用 `dynamic_columns` 或末行推断都不可靠 ⇒ 老实登记为「本工具口径覆盖不到」，
            #    并写清它**不等于**「不可删」。
            #
            #    🔴 D4-29 / D4-12 的 `table_key` 带 `_transposed` 后缀且 A 列是**字段名**
            #    （实测 A11 `统一社会信用代码` / A12 `注册地址` …）—— 它们是**转置表**：
            #    一「行」是一个字段，一「列」是一个业务对象。对转置表谈「删物理行」本身
            #    就不成立（删的应该是列）⇒ 这类表的正确处置是**不进本体检的分母**，
            #    而不是想办法给它凑一个区间。
            if footer is None:
                kind = (
                    "transposed_table_row_deletion_not_applicable"
                    if "transposed" in (result.table_key or "")
                    else "no_footer_anchor_region_unknown"
                )
                result.blocked_by = (
                    f"{kind}: 契约未声明 footer_anchor（合法形态，引擎对它跳过 footer 校验）"
                    "⇒ 本工具取不到受管区末行。**不等于「不可删」**"
                )
                return result
            footer_row = _footer_row_by_marker(
                zf, part=target, footer=footer, from_row=anchor_row
            )
            if footer_row is None:
                result.blocked_by = (
                    f"footer_marker_not_found: marker="
                    f"{getattr(footer, 'marker', None)!r} 在 "
                    f"{getattr(footer, 'search_column', '?')} 列第 {anchor_row} 行之下找不到"
                    "（已放宽尾随标点差异后仍找不到）"
                )
                return result
            # footer 那一行不是受管行：受管区止于 footer 上一行。
            last = footer_row - 1
            result.region_first_row, result.region_last_row = first, last
            if last < first:
                result.blocked_by = (
                    f"empty_region: footer({footer_row}) 紧贴 anchor({first})"
                )
                return result
            scan = W.scan_reference_carriers(
                zf,
                target_sheet=result.excel_name,
                sheet_parts=parts,
                defined_names=defined,
            )
    except (zipfile.BadZipFile, KeyError, ValueError) as exc:
        result.blocked_by = f"{type(exc).__name__}: {exc}"
        return result

    result.managed_rows = last - first + 1
    undeletable = set(
        W.find_undeletable_rows(
            scan, region_first_row=first, region_last_row=last, count=count
        )
    )
    result.deletable = tuple(
        r for r in range(first, last + 1) if r not in undeletable
    )
    result.locked = tuple(sorted(undeletable))

    # 锁死原因按生产的 DanglingSite.reason 归类（逐行问，不做整表推断）。
    reasons: dict[str, int] = {}
    for row in result.locked:
        sites = W.find_dangling_sites(scan, delete_at=row, count=count)
        if not sites:
            reasons["unknown_no_dangling_site"] = (
                reasons.get("unknown_no_dangling_site", 0) + 1
            )
            continue
        for site in sites:
            key = str(getattr(site, "reason", "") or "unspecified")
            reasons[key] = reasons.get(key, 0) + 1
    result.lock_reasons = reasons
    return result


def run_audit(*, table_filter: str | None = None, count: int = 1) -> dict[str, Any]:
    """全语料体检；分母三层全部现算。"""
    files = sorted(C.CONTRACTS_DIR.glob("*.json"))
    unparseable: dict[str, str] = {}
    rows: list[TableReadiness] = []
    tables_total = 0
    tables_with_identity = 0

    for path in files:
        raw = json.loads(path.read_text(encoding="utf-8"))
        try:
            contract = C.parse_contract(raw)
        except Exception as exc:  # noqa: BLE001 - 普查要看全部失败形态
            unparseable[path.name] = f"{type(exc).__name__}: {exc}"
            continue
        for sheet in contract.sheets:
            for table in sheet.tables:
                tables_total += 1
                if not getattr(table, "row_identity", None):
                    continue
                tables_with_identity += 1
                if table_filter and table_filter != getattr(table, "table_key", ""):
                    continue
                rows.append(
                    audit_table(
                        contract=contract,
                        contract_file=path.name,
                        sheet=sheet,
                        table=table,
                        count=count,
                    )
                )

    audited = [r for r in rows if r.blocked_by is None]
    managed = sum(r.managed_rows for r in audited)
    deletable = sum(len(r.deletable) for r in audited)
    locked = sum(len(r.locked) for r in audited)
    all_reasons: dict[str, int] = {}
    for r in audited:
        for k, v in r.lock_reasons.items():
            all_reasons[k] = all_reasons.get(k, 0) + v

    return {
        "tool": "check_row_deletion_readiness",
        # 🔴 口径必须随数字一起输出 —— 否则下游引用这份 JSON 时无从判断
        # 它与「插桩工作簿口径」的那套数字是不是同一件事（见模块 docstring）。
        "measured": {
            "region_source": "contract.anchor → footer_anchor.marker（原始模板现搜）",
            "substrate": "wp_templates 下的原始模板（**未**插桩）",
            "delete_count": count,
            "not_measured": "插桩后工作簿的运行时区（GT_*_ROWS / GT_FOOTER_ROW_*）",
        },
        "contract_files": len(files),
        "contracts_unparseable": unparseable,
        "tables_total": tables_total,
        "tables_with_row_identity": tables_with_identity,
        "tables_audited": len(audited),
        "tables_blocked": [
            {"table_key": r.table_key, "blocked_by": r.blocked_by}
            for r in rows
            if r.blocked_by is not None
        ],
        "managed_rows": managed,
        "deletable_rows": deletable,
        "locked_rows": locked,
        "deletable_ratio": round(deletable / managed, 4) if managed else 0.0,
        "lock_reasons": dict(sorted(all_reasons.items())),
        # 🔴 用**限定键**而不是裸 `table_key`：实测 `related_party_rows` 在 3 份契约里
        # 各有一张，`bad_debt_individual_rows` / `adjudication_other_rows` 各 2 张 ——
        # 裸 key 会让清单出现重复项且无从定位是哪张表。
        "fully_deletable_tables": sorted(
            f"{r.contract_file}::{r.excel_name}::{r.table_key}"
            for r in audited
            if r.managed_rows and not r.locked
        ),
        "zero_deletable_tables": sorted(
            f"{r.contract_file}::{r.excel_name}::{r.table_key}"
            for r in audited
            if r.managed_rows and not r.deletable
        ),
        # 🔴 整表零可删的**结构性归类**（2026-09-30 加）：
        #    实测 9 张全部落在同一个形态上 —— sheet 名形如「明细表X-2」、锁死原因全是
        #    `single_cell`。那是**一个模式**（`-2` 明细页的行被跨 sheet 单格引用指着），
        #    不是 9 个孤立案例。不做这个归类，读者得从 96 张候选里反推「为什么这几张不行」。
        "zero_deletable_pattern": _classify_zero_deletable(
            [r for r in audited if r.managed_rows and not r.deletable]
        ),
        "tables": [r.as_dict() for r in rows],
    }


def _classify_zero_deletable(rows: list[TableReadiness]) -> dict[str, Any]:
    """把「整表零可删」归类，而不是丢一串表名让人自己找规律。

    归类维度取自实测：sheet 名形态 + 锁死原因集合。两者都一致时，这些表是**同一个
    结构性问题**的多个实例 —— 对它们要做的判断是一次性的（「这类表能不能开表」），
    而不是逐张判断。

    🔴 判据侧要求：`families` 里每一族都要给出**共同原因**。若某一族的原因集合不唯一，
    就不能声称它是一族 —— 那时 `mixed_reason_families` 非空，调用方应当把它当成
    「归类失败」而不是「归类结果」。
    """
    import re as _re

    # 🔴 归类维度是**锁死原因**，不是 sheet 名。
    #    首版按 sheet 名形态切，得 4 族（`明细表G#-#` / `H#-#` / `I#-#` / `租赁负债明细表H#-#`）
    #    —— 但那 4 族的锁死原因**完全相同**（全是 `single_cell`）。按 sheet 名切等于把
    #    「一个结构性问题」报成 4 个，读者会以为要做 4 次判断。
    #    原因才是「要不要开表」这个决定的依据；sheet 名形态降级为族内的附加描述。
    families: dict[str, dict[str, Any]] = {}
    for r in rows:
        key = ",".join(sorted(r.lock_reasons)) or "<无原因>"
        fam = families.setdefault(
            key, {"tables": [], "shapes": set(), "rows": 0, "reasons": set()}
        )
        fam["tables"].append(r.table_key)
        fam["shapes"].add(_re.sub(r"\d+", "#", r.excel_name))
        fam["reasons"] |= set(r.lock_reasons)
        fam["rows"] += r.managed_rows

    out_families = []
    mixed: list[str] = []
    for key, fam in sorted(families.items()):
        reasons = sorted(fam["reasons"])
        if len(reasons) != 1:
            mixed.append(key)
        out_families.append(
            {
                "lock_reasons": reasons,
                "table_count": len(fam["tables"]),
                "managed_rows": fam["rows"],
                "sheet_shapes": sorted(fam["shapes"]),
                "tables": sorted(fam["tables"]),
            }
        )

    all_reasons = sorted({x for f in families.values() for x in f["reasons"]})
    return {
        "table_count": len(rows),
        "families": out_families,
        "shared_lock_reasons": all_reasons if len(all_reasons) == 1 else [],
        "mixed_reason_families": mixed,
        "verdict": (
            "single_structural_pattern"
            if len(out_families) == 1 and not mixed
            else ("multiple_patterns" if out_families else "none")
        ),
    }


def _render(report: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("═══ 删物理行开表准入体检 ═══")
    lines.append(
        f"契约 {report['contract_files']} 份"
        f"（不可解析 {len(report['contracts_unparseable'])}）"
        f" / 表 {report['tables_total']}"
        f" / 有行身份 {report['tables_with_row_identity']}"
        f" / 已体检 {report['tables_audited']}"
        f" / 受阻 {len(report['tables_blocked'])}"
    )
    lines.append(
        f"受管行 {report['managed_rows']}"
        f" / 可删 {report['deletable_rows']}"
        f" / 锁死 {report['locked_rows']}"
        f" ⇒ 可删比例 {report['deletable_ratio']:.1%}"
    )
    if report["lock_reasons"]:
        lines.append("锁死原因分布：")
        for reason, n in report["lock_reasons"].items():
            lines.append(f"    {n:4d}  {reason}")
    lines.append("")
    lines.append("逐表（按可删比例升序 —— 越靠前越不该开表）：")
    audited = [t for t in report["tables"] if t["blocked_by"] is None]
    for t in sorted(audited, key=lambda x: (x["deletable_ratio"], x["table_key"])):
        flag = "🔴" if not t["deletable_count"] else ("✅" if not t["locked_count"] else "⚠️ ")
        lines.append(
            f"  {flag} {t['deletable_ratio']:>6.1%}  "
            f"{t['deletable_count']:>3d}/{t['managed_rows']:<3d}  "
            f"{t['table_key']:<34s} {t['excel_name']}"
        )
        if t["lock_reasons"]:
            lines.append(
                "        锁死："
                + "、".join(f"{k}×{v}" for k, v in t["lock_reasons"].items())
            )
    if report["tables_blocked"]:
        lines.append("")
        lines.append("未能体检（语料/模板问题，**不是**「不可删」）：")
        for b in report["tables_blocked"]:
            lines.append(f"    {b['table_key']:<34s} {b['blocked_by']}")
    lines.append("")
    lines.append(
        f"整表可删（候选 canary）：{report['fully_deletable_tables'] or '（无）'}"
    )
    pat = report.get("zero_deletable_pattern") or {}
    n_zero = pat.get("table_count", 0)
    if not n_zero:
        lines.append("整表零可删（禁开表）：（无）")
    else:
        lines.append(f"🔴 整表零可删（**禁开表**）：{n_zero} 张")
        if pat.get("verdict") == "single_structural_pattern":
            lines.append(
                f"    ⇒ 它们是**同一个结构性问题**的 {n_zero} 个实例，不是 {n_zero} 个"
                f"孤立案例：锁死原因全为 {pat['shared_lock_reasons']}。"
                "对这一类要做的是一次性判断（这类表能不能开表），而不是逐张判断。"
            )
        elif pat.get("mixed_reason_families"):
            lines.append(
                f"    ⚠ 归类失败（某族原因集合不唯一）：{pat['mixed_reason_families']} "
                "—— 不要当成一族处理"
            )
        for fam in pat.get("families", []):
            lines.append(
                f"    原因 {fam['lock_reasons']}：{fam['table_count']} 张 / "
                f"{fam['managed_rows']} 行 / sheet 形态 {fam['sheet_shapes']}"
            )
            lines.append(f"        {fam['tables']}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="输出机读 JSON")
    parser.add_argument("--table", default=None, help="只看某个 table_key")
    parser.add_argument(
        "--count",
        type=int,
        default=1,
        help="一次删几行（默认 1；删 1 行没事不代表删 3 行没事）",
    )
    args = parser.parse_args(argv)
    if args.count < 1:
        parser.error("--count 必须 >= 1")

    report = run_audit(table_filter=args.table, count=args.count)

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(_render(report))

    # 🔴 退出码只判「语料本身坏了」，不判「没有可删的表」——
    # 后者是本工具要报告的**事实**，把它做成失败会逼着人去改契约来让脚本变绿。
    if not report["contract_files"]:
        print("\n❌ 契约目录为空 —— 分母没了，体检结论无意义", file=sys.stderr)
        return 2
    if not args.table and not report["tables_audited"]:
        print(
            "\n❌ 一张表都没体检成功 —— 模板目录或 sheet 名解析坏了（不是「都不可删」）",
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
