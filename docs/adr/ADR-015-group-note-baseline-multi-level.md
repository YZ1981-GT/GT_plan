# ADR-015: 集团附注模板基线多层级 lineage

**状态**: 已采纳 (Accepted)
**日期**: 2026-05-28
**Sprint**: A.7

## 背景

集团合并附注涉及多层级（孙合并 → 子合并 → 总合并），原 Sprint 3 仅项目级模板，无跨项目基线机制。

## 决策

新建 `group_note_template_baseline` 表 + `template_lineage` JSONB 字段：

- `parent_baseline_id`: 父基线引用（孙→子→总递归）
- `version`: v{major}.{minor}（语义化版本）
- `template_type`: soe | listed
- `sections_data`: 完整 sections 快照

核心 API（`group_note_baseline_service.py`）：
- `save_baseline`: 自动版本号
- `apply_baseline`: 用 `merge_table_data_preserving_cell_modes` 保留 manual 修改
- `diff_baseline`: 章节级差异
- `sync_baseline`: 批量同步多 child
- `get_baseline_versions`: 历史版本
- `upgrade_baseline`: bump minor/major + needs_notification 标志
- `suggest_feedback`: child 反哺基线建议
- `_resolve_lineage_chain`: 多层级递归

CI-7 卡点：apply_baseline 后 `template_lineage` 必有 `baseline_id`。

## 备选方案

- ❌ 项目级模板：无法跨项目复用
- ❌ 全局模板：无法支持多版本并存

## 后果

正面：
- 集团统一标准 + 子公司本地化兼容
- D14 国企↔上市切换基于此 lineage
- 多层级合并 lineage 链可追溯

负面：
- 基线管理复杂度（partner 权限、版本锁定）
- 需 UI 配套（C.3.6 已实现）

## 相关 CI

- CI-7: apply_baseline 后 lineage 必有 baseline_id
