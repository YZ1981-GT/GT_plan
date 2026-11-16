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

    🔴 2026-11-16 变更：`known_drift` 由「只报告」改为**硬失败**。

    变更前（2026-11-15）的写法是：把 `unregistered` / `missing` 降级进
    `known_drift`，而 `all_failures` 刻意不检查它，理由是「~270 条未登记属
    独立工作量，按 memory ㉗『恒红门禁等于没有门禁』先不硬失败」。

    该理由用错了地方 —— memory ㉗ 针对的是**永假判据**（时间戳 / 随机数 /
    绝对路径进判据），而这里是**已知待办**。后果是三层门禁同时失效：

    | 层 | 变更前行为 |
    | --- | --- |
    | `validate_registry` | 抛异常（正确） |
    | `test_missing_is_zero` | 只看 `missing`，`unregistered` 静默放行 |
    | 本函数 | 两个方向都降级成 `known_drift`，`all_failures` 不算失败 |

    实测证据：把 `is_metadata_only_export_path` 整个删掉（让 status / history /
    manifest 都算导出出口），首轮 8 条变异里 3 条元数据口径变异全部 GREEN 存活。

    漂移已于 2026-11-16 清零（303 → 0），本函数现在要求**双向闭合**：
    `unregistered` / `missing` 任一非空即进 `errors`，`known_drift` 仅在
    非空时填充（键保留以维持 CLI JSON schema 稳定，但填充即失败）。
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
        # 双向闭合都是硬失败：`unregistered` = 实现了没登记（新加导出端点漏登记），
        # `missing` = 登记了没实现（注册表登记 ≠ 路由存在，曾导致用户点一次 404）。
        summary["errors"].extend(
            f"unregistered: {u}" for u in exc.unregistered
        )
        summary["errors"].extend(f"missing: {m}" for m in exc.missing)
        # 键保留（CLI JSON schema 稳定），但**填充即失败** —— 不再有「只报告」语义。
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
    """把三个摘要里的**硬失败**摊平；空清单 = 通过。

    🔴 2026-11-16：`known_drift` 不再是「只报告」—— 它非空即失败。
    变更前本函数刻意跳过 `known_drift`，导致 `unregistered`（实现了没登记）
    与 `missing`（登记了没实现）在 CLI 侧永不阻断；实测把元数据口径过滤
    整个删掉后 CLI 仍然 exit 0。
    """
    issues = failures(results)
    export = results.get("export_surface_results") or {}
    if not export.get("declared"):
        issues.append("export_surface_results.declared == 0")
    for key in ("errors", "duplicate_classification", "known_drift"):
        for item in export.get(key) or []:
            issues.append(f"export_surface_results.{key}: {item}")
    return issues
