"""ACNR 发布门禁（design §5.2 / D4；段四审计 F4-08 补齐语义）。

生成器、CI、测试共用的一组发布门禁。`run_release_gates(new, previous, report, *, today, ...)`
把全部检查跑完再汇总，返回 `list[GateViolation]`（空列表 = 可发布）。

check ∈ schema / duplicate / sheet_code / orphan / a1 / roundtrip / immutable / alias / ack / verdict / override：
- duplicate：sheets 内、cells 内、sheet 与 cell 互撞的 addr_id 重复。
- sheet_code：cell addr_id 前缀 == parent_addr_id；sheet_code 全局唯一（需求 4.1，现行政策）。
- orphan：cell 的 parent_addr_id 必须是目录里的 sheet。
- a1：有 cell_address 的 cell，A1 合法（口径 `catalog_contract.A1_PATTERN`）且等于 addr_id 末段。
- roundtrip（design §6.5 / 需求 5.1）：非停用 sheet 的 sheet_code（作 WP 第二参）与 `sheet:{code}`、非停用且父 sheet
  在目录内的 cell 的 A1、自带 formula_ref、uri、`cell:{code}!{A1}` 经新目录解析都回到自身。sheet / cell 身份用
  exact_identity 判定，`sheet:` / `cell:` 写法用生产解析函数 `catalog._index_ref_to_addr_id`（在
  `use_catalog(新目录)` 作用域内）。父 sheet 不在目录的 cell 只由 orphan 报，不在这里重复报。
- immutable：接 `immutability.validate_addr_id_immutable`（与 `check_addr_id_immutable` 同一判据）——上一批次未停用的
  addr_id 消失、不可变字段（sheet 的 parent_wp_code / sheet_code，cell 的 parent_addr_id / cell_address）改值都阻断。
- alias：父级禁止别名与本父级 sheet_name / sheet_code 不相交（目录顶层 `alias_policy.forbidden` 与传入的
  alias_policy 两种写法都核）；alias_policy 条目须有 owner / reason、处置在五类之内；non_address_label / merge_into
  的键不得已是目录 sheet_code，且须仍是本批次的未登记别名键，否则为失效条目；merge_into 的目标须在目录。
  未处置即阻断（T09）：本批次每个未登记别名键须有 merge_into / non_address_label；每条别名冲突在目录 sheet 上的
  成员须有 forbidden / parent_qualified / project_context，处置冲突的条目所指冲突已不存在即失效条目。
- ack（design §7.4）：标「语义待核对」的有效 cell 须被 seed_semantic_unverified 豁免覆盖（未处置即阻断）；
  豁免须有 owner / reason / expires_on 且未过期、kind 在登记范围、声明了覆盖对象；所覆盖的问题
  已不存在即为失效条目——addr_id / sheet_code 不在新目录；seed_semantic_unverified 覆盖的 cell 已停用或已有语义名；
  ccr_ids / aliases 不在本批次的当前问题清单里；带 head_resolvable_at 的条目，其写法（writing）在新目录里已能解析到
  别的 sheet（不再错配）。
- verdict：deprecate 判定须有可解析的 replaced_by，条目须保留在新目录并标 deprecated（仍是有效条目即「无物理来源的
  有效 cell」/「判定停用的 sheet 仍是有效条目」）；add_platform_sheet 判定的 sheet 须写入新目录。
- override：每条 override 须有 owner / reason / source，所指 addr_id 在目录中。

本批次的当前问题清单由生成器（`catalog_build.build_release`）在跑门禁前放进 `report["open_problems"]`：
`{"unregistered_alias_keys": [...], "alias_conflicts": [...], "alias_conflict_members": {别名: [sheet_code]},
"ccr_unresolved": [...]}`（ccr_unresolved 由 T22 产出，现未提供）。覆盖这几类问题的处置与豁免，在对应清单缺失时
按「无法核实」阻断（fail-closed），不放行。

往返检查用「待发布的新目录」解析：构造临时 `CatalogIndex(new)` 并经 `catalog.use_catalog(index)` 作用域让
`get_catalog()` 返回新目录。只有本模块与测试调用 `use_catalog`（守卫 `tests/acnr/test_only_generator_writes_catalog.py`）；
生成器经 `catalog_build.build_release` 调用本模块，写出与 `--check` 都跑门禁。

本模块只依赖标准库 + 本包（exact_identity / catalog / catalog_contract / immutability）；`jsonschema` 为可选依赖，
缺失时 schema 检查退化为「跳过并记一条 info 违规」，生产 CI 环境已钉 `jsonschema==4.26.0`。
"""
from __future__ import annotations

import re as _re
from dataclasses import dataclass
from datetime import date
from typing import Any, Iterable

from . import catalog as _catalog_mod
from . import catalog_contract, exact_identity
from .immutability import validate_addr_id_immutable

# A1 坐标口径唯一来源：catalog_contract.A1_PATTERN（与 schema、exact_identity 一致）
_A1_RE = _re.compile(catalog_contract.A1_PATTERN)

ALIAS_DISPOSITIONS = frozenset({"parent_qualified", "forbidden", "project_context", "non_address_label", "merge_into"})
ACK_KINDS = frozenset({"seed_semantic_unverified", "ccr_unresolved", "head_resolvable_errmatch"})
#: report["open_problems"] 的三类问题清单（见模块文档）
OPEN_PROBLEM_KEYS = ("unregistered_alias_keys", "alias_conflicts", "ccr_unresolved")
#: 「语义待核对」cell_label 后缀（与 catalog_names.apply_cell_verdicts 写出的一致）
SEMANTIC_UNVERIFIED_SUFFIX = "（语义待核对）"


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


def _all_ids(new: dict[str, Any]) -> set[str]:
    ids = {s.get("addr_id", "") for s in new.get("sheets", [])}
    return ids | {c.get("addr_id", "") for c in new.get("cells", [])}


def _try_index(new: dict[str, Any]):
    try:
        return _catalog_mod.CatalogIndex(new)
    except _catalog_mod.CatalogIntegrityError:
        return None  # addr_id 重复由 _gate_duplicate 单独报告


def _open_problems(report: dict[str, Any] | None) -> dict[str, frozenset[str]]:
    """report["open_problems"] → {清单名: 集合}；未提供的清单不出现在结果里（调用方据此判「无法核实」）。"""
    raw = report.get("open_problems") if isinstance(report, dict) else None
    out: dict[str, frozenset[str]] = {}
    if isinstance(raw, dict):
        for key in OPEN_PROBLEM_KEYS:
            if isinstance(raw.get(key), list):
                out[key] = frozenset(str(x) for x in raw[key])
    return out


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

    for aid in sorted(set(sheet_seen) & set(cell_seen)):
        out.append(GateViolation("duplicate", aid, "addr_id 同时是 sheet 与 cell"))
    return out


def _gate_sheet_code(new: dict[str, Any]) -> list[GateViolation]:
    """cell addr_id 前缀 == parent_addr_id；sheet_code 全局唯一（需求 4.1）。"""
    out: list[GateViolation] = []
    for c in new.get("cells", []):
        aid = c.get("addr_id", "")
        parent = c.get("parent_addr_id", "")
        if not parent:
            out.append(GateViolation("sheet_code", aid, "cell 缺 parent_addr_id"))
            continue
        if not aid.startswith(parent + "/"):
            out.append(GateViolation("sheet_code", aid, f"cell addr_id 前缀与 parent_addr_id「{parent}」不一致"))
    by_code: dict[str, list[str]] = {}
    for s in new.get("sheets", []):
        by_code.setdefault(s.get("sheet_code", ""), []).append(s.get("addr_id", ""))
    for code, aids in sorted(by_code.items()):
        if len(aids) > 1:
            for aid in sorted(aids):
                out.append(GateViolation("sheet_code", aid, f"sheet_code「{code}」全局重复 {len(aids)} 次：{sorted(aids)}"))
    return out


def _gate_orphan(new: dict[str, Any]) -> list[GateViolation]:
    """每个 cell 的 parent_addr_id 必须指向一个存在的 sheet。"""
    out: list[GateViolation] = []
    sheet_ids = {s.get("addr_id", "") for s in new.get("sheets", [])}
    for c in new.get("cells", []):
        parent = c.get("parent_addr_id", "")
        if parent and parent not in sheet_ids:
            out.append(GateViolation("orphan", c.get("addr_id", ""), f"父 sheet「{parent}」不在目录中"))
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
            out.append(GateViolation("a1", c.get("addr_id", ""), f"addr_id 末段「{last}」与 cell_address「{a1}」不一致"))
    return out


def _wp_args(ref: str) -> list[str] | None:
    """WP('a','b','c') / PREV(...) → 单引号参数列表（与 catalog 的参数切分同口径）。"""
    s = (ref or "").strip()
    if not (s.startswith("WP(") or s.startswith("PREV(")) or ")" not in s:
        return None
    body = s[s.index("(") + 1:s.rindex(")")]
    out, cur, quoted = [], "", False
    for ch in body:
        if ch == "'":
            if quoted:
                out.append(cur)
                cur = ""
            quoted = not quoted
        elif quoted:
            cur += ch
    return out


def _uri_parts(uri: str) -> tuple[str, str, str] | None:
    """wp://{parent}/{sheet}#{A1} → (parent, sheet, A1)。"""
    if not (uri or "").startswith("wp://") or "#" not in uri:
        return None
    body, a1 = uri[len("wp://"):].rsplit("#", 1)
    if "/" not in body:
        return None
    parent, sheet = body.split("/", 1)
    return parent, sheet, a1


def _gate_roundtrip(new: dict[str, Any]) -> list[GateViolation]:
    """非停用条目的身份写法经新目录解析回到自身（design §6.5 / 需求 5.1）。"""
    out: list[GateViolation] = []
    index = _try_index(new)
    if index is None:
        return out
    index_ref = _catalog_mod._index_ref_to_addr_id  # 生产解析函数（sheet: / cell: 写法）

    with _catalog_mod.use_catalog(index):
        for s in new.get("sheets", []):
            if s.get("deprecated"):
                continue
            parent, code, aid = s.get("parent_wp_code", ""), s.get("sheet_code", ""), s.get("addr_id", "")
            sm = exact_identity.sheet_of(parent, code, index=index)
            if not sm.ok or (sm.entry or {}).get("addr_id") != aid:
                got = (sm.entry or {}).get("addr_id") if sm.ok else sm.state
                out.append(GateViolation("roundtrip", aid, f"sheet 往返未回本身（得 {got}）"))
            got_ref = index_ref(f"sheet:{code}")
            if got_ref != aid:
                out.append(GateViolation("roundtrip", aid, f"sheet:{code} 往返未回本身（得 {got_ref}）"))

        for c in new.get("cells", []):
            parent_entry = index.sheets_by_addr_id.get(c.get("parent_addr_id", ""))
            if c.get("deprecated") or c.get("cell_address") is None or parent_entry is None:
                continue  # 停用不参与；semantic_only 无 A1；父 sheet 缺失由 orphan 报
            a1, aid = c["cell_address"], c.get("addr_id", "")
            parent, code = parent_entry.get("parent_wp_code", ""), parent_entry.get("sheet_code", "")
            cm = exact_identity.cell_of(parent, code, a1, index=index)
            if not cm.ok or cm.addr_id != aid:
                out.append(GateViolation("roundtrip", aid, f"cell 往返未回本身（得 {cm.addr_id if cm.ok else cm.state}）"))
            got_ref = index_ref(f"cell:{code}!{a1}")
            if got_ref != aid:
                out.append(GateViolation("roundtrip", aid, f"cell:{code}!{a1} 往返未回本身（得 {got_ref}）"))
            args = _wp_args(c.get("formula_ref", ""))
            if not args or len(args) != 3:
                out.append(GateViolation("roundtrip", aid, f"formula_ref「{c.get('formula_ref')}」不是三参 WP 写法"))
            else:
                fm = exact_identity.cell_of(args[0], args[1], args[2], index=index)
                if not fm.ok or fm.addr_id != aid:
                    out.append(GateViolation("roundtrip", aid,
                                             f"formula_ref 往返未回本身（得 {fm.addr_id if fm.ok else fm.state}）"))
            if c.get("uri"):
                parts = _uri_parts(c["uri"])
                um = exact_identity.cell_of(*parts, index=index) if parts else None
                if um is None or not um.ok or um.addr_id != aid:
                    got = (um.addr_id if um.ok else um.state) if um else "无法解析"
                    out.append(GateViolation("roundtrip", aid, f"uri 往返未回本身（得 {got}）"))
    return out


_IMMUTABLE_KIND_ZH = {"removed": "上一批次已发布的 addr_id 在新目录中消失（未先停用）", "value_changed": "不可变字段被改值"}


def _gate_immutable(new: dict[str, Any], previous: dict[str, Any] | None) -> list[GateViolation]:
    """接 validate_addr_id_immutable：未停用即移除、不可变字段改值都阻断（需求 4.1）。"""
    if not previous:
        return []
    return [
        GateViolation("immutable", v["addr_id"], f"{_IMMUTABLE_KIND_ZH.get(v['type'], v['type'])}：{v['detail']}")
        for v in validate_addr_id_immutable(previous, new)
    ]


def _alias_entries(alias_policy: Any) -> list[dict]:
    """sources/alias_policy.json 的条目写法（design §7.2）：列表或 {entries: [...]}。"""
    if isinstance(alias_policy, dict):
        rows = alias_policy.get("entries", [])
    else:
        rows = alias_policy or []
    return [r for r in rows if isinstance(r, dict)]


def _forbidden_map_rows(mapping: Any) -> list[tuple[str, str, list[str]]]:
    """目录顶层 alias_policy.forbidden 写法 {parent_wp_code: {alias: [sheet_code...]}} → 逐条三元组。"""
    rows: list[tuple[str, str, list[str]]] = []
    if isinstance(mapping, dict):
        for parent, by_alias in mapping.items():
            if isinstance(by_alias, dict):
                rows += [(parent, alias, list(codes or [])) for alias, codes in by_alias.items()]
    return rows


def _gate_alias(new: dict[str, Any], alias_policy: Any, report: dict[str, Any] | None) -> list[GateViolation]:
    """禁止别名不相交不变量 + alias_policy 逐条核对（design §6.2 不变量 / §7.2 / §7.3）。

    两种写法都核：目录顶层与传入的 `{"forbidden": {父级: {别名: [sheet_code]}}}`，以及源文件条目
    `{alias, sheet_codes, disposition, reason, owner, target?}`。
    """
    out: list[GateViolation] = []
    index = _try_index(new)
    if index is None:
        return out
    for desc in exact_identity.forbidden_disjoint_violations(index):
        out.append(GateViolation("alias", "", desc))
    pools = index.sheets_by_parent

    def _forbidden(parent: str, alias: str, codes: list[str]) -> None:
        pool = pools.get(parent)
        if pool is None:
            out.append(GateViolation("alias", "", f"失效条目：禁止别名「{alias}」的父级「{parent}」不在目录"))
            return
        pool_codes = {s.get("sheet_code") for s in pool}
        if alias in {s.get("sheet_name") for s in pool} | pool_codes:
            out.append(GateViolation("alias", parent, f"禁止别名「{alias}」又是 {parent} 内的 sheet_name / sheet_code"))
        for code in codes:
            if code not in pool_codes:
                out.append(GateViolation("alias", parent, f"失效条目：禁止别名「{alias}」所列 sheet_code「{code}」不在 {parent} 内"))

    mapping_rows = _forbidden_map_rows((new.get("alias_policy") or {}).get("forbidden"))
    if isinstance(alias_policy, dict):
        mapping_rows += _forbidden_map_rows(alias_policy.get("forbidden"))
    for parent, alias, codes in mapping_rows:
        _forbidden(parent, alias, codes)

    by_code = {s.get("sheet_code", ""): s for s in new.get("sheets", [])}
    sheet_ids = {s.get("addr_id", "") for s in new.get("sheets", [])}
    open_keys = _open_problems(report).get("unregistered_alias_keys")
    out += _alias_undisposed(_alias_entries(alias_policy), report, open_keys, set(by_code))
    for e in _alias_entries(alias_policy):
        alias, disp = e.get("alias", ""), e.get("disposition", "")
        for req in ("alias", "owner", "reason"):
            if not e.get(req):
                out.append(GateViolation("alias", "", f"alias_policy「{alias}」缺 {req}"))
        if disp not in ALIAS_DISPOSITIONS:
            out.append(GateViolation("alias", "", f"alias_policy「{alias}」处置「{disp}」不在 {sorted(ALIAS_DISPOSITIONS)}"))
            continue
        if disp == "forbidden":
            for code in e.get("sheet_codes", []) or []:
                parent = (by_code.get(code) or {}).get("parent_wp_code")
                if parent is None:
                    out.append(GateViolation("alias", "", f"失效条目：禁止别名「{alias}」所列 sheet_code「{code}」不在目录"))
                else:
                    _forbidden(parent, alias, [code])
        elif disp in ("non_address_label", "merge_into"):
            if alias in by_code:
                out.append(GateViolation("alias", "", f"失效条目：{disp}「{alias}」已是目录 sheet_code"))
            if disp == "merge_into" and e.get("writings"):
                out += _merge_writing_violations(e, new)
                if alias not in (open_keys or frozenset()):
                    continue  # 只由写法证据支撑的并入（T10，design §6.5）：不要求是标签源未登记键
            if open_keys is None:
                out.append(GateViolation("alias", "", f"{disp}「{alias}」无法核实：报告未提供 open_problems.unregistered_alias_keys"))
            elif alias not in open_keys:
                out.append(GateViolation("alias", "", f"失效条目：{disp}「{alias}」已不是本批次的未登记别名键（所指问题已不存在）"))
            if disp == "merge_into" and e.get("target") not in sheet_ids:
                out.append(GateViolation("alias", "", f"alias_policy「{alias}」merge_into 目标「{e.get('target')}」不在目录中"))
    return out


def _merge_writing_violations(e: dict, new: dict[str, Any]) -> list[GateViolation]:
    """merge_into 带 writings（HEAD 能解析、改用 exact_identity 后需父级限定别名的静态写法，design §6.5）：
    每条写法须是 {wp_code, sheet, where}、sheet 等于别名键、wp_code 为目标的父级，并入后须解析回目标。"""
    alias, target = e.get("alias", ""), e.get("target", "")
    out: list[GateViolation] = []
    parent = next((s.get("parent_wp_code") for s in new.get("sheets", []) if s.get("addr_id") == target), None)
    if parent is None:
        return [GateViolation("alias", "", f"alias_policy「{alias}」merge_into 目标「{target}」不在目录中")]
    for w in e.get("writings") or []:
        if not (isinstance(w, dict) and w.get("wp_code") and w.get("where") and w.get("sheet") == alias):
            out.append(GateViolation("alias", target, f"merge_into「{alias}」的写法证据须为 {{wp_code, sheet=别名, where}}：{w}"))
        elif w["wp_code"] != parent:
            out.append(GateViolation("alias", target, f"merge_into「{alias}」写法 {w['where']} 的底稿「{w['wp_code']}」不是目标父级「{parent}」"))
    index = _try_index(new)
    if index is not None:
        sm = exact_identity.sheet_of(parent, alias, index=index)
        got = (sm.entry or {}).get("addr_id") if sm.ok else sm.state
        if got != target:
            out.append(GateViolation("alias", target, f"merge_into「{alias}」并入后在 {parent} 下解析为 {got}，不是目标 {target}"))
    return out


_CONFLICT_DISPOSITIONS = ("forbidden", "parent_qualified", "project_context")
_LABEL_KEY_DISPOSITIONS = ("non_address_label", "merge_into")


def _alias_undisposed(entries: list[dict], report: dict[str, Any] | None, open_keys: frozenset[str] | None,
                      catalog_codes: set[str]) -> list[GateViolation]:
    """未处置即阻断（design §7.1 / 需求 6.2~6.3）：本批次的未登记别名键须有 merge_into / non_address_label；
    别名冲突在目录 sheet 上的成员须有 forbidden / parent_qualified / project_context，不在目录的成员须是已处置的
    未登记键；处置冲突的条目所指冲突已不存在即失效条目。清单缺失时，引用它的条目按「无法核实」阻断。"""
    out: list[GateViolation] = []
    disposed_keys = {e.get("alias") for e in entries if e.get("disposition") in _LABEL_KEY_DISPOSITIONS}
    for key in sorted((open_keys or frozenset()) - disposed_keys):
        out.append(GateViolation("alias", "", f"未登记别名键「{key}」未处置（须在 alias_policy 登记 merge_into 或 non_address_label）"))
    conflicts = _open_problems(report).get("alias_conflicts")
    raw = report.get("open_problems") if isinstance(report, dict) else None
    members = raw.get("alias_conflict_members") if isinstance(raw, dict) else None
    covering = [e for e in entries if e.get("disposition") in _CONFLICT_DISPOSITIONS and e.get("alias")]
    if conflicts is None:
        out += [GateViolation("alias", "", f"{e['disposition']}「{e['alias']}」无法核实：报告未提供 open_problems.alias_conflicts")
                for e in covering]
        return out
    if not isinstance(members, dict):
        return out + [GateViolation("alias", "", "别名冲突无法核实：报告未提供 open_problems.alias_conflict_members")]
    for e in covering:
        if e["alias"] not in conflicts:
            out.append(GateViolation("alias", "", f"失效条目：{e['disposition']}「{e['alias']}」所指别名冲突已不存在"))
    for alias in sorted(conflicts):
        covered = {c for e in covering if e["alias"] == alias for c in (e.get("sheet_codes") or [])}
        for code in members.get(alias) or []:
            if code in catalog_codes and code not in covered:
                out.append(GateViolation("alias", "", f"别名冲突「{alias}」在目录 sheet「{code}」上未处置（须登记 forbidden / parent_qualified / project_context）"))
            elif code not in catalog_codes and code not in disposed_keys:
                out.append(GateViolation("alias", "", f"别名冲突「{alias}」的成员「{code}」是未处置的未登记键"))
    return out


def _ack_entries(acknowledgements: Any) -> list[tuple[str, Any]]:
    """支持 design §7.4 的 {entries:[{kind, covers, ...}]} 与按 kind 分组的 {kind: [...]} 两种写法。"""
    if isinstance(acknowledgements, dict) and isinstance(acknowledgements.get("entries"), list):
        return [((e or {}).get("kind", "") if isinstance(e, dict) else "", e) for e in acknowledgements["entries"]]
    if isinstance(acknowledgements, list):
        return [((e or {}).get("kind", "") if isinstance(e, dict) else "", e) for e in acknowledgements]
    out: list[tuple[str, Any]] = []
    for kind, items in (acknowledgements or {}).items():
        if isinstance(items, list):
            out += [(kind, it) for it in items]
    return out


def _ack_field_violations(kind: str, item: dict, aid: str, today: date) -> list[GateViolation]:
    """豁免条目自身字段：kind 在登记范围、owner / reason / expires_on 齐全且未过期。"""
    out: list[GateViolation] = []
    if kind not in ACK_KINDS:
        out.append(GateViolation("ack", aid, f"豁免 kind「{kind}」不在 {sorted(ACK_KINDS)}"))
    for req in ("owner", "reason"):
        if not item.get(req):
            out.append(GateViolation("ack", aid, f"{kind} 豁免缺 {req}"))
    expires = item.get("expires_on")
    if not expires:
        out.append(GateViolation("ack", aid, f"{kind} 豁免缺 expires_on"))
    else:
        try:
            if date.fromisoformat(str(expires)) < today:
                out.append(GateViolation("ack", aid, f"{kind} 豁免已于 {expires} 过期"))
        except ValueError:
            out.append(GateViolation("ack", aid, f"{kind} 豁免 expires_on「{expires}」非法"))
    return out


def _gate_ack(
    new: dict[str, Any],
    report: dict[str, Any] | None,
    acknowledgements: Any,
    *,
    today: date,
) -> list[GateViolation]:
    """豁免可伪证：字段齐全、未过期，且所覆盖的问题仍然存在（否则为失效条目，design §7.4）；
    反向：标「语义待核对」的有效 cell 必须被 seed_semantic_unverified 豁免覆盖（design §6.4，未处置即阻断）。"""
    covered_sem = {x for kind, item in _ack_entries(acknowledgements) if kind == "seed_semantic_unverified"
                   and isinstance(item, dict) and isinstance(item.get("covers"), dict)
                   for x in (item["covers"].get("addr_ids") or [])}
    pre = [GateViolation("ack", c.get("addr_id", ""), "语义待核对的 cell 未登记 seed_semantic_unverified 豁免（未处置）")
           for c in new.get("cells", []) if not c.get("deprecated")
           and str(c.get("cell_label") or "").endswith(SEMANTIC_UNVERIFIED_SUFFIX) and c.get("addr_id") not in covered_sem]
    if not acknowledgements:
        return pre
    by_id = {s.get("addr_id", ""): s for s in new.get("sheets", [])}
    cell_ids = {c.get("addr_id", "") for c in new.get("cells", [])}
    by_id.update({c.get("addr_id", ""): c for c in new.get("cells", [])})
    codes = {s.get("sheet_code", "") for s in new.get("sheets", [])}
    problems = _open_problems(report)
    index = _try_index(new)
    out: list[GateViolation] = pre
    for kind, item in _ack_entries(acknowledgements):
        if not isinstance(item, dict):
            out.append(GateViolation("ack", "", f"{kind} 的豁免条目格式非法"))
            continue
        covers = item.get("covers") or {}
        if not isinstance(covers, dict):
            out.append(GateViolation("ack", "", f"{kind} 豁免 covers 格式非法"))
            covers = {}
        covered = {
            "addr_ids": list(covers.get("addr_ids") or ([item["addr_id"]] if item.get("addr_id") else [])),
            "sheet_codes": list(covers.get("sheet_codes") or []),
            "ccr_ids": list(covers.get("ccr_ids") or []),
            "aliases": list(covers.get("aliases") or []),
        }
        firsts = [xs[0] for xs in covered.values() if xs]
        aid = (firsts or [item.get("id") or item.get("key") or ""])[0]
        out += _ack_field_violations(kind, item, aid, today)
        if not firsts:
            out.append(GateViolation("ack", aid, f"{kind} 豁免未声明覆盖对象（covers 为空，不可伪证）"))
        for x in covered["addr_ids"]:
            entry = by_id.get(x)
            if entry is None:
                out.append(GateViolation("ack", x, f"{kind} 豁免所指条目已不在目录（失效条目）"))
            elif kind == "seed_semantic_unverified":
                if x not in cell_ids:
                    out.append(GateViolation("ack", x, "语义待核对豁免只能覆盖 cell 条目"))
                elif entry.get("deprecated"):
                    out.append(GateViolation("ack", x, "语义待核对豁免所指 cell 已停用（所指问题已不存在，失效条目）"))
                elif entry.get("semantic_label"):
                    out.append(GateViolation("ack", x, "语义待核对豁免所指 cell 已有语义名（所指问题已不存在，失效条目）"))
        for x in covered["sheet_codes"]:
            if x not in codes:
                out.append(GateViolation("ack", x, f"{kind} 豁免所指 sheet 已不在目录（失效条目）"))
        for name, pool in (("ccr_ids", problems.get("ccr_unresolved")), ("aliases", _alias_problem_pool(problems))):
            if not covered[name]:
                continue
            if pool is None:
                out.append(GateViolation("ack", aid, f"{kind} 豁免覆盖 {name}，无法核实：报告未提供对应的 open_problems 清单"))
                continue
            for x in covered[name]:
                if x not in pool:
                    out.append(GateViolation("ack", x, f"{kind} 豁免所指问题「{x}」已不在本批次问题清单（失效条目）"))
        out += _ack_head_resolvable(kind, item, aid, index)
    return out


def _alias_problem_pool(problems: dict[str, frozenset[str]]) -> frozenset[str] | None:
    """别名类问题 = 别名冲突 ∪ 未登记别名键；两份清单都未提供时返回 None（无法核实）。"""
    parts = [problems[k] for k in ("alias_conflicts", "unregistered_alias_keys") if k in problems]
    return frozenset().union(*parts) if parts else None


def _ack_head_resolvable(kind: str, item: dict, aid: str, index: Any) -> list[GateViolation]:
    """带 head_resolvable_at 的豁免：写法须登记；它在新目录里若已解析到别的 sheet（不再错配），豁免失效。"""
    head = item.get("head_resolvable_at")
    if not head:
        return []
    writing = item.get("writing")
    if not (isinstance(writing, dict) and writing.get("wp_code") and isinstance(writing.get("sheet"), str)):
        return [GateViolation("ack", aid, f"{kind} 豁免带 head_resolvable_at 却缺 writing{{wp_code, sheet}}，无法核实是否仍错配")]
    if index is None:
        return []  # 目录本身有重复 addr_id，由 duplicate 门禁报告
    sm = exact_identity.sheet_of(writing["wp_code"], writing["sheet"], index=index)
    got = (sm.entry or {}).get("addr_id") if sm.ok else None
    if got and got != head:
        return [GateViolation("ack", aid, f"{kind} 豁免的写法在新目录已解析到「{got}」（不再错配 {head}），失效条目")]
    return []


def _gate_verdict(new: dict[str, Any], sheet_verdicts: dict[str, Any] | None) -> list[GateViolation]:
    """判定记录落进新目录：deprecate 条目保留为 deprecated 且 replaced_by 可解析；补登 sheet 已写入。"""
    if not sheet_verdicts:
        return []
    out: list[GateViolation] = []
    by_id = {s.get("addr_id", ""): s for s in new.get("sheets", [])}
    by_id.update({c.get("addr_id", ""): c for c in new.get("cells", [])})
    for seg in ("sheet_verdicts", "cell_verdicts"):
        for v in sheet_verdicts.get(seg, []):
            if not isinstance(v, dict):
                continue
            aid, verdict = v.get("addr_id", ""), v.get("verdict")
            entry = by_id.get(aid)
            if verdict == "deprecate":
                rb = v.get("replaced_by")
                if not rb:
                    out.append(GateViolation("verdict", aid, "deprecate 缺 replaced_by"))
                elif rb not in by_id:
                    out.append(GateViolation("verdict", aid, f"replaced_by「{rb}」不在目录中"))
                if entry is None:
                    out.append(GateViolation("verdict", aid, "判定停用的条目不在新目录（停用条目须保留并标 deprecated）"))
                elif not entry.get("deprecated"):
                    kind = "无物理来源的有效 cell" if seg == "cell_verdicts" else "判定停用的 sheet 仍是有效条目"
                    out.append(GateViolation("verdict", aid, f"{kind}（判定为 deprecate，新目录未停用）"))
            elif verdict == "add_platform_sheet" and aid not in by_id:
                out.append(GateViolation("verdict", aid, "判定补登的 sheet 未写入新目录"))
    return out


def _gate_override(new: dict[str, Any], overrides: dict[str, Any] | None) -> list[GateViolation]:
    """每条 override 须有 owner / reason / source，且所指 addr_id 在目录中。"""
    if not overrides:
        return []
    out: list[GateViolation] = []
    ids = _all_ids(new)
    for entry in overrides.get("overrides", []):
        if not isinstance(entry, dict):
            out.append(GateViolation("override", "", "override 条目格式非法"))
            continue
        aid = entry.get("addr_id", "")
        for req in ("owner", "reason", "source"):
            if not entry.get(req):
                out.append(GateViolation("override", aid, f"override 缺 {req}"))
        if aid and aid not in ids:
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
    alias_policy: Any = None,
    acknowledgements: Any = None,
    overrides: dict[str, Any] | None = None,
) -> list[GateViolation]:
    """跑完全部门禁再汇总。空列表 = 可发布。

    参数
    ----
    new          待发布目录（dict，含 sheets / cells / version / registry_version）。
    previous     上一批次目录（dict），None 表示首个合规批次。
    report       本批次报告（dict），可 None；其中 open_problems 为本批次现算的问题清单（见模块文档）。
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
    violations += _gate_alias(new, alias_policy, report)
    violations += _gate_ack(new, report, acknowledgements, today=today)
    violations += _gate_verdict(new, sheet_verdicts)
    violations += _gate_override(new, overrides)
    return violations


def group_by_check(violations: Iterable[GateViolation]) -> dict[str, list[GateViolation]]:
    """按 check 分组（供打印 / 测试断言）。"""
    out: dict[str, list[GateViolation]] = {}
    for v in violations:
        out.setdefault(v.check, []).append(v)
    return out


__all__ = [
    "ACK_KINDS", "ALIAS_DISPOSITIONS", "OPEN_PROBLEM_KEYS", "GateViolation", "run_release_gates", "group_by_check",
]
