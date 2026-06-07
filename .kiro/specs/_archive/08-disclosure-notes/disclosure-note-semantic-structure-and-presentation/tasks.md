# 实施计划：附注语义结构与前端呈现优化

## 概述

本计划按 P0-MVP → P0-Full → P1 → P2 推进。最高约束：不破坏 `DisclosureNote.table_data` 唯一真源，不破坏现有 `_cell_modes/_cell_meta/_formulas/_tables`，不重复实现 `disclosure-note-linkage-and-slimdown` 已覆盖的真实刷新和 auto_pull。

## P0-MVP：语义结构与呈现原型

- [x] 1. 现状盘点与试点章节选择
  - [x] 1.1 选择会计政策章节 2 个作为政策条款试点：国企版“四、重要会计政策及会计估计”、上市版“三、重要会计政策及会计估计”
  - [x] 1.2 选择报表科目注释 3 个作为数据披露试点：应收账款、固定资产、货币资金
  - [x] 1.3 选择关联方章节 2 个作为复杂披露试点：关联方关系及其交易、关联方应收应付款项
  - [x] 1.4 盘点模板源：`note_template_soe/listed`、`consol_note_sections_*`、`note_template_bindings`、`note_wp_mapping_rules`
  - [x] 1.5 明确 P0-MVP 不新增数据库表、不改 `disclosure_notes` 表结构，仅扩展 JSONB sidecar / DTO / 前端展示
  - [x] 1.6 输出 `docs/reference/note-semantic-pilot-sections.md`
  - _Requirements: 1, 2, 3_

- [x] 2. sidecar 类型定义
  - [x] 2.1 后端新增 `backend/app/schemas/note_semantic_schema.py`
  - [x] 2.2 前端新增 `audit-platform/frontend/src/types/noteSemantic.ts`
  - [x] 2.3 定义 `row_type/table_id/row_id/col_id/policy_clause_id/semantic_section_id`
  - [x] 2.4 测试文件：`backend/tests/test_note_semantic_schema.py`
  - _Requirements: 3.1, 3.2, 3.3, 3.5_

- [x] 2.5 semantic sidecar 生成脚本
  - [x] 2.5.1 新建 `backend/scripts/gen/generate_note_semantic_sidecars.py`
  - [x] 2.5.2 输入 `backend/data/note_template_soe.json` 和 `note_template_listed.json`
  - [x] 2.5.3 为候选章节生成 `section_id/table_id/row_id/col_id/row_type` 建议
  - [x] 2.5.4 输出 sidecar 候选 JSON 到 `backend/data/generated/note_semantic_sidecars.preview.json`
  - [x] 2.5.5 输出 diff 报告到 `docs/reference/note-semantic-sidecar-diff.md`
  - [x] 2.5.6 明确脚本不覆盖主模板
  - _Requirements: 11.1, 11.2_

- [x] 3. row_type 最小兼容
  - [x] 3.1 新增推断函数：根据 `is_total`、label、空 values 推断 row_type
  - [x] 3.2 为试点章节写入 sidecar，不改变 values
  - [x] 3.3 `note_cell_merge` 保留 row_type
  - [x] 3.4 测试：重生成/公式执行/用户编辑后 row_type 不丢失
  - _Requirements: 3.2, 3.4, 3.5_

- [x] 4. table_id / col_id 最小兼容
  - [x] 4.1 为 `_tables[]` 缺失 table_id 的表生成稳定 table_id
  - [x] 4.2 为 headers 生成 columns[].col_id
  - [x] 4.3 公式与来源面板优先读取 col_id，缺失回退 col index
  - [x] 4.4 测试：列重命名后 col_id 不变
  - _Requirements: 3.1, 3.3_

- [x] 5. 政策条款审阅原型
  - [x] 5.1 新建后端条款解析 helper：从 text_content 解析标题层级
  - [x] 5.2 实现 clause_id 生成规则：显式 ID → semantic_section_id + heading_path_hash → 重复标题追加序号
  - [x] 5.3 标题改名但路径不变时保留 clause_id 并标记 title_changed
  - [x] 5.4 新建 `NotePolicyReviewPanel.vue`
  - [x] 5.5 展示本年/上年/模板三栏
  - [x] 5.6 支持只看 changed / pending
  - [x] 5.7 支持批量确认 unchanged 条款
  - [x] 5.8 测试文件：`audit-platform/frontend/src/components/notes/__tests__/NotePolicyReviewPanel.spec.ts`
  - [x] 5.9 后端测试：`backend/tests/services/test_note_policy_clause_parser.py`
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5_

- [x] 6. 数据披露四维上下文栏
  - [x] 6.1 新建 `NoteDisclosureContextBar.vue`
  - [x] 6.2 支持单位、年度、科目/明细、金额口径
  - [x] 6.3 明确单位维度来源：单体项目、合并范围、子公司、关联方主体
  - [x] 6.4 接入试点科目注释章节
  - [x] 6.5 切换上下文后刷新表格和校验状态
  - [x] 6.6 测试文件：`audit-platform/frontend/src/components/notes/__tests__/NoteDisclosureContextBar.spec.ts`
  - _Requirements: 2.1, 2.2, 2.3, 2.4_

- [x] 7. 单元格来源面板最小版
  - [x] 7.1 新建 `NoteCellSourceDrawer.vue`
  - [x] 7.2 展示当前值、mode、binding_id、formula、manual override
  - [x] 7.3 支持跳转底稿/报表/试算表来源
  - [x] 7.4 接入试点章节表格单元格点击
  - [x] 7.5 测试文件：`audit-platform/frontend/src/components/notes/__tests__/NoteCellSourceDrawer.spec.ts`
  - _Requirements: 4.1, 4.2, 4.4, 5.5_

## P0-Full：质量清单、权限边界与离线说明页

- [x] 8. 结构编辑权限边界
  - [x] 8.1 在 `StructureEditor` 中识别 row_type
  - [x] 8.2 普通编辑模式禁止修改结构行
  - [x] 8.3 高权限结构编辑模式允许改 table_title/group_header
  - [x] 8.4 测试：普通助理不能修改 locked structure row
  - _Requirements: 3.4_

- [x] 9. 附注质量清单基础
  - [x] 9.1 新建 `note_quality_checklist_service.py`
  - [x] 9.2 定义 checklist result schema：level/category/section_id/table_id/row_id/col_id/message/route/evidence
  - [x] 9.3 增加 category：formula、stale、manual_override、ai、tieout、style、completeness
  - [x] 9.4 聚合 stale、formula error、manual override、AI unconfirmed
  - [x] 9.5 前端新增 `NoteQualityChecklistPanel.vue`
  - [x] 9.6 支持从清单跳转章节/表格/单元格
  - [x] 9.7 测试文件：`backend/tests/services/test_note_quality_checklist_service.py`
  - _Requirements: 9.1, 9.2, 9.3_

- [x] 10. 离线模板说明页
  - [x] 10.1 扩展 `note_offline_export_service.py`
  - [x] 10.2 新增 `00_填报说明`
  - [x] 10.3 新增 `01_章节清单`
  - [x] 10.4 定义颜色规范：可填、锁定、来源底稿、需复核、校验失败、上年/模板参考
  - [x] 10.5 测试文件：`backend/tests/services/test_note_semantic_offline_export.py`
  - [x] 10.6 测试：导出 workbook 包含说明页和章节清单
  - _Requirements: 7.1, 7.2_

- [x] 10.7 离线导入兼容策略
  - [x] 10.7.1 旧版离线包继续走现有导入路径
  - [x] 10.7.2 新版 semantic workbook 增加隐藏 `_meta` sheet
  - [x] 10.7.3 用户修改隐藏语义列时标记 `structure_conflict`
  - [x] 10.7.4 锁定单元格被改时标记 `locked_cell_conflict`
  - [x] 10.7.5 公式列被改时标记 `formula_override_attempt`
  - [x] 10.7.6 测试文件：`backend/tests/services/test_note_semantic_offline_import.py`
  - [x] 10.7.7 用例：旧包兼容、hidden meta 被改、locked cell 被改、公式列被改
  - _Requirements: 12.1, 12.2, 12.3, 12.4_

## P1：绑定注册表、公式依赖图、披露平衡校验

- [x] 11. note_binding_registry JSON 试点
  - [x] 11.1 新建 `backend/data/note_binding_registry.json`
  - [x] 11.2 为试点章节配置 section/table/row/col 绑定
  - [x] 11.3 新建 `note_binding_registry_service.py`
  - [x] 11.4 支持 resolve binding / validate binding / impact by source
  - [x] 11.5 测试文件：`backend/tests/services/test_note_binding_registry_service.py`
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_

- [x] 11.6 binding registry CI 校验
  - [x] 11.6.1 新建 `backend/scripts/check/check_note_binding_registry.py`
  - [x] 11.6.2 校验 section/table/row/col 存在
  - [x] 11.6.3 校验 wp_code/source 枚举合法
  - [x] 11.6.4 校验同一 cell 无重复 active binding
  - [x] 11.6.5 校验 source_missing 有 fallback 或说明
  - _Requirements: 11.3, 11.4_

- [x] 12. 公式依赖图
  - [x] 12.1 扩展 `_formulas` 读取逻辑支持 section/table/row/col 语义锚点
  - [x] 12.2 旧 `_formulas` 下标锚点继续可用
  - [x] 12.3 新语义锚点优先；与旧锚点冲突时记录 warning，不静默覆盖
  - [x] 12.4 解析 TB/WP/REPORT/NOTE/PRIOR 依赖
  - [x] 12.5 `NoteCellSourceDrawer` 展示依赖图
  - [x] 12.6 公式执行失败进入质量清单
  - [x] 12.7 测试：公式依赖解析、旧公式兼容、冲突 warning、错误展示
  - _Requirements: 4.1, 4.3, 4.5_

- [x] 13. 披露平衡规则试点
  - [x] 13.1 新建 `backend/data/note_disclosure_balance_rules.json`
  - [x] 13.2 新建 `note_disclosure_balance_service.py`
  - [x] 13.3 应收账款、固定资产、关联方余额试点规则
  - [x] 13.4 差异进入质量清单
  - [x] 13.5 测试文件：`backend/tests/services/test_note_disclosure_balance_service.py`
  - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_

- [x] 13.6 关联方披露专项试点
  - [x] 13.6.1 新建 `related_party_disclosure_adapter.py`
  - [x] 13.6.2 接入关联方主体、关系类型、交易类型、本期发生额、期末余额
  - [x] 13.6.3 接入附件/函证证据标识
  - [x] 13.6.4 关联方余额与报表项目 tie-out
  - [x] 13.6.5 测试文件：`backend/tests/services/test_related_party_disclosure_adapter.py`
  - [x] 13.6.6 前端新增 `RelatedPartyDisclosurePanel.vue`
  - [x] 13.6.7 展示主体、关系、交易、余额、证据、tie-out 差异
  - [x] 13.6.8 测试文件：`audit-platform/frontend/src/components/notes/__tests__/RelatedPartyDisclosurePanel.spec.ts`
  - _Requirements: 9.1, 9.2, 9.3, 9.4_

## P2：模板变体矩阵与离线工作包增强

- [x] 14. 模板变体矩阵
  - [x] 14.1 新建 `backend/data/note_template_variant_matrix.json`
  - [x] 14.2 映射 soe/listed + standalone/consolidated 四版本
  - [x] 14.3 前端模板切换时展示对应章节和差异摘要
  - [x] 14.4 测试：同一 semantic_section_id 可找到四版本映射
  - _Requirements: 8.1, 8.2, 8.3, 8.4_

- [x] 15. 离线工作包增强
  - [x] 15.1 新增 `政策条款` sheet
  - [x] 15.2 新增 `科目披露` sheet
  - [x] 15.3 新增 `关联方` sheet
  - [x] 15.4 新增 `99_校验结果` sheet
  - [x] 15.5 隐藏列保留 section/table/row/col/binding/cell_mode
  - [x] 15.6 导入识别公式列修改、结构变更和冲突
  - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5_

- [x] 16. 三式样式一致性测试
  - [x] 16.1 前端预览、Word、Excel 样式映射清单
  - [x] 16.2 三线表、标题缩进、金额列对齐测试
  - [x] 16.3 视觉断言覆盖试点章节
  - _Requirements: 7.2, 9.1_

## 验收

- [x] UAT-1 会计政策：只看有差异条款并批量确认未变条款。
- [x] UAT-2 科目注释：按单位、年度、科目、金额口径切换并查看表格。
- [x] UAT-3 单元格：点击金额看到公式、来源、manual 状态和跳转。
- [x] UAT-4 关联方：表格标题行不被普通编辑误改。
- [x] UAT-5 离线模板：用户能根据说明页完成填报并导入。
- [x] UAT-6 关联方：查看主体、交易、余额、证据和报表差异。
- [x] CI-1 `backend/tests/test_note_semantic_schema.py` 通过。
- [x] CI-2 `test_note_binding_registry_service.py` 通过。
- [x] CI-3 `test_note_disclosure_balance_service.py` 通过。
- [x] CI-4 前端 notes 组件 Vitest 通过。
- [x] CI-5 附注既有测试全集不回归。
- [x] CI-6 `check_note_binding_registry.py` 通过。
- [x] CI-7 新旧离线包导入兼容测试通过。
- [x] CI-8 附注既有测试范围至少包括：`backend/tests/services/test_note_*.py`、离线导入导出测试、`DisclosureEditor` / `GtCNoteTable` / notes components Vitest。
