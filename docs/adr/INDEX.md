# ADR 索引

架构决策记录（Architecture Decision Records）汇总。

## ADR 列表

### 数据/账本/底稿（001-006）

- [ADR-001: 辅助维度冗余存储](./ADR-001-auxiliary-dimension-redundant-storage.md)
- [ADR-002: 账本视图重构](./ADR-002-ledger-view-refactor.md)
- [ADR-003: 账本导入恢复 Playbook](./ADR-003-ledger-import-recovery-playbook.md)
- [ADR-004: 账本激活隔离](./ADR-004-ledger-activate-isolation.md)
- [ADR-005: 异步激活](./ADR-005-async-activate.md)
- [ADR-006: SSE vs Polling 导入进度](./ADR-006-sse-vs-polling-import-progress.md)

### 附注模块基础（007-010）

- [ADR-007: 附注三态格式权威源](./ADR-007-note-triple-format-source-of-truth.md)
- [ADR-008: 附注 cell mode 持久化](./ADR-008-note-cell-mode-persistence.md)
- [ADR-009: 致同 Word 模板样式命名空间](./ADR-009-gt-word-template-style-namespace.md)
- [ADR-010: 附注自定义模板版本化](./ADR-010-note-custom-template-versioning.md)

### 附注全维度增强（011-022，本 spec）

- [ADR-011: 附注动态行/列引擎](./ADR-011-note-dynamic-row-column-engine.md)（D1/D2，Sprint A.2）
- [ADR-012: 附注 wp_data 多源 fallback 链](./ADR-012-note-wp-data-multi-source-fallback.md)（D3/D4，Sprint A.2）
- [ADR-013: 附注 auto_trim v2 三级裁剪](./ADR-013-note-auto-trim-v2-three-level.md)（D5，Sprint A.3）
- [ADR-014: 附注文字段落 Jinja 模板引擎](./ADR-014-note-jinja-paragraph-engine.md)（D7，Sprint A.4）
- [ADR-015: 集团附注模板基线多层级 lineage](./ADR-015-group-note-baseline-multi-level.md)（D6，Sprint A.7）
- [ADR-016: 附注章节级协作锁集成](./ADR-016-note-collaboration-lock-integration.md)（D9，Sprint A.6）
- [ADR-017: 合并附注汇总服务](./ADR-017-consol-note-aggregation-service.md)（D12，Sprint B.0）
- [ADR-018: 合并附注内部抵销规则注册器](./ADR-018-consol-elimination-rules-registry.md)（D12，Sprint B.0）
- [ADR-019: 附注章节序号动态层级重构](./ADR-019-note-section-numbering-restructure.md)（D13，Sprint A.0）
- [ADR-020: 章节序号 5 级层级格式注册器](./ADR-020-note-section-5-level-format-registry.md)（D13 子专题，Sprint A.0）
- [ADR-021: 国企↔上市附注模板丝滑切换](./ADR-021-soe-listed-template-conversion.md)（D14，Sprint A.5）
- [ADR-022: 附注离线分发与一键导入](./ADR-022-note-offline-distribution.md)（D15，Sprint C.0）
- [ADR-023: 合并附注 V2 完整章节集（180 章节）](./ADR-023-consol-disclosure-v2-full-section-set.md)（D8，Sprint B.1）

## CI 卡点 22 项汇总

| CI ID | 描述 | ADR | Sprint |
|-------|------|-----|--------|
| CI-1 | `_dynamic_regions` idx/col_id 有效 | ADR-011 | A.1 |
| CI-2 | row_type=dynamic_* 在 region 内 | ADR-011 | A.1 |
| CI-3 | column_id 全表唯一 | ADR-011 | A.1 |
| CI-4 | REGION/WP 公式解析 | - | A.3 |
| CI-5 | 动态删除合计 PBT | - | A.2 |
| CI-6 | round-trip PBT | - | A.8 |
| CI-7 | apply_baseline lineage | ADR-015 | A.7 |
| CI-8 | auto_trim v2 三级互斥 | ADR-013 | A.3 |
| CI-9 | fallback 链 ≤ 3 级 | ADR-012 | A.2 |
| CI-10 | `_cell_provenance` 必有 source | ADR-012 | A.2 |
| CI-11 | Jinja 模板必有变量声明 | ADR-014 | A.4 |
| CI-12 | 合并章节序号不冲突 | ADR-023 | B.1 |
| CI-13 | 锁释放必触发 | ADR-016 | A.6 |
| CI-14 | 版本树无环（DAG） | - | C.2 |
| CI-15 | `consol_aggregation` source 必有 child_section_id | ADR-017 | B.0 |
| CI-16 | 多层合并 lineage 链无环 | ADR-017 | B.0 |
| CI-17 | elimination_rules wp_code 必存在 | ADR-018 | B.0 |
| CI-18 | section_id 唯一 + level 1-5 + parent 引用有效 | ADR-019 | A.0 |
| CI-19 | rendered_number 在 scope 内唯一 | ADR-019 | A.0 |
| CI-20 | 国企↔上市互转 round-trip 无丢失 PBT | ADR-021 | A.5 |
| CI-21 | `_meta_` sheet 必有 section_id + binding_hash | ADR-022 | C.0 |
| CI-22 | 导出→导入 round-trip 字段级 diff 无丢失 PBT | ADR-022 | C.0 |
