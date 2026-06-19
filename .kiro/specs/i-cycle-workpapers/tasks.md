# I 类底稿（无形资产循环）— 任务清单

## Phase 0: 注册与分类基础 (P0)

- [x] 1. 在 `wp_account_mapping.json` 中扩充 I 类 wp_code（~42 条，覆盖 I1~I6 全部子码）
- [x] 2. 在 `_WP_CODE_OVERRIDE` 中添加全部 I 类 componentType 映射（~40 个条目）
- [x] 3. 更新 `test_render_config_smoke.py` 覆盖新增 I 类 wp_code
- [x] 4. 运行 `test_render_config_smoke.py` + `test_auto_data_resolvers.py` 全绿

## Phase 1: 程序表 (P1)

- [x] 5. 从 I1 xlsx 模板提取 I1A 无形资产程序表步骤结构
- [x] 6. 从 I2 xlsx 模板提取 I2A 开发支出程序表步骤结构
- [x] 7. 从 I3 xlsx 模板提取 I3A 商誉程序表步骤结构
- [x] 8. 从 I4 xlsx 模板提取 I4A 长期待摊费用程序表步骤结构
- [x] 9. 从 I5 xlsx 模板提取 I5A 其他非流动资产程序表步骤结构
- [x] 10. 从 I6 xlsx 模板提取 I6A 研发费用程序表步骤结构
- [x] 11. 将 I1A~I6A 共 6 个程序表注册到 `procedure_table_templates.json`
- [x] 12. 验证各程序表在前端 GtAProgramConsole 正确渲染

## Phase 2: 审定表 + 回写联动 (P2)

- [x] 13. 确认 I1-1~I6-1 共 6 个审定表的 d-form-table schema 字段完整
- [x] 14. 创建 I1-1 手工 YAML schema（按无形资产类别分行+摊销/减值扣减）
- [x] 15. 扩展 `_on_audit_determination_saved` handler 正则匹配 I 类（`^I\d+-1$`）
- [x] 16. 验证审定表保存→trial_balance 回写正确（6 个审定表）

## Phase 3: address_registry 坐标注册 (P3)

- [x] 17. 创建 `backend/data/i_address_registry_seed.json`
- [x] 18. 注册 I1-3 摊销测算坐标
- [x] 19. 注册 I3-4/I3-5 DCF+敏感性分析坐标
- [x] 20. 注册 I6-7 研发加计扣除坐标
- [x] 21. 验证 address_registry seed 加载 + custom_query 正确读取

## Phase 4: 特殊程序 (P4)

- [x] 22. 确认 I1-3 摊销测算 audit-sheet schema（直线法/产量法）
- [x] 23. 确认 I3-4 DCF 计算 audit-sheet schema（WACC/CAPM/FCF/TV/NPV）
- [x] 24. 确认 I3-5 敏感性分析 audit-sheet schema（折现率/增长率矩阵）
- [x] 25. 确认 I2-3 资本化条件检查 d-form-table schema（CAS6 五条件）
- [x] 26. 确认 I6-3 研发费用资本化/费用化分类 d-form-table schema
- [x] 27. 确认 I6-7 加计扣除测算 audit-sheet schema
- [x] 28. 验证 I 全系列底稿在前端正确打开

## Phase 5: 联动完善 (P5)*

- [x] 29. 实现 I{n}A 程序表 risk_for_cycle + control_test_result_for_cycle 绑定*
- [x] 30. 实现 I3-4→A3-8 goodwill-impairment DCF ref_index 跳转*
- [x] 31. 实现 I6-7→N5 研发加计扣除 ref_index 跳转*

## Phase 6: 导入导出 + E2E (P6)

- [x] 32. I 类 d-form-table 底稿导出为 Excel
- [x] 33. I 类 audit-sheet 底稿原生导出
- [x] 34. 从 Excel 导入填充 I 类底稿
- [x] 35. 批量导出 I 类全量打包 zip
- [x] 36. Playwright E2E: I1A 程序表打开 + 风险/控制联动
- [x] 37. Playwright E2E: I3-4 DCF audit-sheet 打开
- [x] 38. Playwright E2E: I2-3 资本化条件 d-form-table 编辑
