"""ACNR IE ↔ Catalog Sync Check — CI 守卫。

校验 {cycle}_cycle_ie_manifest.yaml 与 global_catalog.json 的 import_export 段一致。

两种登记模式（差别只在 Step 4 跑不跑）：

- **全量登记**（`_SUPPORTED_CYCLES`）：manifest 是该循环 I/E 的完整清单，
  Step 3 + Step 4 都跑 —— catalog 有 I/E 而 manifest 未登记也算 error。
- **部分登记**（`_PARTIAL_CYCLES`）：manifest 只登记该循环的一部分 sheet
  （如 X-3 调整分录汇总表），只跑 Step 3，**跳过 Step 4**；未被 manifest
  覆盖的启用条目改为**计数并与基线比对（只许下调）**，不逐条判 error。

检测项：
1. Manifest 中有但 catalog 中找不到 sheet_code 的条目（warning）
2. Catalog 中有 import_export 但 manifest 中未登记的 sheet
   —— 全量登记循环判 error；部分登记循环改计数比对基线
3. 字段值不匹配：api_prefix / item_id / storage_field / import_order / depends_on_sheets

Requirements: 18.5；部分登记模式 = spec x3-adjustment-entry-import-export 任务 8.2
（_Requirements: 5.2, 8.6, 11.3）
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

# ---------------------------------------------------------------------------
# 路径设置
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_BACKEND_ROOT = _REPO_ROOT / "backend"
_ACNR_DATA_DIR = _BACKEND_ROOT / "data" / "acnr"
_CATALOG_PATH = _ACNR_DATA_DIR / "global_catalog.json"
_MANIFEST_DIR = _ACNR_DATA_DIR / "sources"

# 全量登记的循环（波 1: D, 波 2: K/F/G/H）—— Step 3 + Step 4 都跑
_SUPPORTED_CYCLES = ["D", "K", "F", "G", "H"]

# 部分登记的循环（spec x3-adjustment-entry-import-export 任务 8.2）。
# 这三份 manifest 标了 `partial: true`：只登记本循环的 X-3 调整分录汇总表
# （L 2 条 / M 10 条 / N 4 条），不是该循环 I/E 的全量清单。
# 故只跑 Step 3，跳过 Step 4 —— Step 4 会把「catalog 有 I/E 而 manifest 未登记」
# 判 error，逼人把未经核验的存量孤儿抄进生成源 = 把错值锁成基线（违反 R8.6），
# 且那些孤儿属别的 spec 半径。改由 `_PARTIAL_UNCOVERED_BASELINE` 计数兜住。
_PARTIAL_CYCLES = ["L", "M", "N"]

# 部分登记循环「catalog 已启用 I/E 但 manifest 未覆盖」的条目数基线 —— 只许下调。
#
# 口径（可复算）：catalog.sheets 中 `cycle` == 该循环且 `import_export.enabled`
# 为真的 sheet_code 集合，减去同循环 manifest `entries` 的 sheet_code 集合，取势。
# 复算 = 跑本脚本读 stdout 的「未被 manifest 覆盖 N 条」。
#
# 实测（2026-08-15，committed catalog）合计 10 条存量孤儿：
#   L 8 —— L1-2 / L1-3 / L3-2 / L3-3 / L4-2 / L4-3 / L5-2 / L5-3
#   M 0 —— M 循环 catalog 侧当前无任何已启用 I/E
#   N 2 —— N4-2 / N4-3
#
# 为什么只许下调：这个数字是**待消化的存量欠账**，不是目标值。
#   变大 = 又有人往 catalog 塞了未登记的启用条目（回归）⇒ 打红；
#   变小 = 欠账被消化（补进 manifest 或停用）⇒ 必须把本基线同步下调，
#          否则守卫会用一个已经过时的宽松上限继续放行（基线自我失效）。
_PARTIAL_UNCOVERED_BASELINE = {"L": 8, "M": 0, "N": 2}

# 需要精确比对的字段（manifest 与 catalog.import_export 共有）
_COMPARE_FIELDS = [
    "api_prefix",
    "item_id",
    "storage_field",
    "import_order",
    "depends_on_sheets",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _normalize_item_id(value) -> list[str] | str:
    """Normalize item_id for comparison — list 排序后比较。"""
    if isinstance(value, list):
        return sorted(value)
    return value


def _normalize_depends_on_sheets(value) -> list[str]:
    """Normalize depends_on_sheets — 始终作为排序 list 比较。"""
    if value is None:
        return []
    if isinstance(value, list):
        return sorted(value)
    return [value]


def _normalize_field(field_name: str, value):
    """按字段名 normalize 值以便比较。"""
    if field_name == "item_id":
        return _normalize_item_id(value)
    if field_name == "depends_on_sheets":
        return _normalize_depends_on_sheets(value)
    return value


def _checked_cycles() -> list[str]:
    """被检查的全部循环 = 全量登记 + 部分登记（保持各自声明顺序）。"""
    return [*_SUPPORTED_CYCLES, *_PARTIAL_CYCLES]


def _config_contradictions() -> list[str]:
    """两个循环组的配置自检 —— 不自洽时必须打红，不许静默偏向某一支。

    ① 同一循环不能既在 `_SUPPORTED_CYCLES` 又在 `_PARTIAL_CYCLES`：两种模式
       对 Step 4 的判定正好相反，重叠时无论哪一支胜出都会让另一支的判据静默
       失效（也会让同一份 manifest 被处理两遍）。
    ② 每个部分登记循环必须有未覆盖条目数基线：缺基线 = Step 4 跳过之后没有
       任何东西接住那些条目，等于凭空放宽。
    """
    problems: list[str] = []
    overlap = sorted(set(_SUPPORTED_CYCLES) & set(_PARTIAL_CYCLES))
    if overlap:
        problems.append(
            f"循环分组配置自相矛盾：{overlap} 同时出现在 _SUPPORTED_CYCLES"
            f"（全量登记，跑 Step 4）与 _PARTIAL_CYCLES（部分登记，跳过 Step 4）"
        )
    missing = sorted(set(_PARTIAL_CYCLES) - set(_PARTIAL_UNCOVERED_BASELINE))
    if missing:
        problems.append(
            f"循环分组配置不完整：部分登记循环 {missing} 缺"
            f" _PARTIAL_UNCOVERED_BASELINE 基线，未覆盖条目数无人比对"
        )
    return problems


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    """执行 IE ↔ Catalog sync 检查。"""
    errors: list[str] = []

    # --- Step 0: 循环分组配置自检（不自洽时不做后续判定，直接打红）---
    contradictions = _config_contradictions()
    if contradictions:
        print(
            f"[ACNR ie-sync] FAIL — 发现 {len(contradictions)} 处不一致：",
            file=sys.stderr,
        )
        for problem in contradictions:
            print(f"  ✗ {problem}", file=sys.stderr)
        return 1

    # --- Step 1: 加载 catalog ---
    if not _CATALOG_PATH.exists():
        print(
            f"[ACNR ie-sync] ERROR: {_CATALOG_PATH} 不存在。",
            file=sys.stderr,
        )
        return 1

    try:
        catalog_data = json.loads(_CATALOG_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        print(
            f"[ACNR ie-sync] ERROR: 读取 global_catalog.json 失败: {e}",
            file=sys.stderr,
        )
        return 1

    # 构建 sheet_code → import_export 映射（全量登记 + 部分登记的循环）
    checked_cycles = _checked_cycles()
    catalog_sheets: dict[str, dict] = {}
    catalog_sheets_by_cycle: dict[str, dict[str, dict]] = {c: {} for c in checked_cycles}
    for sheet in catalog_data.get("sheets", []):
        cycle = sheet.get("cycle", "")
        if cycle not in catalog_sheets_by_cycle:
            continue
        sheet_code = sheet.get("sheet_code", "")
        ie = sheet.get("import_export")
        if ie and ie.get("enabled"):
            catalog_sheets[sheet_code] = ie
            catalog_sheets_by_cycle[cycle][sheet_code] = ie

    # --- Step 2: 遍历每个被检查的 cycle manifest ---
    warnings: list[str] = []
    partial_stats: list[dict] = []
    for cycle in checked_cycles:
        is_partial = cycle in _PARTIAL_CYCLES
        manifest_path = _MANIFEST_DIR / f"{cycle.lower()}_cycle_ie_manifest.yaml"
        if not manifest_path.exists():
            print(
                f"[ACNR ie-sync] ERROR: {manifest_path} 不存在。",
                file=sys.stderr,
            )
            return 1

        try:
            manifest_data = yaml.safe_load(
                manifest_path.read_text(encoding="utf-8")
            )
        except (yaml.YAMLError, OSError) as e:
            print(
                f"[ACNR ie-sync] ERROR: 读取 {manifest_path.name} 失败: {e}",
                file=sys.stderr,
            )
            return 1

        manifest_entries = manifest_data.get("entries", [])
        manifest_sheet_codes: set[str] = set()
        pending_in_catalog: list[str] = []

        # --- Step 3: 逐条比对 manifest → catalog（两种模式都跑）---
        cycle_catalog_sheets = catalog_sheets_by_cycle.get(cycle, {})
        for entry in manifest_entries:
            sheet_code = entry.get("sheet_code", "")
            manifest_sheet_codes.add(sheet_code)

            if sheet_code not in cycle_catalog_sheets:
                # 全量登记循环：M0 阶段 classification 可能未按子 sheet 粒度注册
                # （如 D1-1 在 classification 中只有 D1）；
                # 部分登记循环：committed catalog 尚未启用该条（待登记器补丁）。
                # 两者都报 warning 不报 error。
                pending_in_catalog.append(sheet_code)
                reason = (
                    "committed catalog 尚未启用该条，待登记器补丁"
                    if is_partial
                    else "classification 粒度不足，首期可接受"
                )
                warnings.append(
                    f"[{cycle}] Manifest 条目 '{sheet_code}' 在 catalog 中"
                    f"未找到对应的 import_export（{reason}）"
                )
                continue

            catalog_ie = cycle_catalog_sheets[sheet_code]

            # 逐字段比对
            for field in _COMPARE_FIELDS:
                manifest_val = _normalize_field(field, entry.get(field))
                catalog_val = _normalize_field(field, catalog_ie.get(field))

                if manifest_val != catalog_val:
                    errors.append(
                        f"[{cycle}] '{sheet_code}'.{field} 不一致 — "
                        f"manifest={manifest_val!r}, catalog={catalog_val!r}"
                    )

        # --- Step 4: 检查 catalog 有 import_export 但 manifest 未登记的 sheet ---
        cycle_catalog_sheets = catalog_sheets_by_cycle.get(cycle, {})
        uncovered = sorted(
            code for code in cycle_catalog_sheets if code not in manifest_sheet_codes
        )

        if is_partial:
            # 部分登记模式：**跳过 Step 4 的逐条 error 判定**，改为计数 + 基线
            # 比对（只许下调）。未覆盖条目是别的 spec 半径内的存量欠账，抄进
            # 本 manifest 等于把未经核验的值锁成基线。
            baseline = _PARTIAL_UNCOVERED_BASELINE[cycle]
            partial_stats.append(
                {
                    "cycle": cycle,
                    "catalog_enabled": len(cycle_catalog_sheets),
                    "manifest_entries": len(manifest_sheet_codes),
                    "uncovered": len(uncovered),
                    "uncovered_codes": uncovered,
                    "baseline": baseline,
                    "pending_in_catalog": len(pending_in_catalog),
                }
            )
            if len(uncovered) > baseline:
                errors.append(
                    f"[{cycle}] 部分登记循环未被 manifest 覆盖的启用条目"
                    f" {len(uncovered)} 条 > 基线 {baseline} 条（只许下调）"
                    f" —— 当前未覆盖：{uncovered}"
                )
            elif len(uncovered) < baseline:
                errors.append(
                    f"[{cycle}] NEEDS_BASELINE_LOWERING — 部分登记循环未被"
                    f" manifest 覆盖的启用条目已降至 {len(uncovered)} 条"
                    f"（基线 {baseline} 条），必须把"
                    f" _PARTIAL_UNCOVERED_BASELINE['{cycle}'] 同步下调到"
                    f" {len(uncovered)}，否则基线自我失效"
                )
            continue

        for sheet_code in uncovered:
            errors.append(
                f"[{cycle}] Catalog 中 '{sheet_code}' 有 import_export"
                f"（enabled=true）但 manifest 中未登记"
            )

    # --- Step 5: 部分登记循环的计数汇报（无论过红都输出，便于 CI 直接读数）---
    # 注意：这些行**不以 ✗ 起头** —— 下游（snapshot_x3_baseline._count_ie_sync_drift）
    # 以 ✗ 行数与表头「发现 N 处不一致」交叉核对条目数，混进去会让口径漂掉。
    if partial_stats:
        print(
            f"[ACNR ie-sync] 部分登记循环 {len(partial_stats)} 个"
            f"（只跑 Step 3；跳过 Step 4，改计数比对基线）："
        )
        for stat in partial_stats:
            print(
                f"  · [{stat['cycle']}] catalog 启用 {stat['catalog_enabled']} 条"
                f" / manifest 登记 {stat['manifest_entries']} 条"
                f" / 未被 manifest 覆盖 {stat['uncovered']} 条"
                f"（基线 {stat['baseline']}）"
                f" / manifest 待 catalog 启用 {stat['pending_in_catalog']} 条"
            )
            if stat["uncovered_codes"]:
                print(f"      未覆盖：{', '.join(stat['uncovered_codes'])}")
        total_uncovered = sum(s["uncovered"] for s in partial_stats)
        total_baseline = sum(s["baseline"] for s in partial_stats)
        print(
            f"  合计未被 manifest 覆盖 {total_uncovered} 条"
            f"（基线合计 {total_baseline}，只许下调）。"
        )

    # --- Step 6: 输出结果 ---
    if not errors:
        total_ie_sheets = sum(len(v) for v in catalog_sheets_by_cycle.values())
        msg = (
            f"[ACNR ie-sync] OK — "
            f"manifest 与 catalog import_export 段一致"
            f"（{len(_SUPPORTED_CYCLES)} 全量登记循环"
            f" + {len(_PARTIAL_CYCLES)} 部分登记循环, "
            f"{total_ie_sheets} 条 I/E sheet）。"
        )
        if warnings:
            msg += (
                f"\n  ℹ {len(warnings)} 条 manifest 条目在 catalog 中"
                f"无对应 sheet（classification 粒度不足，首期可接受）。"
            )
        print(msg)
        return 0

    print(
        f"[ACNR ie-sync] FAIL — 发现 {len(errors)} 处不一致：",
        file=sys.stderr,
    )
    for err in errors:
        print(f"  ✗ {err}", file=sys.stderr)
    print("", file=sys.stderr)
    print(
        "修复方式：更新 manifest YAML 或重新运行 generate_catalog.py 使二者同步。",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
