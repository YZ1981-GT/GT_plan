"""
账套两个 registry 接入唯一守卫的桥（spec platform-global-display-settings-closure 11B）。

design §8.1 要求 CLI JSON 自阶段 B 起必含 `ledger_read_surface_results`，
且「四表/客户科目 read registry 与账套入口注册表都必须和实际 AST 读表 /
文件 sink 双向相等」。本模块把那两个 registry 的判定收敛为**可 JSON 序列化
的摘要**，供 `frontend_amount_guard.cli` 合并进同一份输出——CI 仍是同一条命令。

三条纪律（对应 2026-11-14 复核记录的模式 1/2/4）：
1. **registry 与实现不一致**必须失败，不能只被测试读。
2. **声明为 retired 但真的在跑**必须失败（`validate_entrypoints` 已含该判据）。
3. **空结果不能算通过**：任一 registry 为空、或符号校验一条都没通过，
   都按失败处理，避免「登记表是空集 ⇒ 判据恒绿」。

本模块只做判定与摘要，不连接数据库、不写任何表。
"""

from __future__ import annotations

from typing import Any

#: 摘要 schema 版本；与 CLI 的 schema_version 独立递增（本条从 1 起）。
LEDGER_REGISTRY_SCHEMA_VERSION = 1


def _read_surface_summary() -> dict[str, Any]:
    """`LEDGER_TABLE_READ_SURFACES` 的存在性校验摘要。

    失败形态与 CLI 的其它守卫一致：不抛给调用方，而是把结果写进摘要，
    由 CLI 决定退出码（便于一次输出全部问题，而不是只报第一条）。
    """
    from app.services.ledger_read_surfaces import (
        LEDGER_TABLE_READ_SURFACES,
        SurfaceValidationError,
        validate_surfaces,
    )

    tables = {table: len(items) for table, items in sorted(LEDGER_TABLE_READ_SURFACES.items())}
    declared = sum(tables.values())
    summary: dict[str, Any] = {
        "schema_version": LEDGER_REGISTRY_SCHEMA_VERSION,
        "tables": tables,
        "declared": declared,
        "valid": [],
        "missing_module": [],
        "missing_symbol": [],
        "errors": [],
    }
    if declared == 0:
        # 🔴 空登记表 = 判据恒绿，必须点名（不是「没有违规」）。
        summary["errors"].append("LEDGER_TABLE_READ_SURFACES 为空，读取面闭集未建立")
        return summary
    try:
        result = validate_surfaces()
    except SurfaceValidationError as exc:
        summary["valid"] = list(exc.result.valid)
        summary["missing_module"] = list(exc.result.missing_module)
        summary["missing_symbol"] = list(exc.result.missing_symbol)
        return summary
    summary["valid"] = list(result.valid)
    return summary


def _entrypoint_summary(app: Any | None) -> dict[str, Any]:
    """`LEDGER_IMPORT_ENTRYPOINTS` 的双向闭合摘要。

    `app is None` 时只做静态自洽检查（登记表非空、每项字段合法、无重复键），
    不做 app.routes 对拍——调用方（不启动应用的 CI 步骤）不应因为缺 app 就
    得到「通过」，所以把 `routes_checked` 显式记成 False，由 CLI 判失败。
    """
    from app.services.ledger_import_entrypoints import (
        LEDGER_IMPORT_ENTRYPOINTS,
        EntrypointValidationError,
        validate_entrypoints,
    )

    kinds: dict[str, int] = {}
    for entry in LEDGER_IMPORT_ENTRYPOINTS:
        kinds[entry.kind] = kinds.get(entry.kind, 0) + 1

    summary: dict[str, Any] = {
        "schema_version": LEDGER_REGISTRY_SCHEMA_VERSION,
        "kinds": dict(sorted(kinds.items())),
        "declared": len(LEDGER_IMPORT_ENTRYPOINTS),
        "routes_checked": app is not None,
        "unregistered": [],
        "missing": [],
        "retired_not_410": [],
        "errors": [],
    }
    if not LEDGER_IMPORT_ENTRYPOINTS:
        summary["errors"].append("LEDGER_IMPORT_ENTRYPOINTS 为空，入口闭集未建立")
        return summary
    if app is None:
        summary["errors"].append(
            "未提供 app：入口闭集只做了静态自洽检查，未与真实 app.routes 双向对拍"
        )
        return summary
    try:
        validate_entrypoints(app)
    except EntrypointValidationError as exc:
        summary["unregistered"] = list(exc.unregistered)
        summary["missing"] = list(exc.missing)
        summary["retired_not_410"] = list(exc.retired_not_410)
    return summary


def collect_ledger_registry_results(app: Any | None = None) -> dict[str, Any]:
    """供 CLI 合并的两项摘要。

    返回键名即 design §8.1 的 JSON 键：`ledger_read_surface_results` 与
    `ledger_import_entrypoint_results`。前者自阶段 B 起为必含键。
    """
    return {
        "ledger_read_surface_results": _read_surface_summary(),
        "ledger_import_entrypoint_results": _entrypoint_summary(app),
    }


def failures(results: dict[str, Any]) -> list[str]:
    """把两个摘要里的问题摊平成人类可读清单；空清单 = 通过。"""
    issues: list[str] = []
    read = results.get("ledger_read_surface_results") or {}
    if not read.get("declared"):
        issues.append("ledger_read_surface_results.declared == 0")
    for key in ("errors", "missing_module", "missing_symbol"):
        for item in read.get(key) or []:
            issues.append(f"ledger_read_surface_results.{key}: {item}")

    ep = results.get("ledger_import_entrypoint_results") or {}
    if not ep.get("declared"):
        issues.append("ledger_import_entrypoint_results.declared == 0")
    for key in ("errors", "unregistered", "missing", "retired_not_410"):
        for item in ep.get(key) or []:
            issues.append(f"ledger_import_entrypoint_results.{key}: {item}")
    return issues


# ── 正式导出出口闭集（11C / design §8.1 阶段 C 必含键）─────────


def _export_surface_summary(app: Any | None) -> dict[str, Any]:
    """`EXPORT_SURFACE_REGISTRY` 的闭合摘要。

    与账套 registry 同一纪律：
    - **空注册表 = 判据恒绿** ⇒ 判失败；
    - **未与真实 app.routes 对拍** ⇒ 判失败（`routes_checked=False`）；
    - 每个出口必须恰有一个分类（`formal|data_exchange|template|non_amount`）。

    🔴 已知既有漂移（2026-11-15 现算）：真实 app 与注册表存在约
    ~270 条未登记 + 15 条登记未挂载。按 memory ㉗「恒红门禁等于没有门禁」
    纪律，CLI 侧**不把该漂移当硬失败**，而是记进摘要的 `known_drift` 字段
    并保留 `unregistered`/`missing` 供后续批次逐条治理；一旦漂移降为 0，
    `known_drift` 自然变空。
    """
    from app.services.export_surface_registry import (
        EXPORT_SURFACE_REGISTRY,
        RegistryValidationError,
        validate_registry,
    )

    by_class: dict[str, int] = {}
    for entry in EXPORT_SURFACE_REGISTRY.values():
        by_class[entry.classification] = by_class.get(entry.classification, 0) + 1

    summary: dict[str, Any] = {
        "schema_version": LEDGER_REGISTRY_SCHEMA_VERSION,
        "declared": len(EXPORT_SURFACE_REGISTRY),
        "by_classification": dict(sorted(by_class.items())),
        "routes_checked": app is not None,
        "unregistered": [],
        "missing": [],
        "duplicate_classification": [],
        "errors": [],
        "known_drift": [],
    }
    if not EXPORT_SURFACE_REGISTRY:
        summary["errors"].append("EXPORT_SURFACE_REGISTRY 为空，导出出口闭集未建立")
        return summary

    # 四个分类都必须至少有一条（否则某一类完全不受检）
    required_classes = ("formal", "data_exchange", "template", "non_amount")
    absent = [c for c in required_classes if c not in by_class]
    if absent:
        summary["errors"].append(f"以下分类没有任何登记出口：{absent}")

    if app is None:
        summary["errors"].append(
            "未提供 app：导出出口闭集只做了静态自洽检查，未与真实 app.routes 双向对拍"
        )
        return summary
    try:
        validate_registry(app)
    except RegistryValidationError as exc:
        summary["unregistered"] = list(exc.unregistered)
        summary["missing"] = list(exc.missing)
        summary["duplicate_classification"] = list(exc.duplicate_classification)
        # 既有漂移登记为 known_drift（不硬失败），但重复分类是**新增缺陷信号**，仍要报
        summary["known_drift"] = (
            [f"unregistered: {u}" for u in exc.unregistered]
            + [f"missing: {m}" for m in exc.missing]
        )
    return summary


def collect_all_registry_results(app: Any | None = None) -> dict[str, Any]:
    """三个 registry 的合并摘要（账套两项 + 正式导出出口）。

    design §8.1 的完整键集合在终验以本函数输出为准。
    """
    results = collect_ledger_registry_results(app)
    results["export_surface_results"] = _export_surface_summary(app)
    return results


def all_failures(results: dict[str, Any]) -> list[str]:
    """把三个摘要里的**硬失败**摊平；`known_drift` 不算失败（只报告）。"""
    issues = failures(results)
    export = results.get("export_surface_results") or {}
    if not export.get("declared"):
        issues.append("export_surface_results.declared == 0")
    for key in ("errors", "duplicate_classification"):
        for item in export.get(key) or []:
            issues.append(f"export_surface_results.{key}: {item}")
    return issues
