# J 类底稿（职工薪酬循环）— 任务清单

## Phase 0: 注册与分类基础 (P0)

- [x] 1. 在 `wp_account_mapping.json` 中扩充 J 类 wp_code（~23 条，覆盖 J1~J3 全部子码）
- [x] 2. 在 `_WP_CODE_OVERRIDE` 中添加全部 J 类 componentType 映射（~21 个条目）
- [x] 3. 更新 `test_render_config_smoke.py` 覆盖新增 J 类 wp_code
- [x] 4. 运行 `test_render_config_smoke.py` + `test_auto_data_resolvers.py` 全绿

## Phase 1: 程序表 (P1)

- [x] 5. 从 J1 xlsx 模板提取 J1A 应付职工薪酬程序表步骤结构
- [x] 6. 从 J2 xlsx 模板提取 J2A 设定受益计划程序表步骤结构
- [x] 7. 从 J3 xlsx 模板提取 J3A 股份支付程序表步骤结构
- [x] 8. 将 J1A~J3A 共 3 个程序表注册到 `procedure_table_templates.json`
- [x] 9. 验证各程序表在前端 GtAProgramConsole 正确渲染

## Phase 2: 审定表 + 回写联动 (P2)

- [x] 10. 确认 J1-1~J3-1 共 3 个审定表的 d-form-table schema 字段完整
- [x] 11. 创建 J1-1 手工 YAML schema（按薪酬类别分行：工资/奖金/社保/公积金/福利）
- [x] 12. 扩展 `_on_audit_determination_saved` handler 正则匹配 J 类（`^J\d+-1$`）
- [x] 13. 验证审定表保存→trial_balance 回写正确（3 个审定表）

## Phase 3: address_registry 坐标注册 (P3)

- [x] 14. 创建 `backend/data/j_address_registry_seed.json`
- [x] 15. 注册 J1-3/J1-4 工资+社保测算坐标
- [x] 16. 注册 J2-5 精算重算坐标
- [x] 17. 注册 J3-4/J3-5 期权定价+费用分摊坐标
- [x] 18. 验证 address_registry seed 加载 + custom_query 正确读取

## Phase 4: 特殊程序 (P4)

- [x] 19. 确认 J1-3 工资测算 audit-sheet schema（人数×平均工资×月份）
- [x] 20. 确认 J2-3 精算假设评估 d-form-table schema（折现率/工资增长率/离职率/死亡率）
- [x] 21. 确认 J2-5 精算重新计算 audit-sheet schema（DBO/计划资产/净负债）
- [x] 22. 确认 J3-4 期权定价 audit-sheet schema（Black-Scholes 参数+公式）
- [x] 23. 验证 J 全系列底稿在前端正确打开

## Phase 5: 联动完善 (P5)*

- [x] 24. 实现 J{n}A 程序表 risk_for_cycle + control_test_result_for_cycle 绑定*
- [x] 25. 实现 J2→B51 accounting_estimate_b51 精算假设联动*
- [x] 26. 实现 J3→M4 资本公积 ref_index 跳转*

## Phase 6: 导入导出 + E2E (P6)

- [x] 27. J 类 d-form-table 底稿导出为 Excel
- [x] 28. J 类 audit-sheet 底稿原生导出
- [x] 29. 从 Excel 导入填充 J 类底稿
- [x] 30. Playwright E2E: J1A 程序表打开 + 风险/控制联动
- [x] 31. Playwright E2E: J2-3 精算假设 d-form-table 编辑
- [x] 32. Playwright E2E: J3-4 期权定价 audit-sheet 打开
