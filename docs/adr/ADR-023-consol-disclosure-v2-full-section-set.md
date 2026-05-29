# ADR-023: 合并附注 V2 完整章节集（180 章节）

**状态**: 已采纳 (Accepted)
**日期**: 2026-05-28
**Sprint**: B.1

## 背景

ADR-017 提供了汇总服务，但需要顶层编排函数将所有部分串起来：子公司树拉取 → 章节映射 → 汇总 → 序号重排 → Jinja 渲染 → lineage 写入。

## 决策

新建 `consol_disclosure_service.generate_full_consol_notes` 模块级 async 函数（V2），7 步骤流水线：

1. **子公司树拉取**: 调 `consol_tree_service.build_tree`（已有但附注模块未调用）
2. **章节映射加载**: 从 `consol_section_mapping.csv` 加载 P-5 标注
3. **aggregate_section 汇总**: 共有 173 章节调 ConsolNoteAggregationService
4. **7 合并专用章节 wp_data 强化**: `_CONSOL_SECTION_WP_BINDINGS`（goodwill→h08 / MI→g / forex→m）
5. **scope=consolidated 序号重排**: `NoteSectionNumberingService.render_all`
6. **Jinja 合并版 vars 渲染**: subsidiary_count / consolidated_revenue 等
7. **lineage 写入**: `template_lineage` 多层级

抵销前后双列：`_add_elimination_columns` 标记 `_has_elimination_columns=True`

事件驱动：`handle_consol_subsidiary_changed` 监听 `CONSOL_SUBSIDIARY_CHANGED` 事件 → 自动 stale

## 备选方案

- ❌ 类层级方法（class hierarchy）：状态难管理
- ❌ 单函数纯顺序：测试难

## 后果

正面：
- 合并附注完整 173 + 7 = 180 章节
- 子公司清单实时拉取（不写死）
- 7 步骤可独立测试

负面：
- 单次调用耗时（N 子公司 × M 章节）
- 大集团需 Redis 缓存优化

## 相关 CI

- CI-12: 合并章节序号不冲突
