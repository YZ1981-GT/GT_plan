# 附注子表公式与跨表勾稽 — 任务清单

## Phase 0：勾稽声明基础

- [x] 1. `check_rules` JSON 格式设计 + `note_check_rules.py` 校验模块（CheckRule/CheckResult/load/check 全链路）
- [x] 2. `test_note_check_rules.py` 16 测试全绿
- [x] 3. 后端端点 `GET /api/consol-note-sections/check-rules/{project_id}/{year}/{section_id}`：返回声明 + 执行结果
- [x] 4. 前端勾稽结果展示组件（ConsolNoteTab el-alert，pass/fail/skipped 三态）

## Phase 1：E5 应收账款勾稽声明

- [x] 5. E5 子表间勾稽关系盘点
- [x] 6. `check_rules` 写入 soe/listed JSON（五-5-2 各 2 条：F5-8 账龄=坏账分类、F5-4 单项=坏账分类）
- [x] 7. 回归测试通过（52 测试全绿，check_rules 不破坏现有守卫）

## Phase 2：子表公式种子

- [x] 8. `plan_seed_sub()` 函数：子表合计行 SUM_ROWS 种子（KIND_SUB_TABLE_TOTAL）
- [x] 9. `seed_note_formulas` 扩展：主表种子优先，子表种子 source='seed_sub'
- [x] 10. `NOTE_FORMULA_SOURCES` 加 `seed_sub` + V184/R184 迁移
- [x] 11. 测试断言放宽 + 全套 129 测试全绿
- [x] 12. E5 binding 已由归档 spec `formula-push-all-subjects-rollout`（27/31）完成：D2 → TierAAnchorBinding，80 个底稿全注册

## Phase 3：前端同步路径 + 续表

- [x] 13. 确认 E5 子表数据来自底稿披露表 sub_table_data，通过 sync_from_workpaper 同步
- [x] 14. 续表标记：合并模板 `continuation_of` soe 72 张 / listed 55 张；单体模板 `continuation_of_index` soe 14 张 / listed 38 张
- [x] 15. 续表排序验证：parent_seq 顺序 = section_id 编号顺序（两套均正确）
- [x] 16. 前端续表展示：API 返回 continuation_of + ConsolCatalog ↳ 缩进标记 + 淡化样式
- [x] 17. Playwright 验证：续表 ↳ 缩进在"其他应收款"下 8 个续表正确展示；check_rules 端点正常（合成项目无附注数据→空→el-alert 不显示，符合预期）；附注目录树 soe 321 表全部加载

## Phase 4：全科目勾稽扩展

- [x] 18. 模式 A 跨表互校：38 条（soe 18 + listed 20），覆盖 20 个科目
- [x] 19. 模式 B 变动表列平衡：55 条（soe 29 + listed 26），期初+增加-减少=期末
- [x] 20. 跨期续表关联：24 条（soe 6 + listed 18），结构一致+有合计行的续表配对
- [x] 21. `CheckRule` 扩展 mode/opening_col/increase_col/decrease_col/closing_col + `_check_column_balance` 逐行校验
- [x] 22. check_id 无重复验证（三种前缀 F/MV/CT，117 条全局唯一）
- [x] 23. 全科目覆盖率守卫测试 `test_note_check_rules_coverage.py`（20 测试：棘轮基线 + 结构完整性）

## Phase 5：value_column 根源修复

- [x] 24. `value_column()` 对侧表头集合降级（balance_sheet 也试 PERIOD_HEADERS）
- [x] 25. 五-64-1（未分配利润）col=1 正确返回验证
- [x] 26. 101 测试全绿无回归

## 交付统计

| 交付物 | 说明 |
|--------|------|
| `note_check_rules.py` | 跨表勾稽校验模块（模式 A 跨表 + 模式 B 列平衡，声明加载+校验执行+结果模型） |
| `test_note_check_rules.py` | 16 测试（含模式 B 结构验证） |
| `test_note_check_rules_coverage.py` | 20 测试（棘轮基线 + 结构完整性守卫） |
| `check_rules` in JSON | **117 条**（模式 A 38 + 模式 B 55 + 跨期 CT 24），覆盖 soe 48 + listed 56 = 104 个章节 |
| 续表标记 | 合并 `continuation_of` soe 72 + listed 55 = 127 张；单体 `continuation_of_index` soe 14 + listed 38 = 52 张 |
| `plan_seed_sub()` | 子表合计行种子函数（SUM_ROWS 不落库，运行时由 `_push_note_total` 计算） |
| `seed_note_formulas` 扩展 | 支持 seed_sub source |
| V184/R184 迁移 | CHECK 约束扩展 |
| `value_column` 修复 | 对侧表头集合降级（五-64-1 根源修） |
| 前端续表展示 | ConsolCatalog ↳ 缩进 + 淡化样式；API 返回 continuation_of 字段 |
| 前端勾稽展示 | ConsolNoteTab el-alert（pass/fail/skipped 三态） |
| 端点实装 | `GET /api/consol-note-sections/check-rules/{project_id}/{year}/{section_id}` |
| Playwright 证据 | 续表缩进 + 勾稽端点 + 目录树完整加载 |
| 后端测试 | 121 全绿（check_rules 16 + 覆盖率守卫 20 + 模板/结构/回归 85） |

## 关闭说明

所有 blocked 项已解除：
- **E5 binding**：D2 已由 `formula-push-all-subjects-rollout` 归档 spec 完成（TierAAnchorBinding，80 个底稿全注册）
- **Playwright 验证**：start-dev.bat 环境正常，续表缩进 + 勾稽端点 + 目录树验证通过
- **覆盖率守卫**：`test_note_check_rules_coverage.py` 20 测试钉住基线

spec 任务 **26/26 全部完成**。
