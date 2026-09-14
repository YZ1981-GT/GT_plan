# F 类底稿（采购存货循环）— 任务清单

## Phase 0: 注册与分类基础 (P0)

- [x] 1. 在 `wp_account_mapping.json` 中扩充 F 类 wp_code（从 8 条扩充到 ~80 条，覆盖 F0~F5 全部子码）
- [x] 2. 修正 wp_account_mapping 中 F1-2/F1-3 的 wp_name（当前为"存货明细表/跌价准备"应改为"预付账款明细表/账龄分析"）
- [x] 3. 在 `_WP_CODE_OVERRIDE` 中添加全部 F 类 componentType 映射（~78 个条目）
- [x] 4. 验证 F 类不需要 pattern matching（各子底稿结构差异大，逐一映射）
- [x] 5. 更新 `test_render_config_smoke.py` 覆盖新增 F 类 wp_code
- [x] 6. 运行 `test_render_config_smoke.py` + `test_auto_data_resolvers.py` 全绿

## Phase 1: 程序表 (P1)

- [x] 7. 从 F0 xlsx 模板提取 F0A 函证程序表步骤结构
- [x] 8. 从 F1 xlsx 模板提取 F1A 预付账款程序表步骤结构
- [x] 9. 从 F2-1至F2-14 xlsx 模板提取 F2A 存货程序表步骤结构
- [x] 10. 从 F3 xlsx 模板提取 F3A 应付票据程序表步骤结构
- [x] 11. 从 F4 xlsx 模板提取 F4A 应付账款程序表步骤结构
- [x] 12. 从 F5 xlsx 模板提取 F5A 营业成本程序表步骤结构
- [x] 13. 将 F0A~F5A 共 6 个程序表注册到 `procedure_table_templates.json`
- [x] 14. 验证各程序表在前端 GtAProgramConsole 正确渲染（ref_index chip + auto_data_source 面板）

## Phase 2: 审定表 + 回写联动 (P2)

- [x] 15. 确认 F1-1/F2-1/F3-1/F4-1/F5-1 审定表的 d-form-table schema 字段完整（标准审定表字段集）
- [x] 16. 创建 F2-1 手工 YAML schema（存货特殊：多类别行+跌价扣减+净额行）
- [x] 17. 创建 F1-1/F3-1/F4-1/F5-1 手工 YAML schema（标准审定表结构）
- [x] 18. 扩展 `_on_audit_determination_saved` handler 正则匹配 F 类审定表（`^F\d+-1$`）
- [x] 19. 验证审定表保存→trial_balance 回写正确（单元测试，覆盖 F1-1~F5-1 全部 5 个审定表）

## Phase 3: OnlyOffice 底稿 address_registry (P3)

- [x] 20. 创建 `backend/data/f_address_registry_seed.json`，注册 F 类 audit-sheet 底稿关键坐标
- [x] 21. 注册 F1-2/F1-3 预付账款明细坐标
- [x] 22. 注册 F2-2~F2-10 存货各类明细坐标（各类合计行）
- [x] 23. 注册 F2-18~F2-20 分析程序结论坐标
- [x] 24. 注册 F2-21~F2-26 存货监盘坐标（盘点日期/仓库/差异金额/结论）
- [x] 25. 注册 F2-29~F2-35 检查程序结论坐标
- [x] 26. 注册 F2-38~F2-44 计价测试结论坐标
- [x] 27. 注册 F2-47~F2-49 跌价准备测试结论坐标
- [x] 28. 注册 F2-55~F2-58 合同履约成本结论坐标
- [x] 29. 注册 F2-61~F2-72 IPO 底稿结论坐标
- [x] 30. 注册 F3-2/F3-5/F3-6 + F4-2/F4-3 + F5-2~F5-4 坐标
- [x] 31. 验证 address_registry seed 加载 + custom_query 能正确读取注册坐标

## Phase 4: 特殊程序 (P4)

- [x] 32. 确认 F2-21~F2-26 存货监盘系列 audit-sheet schema（监盘计划/观察记录/抽盘测试/截止测试/差异汇总/结论）
- [x] 33. 确认 F2-38~F2-44 计价测试 audit-sheet schema（成本还原公式：加权平均/先进先出/个别计价）
- [x] 34. 确认 F2-47~F2-49 跌价准备测试 audit-sheet schema（可变现净值测算+减值判断）
- [x] 35. 实现 `accounting_estimate_b51` auto_data_source resolver（从 B51 读取舞弊三因素评估）
- [x] 36. 实现 F2-61~F2-72 适用性控制（applicable_when: business_category IN ['ipo','listed','neeq','restructuring']）
- [x] 37. 确认 F2-16 会计政策检查 d-form-table schema（计价方法检查字段）
- [x] 38. 确认 F2-52 关联交易检查 d-form-table schema + 关联 related_party_transactions 取数
- [x] 39. 确认 F2-55~F2-58 合同履约成本 audit-sheet schema（摊销测试公式）
- [x] 40. 确认 F1-4/F3-4/F4-4 调整分录/坏账 d-form-table schema
- [x] 41. 验证 F 全系列底稿在前端正确打开（componentType 路由无 404）

## Phase 5: 联动完善 (P5)*

- [x] 42. 实现 F{n}A 程序表的 risk_for_cycle + control_test_result_for_cycle auto_data_source 绑定*
- [x] 43. 实现 F 检查/分析/盘点/计价/跌价底稿结论→F{n}A 程序表步骤状态回写*
- [x] 44. 实现 F0→ConfirmationHub 路由（前端 render-config 识别 confirmation-hub → 路由跳转 cycle=F）*
- [x] 45. 实现 F 附注 sheet→disclosure_notes 路由确认（c-note-table componentType 正确加载）*
- [x] 46. 实现 F2-47~49 跌价准备→B51 联动面板（auto_data_source: accounting_estimate_b51 + 前端展示）*
- [x] 47. 实现 F5→F2 成本结转 ref_index chip 跳转*
- [x] 48. 扩展 `test_auto_data_resolvers.py` 覆盖新增 F 类 resolver（accounting_estimate_b51）*

## Phase 6: 导入导出 + E2E (P6)

- [x] 49. F 类 d-form-table 底稿导出为 Excel（复用通用导出逻辑）
- [x] 50. F 类 audit-sheet 底稿原生导出（复用通用导出）
- [x] 51. 从 Excel 导入填充已有结构化 F 类底稿
- [x] 52. 批量导出 F 类全量打包 zip
- [x] 53. Playwright E2E: F2A 程序表打开 + 风险/控制测试联动面板展示
- [x] 54. Playwright E2E: F2-1 审定表编辑 + 保存 + trial_balance.audited_amount 回写确认
- [x] 55. Playwright E2E: F2-21 存货监盘底稿 OnlyOffice 打开 + 多 sheet Tab 切换
- [x] 56. Playwright E2E: F2-47 跌价准备测试 + B51 舞弊三因素联动面板
- [x] 57. Playwright E2E: F2-61 IPO 底稿适用性灰显（普通年审项目）
- [x] 58. Playwright E2E: F0 函证底稿→ConfirmationHub 路由跳转
