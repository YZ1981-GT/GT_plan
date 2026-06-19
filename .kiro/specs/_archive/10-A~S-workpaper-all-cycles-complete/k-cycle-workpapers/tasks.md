# K 类底稿（管理循环）— 任务清单

## Phase 0: 注册与分类基础 (P0)

- [x] 1. 在 `wp_account_mapping.json` 中扩充 K 类 wp_code（~76 条，覆盖 K0~K13 全部子码）
- [x] 2. 在 `_WP_CODE_OVERRIDE` 中添加全部 K 类 componentType 映射（~73 个条目）
- [x] 3. 在 confirmation-hub 白名单中添加 K0
- [x] 4. 更新 `test_render_config_smoke.py` 覆盖新增 K 类 wp_code
- [x] 5. 运行 `test_render_config_smoke.py` + `test_auto_data_resolvers.py` 全绿

## Phase 1: 程序表 (P1)

- [x] 6. 从 K0 xlsx 模板提取 K0A 函证程序表步骤结构
- [x] 7. 从 K1 xlsx 模板提取 K1A 其他应收款程序表步骤结构
- [x] 8. 从 K2 xlsx 模板提取 K2A 其他流动资产程序表步骤结构
- [x] 9. 从 K3 xlsx 模板提取 K3A 其他应付款程序表步骤结构
- [x] 10. 从 K4 xlsx 模板提取 K4A 其他流动负债程序表步骤结构
- [x] 11. 从 K5 xlsx 模板提取 K5A 预计负债程序表步骤结构
- [x] 12. 从 K6 xlsx 模板提取 K6A 持有待售程序表步骤结构
- [x] 13. 从 K7 xlsx 模板提取 K7A 递延收益程序表步骤结构
- [x] 14. 从 K8 xlsx 模板提取 K8A 销售费用程序表步骤结构
- [x] 15. 从 K9 xlsx 模板提取 K9A 管理费用程序表步骤结构
- [x] 16. 从 K10 xlsx 模板提取 K10A 其他收益程序表步骤结构
- [x] 17. 从 K11 xlsx 模板提取 K11A 资产减值损失程序表步骤结构
- [x] 18. 从 K12 xlsx 模板提取 K12A 营业外收入程序表步骤结构
- [x] 19. 从 K13 xlsx 模板提取 K13A 营业外支出程序表步骤结构
- [x] 20. 将 K0A~K13A 共 14 个程序表注册到 `procedure_table_templates.json`
- [x] 21. 验证各程序表在前端 GtAProgramConsole 正确渲染

## Phase 2: 审定表 + 回写联动 (P2)

- [x] 22. 确认 K1-1~K13-1 共 13 个审定表的 d-form-table schema 字段完整
- [x] 23. 创建 K8-1/K9-1 手工 YAML schema（损益类：取发生额+按费用明细分行）
- [x] 24. 扩展 `_on_audit_determination_saved` handler 正则匹配 K 类（`^K\d+-1$`）
- [x] 25. 验证审定表保存→trial_balance 回写正确（13 个审定表）

## Phase 3: address_registry 坐标注册 (P3)

- [x] 26. 创建 `backend/data/k_address_registry_seed.json`
- [x] 27. 注册 K1-2/K1-3 其他应收款明细+账龄坐标
- [x] 28. 注册 K3-2/K3-3 其他应付款明细+账龄坐标
- [x] 29. 注册 K5-4 预计负债最佳估计数坐标
- [x] 30. 注册 K8-2/K8-3/K9-2/K9-3 费用明细+分析坐标
- [x] 31. 验证 address_registry seed 加载 + custom_query 正确读取

## Phase 4: 特殊程序 (P4)

- [x] 32. 确认 K5-3 或有事项评估 d-form-table schema（三级可能性+金额区间）
- [x] 33. 确认 K5-4 最佳估计数计算 audit-sheet schema（上下限+加权平均）
- [x] 34. 确认 K5-5 律师函回函分析 d-form-table schema
- [x] 35. 确认 K6-3 持有待售分类条件 d-form-table schema（CAS42 五条件）
- [x] 36. 实现 K8/K9 费用明细从 tb_ledger 取数（`ledger_detail_for_account` resolver）
- [x] 37. 验证 K 全系列底稿在前端正确打开

## Phase 5: 联动完善 (P5)*

- [x] 38. 实现 K{n}A 程序表 risk_for_cycle + control_test_result_for_cycle 绑定*
- [x] 39. 实现 K0→ConfirmationHub 路由确认*
- [x] 40. 实现 K5→A5-3 或有事项 ref_index 跳转*
- [x] 41. 实现 K7↔K10 递延收益↔其他收益联动*

## Phase 6: 导入导出 + E2E (P6)

- [x] 42. K 类 d-form-table 底稿导出为 Excel
- [x] 43. K 类 audit-sheet 底稿原生导出
- [x] 44. 从 Excel 导入填充 K 类底稿
- [x] 45. 批量导出 K 类全量打包 zip
- [x] 46. Playwright E2E: K1A 程序表打开 + 风险/控制联动
- [x] 47. Playwright E2E: K5-3 或有事项 d-form-table 编辑
- [x] 48. Playwright E2E: K9-2 费用明细 audit-sheet 打开
- [x] 49. Playwright E2E: K0→ConfirmationHub 路由
