"""ACNR 发布候选构建（design §5.3 / §6.3，T07）——纯计算，不写任何文件。

生成器 `backend/scripts/acnr/generate_catalog.py` 是唯一写出方；本模块只负责：

1. 定位上一发布批次（`locate_previous`）：报告有 release 段时取 `release.registry_version`（写出新批次）或
   `release.previous_version`（`--check` 以已提交版本重算）对应的快照，并校验快照 LF 内容 sha256 等于报告记录值；
   报告无 release 段（首个合规批次之前的旧报告）时取报告 `registry_version` 的快照，须在
   `release_exceptions.json` 登记其内容 sha256，否则拒绝（不取工作区目录作沿用来源，R2-F11）。
2. `inputs_fingerprint`：全部输入文件按仓库相对路径排序的 (路径, LF 内容 sha256)，再取 sha256；含上一批次快照。
3. `build_release`：在基础产物（`generate_catalog()`：classification 骨架 + I/E manifest + 渲染注册 + 标签别名 + 坐标种子
   + overrides）之上叠加 sheet_verdicts（补登 5 张父 sheet、K14~K18 停用）、平台底稿名与禁止别名、标签源别名处置
   （`sources/alias_policy.json`，T09）、上一批次别名沿用、cell_verdicts（孤儿 25 / 超范围 14 停用、范围内 33 语义待核对）、
   cell 名称规则，再跑发布门禁，产出带 open_problems、release 段与四组分组（`catalog_report_buckets`）的报告；
   open_problems.ccr_unresolved 按新目录经 `ccr_sources` 现算（T22，与 CI 检查器 `check_ccr_resolve` 同一函数）。

只依赖标准库与本包。
"""
from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Callable

from . import catalog_contract, catalog_names, catalog_release, catalog_report_buckets, ccr_sources
from .catalog_integrity import content_sha256
from .loaders.from_classification import SheetCatalogEntry, load_sheet_skeletons_from_classification
from .loaders.from_sheet_verdicts import load_sheet_verdicts

SNAPSHOT_SUBDIR = "catalog_snapshots"
REPORT_NAME = "catalog_report.json"
RELEASE_EXCEPTIONS_NAME = "release_exceptions.json"
OVERRIDES_NAME = "global_catalog.overrides.json"


class ReleaseInputError(ValueError):
    """发布输入不成立（上一批次快照缺失 / 哈希不符 / 未登记的旧报告等），生成器据此失败、不写文件。"""


def deterministic_json(data: Any) -> str:
    """确定性 JSON（sort_keys、indent=2、保留中文、尾换行）——目录、报告、快照共用的唯一口径。"""
    return json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def sheet_dict(entry: SheetCatalogEntry) -> dict[str, Any]:
    """SheetCatalogEntry → 目录 dict（省略 None / 空列表 / 非身份字段的空串；生成器 `_sheet_to_dict` 委托此处）。"""
    out: dict[str, Any] = {}
    for key, value in sorted(asdict(entry).items()):
        if value is None or (isinstance(value, list) and not value):
            continue
        if isinstance(value, str) and not value and key not in ("addr_id", "domain", "sheet_code", "sheet_name"):
            continue
        out[key] = value
    return out


# ─── 上一发布批次 ─────────────────────────────────────────────────────────────


@dataclass
class PreviousBatch:
    version: str
    content_sha256: str
    catalog: dict[str, Any]
    snapshot_path: Path
    basis: str  # release | release_exception


def load_release_exceptions(acnr_dir: Path) -> dict[str, Any]:
    p = acnr_dir / RELEASE_EXCEPTIONS_NAME
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"exceptions": []}


def _exception_for(release_exceptions: dict[str, Any], version: str) -> dict[str, Any] | None:
    for e in release_exceptions.get("exceptions", []) or []:
        if isinstance(e, dict) and e.get("registry_version") == version:
            return e
    return None


def locate_previous(report: dict[str, Any] | None, acnr_dir: Path, *, for_check: bool) -> PreviousBatch | None:
    """按报告定位上一发布批次快照并校验内容哈希（见模块文档第 1 条）。"""
    if not isinstance(report, dict):
        return None
    release = report.get("release")
    if isinstance(release, dict):
        if for_check:
            version, expected, basis = release.get("previous_version"), release.get("previous_catalog_sha256"), "release"
        else:
            version, expected, basis = release.get("registry_version"), release.get("catalog_sha256"), "release"
        if not version:
            return None
    else:
        version = report.get("registry_version")
        if not version:
            return None
        exc = _exception_for(load_release_exceptions(acnr_dir), version)
        if exc is None:
            raise ReleaseInputError(f"报告无 release 段，且 {RELEASE_EXCEPTIONS_NAME} 未登记版本 {version} 的快照哈希，无法确定上一批次")
        expected, basis = exc.get("snapshot_content_sha256"), "release_exception"
    path = acnr_dir / SNAPSHOT_SUBDIR / f"{version}.json"
    if not path.exists():
        raise ReleaseInputError(f"上一批次快照不存在：{path.name}")
    raw = path.read_bytes()
    actual = content_sha256(raw)
    if not expected or actual != expected:
        raise ReleaseInputError(f"上一批次快照 {path.name} 内容 sha256={actual[:16]}… 与记录 {str(expected)[:16]}… 不符")
    return PreviousBatch(version, actual, json.loads(raw.decode("utf-8")), path, basis)


# ─── 输入指纹 ────────────────────────────────────────────────────────────────


def input_files(backend_root: Path, previous: PreviousBatch | None) -> list[tuple[str, Path]]:
    """全部生成输入 (仓库相对路径, 文件)；存在的才计入，目录、报告与 schema 是产物不计入。
    上一批次快照记规范相对路径 `backend/data/acnr/catalog_snapshots/{版本}.json`（与实际读取位置无关）。"""
    repo = backend_root.parent.resolve()
    data = backend_root / "data"
    acnr = data / "acnr"
    sources = acnr / "sources"
    labels = backend_root.parent / "audit-platform" / "frontend" / "src" / "components" / "workpaper" / "composables"
    files = [sources / "classification_cache.json", data / "workpaper_render_registry.json", data / "wp_account_mapping.json",
             acnr / "sheet_display_names.json", sources / "sheet_verdicts.json", sources / "alias_policy.json",
             sources / "acknowledgements.json", acnr / OVERRIDES_NAME, acnr / RELEASE_EXCEPTIONS_NAME,
             data / "cross_wp_references.json"]
    files += sorted(sources.glob("*_cycle_ie_manifest.yaml"))
    files += sorted(p for p in data.glob("*_address_registry_seed.json"))
    files += sorted(labels.glob("*SheetLabels.ts")) if labels.exists() else []
    out = [(p.resolve().relative_to(repo).as_posix(), p) for p in files if p.exists()]
    if previous is not None:
        out.append((f"backend/data/acnr/{SNAPSHOT_SUBDIR}/{previous.snapshot_path.name}", previous.snapshot_path))
    return out


def inputs_fingerprint(pairs: list[tuple[str, Path]]) -> tuple[str, list[dict[str, str]]]:
    rows = sorted(({"path": rel, "sha256": content_sha256(p.read_bytes())} for rel, p in pairs), key=lambda r: r["path"])
    h = hashlib.sha256("".join(f"{r['path']}\0{r['sha256']}\n" for r in rows).encode("utf-8")).hexdigest()
    return h, rows


# ─── 构建 ────────────────────────────────────────────────────────────────────


@dataclass
class ReleaseCandidate:
    catalog: dict[str, Any]
    report: dict[str, Any]
    violations: list[catalog_release.GateViolation] = field(default_factory=list)
    inputs: list[dict[str, str]] = field(default_factory=list)


def _apply_sheet_verdicts(catalog: dict[str, Any], verdicts, *, registry_version: str,
                          render_types: dict[str, str], component_types: dict[str, str],
                          previous: PreviousBatch | None) -> None:
    by_id = {s["addr_id"]: s for s in catalog["sheets"]}
    prev_sheets = {s.get("addr_id"): s for s in (previous.catalog.get("sheets", []) if previous else [])}
    for v in verdicts.sheet_verdicts:
        if v.verdict not in ("add_platform_sheet", "deprecate") or v.addr_id in by_id:
            continue  # 已在骨架中：判定过期由门禁 verdict / 守卫报告，不覆盖骨架
        rec = {"wp_code": v.sheet_code, "sheet_name": v.sheet_name, "class_code": "", "functional_type": "", "template_version_id": ""}
        entry = load_sheet_skeletons_from_classification([rec], registry_version=registry_version, render_type_map=render_types)[0]
        entry.source_of_truth = "sheet_verdicts"
        entry.component_type = component_types.get(v.sheet_code, "")
        d = sheet_dict(entry)
        if d.get("addr_id") != v.addr_id:
            raise ReleaseInputError(f"sheet_verdicts {v.addr_id} 推导出的 addr_id 为 {d.get('addr_id')}")
        if v.verdict == "deprecate":
            d["deprecated"] = True
            d["replaced_by"] = v.replaced_by
            d["deprecated_at_version"] = (prev_sheets.get(v.addr_id) or {}).get("deprecated_at_version") or registry_version
        catalog["sheets"].append(d)
        by_id[v.addr_id] = d


def _carry_over_aliases(catalog: dict[str, Any], previous: PreviousBatch | None) -> dict[str, list[str]]:
    """上一批次快照中的别名在本次消失时保留（alias_policy 禁止的除外），别名只增不减（design §6.3）。"""
    if previous is None:
        return {}
    forbidden = (catalog.get("alias_policy") or {}).get("forbidden") or {}
    by_id = {s["addr_id"]: s for s in catalog["sheets"]}
    kept: dict[str, list[str]] = {}
    for ps in previous.catalog.get("sheets", []):
        cur = by_id.get(ps.get("addr_id"))
        if cur is None:
            continue
        banned = set((forbidden.get(cur.get("parent_wp_code", "")) or {}))
        have = list(cur.get("sheet_name_aliases") or [])
        add = [a for a in ps.get("sheet_name_aliases") or [] if a not in have and a not in banned]
        if add:
            cur["sheet_name_aliases"] = have + add
            kept[cur["addr_id"]] = add
    return kept


def _classification_meta(backend_root: Path) -> dict[str, Any]:
    p = backend_root / "data" / "acnr" / "sources" / "classification_cache.json"
    raw = p.read_bytes()
    records = json.loads(raw.decode("utf-8"))
    tv = sorted({str(r.get("template_version_id") or "") for r in records})
    return {"path": "backend/data/acnr/sources/classification_cache.json", "record_count": len(records),
            "template_version_id": tv, "sha256": content_sha256(raw)}


def _load_optional(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def _ccr_unresolved(catalog: dict[str, Any], backend_root: Path) -> list[str] | None:
    """按新目录现算不可解析的 CCR 源（T22，与 CI 检查器同一函数）；CCR 文件缺失或目录建不了索引返回 None
    （报告不给该清单，覆盖 ccr_ids 的豁免即按「无法核实」阻断）。"""
    ccr = _load_optional(backend_root / "data" / "cross_wp_references.json")
    index = catalog_release._try_index(catalog)
    if not isinstance(ccr, dict) or index is None:
        return None
    return ccr_sources.unresolved_source_ids(ccr.get("references") or [], index)


def build_release(
    *,
    registry_version: str,
    previous: PreviousBatch | None,
    backend_root: Path,
    generate_base: Callable[..., tuple[dict[str, Any], dict[str, Any], bool]],
    render_data: Any,
    today: date,
) -> ReleaseCandidate:
    """在基础产物上叠加判定记录与名称规则，跑发布门禁，产出带 release 段的报告（不写文件）。"""
    acnr_dir = backend_root / "data" / "acnr"
    base_catalog, base_report, _blocked = generate_base(registry_version=registry_version)
    catalog = copy.deepcopy(base_catalog)
    verdicts = load_sheet_verdicts(acnr_dir / "sources" / "sheet_verdicts.json")
    _apply_sheet_verdicts(catalog, verdicts, registry_version=registry_version, render_types=render_data.render_types,
                          component_types=render_data.component_types, previous=previous)
    names = catalog_names.merge_platform_names(catalog)
    alias_policy = _load_optional(acnr_dir / "sources" / "alias_policy.json")
    alias_entries = catalog_release._alias_entries(alias_policy)
    label_aliases = {u.get("sheet_code", ""): list(u.get("aliases") or []) for u in base_report.get("unregistered_aliases", [])}
    merged = catalog_names.apply_alias_policy(catalog, alias_entries, label_aliases)
    kept = _carry_over_aliases(catalog, previous)
    catalog_names.apply_cell_verdicts(catalog, [{"addr_id": c.addr_id, "verdict": c.verdict, "replaced_by": c.replaced_by}
                                                for c in verdicts.cell_verdicts])
    catalog_names.apply_cell_names(catalog)
    catalog["sheets"].sort(key=lambda s: s["addr_id"])
    catalog["cells"].sort(key=lambda c: c["addr_id"])

    catalog_text = deterministic_json(catalog)
    schema_text = catalog_contract.schema_json()
    fp, inputs = inputs_fingerprint(input_files(backend_root, previous))
    conflicts = base_report.get("alias_conflicts", [])
    report: dict[str, Any] = {"registry_version": registry_version}
    report["open_problems"] = {
        "unregistered_alias_keys": sorted(label_aliases),
        "alias_conflicts": sorted({c.get("alias", "") for c in conflicts}),
        "alias_conflict_members": {c.get("alias", ""): sorted(c.get("sheet_codes") or []) for c in conflicts},
    }
    ccr_unresolved = _ccr_unresolved(catalog, backend_root)
    if ccr_unresolved is not None:
        report["open_problems"]["ccr_unresolved"] = ccr_unresolved
    report["release"] = {
        "registry_version": registry_version,
        "previous_version": previous.version if previous else None,
        "previous_catalog_sha256": previous.content_sha256 if previous else None,
        "catalog_sha256": content_sha256(catalog_text.encode("utf-8")),
        "schema_sha256": content_sha256(schema_text.encode("utf-8")),
        "inputs_fingerprint": fp,
        "inputs": inputs,
        "classification": _classification_meta(backend_root),
    }
    overrides = _load_optional(acnr_dir / OVERRIDES_NAME)
    sv_raw = json.loads((acnr_dir / "sources" / "sheet_verdicts.json").read_text(encoding="utf-8"))
    acknowledgements = _load_optional(acnr_dir / "sources" / "acknowledgements.json")
    violations = catalog_release.run_release_gates(
        catalog, previous.catalog if previous else None, report, today=today, sheet_verdicts=sv_raw,
        alias_policy=alias_policy, acknowledgements=acknowledgements, overrides=overrides,
    )
    report.update(catalog_report_buckets.build_buckets(
        catalog, violations=violations, acknowledgements=acknowledgements, alias_entries=alias_entries,
        parent_qualified=names.parent_qualified, carried_over=kept, merged=merged, sheet_verdicts=sv_raw,
        overrides=overrides))
    return ReleaseCandidate(catalog=catalog, report=report, violations=violations, inputs=inputs)


__all__ = [
    "OVERRIDES_NAME", "PreviousBatch", "REPORT_NAME", "RELEASE_EXCEPTIONS_NAME", "ReleaseCandidate", "ReleaseInputError",
    "SNAPSHOT_SUBDIR", "build_release", "deterministic_json", "input_files", "inputs_fingerprint", "load_release_exceptions",
    "locate_previous", "sheet_dict",
]
