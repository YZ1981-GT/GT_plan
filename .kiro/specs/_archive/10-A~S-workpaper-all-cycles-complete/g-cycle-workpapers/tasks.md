# G 类底稿（投资循环）— 任务清单

## Phase 0: 注册与分类基础 (P0)

- [x] 1. 在 `wp_account_mapping.json` 中扩充 G 类 wp_code（~93 条，覆盖 G0~G14 全部子码）
- [x] 2. 在 `_WP_CODE_OVERRIDE` 中添加全部 G 类 componentType 映射（~90 个条目）
- [x] 3. 在 confirmation-hub 白名单中添加 G0（与 D0/E0/F0 同模式）
- [x] 4. 更新 `test_render_config_smoke.py` 覆盖新增 G 类 wp_code
- [x] 5. 运行 `test_render_config_smoke.py` + `test_auto_data_resolvers.py` 全绿

## Phase 1: 程序表 (P1)

- [x] 6. 从 G0 xlsx 模板提取 G0A 函证程序表步骤结构
- [x] 7. 从 G1 xlsx 模板提取 G1A 交易性金融资产程序表步骤结构
- [x] 8. 从 G2 xlsx 模板提取 G2A 应收利息程序表步骤结构
- [x] 9. 从 G3 xlsx 模板提取 G3A 应收股利程序表步骤结构
- [x] 10. 从 G4 xlsx 模板提取 G4A 债权投资程序表步骤结构
- [x] 11. 从 G5 xlsx 模板提取 G5A 长期应收款程序表步骤结构
- [x] 12. 从 G6 xlsx 模板提取 G6A 其他债权投资程序表步骤结构
- [x] 13. 从 G7 xlsx 模板提取 G7A 长期股权投资程序表步骤结构
- [x] 14. 从 G8 xlsx 模板提取 G8A 其他权益工具投资程序表步骤结构
- [x] 15. 从 G9 xlsx 模板提取 G9A 其他非流动金融资产程序表步骤结构
- [x] 16. 从 G10 xlsx 模板提取 G10A 交易性金融负债程序表步骤结构
- [x] 17. 从 G11 xlsx 模板提取 G11A 投资收益程序表步骤结构
- [x] 18. 从 G12 xlsx 模板提取 G12A 净敞口套期收益程序表步骤结构
- [x] 19. 从 G13 xlsx 模板提取 G13A 公允价值变动收益程序表步骤结构
- [x] 20. 从 G14 xlsx 模板提取 G14A 信用减值损失程序表步骤结构
- [x] 21. 将 G0A~G14A 共 15 个程序表注册到 `procedure_table_templates.json`
- [x] 22. 验证各程序表在前端 GtAProgramConsole 正确渲染

## Phase 2: 审定表 + 回写联动 (P2)

- [x] 23. 确认 G1-1~G14-1 共 14 个审定表的 d-form-table schema 字段完整
- [x] 24. 创建 G7-1 手工 YAML schema（长期股权投资特殊：按被投资单位分行+权益法/成本法分组）
- [x] 25. 扩展 `_on_audit_determination_saved` handler 正则匹配 G 类审定表（`^G\d+-1$`）
- [x] 26. 验证审定表保存→trial_balance 回写正确（单元测试，覆盖 G1-1~G14-1）

## Phase 3: address_registry 坐标注册 (P3)

- [x] 27. 创建 `backend/data/g_address_registry_seed.json`
- [x] 28. 注册 G1-2/G1-3 交易性金融资产明细+公允价值坐标
- [x] 29. 注册 G4-3/G4-4/G4-5 债权投资摊余成本+ECL 坐标
- [x] 30. 注册 G7-3/G7-4/G7-5 长期股权投资权益法+减值+收益坐标
- [x] 31. 注册 G14-2 信用减值损失 ECL 计算坐标
- [x] 32. 验证 address_registry seed 加载 + custom_query 正确读取

## Phase 4: 特殊程序 (P4)

- [x] 33. 确认 G4-3/G4-4 实际利率法摊销 audit-sheet schema（含 IRR 公式）
- [x] 34. 确认 G4-5/G14-2 ECL 三阶段模型 audit-sheet schema
- [x] 35. 确认 G7-3 权益法核算 audit-sheet schema（初始成本+损益调整+OCI份额）
- [x] 36. 确认 G7-4 长期股权投资减值测试 audit-sheet schema
- [x] 37. 确认 G1-3/G6-3/G8-3/G10-3 公允价值测试 schema
- [x] 38. 验证 G 全系列底稿在前端正确打开（componentType 路由无 404）

## Phase 5: 联动完善 (P5)*

- [x] 39. 实现 G{n}A 程序表 risk_for_cycle + control_test_result_for_cycle 绑定*
- [x] 40. 实现 G0→ConfirmationHub 路由确认*
- [x] 41. 实现 G13→G1 公允价值变动↔交易性金融资产 ref_index 跳转*
- [x] 42. 实现 G11→G7 投资收益↔长期股权投资 ref_index 跳转*

## Phase 6: 导入导出 + E2E (P6)

- [x] 43. G 类 d-form-table 底稿导出为 Excel
- [x] 44. G 类 audit-sheet 底稿原生导出
- [x] 45. 从 Excel 导入填充已有结构化 G 类底稿
- [x] 46. 批量导出 G 类全量打包 zip
- [x] 47. Playwright E2E: G1A 程序表打开 + 风险/控制联动面板
- [x] 48. Playwright E2E: G7-1 审定表编辑 + 保存 + trial_balance 回写
- [x] 49. Playwright E2E: G4-5 ECL 三阶段 audit-sheet 打开
- [x] 50. Playwright E2E: G0 函证→ConfirmationHub 路由跳转
