# M 类底稿（股东权益循环）— 任务清单

## Phase 0: 注册与分类基础 (P0)

- [x] 1. 在 `wp_account_mapping.json` 中扩充 M 类 wp_code（~58 条，覆盖 M1~M10 全部子码）
- [x] 2. 在 `_WP_CODE_OVERRIDE` 中添加全部 M 类 componentType 映射（~55 个条目）
- [x] 3. 更新 `test_render_config_smoke.py` 覆盖新增 M 类 wp_code
- [x] 4. 运行 `test_render_config_smoke.py` + `test_auto_data_resolvers.py` 全绿

## Phase 1: 程序表 (P1)

- [x] 5. 从 M1 xlsx 模板提取 M1A 应付股利程序表步骤结构
- [x] 6. 从 M2 xlsx 模板提取 M2A 实收资本程序表步骤结构
- [x] 7. 从 M3 xlsx 模板提取 M3A 库存股程序表步骤结构
- [x] 8. 从 M4 xlsx 模板提取 M4A 资本公积程序表步骤结构
- [x] 9. 从 M5 xlsx 模板提取 M5A 盈余公积程序表步骤结构
- [x] 10. 从 M6 xlsx 模板提取 M6A 未分配利润程序表步骤结构
- [x] 11. 从 M7 xlsx 模板提取 M7A 专项储备程序表步骤结构
- [x] 12. 从 M8 xlsx 模板提取 M8A 一般风险准备程序表步骤结构
- [x] 13. 从 M9 xlsx 模板提取 M9A 其他综合收益程序表步骤结构
- [x] 14. 从 M10 xlsx 模板提取 M10A 其他权益工具程序表步骤结构
- [x] 15. 将 M1A~M10A 共 10 个程序表注册到 `procedure_table_templates.json`
- [x] 16. 验证各程序表在前端 GtAProgramConsole 正确渲染

## Phase 2: 审定表 + 回写联动 (P2)

- [x] 17. 确认 M1-1~M10-1 共 10 个审定表的 d-form-table schema 字段完整
- [x] 18. 创建 M2-1 手工 YAML schema（按股东分行：持股比例/出资方式/认缴/实缴）
- [x] 19. 创建 M6-1 手工 YAML schema（单行公式：期初+净利润-提取-分配=期末）
- [x] 20. 扩展 `_on_audit_determination_saved` handler 正则匹配 M 类（`^M\d+-1$`）
- [x] 21. 验证审定表保存→trial_balance 回写正确（10 个审定表）

## Phase 3: address_registry 坐标注册 (P3)

- [x] 22. 创建 `backend/data/m_address_registry_seed.json`
- [x] 23. 注册 M6-2 未分配利润勾稽表坐标（期初/净利润/分配/期末）
- [x] 24. 注册 M6-5 损益联动验证坐标
- [x] 25. 注册 M2-2/M9-2 明细坐标
- [x] 26. 验证 address_registry seed 加载 + custom_query 正确读取

## Phase 4: 特殊程序 (P4)

- [x] 27. 确认 M6-2 勾稽表 audit-sheet schema（期初+净利润-提取-分配=期末）
- [x] 28. 实现 `income_statement_total` auto_data_source resolver（汇总 D~N 损益审定额）
- [x] 29. 确认 M6-5 损益联动验证 audit-sheet schema
- [x] 30. 确认 M2-3/M2-4 验资+工商核实 d-form-table schema
- [x] 31. 确认 M9-3 OCI 分类检查 d-form-table schema
- [x] 32. 确认 M10-3 权益/负债分类 d-form-table schema（永续债条件）
- [x] 33. 实现 M8 适用性控制（applicable_when: industry IN 金融类）
- [x] 34. 验证 M 全系列底稿在前端正确打开

## Phase 5: 联动完善 (P5)*

- [x] 35. 实现 M{n}A 程序表 risk_for_cycle + C1 控制测试绑定*
- [x] 36. 实现 M4-5→J3 股份支付 ref_index 跳转*
- [x] 37. 实现 M9→G8 其他权益工具投资 ref_index 跳转*
- [x] 38. 实现 M6→D~N 损益联动完整验证*

## Phase 6: 导入导出 + E2E (P6)

- [x] 39. M 类 d-form-table 底稿导出为 Excel
- [x] 40. M 类 audit-sheet 底稿原生导出
- [x] 41. 从 Excel 导入填充 M 类底稿
- [x] 42. 批量导出 M 类全量打包 zip
- [x] 43. Playwright E2E: M2A 程序表打开 + C1 控制联动
- [x] 44. Playwright E2E: M6-1 审定表回写
- [x] 45. Playwright E2E: M6-2 勾稽表 audit-sheet 打开
- [x] 46. Playwright E2E: M9-3 OCI 分类 d-form-table
