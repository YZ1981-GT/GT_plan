# H 类底稿（固定资产循环）— 任务清单

## Phase 0: 注册与分类基础 (P0)

- [x] 1. 在 `wp_account_mapping.json` 中扩充 H 类 wp_code（~68 条，覆盖 H0~H10 全部子码）
- [x] 2. 在 `_WP_CODE_OVERRIDE` 中添加全部 H 类 componentType 映射（~65 个条目）
- [x] 3. 在 confirmation-hub 白名单中添加 H0
- [x] 4. 更新 `test_render_config_smoke.py` 覆盖新增 H 类 wp_code
- [x] 5. 运行 `test_render_config_smoke.py` + `test_auto_data_resolvers.py` 全绿

## Phase 1: 程序表 (P1)

- [x] 6. 从 H0 xlsx 模板提取 H0A 函证程序表步骤结构
- [x] 7. 从 H1 xlsx 模板提取 H1A 固定资产程序表步骤结构
- [x] 8. 从 H2 xlsx 模板提取 H2A 在建工程程序表步骤结构
- [x] 9. 从 H3 xlsx 模板提取 H3A 投资性房地产程序表步骤结构
- [x] 10. 从 H4 xlsx 模板提取 H4A 工程物资程序表步骤结构
- [x] 11. 从 H5 xlsx 模板提取 H5A 油气资产程序表步骤结构
- [x] 12. 从 H6 xlsx 模板提取 H6A 固定资产清理程序表步骤结构
- [x] 13. 从 H7 xlsx 模板提取 H7A 生产性生物资产程序表步骤结构
- [x] 14. 从 H8 xlsx 模板提取 H8A 使用权资产程序表步骤结构
- [x] 15. 从 H9 xlsx 模板提取 H9A 租赁负债程序表步骤结构
- [x] 16. 从 H10 xlsx 模板提取 H10A 资产处置损益程序表步骤结构
- [x] 17. 将 H0A~H10A 共 11 个程序表注册到 `procedure_table_templates.json`
- [x] 18. 验证各程序表在前端 GtAProgramConsole 正确渲染

## Phase 2: 审定表 + 回写联动 (P2)

- [x] 19. 确认 H1-1~H10-1 共 10 个审定表的 d-form-table schema 字段完整
- [x] 20. 创建 H1-1 手工 YAML schema（按资产类别分行+累计折旧/减值扣减）
- [x] 21. 扩展 `_on_audit_determination_saved` handler 正则匹配 H 类（`^H\d+-1$`）
- [x] 22. 验证审定表保存→trial_balance 回写正确（10 个审定表）

## Phase 3: address_registry 坐标注册 (P3)

- [x] 23. 创建 `backend/data/h_address_registry_seed.json`
- [x] 24. 注册 H1-3 折旧测算坐标
- [x] 25. 注册 H2-3 利息资本化坐标
- [x] 26. 注册 H8-4/H9-3/H9-4 CAS21 租赁相关坐标
- [x] 27. 注册 H3-3 投资性房地产公允价值坐标
- [x] 28. 验证 address_registry seed 加载 + custom_query 正确读取

## Phase 4: 特殊程序 (P4)

- [x] 29. 确认 H1-3 折旧测算 audit-sheet schema（原值×(1-残值率)/年限+年数总和法+双倍余额）
- [x] 30. 确认 H2-3 利息资本化 audit-sheet schema（加权平均资本化率×累计支出）
- [x] 31. 确认 H8-4 使用权资产还原 + H9-3 租赁负债现值 audit-sheet schema（CAS21 折现公式）
- [x] 32. 确认 H9-4 租赁负债摊销表 audit-sheet schema（每期利息+本金）
- [x] 33. 实现 H5/H7 适用性控制（applicable_when: industry 匹配）
- [x] 34. 验证 H 全系列底稿在前端正确打开

## Phase 5: 联动完善 (P5)*

- [x] 35. 实现 H{n}A 程序表 risk_for_cycle + control_test_result_for_cycle 绑定*
- [x] 36. 实现 H0→ConfirmationHub 路由确认*
- [x] 37. 实现 H8↔H9 CAS21 租赁配对 ref_index 互跳*
- [x] 38. 实现 H1-3 折旧↔H10 处置损益联动*

## Phase 6: 导入导出 + E2E (P6)

- [x] 39. H 类 d-form-table 底稿导出为 Excel
- [x] 40. H 类 audit-sheet 底稿原生导出
- [x] 41. 从 Excel 导入填充 H 类底稿
- [x] 42. 批量导出 H 类全量打包 zip
- [x] 43. Playwright E2E: H1A 程序表打开 + 风险/控制联动
- [x] 44. Playwright E2E: H1-1 审定表编辑 + 回写
- [x] 45. Playwright E2E: H9-3 租赁负债现值 audit-sheet 打开
- [x] 46. Playwright E2E: H0→ConfirmationHub 路由
