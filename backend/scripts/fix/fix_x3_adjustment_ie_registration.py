"""Catalog_Registrar —— X-3 调整分录 I/E 登记器（spec `x3-adjustment-entry-import-export`）。

形态对齐既有 `backend/scripts/fix/fix_acnr_catalog_ie_gap.py`：`--check` / `--dry-run` / `--apply`。
交付于任务 **8.3**（只读态：`--check` / `--dry-run`）；`--apply` 的施加属任务 **9.1**。

作业面 = L/M/N 三份 `partial: true` manifest 登记的 **16 张 X-3 调整分录汇总表**
（L 2 · M 10 · N 4）。这 16 张在 committed catalog 里**已有条目**且 `import_export`
均缺失（R5.2），故本脚本只就地填段、不新建条目。

## 六步（design §C4，R5.1~R5.8）

| Step | 做什么 | 判据形态 |
|---|---|---|
| 1 | **Preflight** | 行为判据：`IE_ADAPTER_REGISTRY[短前缀]` 存在 → 解析模块并**真 import** → `_endpoint_for` 三态**均非 None** → `sheet ∈ module.IE_SHEETS` |
| 2 | manifest 就位（幂等） | manifest 段与 Key_Ledger 派生值**逐字段相等**；不相等 / 未登记 ⇒ 拒绝 |
| 3 | committed catalog **外科补丁** | 16 个 `addr_id` 的 `import_export`；写盘前 round-trip 自检 + 差异集恰好等于目标集 |
| 4 | 可复现性自检 | `generate_catalog(offline=True, registry_version=现值)` 输出中这 16 条与补丁值逐字段相等 |
| 5 | `--check` 退出码 | **0 收口 / 2 未收口**（含一切拒绝态） |
| 6 | 二次执行零变更 | 无待补项 ⇒ 一个字节都不写（两文件 md5 不变） |

## 🔴 三条禁区（写进代码，不只写进注释）

1. **绝不整体重生成 catalog**。跑一次 `generate_catalog` 会顺手杀掉 **38 条**已启用 I/E
   （H5/H7/I/L1/L3/L4/L5/N4 —— Deviation_Registry G2「无 manifest 兜底的启用条目」），
   它们会整批掉出 bulk 作业面。故：①本脚本从不调 `write_catalog`，只在 `json.loads`
   出来的 dict 上就地改 16 个 `addr_id`；②`_assert_surgical` 强制「差异集 == 目标集」
   且「补丁前后已启用集合只增这 16 条、一条不少」，出现第 17 个差异即拒绝写盘。
   Step 4 只把生成器输出当**参照物**读，从不把它当写入源。
2. **`--check` / `--dry-run` 零写盘**。全模块唯一写盘出口是 `_write_text(...)`；`run()` 里
   只有 `--apply` 一条分支把 `write=True` 传进 `patch_catalog`，其余模式根本不进那次调用
   （`--dry-run` 走**同一条**补丁与校验路径，只是不落地 ⇒ 台账与施加物同源）。
   `_write_text(..., allow=False)` 抛 `RegistrarRefusal` 是纵深防御，守卫可直接钉它。
3. **Preflight 失败 = 拒绝，不是警告**。任一门不过的 sheet **不进 plan**（拒绝写入），
   并按 R5.8 落进显式登记表 `PREFLIGHT_BLOCK_REGISTRY` + `Deviation_Registry` 侧车文件；
   `--apply` 在有任何被挡 sheet 时**整体不执行**（R5.1 是任务 9.1 的前置门控）。
   异常一律记 **ERROR 态**并判不过（R10.11 禁 fail-open：`except Exception: pass`
   会把「函数名写错 / 模块改名」吞成「本项目无此数据」）。

## 用法

    python backend/scripts/fix/fix_x3_adjustment_ie_registration.py --check
    python backend/scripts/fix/fix_x3_adjustment_ie_registration.py --dry-run
    python backend/scripts/fix/fix_x3_adjustment_ie_registration.py --apply   # 任务 9.1

Requirements: 5.1, 5.3, 5.4, 5.5, 5.6, 5.8
"""

from __future__ import annotations

import argparse
import importlib
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

import yaml

_BACKEND = Path(__file__).resolve().parents[2]
_REPO_ROOT = _BACKEND.parent
for _p in (str(_BACKEND), str(_BACKEND / "scripts" / "acnr")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

CATALOG = _BACKEND / "data" / "acnr" / "global_catalog.json"
SOURCES = _BACKEND / "data" / "acnr" / "sources"
LEDGER = _BACKEND / "data" / "adjustment_ie_contract.json"
SPEC_DIR = _REPO_ROOT / ".kiro" / "specs" / "x3-adjustment-entry-import-export"

#: Deviation_Registry 侧车（R5.8）。
#:
#: 🔴 为什么是侧车而不是直写 `evidence/deviation_registry.json`：那份是
#: `check_x3_deviation_registry.py --emit` 的产物，组集合 G1~G11 由该脚本
#: `_validate_structure` 闭集校验、每组带活探针与基线。第二个生产者直写它会
#: ①被结构校验判 `STRUCTURE_ERROR`，②与并发会话互相回退。故本脚本产出**可合并的
#: 同形记录**（三列 + `na_reasons`，R8.4），由后续任务并入正表。
DEVIATION_SIDECAR = SPEC_DIR / "evidence" / "registrar_preflight_deviations.json"

#: 三态端点后缀（与 `_kfgh_cycle_adapters._SUFFIX_*` 同值；此处只作 Preflight 探测用）
THREE_STATE: tuple[str, ...] = ("export-template", "export-data", "import-data")

#: Key_Ledger（`adjustment_ie_contract.json`）能派生的字段（R5.3）。
#:   api_prefix    ← sheets[<code>].cycle 小写
#:   item_id       ← sheets[<code>].item_id
#:   storage_field ← sheets[<code>].storage_field
LEDGER_DERIVED_FIELDS: tuple[str, ...] = ("api_prefix", "item_id", "storage_field")

#: manifest 侧约定字段 —— Key_Ledger **没有**这两个字段，凭空从"契约"里取会造值。
#: 取值与理由的真源 = 三份 manifest 的 `notes.import_order_rationale` /
#: `notes.depends_on_sheets_empty_rationale`（任务 8.1 交付）；本脚本要求那两条
#: notes 键在位（见 `_manifest_conventions_declared`），使「值」与「为什么是这个值」
#: 不会分家。
MANIFEST_CONVENTION: dict[str, Any] = {"import_order": 20, "depends_on_sheets": []}

#: 这两条 notes 键必须在每份 partial manifest 里在位（约定与理由锁死）。
_REQUIRED_NOTE_KEYS: tuple[str, ...] = (
    "import_order_rationale",
    "depends_on_sheets_empty_rationale",
)

#: 目标条目数防呆锚点（design §C4 / R5.2 的「16 张」）。
#: 不是写死的作业面：作业面由 `partial: true` manifest 实读得出，本常量只用来在
#: 两侧（manifest 实读集 / Key_Ledger 的 L/M/N X-3 集）都算出别的数时**拒绝**，
#: 避免有人往 manifest 里多塞一条就被静默补进 catalog。
EXPECTED_TARGET_COUNT = 16

#: 目标 sheet 的 catalog 类别（16 张全是调整分录汇总表）。
ADJ_CLASS_CODE = "F-调整分录"

#: **显式登记表（R5.8）**：Preflight 挡下的 sheet → 理由。
#:
#: 🔴 当前**空**不是遗漏 —— 任务 8.3 实测 Preflight **16/16 通过**（4 门 × 16 张全过，
#: 48 个端点均非 None）。留空 + `_unregistered_blocks()` 的完整性校验构成一条断言：
#: 一旦将来有 sheet 被挡下而没人给理由，`--check` 直接 exit 2 并点名，不许静默跳过。
PREFLIGHT_BLOCK_REGISTRY: dict[str, str] = {}


class RegistrarRefusal(RuntimeError):
    """拒绝态（与"警告"相对）：调用方必须以非零退出码结束，不得继续写盘。"""


# ---------------------------------------------------------------------------
# 唯一写盘出口（禁区 2）
# ---------------------------------------------------------------------------


def _write_text(path: Path, text: str, *, allow: bool) -> None:
    """全模块唯一写盘出口。`allow` 为假 ⇒ 拒绝（`--check` / `--dry-run` 零写盘）。"""
    if not allow:
        raise RegistrarRefusal(
            f"拒绝写盘：{path} —— 只有 --apply 允许写盘（--check / --dry-run 零写盘）"
        )
    path.write_text(text, encoding="utf-8")


# ---------------------------------------------------------------------------
# Step 1 —— Preflight（行为判据）
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Gate:
    """一道 Preflight 门的结果。

    `state` 三态：`pass` / `fail` / `error`。`error` = 判据执行本身抛异常
    （R10.11：不吞成 warning，也不当 pass）。`skipped` 门记为 `fail`，理由写
    "前置门未过" —— 前置门没过时后续门无从判定，绝不记 pass。
    """

    name: str
    state: str
    detail: str

    @property
    def ok(self) -> bool:
        return self.state == "pass"


@dataclass(frozen=True)
class SheetPreflight:
    sheet_code: str
    api_prefix: str
    module_path: str | None
    gates: tuple[Gate, ...]

    @property
    def ok(self) -> bool:
        return all(g.ok for g in self.gates)

    @property
    def failures(self) -> tuple[Gate, ...]:
        return tuple(g for g in self.gates if not g.ok)

    @property
    def reason(self) -> str:
        return "; ".join(f"{g.name}={g.state}({g.detail})" for g in self.failures)


def _gate(name: str, probe: Callable[[], tuple[bool, str]]) -> Gate:
    """真跑一次判据；异常 ⇒ `error` 态（禁 fail-open）。"""
    try:
        ok, detail = probe()
    except Exception as exc:  # noqa: BLE001 —— 故意兜住并升级为 error 态，不吞
        return Gate(name, "error", f"{type(exc).__name__}: {exc}")
    return Gate(name, "pass" if ok else "fail", detail)


def _adapter_registry() -> dict[str, Any]:
    """真实注册后的 `IE_ADAPTER_REGISTRY`。

    D 循环需显式调 `register_d_cycle_adapters()`；K/F/G/H 族在模块导入时自注册。
    🔴 这里**不写** `except Exception: pass`（参照脚本那样写会把"注册函数改名/抛错"
    吞成"该前缀没适配器"，方向恰好相反于事实）—— 异常直接上抛，由 `_gate` 记 error。
    """
    from app.services.bulk_tab import _d_cycle_adapters, _kfgh_cycle_adapters
    from app.services.bulk_tab.single_tab_adapter import IE_ADAPTER_REGISTRY

    _d_cycle_adapters.register_d_cycle_adapters()
    _kfgh_cycle_adapters.register_kfgh_cycle_adapters()
    return IE_ADAPTER_REGISTRY


def preflight(targets: Iterable[Target]) -> list[SheetPreflight]:
    """Step 1：逐 sheet 跑四道行为门（真 import、真取端点、真查白名单）。"""
    from app.services.bulk_tab import _kfgh_cycle_adapters as kfgh

    registry = _adapter_registry()
    results: list[SheetPreflight] = []

    for t in targets:
        prefix = t.api_prefix
        gates: list[Gate] = []

        g1 = _gate(
            "adapter_registered",
            lambda: (
                prefix in registry,
                f"IE_ADAPTER_REGISTRY['{prefix}']"
                + (" 在位" if prefix in registry else " 缺失 ⇒ bulk 会标 skip_reason=no_adapter"),
            ),
        )
        gates.append(g1)

        module: Any = None
        module_path: str | None = None
        if not g1.ok:
            gates.append(Gate("module_resolved", "fail", "前置门未过（adapter_registered）"))
        else:

            def _resolve() -> tuple[bool, str]:
                nonlocal module, module_path
                raw = kfgh._PREFIX_TO_MODULE.get(prefix)
                if not raw:
                    return False, f"_PREFIX_TO_MODULE 无 '{prefix}'，模块不可解析"
                module_path = kfgh._resolve_module_path(raw)
                module = importlib.import_module(module_path)
                return True, module_path

            gates.append(_gate("module_resolved", _resolve))

        if module is None:
            gates.append(Gate("three_state_endpoints", "fail", "前置门未过（module_resolved）"))
            gates.append(Gate("sheet_in_ie_sheets", "fail", "前置门未过（module_resolved）"))
        else:

            def _three() -> tuple[bool, str]:
                found = {s: kfgh._endpoint_for(module, prefix, s) for s in THREE_STATE}
                missing = sorted(s for s, fn in found.items() if fn is None)
                if missing:
                    return False, f"缺端点 {missing}（三态必须均非 None）"
                names = ", ".join(
                    f"{s}→{getattr(found[s], '__qualname__', found[s])}" for s in THREE_STATE
                )
                return True, names

            def _whitelist() -> tuple[bool, str]:
                declared = getattr(module, "IE_SHEETS", None)
                if declared is None:
                    return False, f"{module_path} 未声明 IE_SHEETS"
                if not isinstance(declared, (set, frozenset)):
                    return False, (
                        f"IE_SHEETS 类型 {type(declared).__name__}，期望 set/frozenset"
                    )
                if t.sheet_code not in declared:
                    return False, (
                        f"IE_SHEETS 缺 {t.sheet_code}，现值 {sorted(declared)}"
                        " ⇒ 形态 A 端点收到该 sheet 会走 400 分支"
                    )
                return True, f"{t.sheet_code} ∈ IE_SHEETS({len(declared)} 项)"

            gates.append(_gate("three_state_endpoints", _three))
            gates.append(_gate("sheet_in_ie_sheets", _whitelist))

        results.append(SheetPreflight(t.sheet_code, prefix, module_path, tuple(gates)))

    return results


# ---------------------------------------------------------------------------
# 作业面（目标集）—— 由 `partial: true` manifest 实读 + Key_Ledger 双向锁死
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Target:
    cycle: str
    sheet_code: str
    api_prefix: str
    manifest_file: str
    manifest_segment: dict[str, Any]
    expected_segment: dict[str, Any]

    @property
    def manifest_matches_ledger(self) -> bool:
        return self.manifest_segment == self.expected_segment


def _ledger_x3() -> dict[str, dict[str, Any]]:
    """Key_Ledger 的 X-3 条目 → 派生段（真源，R5.3）。"""
    doc = json.loads(LEDGER.read_text(encoding="utf-8"))
    out: dict[str, dict[str, Any]] = {}
    for code, entry in (doc.get("sheets") or {}).items():
        cycle = str(entry.get("cycle") or "")
        out[code] = {
            "enabled": True,
            "api_prefix": cycle.lower(),
            "item_id": entry.get("item_id"),
            "storage_field": entry.get("storage_field"),
            **MANIFEST_CONVENTION,
        }
    return out


def _partial_manifests(sources_dir: Path) -> dict[str, dict[str, Any]]:
    """实读 `partial: true` 的 manifest（作业面真源，不写死 l/m/n）。"""
    out: dict[str, dict[str, Any]] = {}
    for path in sorted(sources_dir.glob("*_cycle_ie_manifest.yaml")):
        doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if doc.get("partial") is True:
            out[path.name] = doc
    return out


def _manifest_conventions_declared(doc: dict[str, Any]) -> list[str]:
    notes = doc.get("notes") or {}
    return [k for k in _REQUIRED_NOTE_KEYS if not str(notes.get(k) or "").strip()]


def build_targets(*, sources_dir: Path | None = None) -> tuple[list[Target], list[str]]:
    """Step 2 的输入：目标集 + 结构性拒绝理由。

    双向锁死：manifest 实读集 与 Key_Ledger 的 L/M/N X-3 集必须**互为子集**；
    条目数两侧都必须 == `EXPECTED_TARGET_COUNT`。任一不成立 ⇒ 拒绝（不猜、不放宽）。
    """
    src = sources_dir or SOURCES
    refusals: list[str] = []
    ledger = _ledger_x3()
    docs = _partial_manifests(src)

    targets: list[Target] = []
    for name, doc in docs.items():
        cycle = str(doc.get("cycle") or "")
        for missing in _manifest_conventions_declared(doc):
            refusals.append(
                f"{name}: notes.{missing} 缺失 —— import_order / depends_on_sheets"
                f" 的取值与理由必须同在（Key_Ledger 无这两个字段）"
            )
        for raw in doc.get("entries") or []:
            code = str(raw.get("sheet_code") or "")
            if not code:
                refusals.append(f"{name}: 存在无 sheet_code 的条目")
                continue
            seg = {
                "enabled": True,
                "api_prefix": raw.get("api_prefix"),
                "item_id": raw.get("item_id"),
                "storage_field": raw.get("storage_field"),
                "import_order": raw.get("import_order"),
                "depends_on_sheets": raw.get("depends_on_sheets") or [],
            }
            expected = ledger.get(code)
            if expected is None:
                refusals.append(
                    f"{name}: '{code}' 不在 Key_Ledger（adjustment_ie_contract.json）"
                    f" ⇒ 取值不可确证，拒绝登记"
                )
                continue
            targets.append(
                Target(
                    cycle=cycle,
                    sheet_code=code,
                    api_prefix=str(seg["api_prefix"] or ""),
                    manifest_file=name,
                    manifest_segment=seg,
                    expected_segment=dict(expected),
                )
            )

    partial_cycle_initials = {str(d.get("cycle") or "")[:1].upper() for d in docs.values()}
    ledger_side = {
        code
        for code, seg in ledger.items()
        if code.endswith("-3")
        and str(seg["api_prefix"])[:1].upper() in partial_cycle_initials
    }
    manifest_side = {t.sheet_code for t in targets}
    if manifest_side != ledger_side:
        refusals.append(
            "manifest 实读集与 Key_Ledger 派生集不一致 —— "
            f"manifest-only={sorted(manifest_side - ledger_side)}, "
            f"ledger-only={sorted(ledger_side - manifest_side)}"
        )
    for side, label in ((manifest_side, "manifest 实读集"), (ledger_side, "Key_Ledger 派生集")):
        if len(side) != EXPECTED_TARGET_COUNT:
            refusals.append(
                f"{label}条目数 {len(side)} != 防呆锚点 {EXPECTED_TARGET_COUNT}"
                f"（design §C4 / R5.2 的「16 张」）⇒ 拒绝，先核对作业面再登记"
            )

    for t in targets:
        if not t.manifest_matches_ledger:
            diff = {
                k: (t.manifest_segment.get(k), t.expected_segment.get(k))
                for k in sorted(set(t.manifest_segment) | set(t.expected_segment))
                if t.manifest_segment.get(k) != t.expected_segment.get(k)
            }
            refusals.append(
                f"{t.manifest_file}: '{t.sheet_code}' manifest 段与 Key_Ledger 派生值不一致"
                f"（字段: manifest / ledger）{diff}"
            )

    return sorted(targets, key=lambda x: (x.cycle, x.sheet_code)), refusals


# ---------------------------------------------------------------------------
# Step 3 —— committed catalog 外科补丁
# ---------------------------------------------------------------------------


@dataclass
class Plan:
    targets: list[Target] = field(default_factory=list)
    preflight: list[SheetPreflight] = field(default_factory=list)
    refusals: list[str] = field(default_factory=list)
    #: 已收口（catalog 现值已等于目标段）
    already: list[str] = field(default_factory=list)
    #: 待补（catalog 无 import_export）
    pending: list[Target] = field(default_factory=list)
    #: 被 Preflight 挡下
    blocked: list[SheetPreflight] = field(default_factory=list)
    registry_version: str = ""

    @property
    def closed(self) -> bool:
        return not self.refusals and not self.blocked and not self.pending


def _catalog_index(data: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    idx: dict[str, list[dict[str, Any]]] = {}
    for sheet in data.get("sheets", []):
        idx.setdefault(str(sheet.get("sheet_code") or ""), []).append(sheet)
    return idx


def build_plan(
    *,
    catalog_path: Path | None = None,
    sources_dir: Path | None = None,
) -> tuple[Plan, dict[str, Any], str]:
    """Step 1~3 的规划（不写盘）。返回 `(plan, catalog_data, catalog_raw)`。"""
    cat_path = catalog_path or CATALOG
    raw = cat_path.read_text(encoding="utf-8")
    data = json.loads(raw)

    targets, refusals = build_targets(sources_dir=sources_dir)
    plan = Plan(targets=targets, refusals=refusals, registry_version=str(data.get("registry_version") or ""))
    plan.preflight = preflight(targets)
    plan.blocked = [p for p in plan.preflight if not p.ok]
    blocked_codes = {p.sheet_code for p in plan.blocked}

    idx = _catalog_index(data)
    for t in targets:
        if t.sheet_code in blocked_codes:
            continue  # 🔴 拒绝写入该 sheet（不是警告）—— 不进 plan
        hits = idx.get(t.sheet_code) or []
        if len(hits) != 1:
            plan.refusals.append(
                f"catalog 中 '{t.sheet_code}' 有 {len(hits)} 个条目（期望恰 1）"
                f" ⇒ 拒绝（R5.2 只填既有条目，不新建、不猜哪一条）"
            )
            continue
        sheet = hits[0]
        if str(sheet.get("cycle") or "") != t.cycle:
            plan.refusals.append(
                f"catalog '{t.sheet_code}'.cycle={sheet.get('cycle')!r} != manifest cycle {t.cycle!r}"
            )
            continue
        if str(sheet.get("class_code") or "") != ADJ_CLASS_CODE:
            plan.refusals.append(
                f"catalog '{t.sheet_code}'.class_code={sheet.get('class_code')!r}"
                f" != {ADJ_CLASS_CODE!r} ⇒ 非调整分录汇总表，拒绝"
            )
            continue
        current = sheet.get("import_export")
        if current == t.expected_segment:
            plan.already.append(t.sheet_code)
        elif current in (None, {}):
            plan.pending.append(t)
        else:
            plan.refusals.append(
                f"catalog '{t.sheet_code}'.import_export 已有值且与目标段不同 ⇒ 拒绝覆盖"
                f"（现值 {current!r}）"
            )

    return plan, data, raw


def _addr_of(data: dict[str, Any], sheet_code: str) -> str:
    for sheet in data.get("sheets", []):
        if str(sheet.get("sheet_code") or "") == sheet_code:
            return str(sheet.get("addr_id") or "")
    return ""


def _enabled_addr_ids(data: dict[str, Any]) -> set[str]:
    return {
        str(s.get("addr_id") or "")
        for s in data.get("sheets", [])
        if (s.get("import_export") or {}).get("enabled")
    }


def _structural_diff(before: dict[str, Any], after: dict[str, Any]) -> dict[str, list[str]]:
    """逐 `addr_id` 结构化差异（禁区 1 的判据载体）。"""
    out: dict[str, list[str]] = {}
    b_top = {k: v for k, v in before.items() if k not in ("sheets", "cells")}
    a_top = {k: v for k, v in after.items() if k not in ("sheets", "cells")}
    if b_top != a_top:
        out["<top-level>"] = sorted(
            k for k in set(b_top) | set(a_top) if b_top.get(k) != a_top.get(k)
        )
    if before.get("cells") != after.get("cells"):
        out["<cells>"] = ["cells 整段被改动"]

    b_sheets = {str(s.get("addr_id") or ""): s for s in before.get("sheets", [])}
    a_sheets = {str(s.get("addr_id") or ""): s for s in after.get("sheets", [])}
    for addr in sorted(set(b_sheets) ^ set(a_sheets)):
        out[addr] = ["<条目新增/删除>"]
    for addr in sorted(set(b_sheets) & set(a_sheets)):
        b, a = b_sheets[addr], a_sheets[addr]
        if b == a:
            continue
        out[addr] = sorted(k for k in set(b) | set(a) if b.get(k) != a.get(k))
    return out


def _assert_surgical(
    before: dict[str, Any],
    after: dict[str, Any],
    target_addrs: set[str],
) -> dict[str, list[str]]:
    """禁区 1 的硬判据：差异集 == 目标集，且每处只动 `import_export`。

    额外钉住「已启用集合只增这些、一条不少」—— 整体重生成会让 38 条已启用条目
    （Deviation_Registry G2）掉出集合，这条断言使那种写法无法通过。
    """
    diff = _structural_diff(before, after)
    extra = sorted(set(diff) - target_addrs)
    if extra:
        raise RegistrarRefusal(
            f"差异集含非目标 addr_id {extra} ⇒ 拒绝写盘"
            "（禁区：绝不整体重生成 catalog —— 会杀掉 38 条已启用 I/E）"
        )
    for addr, keys in diff.items():
        if keys != ["import_export"]:
            raise RegistrarRefusal(
                f"{addr} 被改动的键 {keys} != ['import_export'] ⇒ 拒绝写盘"
            )
    lost = _enabled_addr_ids(before) - _enabled_addr_ids(after)
    if lost:
        raise RegistrarRefusal(
            f"补丁后 {len(lost)} 条已启用 I/E 掉出集合（如 {sorted(lost)[:5]}）⇒ 拒绝写盘"
        )
    gained = _enabled_addr_ids(after) - _enabled_addr_ids(before)
    if not gained <= target_addrs:
        raise RegistrarRefusal(
            f"补丁后新增的已启用条目 {sorted(gained - target_addrs)} 不在目标集内 ⇒ 拒绝写盘"
        )
    return diff


def _deterministic(data: dict[str, Any]) -> str:
    """复用生成器的确定性序列化，保证格式不可能与 committed 文件漂移。"""
    from generate_catalog import _deterministic_json

    return _deterministic_json(data)


def patch_catalog(
    data: dict[str, Any],
    raw: str,
    plan: Plan,
    *,
    write: bool,
    catalog_path: Path | None = None,
) -> dict[str, list[str]]:
    """Step 3：round-trip 自检 → 就地补丁 → 差异集校验 → （仅 `write=True`）写盘。

    `write` 只在 `--apply` 为真（`run()` 里一行决定）；`--dry-run` 走同一条补丁与
    校验路径、只是不落地 ⇒ 台账与施加物同源，不会出现"dry-run 说的和 apply 做的不同"。
    """
    cat_path = catalog_path or CATALOG

    # round-trip 自检（R5.5）：json.loads(原文) 重序列化后必须与磁盘逐字节相同
    round_trip = _deterministic(data)
    if round_trip != raw:
        raise RegistrarRefusal(
            "round-trip 不一致，拒绝写盘（防重排整个文件与并发会话互相回退）"
            f"—— 重序列化 {len(round_trip)} B vs 磁盘 {len(raw)} B"
        )

    before = json.loads(raw)
    target_addrs = {_addr_of(data, t.sheet_code) for t in plan.pending}
    if "" in target_addrs:
        raise RegistrarRefusal("目标 sheet 在 catalog 无 addr_id ⇒ 拒绝写盘")

    idx = _catalog_index(data)
    for t in plan.pending:
        idx[t.sheet_code][0]["import_export"] = dict(t.expected_segment)

    diff = _assert_surgical(before, data, target_addrs)
    text = _deterministic(data)
    if write and plan.pending:
        _write_text(cat_path, text, allow=True)
    return diff


# ---------------------------------------------------------------------------
# Step 4 —— 可复现性自检
# ---------------------------------------------------------------------------


def reproducibility(plan: Plan) -> list[str]:
    """Step 4：`generate_catalog(offline=True, 同版本号)` 的这些条目与补丁值逐字段相等。

    只读参照物：本函数**从不**把生成器输出写入磁盘（那会杀掉 38 条已启用 I/E）。
    """
    from generate_catalog import generate_catalog

    problems: list[str] = []
    fresh, _report, _blocked = generate_catalog(
        offline=True, registry_version=plan.registry_version
    )
    fresh_by_code = {str(s.get("sheet_code") or ""): s for s in fresh.get("sheets", [])}
    for t in plan.targets:
        sheet = fresh_by_code.get(t.sheet_code)
        if sheet is None:
            problems.append(f"{t.sheet_code}: 生成器输出中无该 sheet")
            continue
        got = sheet.get("import_export")
        if got is None:
            problems.append(f"{t.sheet_code}: 生成器输出无 import_export 段（manifest 未被吃进）")
            continue
        for key in sorted(set(t.expected_segment) | set(got)):
            if got.get(key) != t.expected_segment.get(key):
                problems.append(
                    f"{t.sheet_code}.{key}: 生成器={got.get(key)!r} != 补丁值="
                    f"{t.expected_segment.get(key)!r}"
                )
    return problems


# ---------------------------------------------------------------------------
# R5.8 —— 显式登记表 + Deviation_Registry 侧车
# ---------------------------------------------------------------------------


def _unregistered_blocks(plan: Plan) -> list[str]:
    return sorted(p.sheet_code for p in plan.blocked if p.sheet_code not in PREFLIGHT_BLOCK_REGISTRY)


def deviation_records(plan: Plan) -> list[dict[str, Any]]:
    """把被挡下的 sheet 转成可并入 Deviation_Registry 的同形记录（三列 + na_reasons）。"""
    by_code = {t.sheet_code: t for t in plan.targets}
    out: list[dict[str, Any]] = []
    for p in plan.blocked:
        t = by_code.get(p.sheet_code)
        out.append(
            {
                "group": "REGISTRAR_PREFLIGHT",
                "key": p.sheet_code,
                "sheet_code": p.sheet_code,
                "catalog_value": None,
                "contract_value": (t.expected_segment.get("item_id") if t else None),
                "frontend_observed": None,
                "na_reasons": {
                    "catalog_value": "本条被 Preflight 拒绝登记 ⇒ catalog 侧无值（这正是本记录的事实）",
                    "frontend_observed": "Preflight 只判后端适配器/端点/白名单三态，不观察前端",
                },
                "verdict": "real_drift",
                "method_ref": "8.3.Step1",
                "evidence": {
                    "api_prefix": p.api_prefix,
                    "module_path": p.module_path,
                    "gates": [
                        {"name": g.name, "state": g.state, "detail": g.detail} for g in p.gates
                    ],
                    "reason": p.reason,
                    "registered_reason": PREFLIGHT_BLOCK_REGISTRY.get(p.sheet_code),
                    "refused_write": True,
                },
            }
        )
    return out


def write_deviation_sidecar(
    records: list[dict[str, Any]],
    *,
    allow_write: bool,
    path: Path | None = None,
) -> None:
    out = path or DEVIATION_SIDECAR
    doc = {
        "_meta": {
            "spec": "x3-adjustment-entry-import-export",
            "task": "8.3",
            "artifact": "Deviation_Registry（侧车 / 可合并记录）",
            "merge_target": "evidence/deviation_registry.json",
            "merge_note": (
                "正表由 check_x3_deviation_registry.py --emit 生成、组集合 G1~G11 闭集校验，"
                "第二个生产者直写会判 STRUCTURE_ERROR；故本文件产出同形记录待并入。"
            ),
            "generated_by": "python backend/scripts/fix/fix_x3_adjustment_ie_registration.py --apply",
            "written_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
            "record_count": len(records),
            "requirements": ["5.1", "5.8"],
        },
        "records": records,
    }
    _write_text(
        out, json.dumps(doc, ensure_ascii=False, indent=2, sort_keys=True) + "\n", allow=allow_write
    )


# ---------------------------------------------------------------------------
# 台账输出
# ---------------------------------------------------------------------------


def _print_preflight(plan: Plan, *, verbose: bool) -> None:
    passed = [p for p in plan.preflight if p.ok]
    print(
        f"[Step 1 Preflight] {len(passed)}/{len(plan.preflight)} 通过"
        f"（4 门 × {len(plan.preflight)} 张 = {4 * len(plan.preflight)} 次行为判定）"
    )
    if verbose:
        for p in plan.preflight:
            mark = "✓" if p.ok else "✗"
            print(f"  {mark} {p.sheet_code:6s} px={p.api_prefix:4s} mod={p.module_path}")
            for g in p.gates:
                print(f"      · {g.name}: {g.state} — {g.detail}")
    for p in plan.blocked:
        print(f"  ✗ {p.sheet_code}: 拒绝写入 —— {p.reason}")


def _print_manifest_state(plan: Plan) -> None:
    files = sorted({t.manifest_file for t in plan.targets})
    print(
        f"[Step 2 manifest] {len(plan.targets)} 条已登记于 {len(files)} 份 partial manifest"
        f"（{', '.join(files)}），逐字段 == Key_Ledger 派生值 ⇒ 无待写内容（幂等）"
    )


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------


def run(
    mode: str,
    *,
    catalog_path: Path | None = None,
    sources_dir: Path | None = None,
    deviation_path: Path | None = None,
    verbose: bool = False,
) -> int:
    """三态入口。返回退出码：0 收口 / 2 未收口（含一切拒绝态）。"""
    if mode not in ("check", "dry-run", "apply"):
        raise ValueError(f"未知模式 {mode!r}")
    allow_write = mode == "apply"

    try:
        plan, data, raw = build_plan(catalog_path=catalog_path, sources_dir=sources_dir)
    except RegistrarRefusal as exc:
        print(f"[FAIL] {exc}")
        return 2
    except (OSError, ValueError, yaml.YAMLError) as exc:
        # R10.11：取值层异常记 ERROR 态并判不过，绝不吞成"本项目无此数据"
        print(f"[ERROR] 规划阶段失败（{type(exc).__name__}）：{exc}")
        return 2

    _print_preflight(plan, verbose=verbose)

    unregistered = _unregistered_blocks(plan)
    if unregistered:
        plan.refusals.append(
            f"以下被 Preflight 挡下的 sheet 未在 PREFLIGHT_BLOCK_REGISTRY 登记理由"
            f"（R5.8 要求显式登记）: {unregistered}"
        )

    if plan.blocked:
        records = deviation_records(plan)
        print(f"[R5.8] {len(records)} 条拒绝记录 → Deviation_Registry 侧车")
        if allow_write:
            write_deviation_sidecar(records, allow_write=True, path=deviation_path)
            print(f"  已写 {(deviation_path or DEVIATION_SIDECAR)}")
        else:
            for r in records:
                print(f"  · {r['sheet_code']}: {r['evidence']['reason']}")

    if plan.refusals:
        print(f"[FAIL] {len(plan.refusals)} 条结构性拒绝：")
        for r in plan.refusals:
            print(f"  ✗ {r}")
        return 2

    _print_manifest_state(plan)

    print(
        f"[Step 3 台账] 待补 {len(plan.pending)} / 已收口 {len(plan.already)}"
        f" / 被挡 {len(plan.blocked)}（目标 {len(plan.targets)}）"
    )
    for t in plan.pending:
        addr = _addr_of(data, t.sheet_code)
        print(
            f"  + {addr:12s} import_export = api_prefix={t.expected_segment['api_prefix']}"
            f" item_id={t.expected_segment['item_id']}"
            f" storage_field={t.expected_segment['storage_field']}"
            f" import_order={t.expected_segment['import_order']}"
        )

    try:
        repro = reproducibility(plan)
    except (OSError, ValueError, ImportError) as exc:
        print(f"[ERROR] Step 4 可复现性自检执行失败（{type(exc).__name__}）：{exc}")
        return 2
    if repro:
        print(f"[FAIL] Step 4 可复现性自检 {len(repro)} 处不等：")
        for r in repro:
            print(f"  ✗ {r}")
        return 2
    print(
        f"[Step 4 可复现性] generate_catalog(offline=True,"
        f" registry_version={plan.registry_version}) 的 {len(plan.targets)} 条"
        f" import_export 与补丁值逐字段相等"
    )

    if plan.blocked:
        # R5.1 是任务 9.1 的前置门控：有任何一张被挡 ⇒ 整体不施加
        print("[FAIL] Preflight 未 16/16 通过 ⇒ 不施加（R5.1 先适配器、再 catalog）")
        return 2

    if mode == "check":
        if plan.pending:
            print(f"[FAIL] {len(plan.pending)} 张未在 committed catalog 启用 I/E ⇒ 未收口，请跑 --apply")
            return 2
        print("[OK] 16/16 已收口：catalog 的 import_export 段与 manifest / Key_Ledger 一致")
        return 0

    if mode == "dry-run":
        try:
            diff = patch_catalog(
                json.loads(raw), raw, plan, write=False, catalog_path=catalog_path
            )
        except RegistrarRefusal as exc:
            print(f"[FAIL] {exc}")
            return 2
        print(
            f"[DRY-RUN] 差异集 {len(diff)} 个 addr_id，均只改 import_export："
            f"{sorted(diff)}"
        )
        print("[DRY-RUN] 未写盘（零字节写入）")
        return 0

    # --apply（任务 9.1）
    if not plan.pending:
        print("[OK] 无待补项 ⇒ 一个字节都不写（幂等，R5.4）")
        return 0
    try:
        diff = patch_catalog(data, raw, plan, write=True, catalog_path=catalog_path)
    except RegistrarRefusal as exc:
        print(f"[FAIL] {exc}")
        return 2
    print(f"[APPLIED] {len(diff)} 个 addr_id 的 import_export 段：{sorted(diff)}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Catalog_Registrar — X-3 I/E 登记器")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--check", action="store_true", help="以退出码表达收口（0 收口 / 2 未收口）")
    g.add_argument("--dry-run", action="store_true", help="全量台账，零写盘")
    g.add_argument("--apply", action="store_true", help="施加（任务 9.1）")
    ap.add_argument("--verbose", action="store_true", help="逐门打印 Preflight 明细")
    args = ap.parse_args(argv)

    mode = "check" if args.check else ("dry-run" if args.dry_run else "apply")
    return run(mode, verbose=args.verbose)


if __name__ == "__main__":
    raise SystemExit(main())
