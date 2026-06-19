# L 类底稿（筹资循环）— 任务清单

## Phase 0: 注册与分类基础 (P0)

- [x] 1. 在 `wp_account_mapping.json` 中扩充 L 类 wp_code（~56 条，覆盖 L0~L8 全部子码）
- [x] 2. 在 `_WP_CODE_OVERRIDE` 中添加全部 L 类 componentType 映射（~53 个条目）
- [x] 3. 在 confirmation-hub 白名单中添加 L0
- [x] 4. 更新 `test_render_config_smoke.py` 覆盖新增 L 类 wp_code
- [x] 5. 运行 `test_render_config_smoke.py` + `test_auto_data_resolvers.py` 全绿

## Phase 1: 程序表 (P1)

- [x] 6. 从 L0 xlsx 模板提取 L0A 函证程序表步骤结构
- [x] 7. 从 L1 xlsx 模板提取 L1A 短期借款程序表步骤结构
- [x] 8. 从 L2 xlsx 模板提取 L2A 应付利息程序表步骤结构
- [x] 9. 从 L3 xlsx 模板提取 L3A 长期借款程序表步骤结构
- [x] 10. 从 L4 xlsx 模板提取 L4A 应付债券程序表步骤结构
- [x] 11. 从 L5 xlsx 模板提取 L5A 长期应付款程序表步骤结构
- [x] 12. 从 L6 xlsx 模板提取 L6A 专项应付款程序表步骤结构
- [x] 13. 从 L7 xlsx 模板提取 L7A 其他非流动负债程序表步骤结构
- [x] 14. 从 L8 xlsx 模板提取 L8A 财务费用程序表步骤结构
- [x] 15. 将 L0A~L8A 共 9 个程序表注册到 `procedure_table_templates.json`
- [x] 16. 验证各程序表在前端 GtAProgramConsole 正确渲染

## Phase 2: 审定表 + 回写联动 (P2)

- [x] 17. 确认 L1-1~L8-1 共 8 个审定表的 d-form-table schema 字段完整
- [x] 18. 创建 L4-1 手工 YAML schema（按债券品种分行：面值/票面利率/到期日/摊余成本）
- [x] 19. 扩展 `_on_audit_determination_saved` handler 正则匹配 L 类（`^L\d+-1$`）
- [x] 20. 验证审定表保存→trial_balance 回写正确（8 个审定表）

## Phase 3: address_registry 坐标注册 (P3)

- [x] 21. 创建 `backend/data/l_address_registry_seed.json`
- [x] 22. 注册 L1-3/L3-3 借款利息测算坐标
- [x] 23. 注册 L4-3/L4-4 实际利率+摊余成本摊销表坐标
- [x] 24. 注册 L8-3/L8-5 财务费用利息+汇兑坐标
- [x] 25. 验证 address_registry seed 加载 + custom_query 正确读取

## Phase 4: 特殊程序 (P4)

- [x] 26. 确认 L4-3 实际利率计算 audit-sheet schema（IRR 公式）
- [x] 27. 确认 L4-4 摊余成本摊销表 audit-sheet schema（期初×实际利率-票面利息=摊销）
- [x] 28. 确认 L1-3/L3-3 借款利息测算 audit-sheet schema（本金×利率×天数/360）
- [x] 29. 确认 L8-5 汇兑损益测算 audit-sheet schema（汇率差×外币余额）
- [x] 30. 确认 L3-4 一年内到期重分类 d-form-table schema
- [x] 31. 验证 L 全系列底稿在前端正确打开

## Phase 5: 联动完善 (P5)*

- [x] 32. 实现 L{n}A 程序表 risk_for_cycle + control_test_result_for_cycle 绑定*
- [x] 33. 实现 L0→ConfirmationHub 路由确认*
- [x] 34. 实现 L1/L3/L4→L8 利息汇总 ref_index 跳转*
- [x] 35. 实现 L4↔G4 对称关联 ref_index*

## Phase 6: 导入导出 + E2E (P6)

- [x] 36. L 类 d-form-table 底稿导出为 Excel
- [x] 37. L 类 audit-sheet 底稿原生导出
- [x] 38. 从 Excel 导入填充 L 类底稿
- [x] 39. 批量导出 L 类全量打包 zip
- [x] 40. Playwright E2E: L1A 程序表打开 + 风险/控制联动
- [x] 41. Playwright E2E: L4-4 摊余成本摊销表 audit-sheet
- [x] 42. Playwright E2E: L8-1 审定表回写
- [x] 43. Playwright E2E: L0→ConfirmationHub 路由
