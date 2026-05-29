# ADR-011: 附注动态行/列引擎

**状态**: 已采纳 (Accepted)
**日期**: 2026-05-28
**Sprint**: A.2

## 背景

致同附注 173 章节中约 60+ 章节存在动态行/列需求（应收账款前 N 名 / 子公司明细 / 借款明细等），原 v1 模板写死 rows 数量，无法适配业务数据。

## 决策

引入双 sidecar 数据结构：
- `_columns_meta`: 列元数据（width / is_frozen / col_type / header_path）
- `_dynamic_regions`: 动态区域定义（axis=row|column, start_idx, end_idx, dynamic_source）

判定规则：`row.is_dynamic = row_type.startswith('dynamic_')` / `column.is_dynamic = col_type == 'dynamic'`

引擎层（`dynamic_region_engine.py`，纯函数）：
- `_expand_dynamic_regions`: 行展开
- `_expand_dynamic_columns`: 列展开（含合并表头）
- `aux_balance` row explode（同 aux_code 多月份自动 sum）

## 备选方案

- ❌ 写死所有可能行数：维护成本大、灵活性差
- ❌ 单一 sidecar：行/列耦合难维护

## 后果

正面：
- 60+ 章节统一动态化机制
- 引擎纯函数易测（CI-1/2/3 PBT）
- 与 D2 列动态共用框架

负面：
- 数据结构复杂度增加（两个 sidecar）
- 历史模板需迁移

## 相关 CI

- CI-1: `_dynamic_regions` idx/col_id 有效
- CI-2: row_type=dynamic_* 在 region 内
- CI-3: column_id 全表唯一
