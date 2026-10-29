"""ACNR Catalog Generator — 目录唯一写出方（design §5.3，T07）。

`generate_catalog()` 合并基础输入（classification 骨架、I/E manifest、渲染注册、标签别名、坐标种子、overrides）；
写出走 `main()`：`app.services.acnr.catalog_build.build_release` 在基础产物上叠加判定记录与名称规则、
写统一显示名（`display.apply_display_labels`，输入含 `wp_account_mapping.json` 与 `sheet_display_names.json`，T29）、跑发布门禁，
门禁通过后同批写出 快照 → schema → 报告（含 release 段）→ 目录，每个文件先写临时文件再 `os.replace`。

Usage:
    python backend/scripts/acnr/generate_catalog.py            # 写出（内容不变则不写，幂等）
    python backend/scripts/acnr/generate_catalog.py --check    # 结构化比对：漂移退出 2、门禁违规退出 1
    python backend/scripts/acnr/generate_catalog.py --registry-version 20261027120000

函数参数 `offline`（接受但忽略，恒读离线缓存）与 `cycle`（只供单测，非 "all" 时拒绝写出）保留（R2-N3）。

Requirements: 1.3, 1.4, 3.3, 3.4, 3.5, 18.1；本 spec 需求 4（D4）
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# 路径设置
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_BACKEND_ROOT = _REPO_ROOT / "backend"
_DATA_DIR = _BACKEND_ROOT / "data"
_ACNR_DATA_DIR = _DATA_DIR / "acnr"
_SOURCES_DIR = _ACNR_DATA_DIR / "sources"

# 确保 backend 在 sys.path 以便 import loaders
sys.path.insert(0, str(_BACKEND_ROOT))


# ---------------------------------------------------------------------------
# Imports (after path setup)
# ---------------------------------------------------------------------------

from app.services.acnr.loaders.from_classification import (  # noqa: E402
    SheetCatalogEntry,
    load_sheet_skeletons_from_classification,
)
from app.services.acnr.loaders.from_ie_manifest import load_ie_manifest  # noqa: E402
from app.services.acnr.loaders.from_address_seeds import (  # noqa: E402
    CellCatalogEntry,
    load_cell_entries_from_seeds,
)
from app.services.acnr.loaders.from_frontend_labels import (  # noqa: E402
    load_sheet_name_aliases,
)
from app.services.acnr.loaders.from_render_registry import (  # noqa: E402
    load_render_registry_edges,
)


# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

CATALOG_VERSION = "1"


# ---------------------------------------------------------------------------
# Overrides 加载
# ---------------------------------------------------------------------------

_OVERRIDES_PATH = _ACNR_DATA_DIR / "global_catalog.overrides.json"


def _load_overrides() -> dict[str, dict[str, Any]]:
    """加载 global_catalog.overrides.json，返回 {addr_id → override_fields}。

    overrides 文件格式：
    {
      "overrides": [
        { "addr_id": "D2/D2-2", "fields": {...}, "reason": "...", "owner": "..." }
      ]
    }
    """
    if not _OVERRIDES_PATH.exists():
        return {}

    with open(_OVERRIDES_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    result: dict[str, dict[str, Any]] = {}
    for entry in data.get("overrides", []):
        addr_id = entry.get("addr_id", "")
        if addr_id and "fields" in entry:
            result[addr_id] = entry["fields"]

    return result


# ---------------------------------------------------------------------------
# Classification 离线缓存（CI/offline 模式）
# ---------------------------------------------------------------------------

_CLASSIFICATION_CACHE_PATH = _ACNR_DATA_DIR / "sources" / "classification_cache.json"


def _load_classification_records_offline() -> list[dict[str, Any]]:
    """从离线缓存 JSON 读取 classification 记录。"""
    if not _CLASSIFICATION_CACHE_PATH.exists():
        raise FileNotFoundError(
            f"Classification cache not found: {_CLASSIFICATION_CACHE_PATH}\n"
            f"Run with DB access first to generate cache, or provide records."
        )
    with open(_CLASSIFICATION_CACHE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# 别名冲突检测（R3.3, R3.4, R3.5）
# ---------------------------------------------------------------------------


def _detect_alias_conflicts(
    aliases: dict[str, list[str]],
) -> tuple[dict[str, list[str]], list[dict[str, Any]]]:
    """检测一对多别名冲突。

    Returns
    -------
    (clean_aliases, conflicts)
        clean_aliases: 去除冲突后的干净别名映射 {sheet_code → safe_aliases}
        conflicts: 冲突报告列表 [{alias, sheet_codes, action}]
    """
    # 反转映射：alias → list[sheet_codes]
    alias_to_sheets: dict[str, list[str]] = {}
    for sheet_code, alias_list in aliases.items():
        for alias in alias_list:
            if alias not in alias_to_sheets:
                alias_to_sheets[alias] = []
            if sheet_code not in alias_to_sheets[alias]:
                alias_to_sheets[alias].append(sheet_code)

    # 找出一对多冲突（一个别名映射多个 sheet_code）
    conflicting_aliases: set[str] = set()
    conflicts: list[dict[str, Any]] = []
    for alias, sheet_codes in alias_to_sheets.items():
        if len(sheet_codes) > 1:
            conflicting_aliases.add(alias)
            conflicts.append({
                "alias": alias,
                "sheet_codes": sorted(sheet_codes),
                "action": "blocked",
                "reason": "one-to-many conflict: alias maps to multiple sheet_codes",
            })

    # 构建干净别名：移除冲突别名（R3.5 阻断优先于缺口标记）
    clean_aliases: dict[str, list[str]] = {}
    for sheet_code, alias_list in aliases.items():
        safe = [a for a in alias_list if a not in conflicting_aliases]
        if safe:
            clean_aliases[sheet_code] = safe

    return clean_aliases, conflicts


# ---------------------------------------------------------------------------
# 合并管线
# ---------------------------------------------------------------------------


def generate_catalog(
    *,
    classification_records: list[Any] | None = None,
    cycle: str = "all",
    offline: bool = False,
    registry_version: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any], bool]:
    """执行 catalog 生成管线。

    Parameters
    ----------
    classification_records
        classification 记录（ORM/dict），None 时走离线缓存。
    cycle
        循环码（小写），默认 'all'。'all' 加载所有可用 manifest。
        单循环如 'd' 仅加载该循环。
    offline
        是否使用离线缓存。
    registry_version
        catalog 版本号。None 时自动生成。

    Returns
    -------
    (catalog_data, report_data, manifest_blocked)
        catalog_data: global_catalog.json 内容
        report_data: catalog_report.json 内容
        manifest_blocked: skip_reason 是否阻止 bulk manifest
    """
    # --- 版本号 ---
    if registry_version is None:
        registry_version = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")

    # --- Step 1: 加载 classification 骨架 ---
    if classification_records is None:
        if offline:
            classification_records = _load_classification_records_offline()
        else:
            # 从 DB 加载 — 非离线模式需要 classification_cache 或 DB
            # 首期用离线缓存兜底
            classification_records = _load_classification_records_offline()

    # Step 1 也获取 render_registry 的 render_type_map 用于 editor_engine 推断
    render_data = load_render_registry_edges()
    render_type_map = render_data.render_types

    sheets = load_sheet_skeletons_from_classification(
        classification_records,
        registry_version=registry_version,
        render_type_map=render_type_map,
    )

    # 建立 addr_id → SheetCatalogEntry 索引
    sheet_index: dict[str, SheetCatalogEntry] = {s.addr_id: s for s in sheets}
    sheet_by_code: dict[str, SheetCatalogEntry] = {s.sheet_code: s for s in sheets}

    # --- Step 2: 合并 import_export（IE manifest） ---
    # 支持 cycle='all' 加载所有可用 manifest，或单循环加载
    #
    # l / m / n 是 `partial: true` 清单（spec x3-adjustment-entry-import-export 任务 8.1）：
    # 只登记本循环的 X-3 调整分录汇总表（L 2 条 / M 10 条 / N 4 条 = 16 条），
    # 不是该循环 I/E 的全量清单 —— 未被覆盖的存量启用条目由 check_ie_catalog_sync 的
    # 部分登记模式报告，不抄进真源（把未经核验的存量条目写进生成源 = 把错值锁成基线）。
    # 这三条加进来后，`cycle='all'` 的输出会比 committed catalog 多出这 16 条
    # import_export 段；差额由该 spec 任务 9.1 的 catalog 外科补丁抹平。
    _ALL_CYCLES = ["d", "k", "f", "g", "h", "l", "m", "n"]

    if cycle.lower() == "all":
        cycles_to_load = _ALL_CYCLES
    else:
        cycles_to_load = [cycle.lower()]

    for c in cycles_to_load:
        try:
            ie_data = load_ie_manifest(c)
        except FileNotFoundError:
            ie_data = {}

        for sheet_code, ie_segment in ie_data.items():
            if sheet_code in sheet_by_code:
                sheet_by_code[sheet_code].import_export = ie_segment

    # --- Step 3: 合并 component_type（render_registry） ---
    for wp_code, comp_type in render_data.component_types.items():
        if wp_code in sheet_by_code:
            sheet_by_code[wp_code].component_type = comp_type

    # --- Step 4: 合并 sheet_name_aliases（frontend labels） ---
    raw_aliases = load_sheet_name_aliases()
    clean_aliases, alias_conflicts = _detect_alias_conflicts(raw_aliases)

    for sheet_code, alias_list in clean_aliases.items():
        if sheet_code in sheet_by_code:
            # 合并，去重
            existing = set(sheet_by_code[sheet_code].sheet_name_aliases)
            for alias in alias_list:
                if alias not in existing:
                    sheet_by_code[sheet_code].sheet_name_aliases.append(alias)
                    existing.add(alias)

    # --- Step 5: 加载 CellCatalogEntry（坐标种子） ---
    cells = load_cell_entries_from_seeds(
        data_dir=_DATA_DIR,
        registry_version=registry_version,
    )

    # --- Step 6: 应用 overrides（最高优先级） ---
    overrides = _load_overrides()
    for addr_id, fields in overrides.items():
        if addr_id in sheet_index:
            entry = sheet_index[addr_id]
            for key, value in fields.items():
                if hasattr(entry, key):
                    setattr(entry, key, value)
        # 也尝试 cell 级 override（按 addr_id 匹配）
        for cell in cells:
            if cell.addr_id == addr_id:
                for key, value in fields.items():
                    if hasattr(cell, key):
                        setattr(cell, key, value)

    # --- skip_reason 全局阻断检测（R1.4） ---
    manifest_blocked = False
    for entry in sheets:
        if entry.skip_reason:
            manifest_blocked = True
            break

    # --- 生成报告 ---
    # 缺口检测：semantic_only 无 A1 的 cell
    gaps: list[dict[str, Any]] = []
    for cell in cells:
        if cell.semantic_only:
            gaps.append({
                "addr_id": cell.addr_id,
                "parent_addr_id": cell.parent_addr_id,
                "type": "semantic_only_missing_a1",
                "description": f"CellCatalogEntry {cell.addr_id} 无可靠 A1 坐标",
            })

    # 未登记别名（在 labels 中出现但对应 sheet_code 不在 catalog 的）
    unregistered_aliases: list[dict[str, Any]] = []
    for sheet_code, alias_list in raw_aliases.items():
        if sheet_code not in sheet_by_code:
            unregistered_aliases.append({
                "sheet_code": sheet_code,
                "aliases": alias_list,
                "reason": "sheet_code not found in classification catalog",
            })

    # --- acknowledged_conflicts 机制 (Req-10.4) ---
    # 有 reason 字段的已知例外从 gap_count 扣除
    acknowledged_conflicts: list[dict[str, Any]] = []
    effective_alias_conflicts: list[dict[str, Any]] = []
    for conflict in alias_conflicts:
        if conflict.get("reason") and conflict.get("action") == "acknowledged":
            acknowledged_conflicts.append(conflict)
        else:
            effective_alias_conflicts.append(conflict)

    # --- gap_count 真实计算 (Req-10.1) ---
    # gap_count = alias_conflicts(未确认) + unregistered_aliases + gaps + skip_reason
    skip_reason_count = sum(1 for s in sheets if s.skip_reason)
    gap_count = (
        len(effective_alias_conflicts)
        + len(unregistered_aliases)
        + len(gaps)
        + skip_reason_count
    )

    report_data: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "registry_version": registry_version,
        "manifest_blocked": manifest_blocked,
        "alias_conflicts": alias_conflicts,
        "acknowledged_conflicts": acknowledged_conflicts,
        "gaps": gaps,
        "unregistered_aliases": unregistered_aliases,
        "summary": {
            "total_sheets": len(sheets),
            "total_cells": len(cells),
            "alias_conflict_count": len(alias_conflicts),
            "gap_count": gap_count,
            "unregistered_alias_count": len(unregistered_aliases),
            "sheets_with_skip_reason": skip_reason_count,
            "acknowledged_conflict_count": len(acknowledged_conflicts),
        },
    }

    # --- 构建 catalog 输出 ---
    catalog_data = _build_catalog_output(sheets, cells, registry_version)

    return catalog_data, report_data, manifest_blocked


# ---------------------------------------------------------------------------
# 确定性输出构建
# ---------------------------------------------------------------------------


def _sheet_to_dict(entry: SheetCatalogEntry) -> dict[str, Any]:
    """将 SheetCatalogEntry 转为 dict（口径唯一来源 catalog_build.sheet_dict）。"""
    from app.services.acnr.catalog_build import sheet_dict

    return sheet_dict(entry)


def _cell_to_dict(entry: CellCatalogEntry) -> dict[str, Any]:
    """将 CellCatalogEntry 转为 dict。"""
    d = entry.to_dict()
    result: dict[str, Any] = {}
    for key, value in sorted(d.items()):
        if value is None and key not in ("cell_address", "semantic_label"):
            continue
        if isinstance(value, str) and not value and key not in (
            "addr_id", "parent_addr_id", "domain"
        ):
            continue
        result[key] = value
    return result


def _build_catalog_output(
    sheets: list[SheetCatalogEntry],
    cells: list[CellCatalogEntry],
    registry_version: str,
) -> dict[str, Any]:
    """构建确定性 catalog JSON 结构（sheets / cells 按 addr_id 排序）。"""
    sorted_sheets = sorted(sheets, key=lambda s: s.addr_id)
    sorted_cells = sorted(cells, key=lambda c: c.addr_id)
    return {
        "version": CATALOG_VERSION,
        "registry_version": registry_version,
        "sheets": [_sheet_to_dict(s) for s in sorted_sheets],
        "cells": [_cell_to_dict(c) for c in sorted_cells],
    }


def _deterministic_json(data: Any) -> str:
    """确定性 JSON 输出（口径唯一来源 catalog_build.deterministic_json）。"""
    from app.services.acnr.catalog_build import deterministic_json

    return deterministic_json(data)


# ---------------------------------------------------------------------------
# 发布：构建候选、写出、--check（design §5.3）
# ---------------------------------------------------------------------------

_CATALOG_PATH = _ACNR_DATA_DIR / "global_catalog.json"
_REPORT_PATH = _ACNR_DATA_DIR / "catalog_report.json"
_SNAPSHOTS_DIR = _ACNR_DATA_DIR / "catalog_snapshots"
_SCHEMA_PATH = _REPO_ROOT / "docs" / "acnr" / "schemas" / "global_catalog.schema.json"
_MAX_DRIFT_LINES = 50


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def _build_candidate(registry_version: str, previous: Any):
    from app.services.acnr.catalog_build import build_release

    return build_release(
        registry_version=registry_version,
        previous=previous,
        backend_root=_BACKEND_ROOT,
        generate_base=lambda **kw: generate_catalog(**kw),
        render_data=load_render_registry_edges(),
        today=datetime.now(timezone.utc).date(),
    )


def _print_violations(violations: list[Any]) -> None:
    from app.services.acnr.catalog_release import group_by_check

    groups = group_by_check(violations)
    print(f"[ACNR] 发布门禁违规 {len(violations)} 条（按检查分组）：", file=sys.stderr)
    for check, items in sorted(groups.items()):
        print(f"  ── {check}：{len(items)} 条", file=sys.stderr)
        for v in items[:20]:
            aid = f" [{v.addr_id}]" if v.addr_id else ""
            print(f"     ·{aid} {v.detail}", file=sys.stderr)
        if len(items) > 20:
            print(f"     … 另有 {len(items) - 20} 条", file=sys.stderr)


def _atomic_write(path: Path, text: str) -> None:
    """先写同目录临时文件再 os.replace（中途失败由加载期互校拒绝不一致批次，重跑即恢复）。"""
    import os

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    os.replace(tmp, path)


def _strip_generated_at(report: Any) -> Any:
    if isinstance(report, dict):
        report = dict(report)
        report.pop("generated_at", None)
    return report


def _structural_drift(committed: dict[str, Any], rebuilt: dict[str, Any]) -> list[str]:
    """目录逐 addr_id 逐字段比对：返回「addr_id: 字段」形式的漂移行。"""
    lines: list[str] = []
    for key in sorted(set(committed) | set(rebuilt)):
        if key in ("sheets", "cells"):
            continue
        if committed.get(key) != rebuilt.get(key):
            lines.append(f"(顶层): {key}")
    for kind in ("sheets", "cells"):
        a = {e.get("addr_id"): e for e in committed.get(kind, [])}
        b = {e.get("addr_id"): e for e in rebuilt.get(kind, [])}
        for aid in sorted(set(a) - set(b)):
            lines.append(f"{aid}: 已提交目录有、重算没有")
        for aid in sorted(set(b) - set(a)):
            lines.append(f"{aid}: 重算有、已提交目录没有")
        for aid in sorted(set(a) & set(b)):
            for field in sorted(set(a[aid]) | set(b[aid])):
                if a[aid].get(field) != b[aid].get(field):
                    lines.append(f"{aid}: {field}")
    return lines


def run_check() -> int:
    """--check：以已提交版本号重算并结构化比对（漂移退出 2），再对已提交产物跑门禁（违规退出 1）。"""
    from app.services.acnr.catalog_build import ReleaseInputError, locate_previous
    from app.services.acnr.catalog_contract import schema_json
    from app.services.acnr.catalog_release import run_release_gates

    committed = _read_json(_CATALOG_PATH)
    report = _read_json(_REPORT_PATH)
    if not isinstance(committed, dict) or not isinstance(report, dict):
        print("[ACNR check] 漂移：global_catalog.json 或 catalog_report.json 缺失 / 无法解析", file=sys.stderr)
        return 2
    release = report.get("release")
    if not isinstance(release, dict) or release.get("registry_version") != committed.get("registry_version"):
        print("[ACNR check] 漂移：报告缺 release 段或其版本号与目录不一致（目录未经生成器发布）", file=sys.stderr)
        return 2
    try:
        previous = locate_previous(report, _ACNR_DATA_DIR, for_check=True)
        cand = _build_candidate(committed["registry_version"], previous)
    except (ReleaseInputError, ValueError) as exc:
        print(f"[ACNR check] 无法重算：{exc}", file=sys.stderr)
        return 2

    drift = _structural_drift(committed, cand.catalog)
    schema_text = _SCHEMA_PATH.read_text(encoding="utf-8") if _SCHEMA_PATH.exists() else ""
    if schema_text != schema_json():
        drift.append("(schema): global_catalog.schema.json 与 build_schema() 不一致")
    snap = _SNAPSHOTS_DIR / f"{committed['registry_version']}.json"
    if not snap.exists() or snap.read_text(encoding="utf-8") != _CATALOG_PATH.read_text(encoding="utf-8"):
        drift.append(f"(快照): {snap.name} 缺失或与目录不同")
    if not drift and cand.violations:
        # 目录与重算一致但门禁不过（如豁免到期）：按门禁违规退出 1，报告 blocking 组的差异是它的结果、不另报漂移
        _print_violations(cand.violations)
        return 1
    if _strip_generated_at(report) != cand.report:
        rk = sorted(k for k in set(_strip_generated_at(report)) | set(cand.report)
                    if _strip_generated_at(report).get(k) != cand.report.get(k))
        drift += [f"(报告): {k}" for k in rk]
    if drift:
        print(f"[ACNR check] 漂移 {len(drift)} 处（绕过生成器改了产物，或输入变了未重新发布）：", file=sys.stderr)
        for line in drift[:_MAX_DRIFT_LINES]:
            print(f"  {line}", file=sys.stderr)
        if len(drift) > _MAX_DRIFT_LINES:
            print(f"  … 共 {len(drift)} 处", file=sys.stderr)
        return 2

    sv = _read_json(_SOURCES_DIR / "sheet_verdicts.json")
    violations = run_release_gates(
        committed, previous.catalog if previous else None, report,
        today=datetime.now(timezone.utc).date(), sheet_verdicts=sv,
        alias_policy=_read_json(_SOURCES_DIR / "alias_policy.json"),
        acknowledgements=_read_json(_SOURCES_DIR / "acknowledgements.json"),
        overrides=_read_json(_OVERRIDES_PATH),
    )
    if violations:
        _print_violations(violations)
        return 1
    print(f"[ACNR check] OK — 目录 {committed['registry_version']} 与生成器重算一致，发布门禁 0 违规")
    return 0


def run_write(registry_version: str | None) -> int:
    """写出：内容不变不写（幂等）；门禁违规退出 1 且不写任何文件。"""
    from app.services.acnr.catalog_build import ReleaseInputError, load_release_exceptions, locate_previous
    from app.services.acnr.catalog_contract import schema_json
    from app.services.acnr.catalog_integrity import content_sha256

    committed = _read_json(_CATALOG_PATH)
    report = _read_json(_REPORT_PATH)
    try:
        if isinstance(report, dict) and isinstance(report.get("release"), dict) and isinstance(committed, dict):
            same = _build_candidate(committed["registry_version"], locate_previous(report, _ACNR_DATA_DIR, for_check=True))
            if (not same.violations and same.catalog == committed
                    and same.report == _strip_generated_at(report)):
                print(f"[ACNR] 内容未变化，目录仍为 {committed['registry_version']}，不写任何文件")
                return 0
        previous = locate_previous(report, _ACNR_DATA_DIR, for_check=False)
        version = registry_version or datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        cand = _build_candidate(version, previous)
    except (ReleaseInputError, ValueError) as exc:
        print(f"[ACNR] 发布输入不成立：{exc}", file=sys.stderr)
        return 1
    if cand.violations:
        _print_violations(cand.violations)
        return 1

    catalog_text = _deterministic_json(cand.catalog)
    snap = _SNAPSHOTS_DIR / f"{version}.json"
    if snap.exists() and content_sha256(snap.read_bytes()) != content_sha256(catalog_text.encode("utf-8")):
        registered = any(e.get("registry_version") == version
                         for e in load_release_exceptions(_ACNR_DATA_DIR).get("exceptions", []))
        if not registered:
            print(f"[ACNR] 失败：快照 {snap.name} 已存在且内容不同（快照不可变）", file=sys.stderr)
            return 1
    out_report = dict(cand.report)
    out_report["generated_at"] = datetime.now(timezone.utc).isoformat()
    _atomic_write(snap, catalog_text)
    _atomic_write(_SCHEMA_PATH, schema_json())
    _atomic_write(_REPORT_PATH, _deterministic_json(out_report))
    _atomic_write(_CATALOG_PATH, catalog_text)
    summary = cand.report.get("summary", {})
    print(f"[ACNR] 已发布 {version}（上一批次 {cand.report['release']['previous_version']}）")
    print(f"  sheets {summary.get('total_sheets')} / cells {summary.get('total_cells')} / blocking {summary.get('blocking')} / "
          f"豁免 {summary.get('acknowledged')} / 停用 {summary.get('deprecated')} / 提示 {summary.get('info')}")
    print(f"  目录 sha256 {cand.report['release']['catalog_sha256'][:16]}… 输入指纹 {cand.report['release']['inputs_fingerprint'][:16]}…")
    _run_offline_gc()
    return 0


def _run_offline_gc() -> None:
    """离线快照清理：无 DB 会话无法验证引用 ⇒ referenced_versions=None ⇒ fail-closed 不删（Req-16.3）。"""
    try:
        from app.services.acnr.catalog_snapshot_gc import cleanup_stale_snapshots

        gc_result = cleanup_stale_snapshots(keep_recent=10, referenced_versions=None)
        if gc_result.get("reference_status") == "unverifiable":
            print("  快照清理：引用集合不可验证 → fail-closed，未删除任何快照")
        elif gc_result["deleted"]:
            print(f"  快照清理：删除 {len(gc_result['deleted'])} 份过期快照")
    except Exception as e:  # noqa: BLE001 — 清理失败不影响已完成的发布
        print(f"  WARNING: 快照清理失败（不影响发布）：{e}", file=sys.stderr)


# ---------------------------------------------------------------------------
# CLI 入口
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    """CLI 入口：只保留 --write（缺省）/ --check / --registry-version。"""
    parser = argparse.ArgumentParser(description="ACNR 目录生成器（唯一写出方）")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--write", action="store_true", help="写出（缺省）")
    mode.add_argument("--check", action="store_true", help="结构化比对：漂移退出 2，门禁违规退出 1")
    parser.add_argument("--registry-version", default=None, help="指定新版本号（14 位 UTC 时间戳，缺省取当前时间）")
    args = parser.parse_args(argv)
    if args.check:
        return run_check()
    return run_write(args.registry_version)


if __name__ == "__main__":
    sys.exit(main())
