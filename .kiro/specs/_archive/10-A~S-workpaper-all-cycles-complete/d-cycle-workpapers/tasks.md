# D 类底稿（销售收入循环）— 任务清单

## Phase 0: 注册与分类基础 (P0)

- [x] 1. 在 `wp_account_mapping.json` 中扩充 D 类 wp_code（从 13 条扩充到 ~55 条，覆盖 D0~D7 全部子码）
- [x] 2. 修正 wp_account_mapping 中 D5/D6/D7 的 wp_name 错配（D5=应收款项融资，D6=合同资产，D7=合同负债）
- [x] 3. 在 `_WP_CODE_OVERRIDE` 中添加全部 D 类 componentType 映射（~45 个条目）
- [x] 4. 验证 generated YAML schema（19 个）中的 component_type 与 _WP_CODE_OVERRIDE 一致，不一致的以 _WP_CODE_OVERRIDE 为准
- [x] 5. 更新 `test_render_config_smoke.py` 覆盖新增 D 类 wp_code
- [x] 6. 运行 `test_render_config_smoke.py` + `test_auto_data_resolvers.py` 全绿

## Phase 1: 程序表 (P1)

- [x] 7. 从 D0 xlsx 模板提取 D0A 函证程序表步骤结构
- [x] 8. 从 D1 xlsx 模板提取 D1A 应收票据程序表步骤结构
- [x] 9. 从 D2-1至D2-4 xlsx 模板提取 D2A 应收账款程序表步骤结构
- [x] 10. 从 D3 xlsx 模板提取 D3A 预收账款程序表步骤结构
- [x] 11. 从 D4-1至D4-4 xlsx 模板提取 D4A 营业收入程序表步骤结构
- [x] 12. 从 D5 xlsx 模板提取 D5A 应收款项融资程序表步骤结构
- [x] 13. 从 D6 xlsx 模板提取 D6A 合同资产程序表步骤结构
- [x] 14. 从 D6 xlsx 模板提取 D7A 合同负债程序表步骤结构（注：D7A 物理上在 D6.xlsx 中）
- [x] 15. 将 D0A~D7A 共 8 个程序表注册到 `procedure_table_templates.json`
- [x] 16. 验证各程序表在前端 GtAProgramConsole 正确渲染（ref_index chip + auto_data_source 面板）

## Phase 2: 审定表 + 回写联动 (P2)

- [x] 17. 确认 D1-1/D2-1/D3-1/D4-1/D5-1/D6-1/D7-1 审定表的 d-form-table schema 字段完整（标准审定表字段集）
- [x] 18. 为各审定表创建手工 YAML schema（如不使用 generated 版本需按标准字段新建，否则确认 generated schema 可用）
- [x] 19. 实现 `_on_d_audit_determination_saved` EventBus handler（D{n}-1 保存→回写 trial_balance.audited_amount）
- [x] 20. 实现 `confirmation_summary_for_cycle` auto_data_source resolver（从 ConfirmationHub 读取 D 循环函证摘要）
- [x] 21. 验证审定表保存→trial_balance 回写正确（单元测试 + in-process 验证）

## Phase 3: OnlyOffice 底稿 address_registry (P3)

- [x] 22. 创建 `backend/data/d_address_registry_seed.json`，注册 D 类 audit-sheet 底稿关键坐标
- [x] 23. 注册 D1-2/D1-3 明细表坐标（合计行余额列）
- [x] 24. 注册 D2-2/D2-3/D2-5/D2-6 坐标（明细合计+分析结论+检查结论）
- [x] 25. 注册 D4-2~D4-4/D4-6/D4-13/D4-22 坐标（收入明细+分析+检查+IPO 结论）
- [x] 26. 注册 D6-2/D6-3/D6-8 坐标（合同资产明细+减值测算结果）
- [x] 27. 验证 address_registry seed 加载 + custom_query 能正确读取注册坐标

## Phase 4: D4 营业收入完整覆盖 (P4)

- [x] 28. 确认 D4-5 会计政策检查 d-form-table schema（收入确认五步法字段）
- [x] 29. 确认 D4-12 合同检查 d-form-table schema
- [x] 30. 确认 D4-21 关联方检查 d-form-table schema + 关联 related_party_transactions 取数
- [x] 31. 实现 D4-22~D4-32 适用性控制（applicable_when: business_category IN ['ipo','listed','neeq','restructuring']）
- [x] 32. 确认 D4-33~D4-36 其他业务收入 schema
- [x] 33. 验证 D4 全系列底稿在前端正确打开（componentType 路由无 404）

## Phase 5: 联动完善 (P5)*

- [x] 34. 实现 D{n}A 程序表的 risk_for_cycle + control_test_result_for_cycle auto_data_source 绑定*
- [x] 35. 实现 D 检查/分析底稿结论→D{n}A 程序表步骤状态回写*
- [x] 36. 实现 D0→ConfirmationHub 路由（前端 render-config 识别 confirmation-hub → 路由跳转）*
- [x] 37. 实现 D 附注 sheet→disclosure_notes 路由确认（c-note-table componentType 正确加载）*
- [x] 38. 扩展 `test_auto_data_resolvers.py` 覆盖新增 D 类 resolver（confirmation_summary_for_cycle）*

## Phase 6: 导入导出 + E2E (P6)

- [x] 39. D 类 d-form-table 底稿导出为 Excel（复用通用 d-form-table 导出逻辑）
- [x] 40. D 类 audit-sheet 底稿原生导出（复用 audit-sheet 通用导出）
- [x] 41. 从 Excel 导入填充已有结构化 D 类底稿
- [x] 42. 批量导出 D 类全量打包 zip（项目归档场景）
- [x] 43. Playwright E2E: D2A 程序表打开 + 风险/控制测试联动面板展示
- [x] 44. Playwright E2E: D2-1 审定表编辑 + 保存 + trial_balance.audited_amount 回写确认
- [x] 45. Playwright E2E: D6 合同资产多 sheet Tab 切换 + audit-sheet 打开
- [x] 46. Playwright E2E: D4-22 IPO 底稿适用性灰显（普通年审项目）
- [x] 47. Playwright E2E: D0 函证底稿→ConfirmationHub 路由跳转
