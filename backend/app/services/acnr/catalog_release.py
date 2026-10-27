"""ACNR 发布门禁（design §5.2 / D4）。

生成器、CI、测试共用的一组发布门禁。`run_release_gates(new, previous, report, *, today)`
把全部检查跑完再汇总，返回 `list[GateViolation]`（空列表 = 可发布）。

check ∈ schema / duplicate / sheet_code / orphan / a1 / roundtrip / immutable /
alias / ack / verdict / override。

往返检查（roundtrip）用「待发布的新目录」解析而不是磁盘上的已提交目录：
构造一个临时 `CatalogIndex(new)` 并经 `catalog.use_catalog(index)` 作用域让
`exact_identity` / `full_resolve` 解析到新目录。生产代码不调用 `use_catalog`
（守卫 test_only_generator_writes_catalog 断言只有门禁模块与测试引用它）。

本模块只依赖标准库 + 本包（exact_identity / catalog / catalog_contract）；
`jsonschema` 为可选依赖，缺失时 schema 检查退化为「跳过并记一条 info 违规」，
生产 CI 环境已钉 `jsonschema==4.26.0`。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Iterable

from . import catalog as _catalog_mod
from . import catalog_contract, exact_identity

# A1 坐标（与 catalog_contract._CELL cell_address 口径一致）
import re as _re

_A1_RE = _re.compile(r"^[A-Z]+[0-9]+$")


# ─── 违规对象 ──────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class GateViolation:
    """单条发布门禁违规。check 为门禁名，addr_id 为涉及条目（无则空串），detail 中文。"""

    check: str
    addr_id: str
    detail: str

    def __str__(self) -> str:  # pragma: no cover - 仅打印用
        aid = f" [{self.addr_id}]" if self.addr_id else ""
        return f"{self.check}{aid}: {self.detail}"


# ─── 各门禁（每个返回自己的违规列表） ─────────────────────────────────────────


def _gate_schema(new: dict[str, Any]) -> list[GateViolation]:
    """new 必须通过 build_schema()。缺 jsonschema 时记一条 info 违规（不阻断本地）。"""
    try:
        import jsonschema  # type: ignore
    except ImportError:
        return [GateViolation("schema", "", "jsonschema 未安装，schema 门禁跳过（CI 已钉 4.26.0）")]
    validator = jsonschema.Draft7Validator(catalog_contract.build_schema())
    out: list[GateViolation] = []
    for err in sorted(validator.iter_errors(new), key=lambda e: list(e.absolute_path)):
        path = "/".join(str(p) for p in err.absolute_path)
        out.append(GateViolation("schema", path, err.message))
    return out


def _gate_duplicate(new: dict[str, Any]) -> list[GateViolation]:
    """sheets 内、cells 内、sheet↔cell 互撞的 addr_id 重复。"""
    out: list[GateViolation] = []
    sheet_seen: dict[str, int] = {}
    for s in new.get("sheets", []):
        aid = s.get("addr_id", "")
        sheet_seen[aid] = sheet_seen.get(aid, 0) + 1
    for aid, n in sorted(sheet_seen.items()):
        if n > 1:
            out.append(GateViolation("duplicate", aid, f"sheets 内 addr_id 重复 {n} 次"))

    cell_seen: dict[str, int] = {}
    for c in new.get("cells", []):
        aid = c.get("addr_id", "")
        cell_seen[aid] = cell_seen.get(aid, 0) + 1
    for aid, n in sorted(cell_seen.items()):
        if n > 1:
            out.append(GateViolation("duplicate", aid, f"cells 内 addr_id 重复 {n} 次"))

    cross = set(sheet_seen) & set(cell_seen)
    for aid in sorted(cross):
        out.append(GateViolation("duplicate", aid, "addr_id 同时是 sheet 与 cell"))
    return out


def _gate_sheet_code(new: dict[str, Any]) -> list[GateViolation]:
    """每个 cell 的 addr_id 前缀必须等于 parent_addr_id（{parent}/{sheet}/{...}）。"""
    out: list[GateViolation] = []
    for c in new.get("cells", []):
        aid = c.get("addr_id", "")
        parent = c.get("parent_addr_id", "")
        if not parent:
            out.append(GateViolation("sheet_code", aid, "cell 缺 parent_addr_id"))
            continue
        if not aid.startswith(parent + "/"):
            out.append(
                GateViolation("sheet_code", aid, f"cell addr_id 前缀与 parent_addr_id「{parent}」不一致")
            )
    return out


def _gate_orphan(new: dict[str, Any]) -> list[GateViolation]:
    """每个 cell 的 parent_addr_id 必须指向一个存在的 sheet。"""
    out: list[GateViolation] = []
    sheet_ids = {s.get("addr_id", "") for s in new.get("sheets", [])}
    for c in new.get("cells", []):
        parent = c.get("parent_addr_id", "")
        if parent and parent not in sheet_ids:
            out.append(
                GateViolation("orphan", c.get("addr_id", ""), f"父 sheet「{parent}」不在目录中")
            )
    return out


def _gate_a1(new: dict[str, Any]) -> list[GateViolation]:
    """有 cell_address 的 cell 其 A1 必须合法且与 addr_id 末段一致。"""
    out: list[GateViolation] = []
    for c in new.get("cells", []):
        a1 = c.get("cell_address")
        if a1 is None:
            continue  # semantic_only
        if not _A1_RE.match(a1):
            out.append(GateViolation("a1", c.get("addr_id", ""), f"非法 A1 坐标「{a1}」"))
            continue
        last = c.get("addr_id", "").rsplit("/", 1)[-1]
        if last != a1:
            out.append(
                GateViolation("a1", c.get("addr_id", ""), f"addr_id 末段「{last}」与 cell_address「{a1}」不一致")
            )
    return out


def _gate_roundtrip(new: dict[str, Any]) -> list[GateViolation]:
    """非停用条目的身份经新目录往返回到自身。

    sheet：sheet_of(parent, sheet_code) 回到本 addr_id。
    cell ：cell_of(parent, sheet_code, A1) 回到本 addr_id（跳过 semantic_only）。
    """
    out: list[GateViolation] = []
    index = _catalog_mod.CatalogIndex(new)
    with _catalog_mod.use_catalog(index):
        for s in new.get("sheets", []):
            if s.get("deprecated"):
                continue
            parent = s.get("parent_wp_code", "")
            code = s.get("sheet_code", "")
            aid = s.get("addr_id", "")
            sm = exact_identity.sheet_of(parent, code, index=index)
            if not sm.ok or (sm.entry or {}).get("addr_id") != aid:
                got = (sm.entry or {}).get("addr_id") if sm.ok else sm.state
                out.append(GateViolation("roundtrip", aid, f"sheet 往返未回本身（得 {got}）"))

        for c in new.get("cells", []):
            if c.get("deprecated"):
                continue
            a1 = c.get("cell_address")
            if a1 is None:
                continue  # semantic_only 无 A1，不参与往返
            aid = c.get("addr_id", "")
            parent_addr = c.get("parent_addr_id", "")
            parent_entry = index.sheets_by_addr_id.get(parent_addr, {})
            parent = parent_entry.get("parent_wp_code", "")
            code = parent_entry.get("sheet_code", "")
            cm = exact_identity.cell_of(parent, code, a1, index=index)
            if not cm.ok or cm.addr_id != aid:
                got = cm.addr_id if cm.ok else cm.state
                out.append(GateViolation("roundtrip", aid, f"cell 往返未回本身（得 {got}）"))
    return out


def _gate_immutable(new: dict[str, Any], previous: dict[str, Any] | None) -> list[GateViolation]:
    """上一批次已发布的 addr_id 不得在新目录中消失（停用保留，不删）。"""
    if not previous:
        return []
    out: list[GateViolation] = []
    new_ids = {s.get("addr_id", "") for s in new.get("sheets", [])}
    new_ids |= {c.get("addr_id", "") for c in new.get("cells", [])}
    prev_ids = {s.get("addr_id", "") for s in previous.get("sheets", [])}
    prev_ids |= {c.get("addr_id", "") for c in previous.get("cells", [])}
    for aid in sorted(prev_ids - new_ids):
        out.append(GateViolation("immutable", aid, "上一批次已发布的 addr_id 在新目录中消失"))
    return out


def _gate_alias(
    new: dict[str, Any], alias_policy: dict[str, Any] | None
) -> list[GateViolation]:
    """禁止别名不得同时是本父级内某 sheet 的 sheet_name / sheet_code（不相交不变量）。"""
    index = _catalog_mod.CatalogIndex(new)
    out: list[GateViolation] = []
    for desc in exact_identity.forbidden_disjoint_violations(index):
        out.append(GateViolation("alias", "", desc))
    return out


def _gate_ack(
    report: dict[str, Any] | None,
    acknowledgements: dict[str, Any] | None,
    *,
    today: date,
) -> list[GateViolation]:
    """豁免清单每条必须未过期（expires_on >= today）且带 owner/reason。"""
    if not acknowledgements:
        return []
    out: list[GateViolation] = []
    for kind, items in acknowledgements.items():
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                out.append(GateViolation("ack", "", f"{kind} 的豁免条目格式非法"))
                continue
            aid = item.get("addr_id") or item.get("key") or ""
            if not item.get("owner"):
                out.append(GateViolation("ack", aid, f"{kind} 豁免缺 owner"))
            if not item.get("reason"):
                out.append(GateViolation("ack", aid, f"{kind} 豁免缺 reason"))
            expires = item.get("expires_on")
            if not expires:
                out.append(GateViolation("ack", aid, f"{kind} 豁免缺 expires_on"))
                continue
            try:
                exp = date.fromisoformat(str(expires))
            except ValueError:
                out.append(GateViolation("ack", aid, f"{kind} 豁免 expires_on「{expires}」非法"))
                continue
            if exp < today:
                out.append(GateViolation("ack", aid, f"{kind} 豁免已于 {expires} 过期"))
    return out


def _gate_verdict(
    new: dict[str, Any], sheet_verdicts: dict[str, Any] | None
) -> list[GateViolation]:
    """deprecate 结论必须有可解析的 replaced_by（指向存在的 addr_id）。"""
    if not sheet_verdicts:
        return []
    out: list[GateViolation] = []
    all_ids = {s.get("addr_id", "") for s in new.get("sheets", [])}
    all_ids |= {c.get("addr_id", "") for c in new.get("cells", [])}
    for seg in ("sheet_verdicts", "cell_verdicts"):
        for v in sheet_verdicts.get(seg, []):
            if not isinstance(v, dict):
                continue
            if v.get("verdict") != "deprecate":
                continue
            aid = v.get("addr_id", "")
            rb = v.get("replaced_by")
            if not rb:
                out.append(GateViolation("verdict", aid, "deprecate 缺 replaced_by"))
            elif rb not in all_ids:
                out.append(GateViolation("verdict", aid, f"replaced_by「{rb}」不在目录中"))
    return out


def _gate_override(
    new: dict[str, Any], overrides: dict[str, Any] | None
) -> list[GateViolation]:
    """每条 override 须有 owner / reason / source，且所指 addr_id 在目录中。"""
    if not overrides:
        return []
    out: list[GateViolation] = []
    all_ids = {s.get("addr_id", "") for s in new.get("sheets", [])}
    all_ids |= {c.get("addr_id", "") for c in new.get("cells", [])}
    for entry in overrides.get("overrides", []):
        if not isinstance(entry, dict):
            out.append(GateViolation("override", "", "override 条目格式非法"))
            continue
        aid = entry.get("addr_id", "")
        for req in ("owner", "reason", "source"):
            if not entry.get(req):
                out.append(GateViolation("override", aid, f"override 缺 {req}"))
        if aid and aid not in all_ids:
            out.append(GateViolation("override", aid, "override 所指 addr_id 不在目录中"))
    return out


# ─── 汇总入口 ──────────────────────────────────────────────────────────────


def run_release_gates(
    new: dict[str, Any],
    previous: dict[str, Any] | None,
    report: dict[str, Any] | None,
    *,
    today: date,
    sheet_verdicts: dict[str, Any] | None = None,
    alias_policy: dict[str, Any] | None = None,
    acknowledgements: dict[str, Any] | None = None,
    overrides: dict[str, Any] | None = None,
) -> list[GateViolation]:
    """跑完全部门禁再汇总。空列表 = 可发布。

    参数
    ----
    new          待发布目录（dict，含 sheets / cells / version / registry_version）。
    previous     上一批次目录（dict），None 表示首个合规批次。
    report       本批次报告（dict），schema/ack 检查用，可 None。
    today        豁免到期比对基准（注入以避免「今天」进判据产生非确定性）。
    """
    violations: list[GateViolation] = []
    violations += _gate_schema(new)
    violations += _gate_duplicate(new)
    violations += _gate_sheet_code(new)
    violations += _gate_orphan(new)
    violations += _gate_a1(new)
    violations += _gate_roundtrip(new)
    violations += _gate_immutable(new, previous)
    violations += _gate_alias(new, alias_policy)
    violations += _gate_ack(report, acknowledgements, today=today)
    violations += _gate_verdict(new, sheet_verdicts)
    violations += _gate_override(new, overrides)
    return violations


def group_by_check(violations: Iterable[GateViolation]) -> dict[str, list[GateViolation]]:
    """按 check 分组（供打印 / 测试断言）。"""
    out: dict[str, list[GateViolation]] = {}
    for v in violations:
        out.setdefault(v.check, []).append(v)
    return out


__all__ = ["GateViolation", "run_release_gates", "group_by_check"]
