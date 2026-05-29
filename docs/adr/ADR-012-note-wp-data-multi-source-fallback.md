# ADR-012: 附注 wp_data 多源 fallback 链

**状态**: 已采纳 (Accepted)
**日期**: 2026-05-28
**Sprint**: A.2

## 背景

附注 binding 单源不够：底稿可能未导入 / TB 可能未审定 / 用户可能直接手填，需要主源失败自动回退。

## 决策

引入 binding 多源 fallback 链：

```json
{
  "primary": {"source": "wp_data", "wp_code": "h08", ...},
  "fallback": [
    {"source": "trial_balance", "account_codes": ["1601"]},
    {"source": "manual", "default_value": null}
  ]
}
```

每个 cell 记录 `_cell_provenance`，包含：
- `source`: 实际取数来源
- `fallback_used`: 是否回退
- `fallback_index`: 回退到第几级
- `value`: 实际取数值

约束：
- `MAX_FALLBACK_DEPTH=3`（CI-9）
- `provenance` 必须有 `source` 字段（CI-10）
- 空值语义：`None`/`[]` 走 fallback；`0`/`""` 视为有效命中

## 备选方案

- ❌ 单源 + 缺失抛错：流程中断
- ❌ 静默用 0 替代：审计追溯困难

## 后果

正面：
- 流程鲁棒性提升
- 审计师可点击 cell 看到完整溯源链
- provenance 支持 cell 级数据源 chip 显示

负面：
- fallback 性能开销（最多 3 级）
- 用户需理解多源优先级

## 相关 CI

- CI-9: fallback 链 ≤ 3 级
- CI-10: `_cell_provenance` 必有 `source` 字段
