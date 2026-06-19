# E 类底稿（货币资金循环）— 任务清单

## Phase 0: 注册与分类基础 (P0)

- [x] 1. 在 `wp_account_mapping.json` 中扩充 E 类 wp_code（从 5 条扩充到 ~35 条，覆盖 E0~E1-32 全部子码）
- [x] 2. 在 `_WP_CODE_OVERRIDE` 中添加全部 E 类 componentType 映射（~33 个条目）
- [x] 3. 验证 E 类不需要 pattern matching（子码编号不连续且结构差异大，按 wp_code 逐一映射）
- [x] 4. 更新 `test_render_config_smoke.py` 覆盖新增 E 类 wp_code
- [x] 5. 运行 `test_render_config_smoke.py` + `test_auto_data_resolvers.py` 全绿

## Phase 1: 程序表 (P1)

- [x] 6. 从 E0 xlsx 模板提取 E0A 函证程序表步骤结构
- [x] 7. 从 E1-1至E1-11 xlsx 模板提取 E1A 货币资金程序表步骤结构
- [x] 8. 将 E0A + E1A 共 2 个程序表注册到 `procedure_table_templates.json`
- [x] 9. 验证各程序表在前端 GtAProgramConsole 正确渲染（ref_index chip + auto_data_source 面板）

## Phase 2: 审定表 + 回写联动 (P2)

- [x] 10. 确认 E1-1 审定表的 d-form-table schema 字段完整（标准审定表字段集，3 组：库存现金/银行存款/其他货币资金）
- [x] 11. 创建 E1-1 手工 YAML schema（`backend/data/ledger_adapters/wp_render_schema/E1-1.yaml`）
- [x] 12. 扩展 `_on_audit_determination_saved` handler 正则匹配 E 类审定表（`^E\d+-1$`）
- [x] 13. 验证审定表保存→trial_balance 回写正确（单元测试）

## Phase 3: OnlyOffice 底稿 address_registry (P3)

- [x] 14. 创建 `backend/data/e_address_registry_seed.json`，注册 E 类 audit-sheet 底稿关键坐标
- [x] 15. 注册 E1-3/E1-4 明细表坐标（合计行余额列）
- [x] 16. 注册 E1-5 余额调节表坐标（调节后余额）
- [x] 17. 注册 E1-9 利息测算坐标（测算利息/差异）
- [x] 18. 注册 E1-14/E1-15 分析程序结论坐标
- [x] 19. 注册 E1-18~E1-23 检查程序结论坐标
- [x] 20. 注册 E1-26~E1-32 IPO 底稿结论坐标
- [x] 21. 验证 address_registry seed 加载 + custom_query 能正确读取注册坐标

## Phase 4: 特殊程序 (P4)

- [x] 22. 确认 E1-5 银行存款余额调节表 audit-sheet schema（企业账面→调节→银行对账单结构）
- [x] 23. 确认 E1-9 利息测算 audit-sheet schema（本金×利率×天数 公式自动计算）
- [x] 24. 实现 E1-26~E1-32 适用性控制（applicable_when: business_category IN ['ipo','listed','neeq','restructuring']）
- [x] 25. 确认 E1-2/E1-6/E1-10 d-form-table schema（库存现金/受限资金/调整分录）
- [x] 26. 验证 E 全系列底稿在前端正确打开（componentType 路由无 404）

## Phase 5: 联动完善 (P5)*

- [x] 27. 实现 E1A 程序表的 risk_for_cycle + control_test_result_for_cycle auto_data_source 绑定*
- [x] 28. 实现 E 检查/分析底稿结论→E1A 程序表步骤状态回写*
- [x] 29. 实现 E0→ConfirmationHub 路由（前端 render-config 识别 confirmation-hub → 路由跳转 cycle=E）*
- [x] 30. 实现 E 附注 sheet→disclosure_notes 路由确认（c-note-table componentType 正确加载）*

## Phase 6: 导入导出 + E2E (P6)

- [x] 31. E 类 d-form-table 底稿导出为 Excel（复用通用导出逻辑）
- [x] 32. E 类 audit-sheet 底稿原生导出（复用通用导出）
- [x] 33. 从 Excel 导入填充已有结构化 E 类底稿
- [x] 34. 批量导出 E 类全量打包 zip
- [x] 35. Playwright E2E: E1A 程序表打开 + 风险/控制测试联动面板展示
- [x] 36. Playwright E2E: E1-1 审定表编辑 + 保存 + trial_balance.audited_amount 回写确认
- [x] 37. Playwright E2E: E1-5 银行存款余额调节表 OnlyOffice 打开
- [x] 38. Playwright E2E: E1-26 IPO 底稿适用性灰显（普通年审项目）
- [x] 39. Playwright E2E: E0 函证底稿→ConfirmationHub 路由跳转
