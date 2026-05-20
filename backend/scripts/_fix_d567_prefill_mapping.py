"""一次性修复脚本：D 销售循环 D5/D6/D7 三连 wp_code 错位。

【背景】
致同 2025 修订版编码已重排（D5=应收款项融资 / D6=合同资产 / D7=合同负债），
但 backend/data/prefill_formula_mapping.json 第一段（审定表）3 条 entry 的
wp_code 标签与 wp_name / formula 业务错位（entry 内容已对齐，只是 wp_code 标签写错）。

【修复方式】
仅交换 wp_code 标签（不动 wp_name / formula / cells / account_codes）：
  wp_code='D5' (合同资产审定表)     → wp_code='D6'
  wp_code='D6' (合同负债审定表)     → wp_code='D7'
  wp_code='D7' (应收款项融资审定表) → wp_code='D5'

【匹配条件】
精确匹配 wp_code ∈ {D5, D6, D7} 且 wp_name 含"审定"
预期命中 3 条 entry（Sprint 0 实测确认，N_d_audited_entries=3）。

【不动的 entry】
  - 第二段分析程序 3 条（D5/D6/D7 各 1 条 cells_count=2，wp_name 含"分析程序"不含"审定"）
  - 第三段子明细 D5-1（wp_name='应收款项融资子科目明细' cells_count=2，不含"审定"）
  这些 entry 的 wp_code 与 wp_name 业务已对齐，无需改动。

【可重入（idempotent）】
若所有 3 条审定表 entry 的 wp_code 已与 wp_name 业务一致，则跳过修复并打印提示。

【备份】
首次修复时备份原文件到 backend/data/_archive/prefill_formula_mapping.<YYYYMMDD>.json。

【用完即删】
本脚本是一次性 quickfix（spec workpaper-d-sales-cycle Task 1.1）。
执行成功后由 Task 1.2 跑 reseed，验证通过后删除本脚本。

执行方式：
    python backend/scripts/_fix_d567_prefill_mapping.py

Spec: .kiro/specs/workpaper-d-sales-cycle/{requirements.md §F1, design.md §D1, tasks.md §1.1}
"""
from __future__ import annotations

import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

# 固定路径（脚本独立于 cwd 运行，按 repo 根定位）
REPO_ROOT = Path(__file__).resolve().parents[2]
MAPPING_PATH = REPO_ROOT / "backend" / "data" / "prefill_formula_mapping.json"
ARCHIVE_DIR = REPO_ROOT / "backend" / "data" / "_archive"

# 修复表：基于 wp_name（业务名称是稳定的）确定该 entry 应有的 wp_code
# wp_name → 正确 wp_code（与致同 2025 修订版编码体系一致）
WP_NAME_TO_CORRECT_CODE: dict[str, str] = {
    "合同资产审定表": "D6",
    "合同负债审定表": "D7",
    "应收款项融资审定表": "D5",
}
TARGET_CODES = {"D5", "D6", "D7"}
EXPECTED_HIT_COUNT = 3  # Sprint 0 实测基线 N_d_audited_entries


def _is_target_entry(entry: dict) -> bool:
    """匹配条件：wp_code ∈ {D5,D6,D7} 且 wp_name 含"审定"。"""
    return (
        entry.get("wp_code") in TARGET_CODES
        and "审定" in (entry.get("wp_name") or "")
    )


def _already_fixed(entries: list[dict]) -> bool:
    """检查 3 条审定表 entry 是否已全部业务对齐。"""
    target_entries = [e for e in entries if _is_target_entry(e)]
    if len(target_entries) != EXPECTED_HIT_COUNT:
        return False
    for e in target_entries:
        wp_name = e.get("wp_name", "")
        expected_code = WP_NAME_TO_CORRECT_CODE.get(wp_name)
        if expected_code is None:
            return False
        if e.get("wp_code") != expected_code:
            return False
    return True


def _backup(src: Path) -> Path:
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d")
    dst = ARCHIVE_DIR / f"prefill_formula_mapping.{stamp}.json"
    if dst.exists():
        # 同日重跑：用时间戳区分，避免覆盖已存在的备份
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        dst = ARCHIVE_DIR / f"prefill_formula_mapping.{ts}.json"
    shutil.copy2(src, dst)
    return dst


def main() -> int:
    if not MAPPING_PATH.exists():
        print(f"[ERROR] mapping file not found: {MAPPING_PATH}", file=sys.stderr)
        return 1

    raw = MAPPING_PATH.read_text(encoding="utf-8")
    data = json.loads(raw)
    entries: list[dict] = data.get("mappings") or []

    if _already_fixed(entries):
        print("[SKIP] D5/D6/D7 审定表 wp_code 已业务对齐，无需修复")
        # 打印当前对齐状态以便确认
        for e in entries:
            if _is_target_entry(e):
                print(
                    f"  - wp_code={e['wp_code']!r} "
                    f"wp_name={e['wp_name']!r} "
                    f"cells={len(e.get('cells', []))}"
                )
        return 0

    # 收集匹配的 entry 索引和修复计划
    matches: list[tuple[int, dict, str]] = []  # (idx, entry, target_code)
    for idx, e in enumerate(entries):
        if not _is_target_entry(e):
            continue
        wp_name = e.get("wp_name", "")
        target_code = WP_NAME_TO_CORRECT_CODE.get(wp_name)
        if target_code is None:
            print(
                f"[ERROR] 无法识别的 wp_name: {wp_name!r} "
                f"（idx={idx} wp_code={e.get('wp_code')!r}）。"
                "请人工核查后再跑。",
                file=sys.stderr,
            )
            return 2
        matches.append((idx, e, target_code))

    if len(matches) != EXPECTED_HIT_COUNT:
        print(
            f"[ERROR] 命中 entry 数 = {len(matches)}，期望 = {EXPECTED_HIT_COUNT}。"
            "可能 mapping 文件已被其他改动污染，请人工核查后再跑。",
            file=sys.stderr,
        )
        for idx, e, target in matches:
            print(
                f"  idx={idx} wp_code={e.get('wp_code')!r} "
                f"wp_name={e.get('wp_name')!r} → expect {target}"
            )
        return 3

    # 备份
    backup_path = _backup(MAPPING_PATH)
    print(f"[BACKUP] {backup_path}")

    # 应用修复（仅改 wp_code 字段）
    for idx, e, target_code in matches:
        old_code = e.get("wp_code")
        e["wp_code"] = target_code
        print(
            f"[FIX] idx={idx} wp_name={e.get('wp_name')!r}: "
            f"wp_code {old_code!r} → {target_code!r}"
        )

    # 回写（保持 ASCII=False 中文可读 + 缩进 2 + 末尾换行，对齐源文件风格）
    new_raw = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    MAPPING_PATH.write_text(new_raw, encoding="utf-8")
    print(f"[WRITE] {MAPPING_PATH}")

    # 验证修复结果
    re_data = json.loads(MAPPING_PATH.read_text(encoding="utf-8"))
    if not _already_fixed(re_data.get("mappings") or []):
        print("[ERROR] 修复后仍未对齐，请人工核查", file=sys.stderr)
        return 4

    print("[OK] D5/D6/D7 审定表 wp_code 修复完成 ✅")
    return 0


if __name__ == "__main__":
    sys.exit(main())
