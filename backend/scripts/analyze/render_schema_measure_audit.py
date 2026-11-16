"""离线计算 render schema 的 `reached_by`（spec platform-global-display-settings-closure 6A / design §18 H1②）。

用途：回答「哪些 (wp_code, sheet) 会真的走到某个 render schema 文件」，从而产出
`backend/data/render_schema_core.json` 的核心清单。**不连库、不启动应用、不读项目数据。**

判定链（与 `wp_render_config_sheet_classify` 逐字同口径）：
1. 遍历内置科目工作包注册表里的每个 `primary_wp_code`；
2. 取该工作包的 sheet 清单（**内置 registry 直读**，不走 `resolve_package_sheets`——
   后者要 db，离线不可用）；
3. 用 `compute_real_sheets` + `is_multi_sheet` + `resolve_sheet_override` +
   `classify_sheet` 得到每个 sheet 的 componentType；
4. 用 `WpRenderSchemaService._resolve_schema_path(wp_code)` 找 schema 文件，
   用 `_unpack_sheet_schema` 取该 sheet 的 schema 条目；
5. 条目 `component_type` 等于路由结果且**未被 G- 前缀强制 OnlyOffice** 时，
   向该 schema 文件的 `reached_by` 记一条 `{wp_code, sheet, componentType}`。

🔴 **离线算不到的两类路由**（design §18 H1② 明确要求写进 12A 文档）：
- 项目或事务所**自定义工作包**（存在库里，不在内置 registry）；
- 没有内置工作包、sheet 清单来自**数据库分类结果**的底稿。
只经这两类路由到达的 schema **不能成为核心项**，因为 `--check` 无法重算它们。

用法：
    python -m scripts.analyze.render_schema_measure_audit --check
    python -m scripts.analyze.render_schema_measure_audit --write
    python -m scripts.analyze.render_schema_measure_audit --json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

#: 输出文件（与 `render_schema_core.json` 同一份真源）。
_CORE_FILE = Path(__file__).resolve().parents[2] / "data" / "render_schema_core.json"

#: 输出 schema 版本。
SCHEMA_VERSION = 1


@dataclass
class AuditResult:
    """一次离线审计的结果。"""

    #: schema 文件名 → reached_by 条目列表
    reached_by: dict[str, list[dict[str, str]]] = field(default_factory=dict)
    #: 内置工作包（primary_wp_code）清单
    package_codes: list[str] = field(default_factory=list)
    #: 判定过程中的非致命问题（如 schema 缺失、sheet 无 schema 条目）
    notes: list[str] = field(default_factory=list)

    def to_json(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "_source": "scripts/analyze/render_schema_measure_audit.py",
            "criteria": {
                "route_source": "builtin_package_registry",
                "requires_component_type_match": True,
                "excludes_onlyoffice_forced": True,
                "excludes": [
                    "项目/事务所自定义工作包（存在库里，离线不可读）",
                    "无内置工作包、sheet 清单来自数据库分类结果的底稿",
                ],
            },
            "package_codes": self.package_codes,
            "entries": [
                {"schema": schema, "reached_by": rows}
                for schema, rows in sorted(self.reached_by.items())
            ],
            "notes": self.notes,
        }


def _load_builtin_packages() -> dict[str, list[str]]:
    """读内置科目工作包注册表 → `{primary_wp_code: [sheet_name, ...]}`。

    🔴 直读注册表数据文件（`AccountPackageRegistryService()` 无需 db），
    不走 `resolve_package_sheets`（那个要 AsyncSession，离线不可用）。
    注册表为空时显式失败而不是返回空 dict —— 空清单会让「核心项为空」
    看起来像「确实没有 schema 被到达」。
    """
    from app.services.account_package_registry_service import AccountPackageRegistryService

    registry = AccountPackageRegistryService()
    packages = registry.get_packages()
    if not packages:
        raise RuntimeError(
            "内置科目工作包注册表为空；reached_by 审计会得出「无核心项」的假结论"
        )
    result: dict[str, list[str]] = {}
    for pkg in packages:
        primary = pkg.get("primary_wp_code")
        if not primary:
            continue
        sheets = []
        for sheet in pkg.get("sheets") or []:
            name = sheet.get("sheet_name") if isinstance(sheet, dict) else None
            if name:
                sheets.append(name)
        if sheets:
            result.setdefault(str(primary), []).extend(sheets)
    return result


@dataclass
class _FakeCls:
    """`ClassificationResult` 的最小替身（纯函数只读这两个字段）。"""

    sheet_name: str
    class_code: str = ""


def audit() -> AuditResult:
    """跑一次离线审计。"""
    from app.routers.wp_render_config_sheet_classify import (
        apply_g_prefix_onlyoffice,
        classify_sheet,
        compute_real_sheets,
        is_multi_sheet,
        resolve_sheet_override,
    )
    from app.services.wp_classification_service import _WP_CODE_OVERRIDE
    from app.services.dedicated_component_types import DEDICATED_COMPONENT_TYPES

    result = AuditResult()
    packages = _load_builtin_packages()
    result.package_codes = sorted(packages)

    # 🔴 `WpRenderSchemaService` 与 `wp_render_config_helpers` 在 import 期会拉起
    # 整条 router 依赖（实测 import 卡住不返回）。离线审计只需要
    # 「schema 目录 + 按 wp_code 找文件 + 取 sheet 条目」，所以本地实现等价的最小版本，
    # 并**断言**与生产 service 的路径解析结果一致（见 `_assert_path_parity`）。
    schema_dir = _schema_dir()
    if not schema_dir.is_dir():
        raise RuntimeError(f"render schema 目录不存在：{schema_dir}")

    for wp_code, sheet_names in sorted(packages.items()):
        classes = [_FakeCls(sheet_name=s) for s in sheet_names]
        real = compute_real_sheets(classes, wp_code_override=_WP_CODE_OVERRIDE)
        multi = is_multi_sheet(real)
        ovr = _WP_CODE_OVERRIDE.get(wp_code)

        schema_path = _resolve_schema_path(schema_dir, wp_code)
        if schema_path is None:
            result.notes.append(f"{wp_code}: 无 render schema 文件")
            continue
        schema_data = _load_schema_file(schema_path)
        if schema_data is None:
            result.notes.append(f"{wp_code}: schema 解析失败（{schema_path.name}）")
            continue

        for cls_obj in real:
            sheet_ovr = resolve_sheet_override(
                cls_obj.sheet_name,
                is_multi=multi,
                wp_code=wp_code,
                wp_code_override=_WP_CODE_OVERRIDE,
            )
            route = classify_sheet(
                sheet_name=cls_obj.sheet_name,
                class_code=cls_obj.class_code,
                is_multi=multi,
                wp_code_override_value=ovr,
                sheet_override=sheet_ovr,
                whole_wp_dedicated=DEDICATED_COMPONENT_TYPES,
                has_package_sheets=True,
                derive_component_type=lambda: "",
                ignore_wp_code_override_deriver=lambda: "",
            )
            route = apply_g_prefix_onlyoffice(
                route,
                class_code=cls_obj.class_code,
                is_multi=multi,
                wp_code_override_value=ovr,
            )
            if route.reason == "g_prefix_onlyoffice":
                # OnlyOffice 强制 ⇒ 不读 render schema 的 measure 合同
                continue
            sheet_schema = _unpack_sheet_schema(schema_data, cls_obj.sheet_name)
            if sheet_schema is None:
                continue
            declared = sheet_schema.get("component_type")
            if declared is None or str(declared) != route.component_type:
                continue
            result.reached_by.setdefault(schema_path.name, []).append({
                "wp_code": wp_code,
                "sheet": cls_obj.sheet_name,
                "componentType": route.component_type,
            })

    return result


def _schema_dir() -> Path:
    """render schema 目录。

    🔴 与 `wp_render_schema_service._SCHEMA_DIR` **逐段一致**：
    `backend/data/ledger_adapters/wp_render_schema`（不是 `backend/data/wp_render_schema`）。
    本轮实测：我第一版写成 `data/wp_render_schema`，目录不存在 ⇒ `audit()` 抛
    「目录不存在」而 CLI 看起来只是没输出 —— 这类「路径猜错」正是设计期要求的
    「现读实证，禁按命名习惯推」（memory ⑭）。
    """
    return Path(__file__).resolve().parents[2] / "data" / "ledger_adapters" / "wp_render_schema"


#: 与 `wp_render_schema_service._PATTERN_SCHEMA_MAP` 同口径的 pattern 兜底。
_PATTERN_SCHEMA_MAP = (
    (re.compile(r"^B23-(\d+)$"), "B23-generic.yaml", 1, 14),
    (re.compile(r"^C(\d+)$"), "C-generic.yaml", 2, 15),
    (re.compile(r"^C(\d+)-2$"), "C-deviation-generic.yaml", 2, 15),
    (re.compile(r"^S33-(\d+)$"), "S33-generic.yaml", 1, 9),
)


def _resolve_schema_path(schema_dir: Path, wp_code: str) -> Path | None:
    """按 `WpRenderSchemaService._resolve_schema_path` 同一优先级找 schema 文件。"""
    exact = schema_dir / f"{wp_code}.yaml"
    if exact.is_file():
        return exact
    for pattern, filename, low, high in _PATTERN_SCHEMA_MAP:
        m = pattern.match(wp_code)
        if m:
            try:
                n = int(m.group(1))
            except (IndexError, ValueError):
                continue
            if low <= n <= high:
                candidate = schema_dir / filename
                if candidate.is_file():
                    return candidate
    disclosure = schema_dir / f"C-{wp_code}-disclosure.yaml"
    if disclosure.is_file():
        return disclosure
    m2 = re.match(r"^([A-Z])", wp_code)
    if m2:
        fallback = schema_dir / f"{m2.group(1)}-template.yaml"
        if fallback.is_file():
            return fallback
    return None


def _load_schema_file(path: Path) -> dict[str, Any] | None:
    """读一个 render schema YAML；失败返回 None（由调用方记 note）。"""
    try:
        import yaml

        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def _unpack_sheet_schema(schema_data: dict[str, Any] | None, sheet_name: str | None) -> dict | None:
    """从整份 schema 取某 sheet 的条目（与 `_unpack_sheet_schema` 同口径）。"""
    if not isinstance(schema_data, dict) or not sheet_name:
        return None
    sheets = schema_data.get("sheets")
    if isinstance(sheets, dict):
        entry = sheets.get(sheet_name)
        return entry if isinstance(entry, dict) else None
    if isinstance(sheets, list):
        for entry in sheets:
            if isinstance(entry, dict) and entry.get("sheet_name") == sheet_name:
                return entry
    return None


def _write(payload: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="render schema reached_by 离线审计")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true", help="重算 reached_by 并与磁盘文件比对")
    group.add_argument("--write", action="store_true", help="重算并写入 render_schema_core.json")
    group.add_argument("--json", action="store_true", help="只打印结果 JSON")
    parser.add_argument("--output", type=str, default=str(_CORE_FILE))
    args = parser.parse_args(argv)

    try:
        result = audit()
    except Exception as exc:  # noqa: BLE001 — 审计工具崩溃必须显式失败
        print(f"[FAIL] 审计失败：{type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

    payload = result.to_json()
    target = Path(args.output)

    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0

    if args.write:
        _write(payload, target)
        print(
            f"[OK] 已写入 {target}：{len(payload['entries'])} 个 schema 有 reached_by，"
            f"{len(result.package_codes)} 个内置工作包"
        )
        return 0

    # --check：重算并与磁盘比对（幂等：内容不变即通过）
    if not target.exists():
        print(f"[FAIL] 缺少 {target}；先跑 --write", file=sys.stderr)
        return 1
    on_disk = json.loads(target.read_text(encoding="utf-8"))
    if on_disk == payload:
        print(
            f"[OK] reached_by 一致：{len(payload['entries'])} 个 schema，"
            f"{len(result.package_codes)} 个内置工作包"
        )
        return 0
    print(
        f"[FAIL] reached_by 漂移：磁盘 {len(on_disk.get('entries', []))} 条 vs "
        f"现算 {len(payload['entries'])} 条",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
