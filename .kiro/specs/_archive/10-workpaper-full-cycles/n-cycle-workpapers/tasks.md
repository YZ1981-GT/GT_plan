# N 类底稿（税费循环）— 任务清单

## Phase 0: 注册与分类基础 (P0)

- [x] 1. 在 `wp_account_mapping.json` 中扩充 N 类 wp_code（~35 条，覆盖 N1~N5 全部子码）
- [x] 2. 在 `_WP_CODE_OVERRIDE` 中添加全部 N 类 componentType 映射（~33 个条目）
- [x] 3. 更新 `test_render_config_smoke.py` 覆盖新增 N 类 wp_code
- [x] 4. 运行 `test_render_config_smoke.py` + `test_auto_data_resolvers.py` 全绿

## Phase 1: 程序表 (P1)

- [x] 5. 从 N1 xlsx 模板提取 N1A 递延所得税资产程序表步骤结构
- [x] 6. 从 N2 xlsx 模板提取 N2A 应交税费程序表步骤结构
- [x] 7. 从 N3 xlsx 模板提取 N3A 递延所得税负债程序表步骤结构
- [x] 8. 从 N4 xlsx 模板提取 N4A 税金及附加程序表步骤结构
- [x] 9. 从 N5 xlsx 模板提取 N5A 所得税费用程序表步骤结构
- [x] 10. 将 N1A~N5A 共 5 个程序表注册到 `procedure_table_templates.json`
- [x] 11. 验证各程序表在前端 GtAProgramConsole 正确渲染

## Phase 2: 审定表 + 回写联动 (P2)

- [x] 12. 确认 N1-1~N5-1 共 5 个审定表的 d-form-table schema 字段完整
- [x] 13. 创建 N2-1 手工 YAML schema（按税种分行：增值税/所得税/个税/城建/教育/房产/土地等）
- [x] 14. 创建 N5-1 手工 YAML schema（当期+递延=合计）
- [x] 15. 扩展 `_on_audit_determination_saved` handler 正则匹配 N 类（`^N\d+-1$`）
- [x] 16. 验证审定表保存→trial_balance 回写正确（5 个审定表）

## Phase 3: address_registry 坐标注册 (P3)

- [x] 17. 创建 `backend/data/n_address_registry_seed.json`
- [x] 18. 注册 N1-3/N3-3 暂时性差异计算坐标
- [x] 19. 注册 N2-3 增值税核对坐标
- [x] 20. 注册 N5-3/N5-4/N5-5 所得税计算+调增调减+有效税率坐标
- [x] 21. 验证 address_registry seed 加载 + custom_query 正确读取

## Phase 4: 特殊程序 (P4)

- [x] 22. 确认 N5-3 所得税计算表 audit-sheet schema（利润±调整=应纳税所得×税率）
- [x] 23. 确认 N5-4 纳税调增调减明细 audit-sheet schema
- [x] 24. 确认 N5-5 有效税率分析 audit-sheet schema（实际vs法定+差异解释）
- [x] 25. 确认 N1-3/N3-3 暂时性差异计算 audit-sheet schema（账面-计税=差异×税率）
- [x] 26. 确认 N2-3 增值税核对 audit-sheet schema（销项-进项-转出=应缴）
- [x] 27. 确认 N1-4 可抵扣确认条件 d-form-table schema
- [x] 28. 验证 N 全系列底稿在前端正确打开

## Phase 5: 联动完善 (P5)*

- [x] 29. 实现 N{n}A 程序表 risk_for_cycle + control_test_result_for_cycle 绑定*
- [x] 30. 实现 N5-6→N1/N3 递延所得税联动*
- [x] 31. 实现 I6-7→N5-7 研发加计扣除 ref_index 跳转*
- [x] 32. 实现 `temporary_differences_summary` resolver*
- [x] 33. 实现 `income_tax_calculation` resolver*

## Phase 6: 导入导出 + E2E (P6)

- [x] 34. N 类 d-form-table 底稿导出为 Excel
- [x] 35. N 类 audit-sheet 底稿原生导出
- [x] 36. 从 Excel 导入填充 N 类底稿
- [x] 37. 批量导出 N 类全量打包 zip
- [x] 38. Playwright E2E: N1A 程序表打开 + 风险/控制联动
- [x] 39. Playwright E2E: N5-3 所得税计算 audit-sheet 打开
- [x] 40. Playwright E2E: N1-3 暂时性差异 audit-sheet 打开
