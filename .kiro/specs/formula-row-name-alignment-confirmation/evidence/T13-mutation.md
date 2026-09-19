# Task 13 — 变异检验（守卫有效性证明）

产物：
- 变异脚本 `backend/scripts/diagnose/mutate_row_name_alignment_guards.py`
- 判定 JSON `evidence/T13-mutation-verdict.json`（`"pass": true`）
- 新增隔离守卫（变异过程真实发现缺陷后补）

## 四锚点全 RED（`"pass": true`）

| 锚点 | 变异 | 预期打红守卫 | 结果 |
|---|---|---|---|
| M1 | `classify` 忽略 saved_mapping（`if False and ...`）| `test_classify_saved_mapping_valid` / `..._stale` | **RED** |
| M2 | `load_active_mappings` where 漏 `wp_code` | `test_scope_isolation_wp_code` | **RED** |
| M3 | `_load_active_rows` where 漏 `year` | `test_confirm_baseline_isolated_by_year` | **RED**（`MappingConflictError: base=None != current active=1`）|
| M4 | `classify` 归一后多命中判成 `auto_matched` | `test_classify_normalized_multi_hit` / `test_property_normalized_multi_hit_never_auto` | **RED** |

## 变异真实暴露并修复的守卫缺陷（GREEN→RED）

变异第一轮 M2/M3 判 **GREEN**（守卫缺陷），非放过：
- **M2 GREEN 根因**：原隔离测试两个作用域用**同 row_key**，`load_active_mappings` 的 `out[row_key]` dict 覆盖
  掩盖了「串行」——漏 wp_code 捞到 2 行但 `len==1` 仍成立。
  **修**：隔离测试改用**不同 row_key**（`k1_row` / `d3_row`），断言 `set(keys)=={'k1_row'}`，漏 wp_code 即打红。
- **M3 GREEN 根因**：`_load_active_rows` 漏 year 在「异 row_key 异 year」场景不产生可观测差异。
  **修**：新增 `test_confirm_baseline_isolated_by_year`（**同 row_key 异 year** 各首次确认，都应是 v1）；
  漏 year 会把上年 active 当本年基线 → `base=None` 冲突 → 打红。

## 四态判定与工程细节

- 四态：RED（打红且命中预期测试）/ GREEN（守卫缺陷）/ ANCHOR-MISS（锚点 count≠1）/ WRONG-TEST
- 锚点唯一：每个 `old` 在目标文件 `count==1` 才变异，否则 ANCHOR-MISS
- **finally 字节复原**：变异后无论成败都 `write_text(src)` 还原
- **subprocess 编码**：`encoding="utf-8", errors="replace"`（Windows 默认 gbk 会 UnicodeDecodeError 吞掉 pytest 中文输出 → 误判 WRONG-TEST，已修）

## 基线 + 复跑

变异前基线两测试文件全绿（脚本内 `_verify_baseline`）；复原后 36 passed（含 3 个新隔离守卫）。
