# 合并附注明细模板与多企业行映射规则 — 任务清单

只勾本轮代码及验证均完成的任务；历史通过不替代本轮实测。

## Phase 1: 数据模型与模板 CRUD（R1 / D§二~§五）

- [x] 1. V185/R185 迁移：5 张表（`consol_note_detail_template` / `_version` / `_binding` / `consol_note_mapping_rule` / `_binding`）+ 索引 + 约束（R1.2 / R2.4 / D§二）— **实际为 V186/R186**（V185 被 multi-window-ledger-workbench 占用）
- [x] 2. ORM `consol_note_mapping_models.py`：5 个 ORM 类，主键全部 `default=uuid.uuid4`（D§二.3）
- [x] 3. 模板 CRUD service `consol_note_detail_template_service.py`：create / list / get / add_version / get_versions / soft_delete / change_visibility + 绑定 bind/get/get_bindings + 编辑约束 check_row_deletion_impact（R1.2 / R1.3 / R1.4 / D§五.1~2）
- [x] 4. 模板 CRUD router `consol_note_detail_templates.py`：11 个端点，注册至 `router_registry/system.py` §6（D§五.1~2）
- [x] 5. 模板绑定 service + router：bind / get / 切换版本二次确认参数（R1.3.4~R1.3.5 / D§五.2）— 合入 Task 3/4
- [x] 6. 模板编辑约束：删除已引用行时检测受影响规则数和企业数，返回 `affected_count`，前端须传 `confirm=true`（R1.4.2）— 合入 Task 3
- [x] 7. Phase 1 测试：23 例全绿（模板 CRUD 5 + 列表/查询 4 + 版本 3 + 软删除 2 + 可见范围 2 + 绑定 4 + 删除检查 3）（D§九）

## Phase 2: 来源扫描与建议（R1.1 / R2.1 / R3.1 / D§三~§六）

- [x] 8. 来源读取 service `consol_note_detail_source_service.py`：按章节从数据叶子企业 `disclosure_notes.table_data.rows` 提取行标签/行类型/稳定键（R2.1.1）
- [x] 9. 结构指纹算法 `compute_source_structure_hash`：SHA-256，排除金额，含伪键生成（R2.1.2 / D§三）
- [x] 10. 企业分组：相同 `source_structure_hash` 归组，返回 `[{hash, entities: [...], rows: [...]}]`（R2.1.3）
- [x] 11. 模板建议算法 `suggest_template_rows`：精确→别名→模糊→历史复用→人工，返回排序后的建议列表（R1.1 / D§六）
- [x] 12. preview API `POST .../preview`：生成 `preview_token` + 各组映射状态 + stale 企业标识（R4.1 / D§四）
- [x] 13. suggest-template API `POST .../suggest-template`：从来源扫描生成模板行建议（D§五.5）
- [x] 14. Phase 2 测试：25 例全绿（指纹稳定性 7 + 提取 5 + 分组 3 + 建议五级匹配 10），与 Phase 1 合跑 48 passed 无回归（D§九）

## Phase 3: 映射规则与确认（R2.2~R2.4 / R3.2~R3.3 / D§四~§五）

- [x] 15. 映射规则 CRUD service `consol_note_mapping_rule_service.py`：create / upgrade_version / deactivate / get_versions / get_active_rules / get_active_rule_for_hash + confirm_mapping + detect_stale_bindings + get_binding_status_summary（R2.4 / R3.1 / R3.2）
- [x] 16. 映射规则 router：5 个端点（rules GET/POST + deactivate + versions + confirm-mapping），追加至同一 router 文件（D§五.3~4）
- [x] 17. confirm_mapping API：校验 `template_version_id` + `source_structure_hash` 未变化，否则 409（R4.2 / D§四）— 合入 Task 15
- [x] 18. 绑定管理：按企业 `node_key` 创建/更新 `consol_note_mapping_binding`，stale 检测与状态扭转（R3.1 / R3.2）— 合入 Task 15
- [x] 19. 批量确认：同组内映射确认一次后批量创建 binding（R2.3.2）— 合入 Task 15 confirm_mapping
- [x] 20. 单独排除企业：排除后该企业 binding 标记 `excluded`（R2.3.4）— 合入 Task 15 confirm_mapping
- [x] 21. Phase 3 测试：13 例全绿（规则 CRUD 5 + 升版 1 + 停用 2 + confirm_mapping 4 + stale 2），三 Phase 合跑 61 passed 无回归（D§九）

## Phase 4: 应用写入与穿透（R4.3~R4.4 / R5.4 / D§四~§八）

- [x] 22. apply service `consol_note_detail_apply_service.py`：校验 `preview_token` + hash → 按规则转换来源行 → 金额求和 → 写 `consol_note_data.data.rows`（R4.1.3 / R4.3）
- [x] 23. 手工保护：apply 时 `manual_cells` / `locked_cells` / `cell_state=locked` 全部跳过（R4.4）— 合入 Task 22
- [x] 24. 阻断规则：未处理行阻断该章节 / stale 企业数据不参与但不阻断其他（R4.3.1~R4.3.3）— 合入 Task 22
- [x] 25. 行级穿透：每次 apply 在 `consol_note_data.data` 中写入 `_detail_provenance`，格式兼容 `consolidation_breakdown`（R5.4.1~R5.4.2）— 合入 Task 22
- [x] 26. stale 联动：apply 后清除 `is_stale = False`（D§八.2）— 合入 Task 22
- [x] 27. Phase 4 测试：9 例全绿（全链路金额求和 + 穿透写入 + 手工保护 + locked 跳过 + 无绑定阻断 + 无确认阻断 + stale 清除 + ignore 排除 + map_merge 合并），四 Phase 合跑 70 passed 无回归（D§九）

## Phase 5: 前端（R5.1~R5.3 / D§七）

- [ ] 28. `ConsolNoteDetailTemplateEditor.vue`：模板行编辑器（拖拽排序 / 新增 / 删除 / 改名 / 版本发布）+ 建议导入按钮（R1.4 / D§七.5）
- [ ] 29. `ConsolNoteMappingDialog.vue`：批量映射弹窗（来源分组表 / 操作下拉 / 企业展开 / 目标预览 / stale 高亮）（R2.2 / R2.3 / R3.3 / D§七.2~§七.3）
- [ ] 30. `ConsolNoteMappingRulesPanel.vue`：规则管理面板（章节状态表 / 版本 diff / 回滚）（R5.1 / R5.2 / D§七.4）
- [ ] 31. ConsolNoteTab 工具栏接入：新增"📋 明细刷新"按钮 → preview → 根据状态打开映射弹窗或直接 apply（D§七.1 / D§四）
- [ ] 32. 二次确认对话框：6 种操作（R5.3.1~R5.3.6）全部接入 `confirmDangerous`
- [ ] 33. Phase 5 测试：vitest 组件测试 ~12 例（D§九）

## Phase 6: 集成回归与文档（D§九）

- [ ] 34. 后端全量回归：V185 迁移 + 5 ORM + 4 service + 4 router + 合并锁定/签字冻结下 403 测试
- [ ] 35. 前端全量回归：3 组件 + ConsolNoteTab 接入 + 二次确认
- [ ] 36. ADR-017 勘误 commit：在 `docs/adr/ADR-017-consol-note-aggregation-service.md` 追加"§勘误"段落（R6）
- [ ] 37. Playwright 端到端实测（需 start-dev.bat 环境）：模板创建→绑定→预览→映射→apply→穿透查看→来源改名→stale→重新确认
- [ ]*38. 真实 PG 写路径 / 真实集团多企业 UAT / 6000 并发（需另行授权）

## 任务引用闭合校验

| 需求 | 覆盖任务 |
|---|---|
| R1.1 | 11, 13 |
| R1.2 | 1, 2, 3 |
| R1.3 | 3, 4, 5, 7 |
| R1.4 | 6, 28, 32 |
| R2.1 | 8, 9, 10 |
| R2.2 | 15, 17, 29 |
| R2.3 | 19, 20, 29 |
| R2.4 | 1, 2, 15, 16 |
| R3.1 | 9, 12, 18 |
| R3.2 | 18, 21 |
| R3.3 | 12, 29 |
| R4.1 | 12, 17, 22 |
| R4.2 | 17, 27 |
| R4.3 | 22, 24 |
| R4.4 | 23 |
| R5.1 | 30, 31 |
| R5.2 | 30, 32 |
| R5.3 | 32 |
| R5.4 | 25, 27 |
| R6 | 36 |

设计决策引用：D§二→1,2 / D§三→9 / D§四→12,17,22,24 / D§五→4,5,13,16 / D§六→11 / D§七→28~33 / D§八→22,23,25,26 / D§九→7,14,21,27,33,34,35,37
