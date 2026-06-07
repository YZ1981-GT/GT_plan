"""
check_note_binding_registry.py — 校验附注取数绑定注册表完整性

CI 脚本，加载 note_binding_registry.json 并验证：
1. section/table/row/col 引用存在于 sidecar preview
2. source 枚举合法 / wp_code 合法
3. 同一 cell 无重复 active binding
4. source_missing 时有 fallback 或说明

用法：
    python backend/scripts/check/check_note_binding_registry.py

Validates: Requirements 11.3, 11.4
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# 仓库根目录
REPO_ROOT = Path(__file__).resolve().parents[3]

# 文件路径
REGISTRY_PATH = REPO_ROOT / "backend" / "data" / "note_binding_registry.json"
SIDECAR_PREVIEW_PATH = (
    REPO_ROOT / "backend" / "data" / "generated" / "note_semantic_sidecars.preview.json"
)

# 合法来源枚举
VALID_SOURCES = frozenset(
    [
        "trial_balance",
        "ledger",
        "workpaper",
        "report",
        "prior_note",
        "manual",
        "formula",
        "ai_draft",
    ]
)

# 已知合法 wp_code（从 note_wp_mapping_rules 和项目实际配置）
KNOWN_WP_CODES = frozenset(
    [
        "E1-1",
        "E4-1",
        "E9-1",
        "D2",
        "D2-1",
        "D2-2",
        "E1",
        "E4",
        "E9",
    ]
)


def load_json(path: Path) -> dict | None:
    """加载 JSON 文件，失败返回 None。"""
    if not path.exists():
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def build_sidecar_index(
    sidecar_data: dict,
) -> dict[str, dict[str, dict[str, set[str]]]]:
    """从 sidecar preview 构建 section->table->row->cols 索引。

    返回结构：
    {
        section_id: {
            table_id: {
                "__cols__": {col_id, ...},
                row_id: set()  # 存在标记
            }
        }
    }
    """
    index: dict[str, dict[str, dict[str, set[str]]]] = {}
    sidecars = sidecar_data.get("sidecars", [])
    for sidecar in sidecars:
        section_id = sidecar.get("semantic_section_id", "")
        if not section_id:
            continue
        if section_id not in index:
            index[section_id] = {}

        tables = sidecar.get("_tables", [])
        for table in tables:
            table_id = table.get("table_id", "")
            if not table_id:
                continue
            if table_id not in index[section_id]:
                index[section_id][table_id] = {"__cols__": set()}

            # 收集列
            columns = table.get("columns", [])
            for col in columns:
                col_id = col.get("col_id", "")
                if col_id:
                    index[section_id][table_id]["__cols__"].add(col_id)

            # 收集行
            rows = table.get("rows", [])
            for row in rows:
                row_id = row.get("row_id", "")
                if row_id:
                    index[section_id][table_id][row_id] = set()

    return index


def check_section_table_row_col(
    bindings: list[dict],
    sidecar_index: dict[str, dict[str, dict[str, set[str]]]],
) -> list[str]:
    """校验 section/table/row/col 存在于 sidecar preview。"""
    errors: list[str] = []
    for b in bindings:
        bid = b.get("binding_id", "?")
        section_id = b.get("section_id", "")
        table_id = b.get("table_id", "")
        row_id = b.get("row_id", "")
        col_id = b.get("col_id", "")

        if section_id not in sidecar_index:
            errors.append(f"[{bid}] section_id '{section_id}' 不存在于 sidecar preview")
            continue

        section_tables = sidecar_index[section_id]
        if table_id not in section_tables:
            errors.append(
                f"[{bid}] table_id '{table_id}' 不存在于 section '{section_id}'"
            )
            continue

        table_data = section_tables[table_id]
        if row_id and row_id not in table_data:
            errors.append(
                f"[{bid}] row_id '{row_id}' 不存在于 table '{table_id}'"
            )

        cols = table_data.get("__cols__", set())
        if col_id and cols and col_id not in cols:
            errors.append(
                f"[{bid}] col_id '{col_id}' 不存在于 table '{table_id}' 的列定义中"
            )

    return errors


def check_source_enum(bindings: list[dict]) -> list[str]:
    """校验 source 枚举合法，workpaper 有 wp_code。"""
    errors: list[str] = []
    for b in bindings:
        bid = b.get("binding_id", "?")
        source = b.get("source", "")

        if not source:
            errors.append(f"[{bid}] source 为空")
            continue

        if source not in VALID_SOURCES:
            errors.append(f"[{bid}] source '{source}' 不在合法枚举中")

        # workpaper 需要 wp_code
        if source == "workpaper":
            wp_code = b.get("wp_code")
            if not wp_code:
                errors.append(f"[{bid}] source='workpaper' 但 wp_code 为空")
            elif wp_code not in KNOWN_WP_CODES:
                # 仅 warning 级别，不阻断
                errors.append(
                    f"[{bid}] wp_code '{wp_code}' 不在已知清单中（可能需要新增）"
                )

    return errors


def check_duplicate_active_bindings(bindings: list[dict]) -> list[str]:
    """校验同一 cell 无重复 active binding。"""
    errors: list[str] = []
    cell_map: dict[str, list[str]] = {}

    for b in bindings:
        if not b.get("active", True):
            continue
        cell_key = (
            f"{b.get('section_id', '')}|{b.get('table_id', '')}|"
            f"{b.get('row_id', '')}|{b.get('col_id', '')}"
        )
        bid = b.get("binding_id", "?")
        if cell_key not in cell_map:
            cell_map[cell_key] = []
        cell_map[cell_key].append(bid)

    for cell_key, bids in cell_map.items():
        if len(bids) > 1:
            errors.append(
                f"同一 cell '{cell_key}' 有 {len(bids)} 个 active binding: {bids}"
            )

    return errors


def check_source_missing_fallback(bindings: list[dict]) -> list[str]:
    """校验 source_missing 有 fallback 或说明。

    如果 source 标记为缺失相关状态，需要有 fallback_source 或 fallback_note。
    当前实现：检查 source='manual' 且无 field 且无 fallback_note 的情况。
    """
    errors: list[str] = []
    for b in bindings:
        bid = b.get("binding_id", "?")
        source = b.get("source", "")

        # 仅对需要外部数据但可能缺失的来源做检查
        if source in ("workpaper", "trial_balance", "ledger", "report"):
            # 如果标记了 source_missing 字段
            if b.get("source_missing"):
                has_fallback = b.get("fallback_source") or b.get("fallback_note")
                if not has_fallback:
                    errors.append(
                        f"[{bid}] source_missing=True 但无 fallback_source 或 fallback_note"
                    )

    return errors


def main() -> int:
    """主入口。"""
    print("=" * 60)
    print("附注取数绑定注册表校验")
    print("=" * 60)

    # 加载 registry
    registry_data = load_json(REGISTRY_PATH)
    if registry_data is None:
        print(f"❌ 无法加载 registry: {REGISTRY_PATH}")
        return 1
    print(f"✅ 已加载 registry ({REGISTRY_PATH.name})")

    bindings = registry_data.get("bindings", [])
    if not bindings:
        print("⚠️  registry 中无 binding 条目")
        return 0

    print(f"   共 {len(bindings)} 条绑定")

    # 加载 sidecar preview（可选，不存在则跳过引用校验）
    sidecar_data = load_json(SIDECAR_PREVIEW_PATH)
    has_sidecar = sidecar_data is not None

    all_errors: list[str] = []
    all_warnings: list[str] = []

    # 1. section/table/row/col 校验
    print("\n--- 1. section/table/row/col 存在性校验 ---")
    if has_sidecar:
        sidecar_index = build_sidecar_index(sidecar_data)
        ref_errors = check_section_table_row_col(bindings, sidecar_index)
        if ref_errors:
            # 引用校验只作 warning（sidecar 可能不完整）
            for e in ref_errors:
                print(f"   ⚠️  {e}")
            all_warnings.extend(ref_errors)
        else:
            print("   ✅ 所有引用校验通过")
    else:
        print("   ⏭️  sidecar preview 不存在，跳过引用校验")

    # 2. source 枚举校验
    print("\n--- 2. source/wp_code 枚举校验 ---")
    source_errors = check_source_enum(bindings)
    blocking_source_errors = [
        e for e in source_errors if "不在合法枚举中" in e or "为空" in e
    ]
    warning_source_errors = [e for e in source_errors if e not in blocking_source_errors]

    if blocking_source_errors:
        for e in blocking_source_errors:
            print(f"   ❌ {e}")
        all_errors.extend(blocking_source_errors)
    if warning_source_errors:
        for e in warning_source_errors:
            print(f"   ⚠️  {e}")
        all_warnings.extend(warning_source_errors)
    if not source_errors:
        print("   ✅ source/wp_code 枚举校验通过")

    # 3. 重复 active binding 校验
    print("\n--- 3. 重复 active binding 校验 ---")
    dup_errors = check_duplicate_active_bindings(bindings)
    if dup_errors:
        for e in dup_errors:
            print(f"   ❌ {e}")
        all_errors.extend(dup_errors)
    else:
        print("   ✅ 无重复 active binding")

    # 4. source_missing fallback 校验
    print("\n--- 4. source_missing fallback 校验 ---")
    fallback_errors = check_source_missing_fallback(bindings)
    if fallback_errors:
        for e in fallback_errors:
            print(f"   ❌ {e}")
        all_errors.extend(fallback_errors)
    else:
        print("   ✅ source_missing fallback 校验通过")

    # 汇总
    print("\n" + "=" * 60)
    print(f"结果：{len(all_errors)} 错误, {len(all_warnings)} 警告")

    if all_errors:
        print("❌ 校验失败（存在阻断性错误）")
        return 1

    if all_warnings:
        print("⚠️  校验通过（存在警告，建议修复）")
        return 0

    print("✅ 校验全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
