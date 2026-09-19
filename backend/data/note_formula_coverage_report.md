# 附注公式数据覆盖率报告

> 由 `scripts/gen/generate_note_formula_data.py` 自动生成（2026-07-26 11:33:00）。
> spec: `.kiro/specs/disclosure-note-formula-data-population/`

## 章节配对

- 已配对章节（listed 优先）：**146**
  - listed：84；soe：60
- 未在任何模板找到 section_number：0 []
- 结构未对齐跳过：2
  - 八、1: tables_missing
  - 十一、关联交易情况: table_count_mismatch

## 变动表恒等式（期末 = 期初 + 增 − 减）

- 产出公式：**0** 条，覆盖 **0** 个章节
- 写入 binding：**0** 格（仅覆盖 manual+todo 候选）

## 合计 / 小计

- 登记预设：**876** 条（逐列）
- binding 追溯标注：**393** 行
- **不写公式 binding**（决策 2）：计算真源仍是 `_backfill_totals`，避免与生成路径第二遍求值双写

## 候选格三分类（Property 16）

- 候选单元格总数（data 行 × 有语义列 × 当前 manual+todo）：**2953**
- 已公式化：**0**
- 被跳过的候选：**154**
- 仍 manual+todo：**2799**
- 校验：0 + 154 + 2799 = 2953（应等于 2953）

## 跳过原因分布

| reason | 次数 |
| --- | --- |
| non_summable_semantic | 382 |
| movement_quad_incomplete | 252 |
| duplicate_label | 156 |
| target_not_manual_todo | 138 |
| total_at_first_row | 117 |
| empty_sum_range | 11 |
| rows_empty | 11 |

## 预设登记

- 写入 `formula_presets_seed.json` 条目：**876**

## 未产出的公式类型（诚实说明）

- `aging`：`refill_sections` / 生成第二遍的 ctx **未注入 `aging_data`**（Wave 0 §V1）→ 本轮不产出账龄公式，避免写入永不可求值的 binding。
- `report`（报表→附注写值）：按用户拍板的决策 1，报表↔附注**只做校验不做写值**，故不产出 report 取数 binding；勾稽关系由 `logic_check` 预设承载。
