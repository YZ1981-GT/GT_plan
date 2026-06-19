# S 类底稿（专项循环）— 任务清单

## Phase 0: 注册与分类基础 (P0)

- [x] 1. 在 `wp_account_mapping.json` 中新增 S 类全部 90 个 wp_code（S1~S17/S20~S21/S32-1~S32-13/S33-1~S33-9+S33-REV/S34-0~S34-41+S34-1-1/S35-1~S35-5/S12A）
- [x] 2. 在 `_WP_CODE_OVERRIDE` 中添加全部 S 类 componentType 映射（90 个条目）
  - 程序表式（7 个）：S1/S2/S3/S8/S10/S11/S13 → `a-program-console`
  - 检查表式（78 个）：S4/S5/S6/S9/S12/S14/S16/S20/S21 + S32全系列(13) + S33-1~9(9) + S34-0~41(42) + S35全系列(5) → `d-form-table`
  - 计算表（2 个）：S15/S17 → `audit-sheet`
  - 文档（3 个）：S12A/S33-REV/S34-1-1 → `word-template`
- [x] 3. 为 S32~S35 全系列设置 applicable_when 字段（S32/S33=ipo+listed+neeq，S34=ipo+listed+neeq+refinancing，S35=refinancing）
- [x] 4. 验证 S 类不需要 pattern matching + 不需要 generic schema（各底稿结构差异大，逐一映射）
- [x] 5. 更新 `test_render_config_smoke.py` 覆盖全部 90 个 S 类 wp_code
- [x] 6. 运行 `test_render_config_smoke.py` + `test_auto_data_resolvers.py` 全绿

## Phase 1: 特殊审计考虑程序表 (P1)

- [x] 7. 从 S1.xlsx 模板提取"违反法规行为的考虑"程序表步骤结构
- [x] 8. 从 S2.xlsx 模板提取"首次接受委托期初余额"程序表步骤结构
- [x] 9. 从 S3.xlsx 模板提取"会计政策变更/前期差错/估计变更"程序表步骤结构
- [x] 10. 从 S8.xlsx 模板提取"租赁"程序表步骤结构
- [x] 11. 从 S10.xlsx 模板提取"环境事项考虑"程序表步骤结构
- [x] 12. 从 S11.xlsx 模板提取"利用服务机构"程序表步骤结构
- [x] 13. 从 S13.xlsx 模板提取"利用管理层专家"程序表步骤结构
- [x] 14. 将 S1/S2/S3/S8/S10/S11/S13 共 7 个程序表注册到 `procedure_table_templates.json`
- [x] 15. 验证各程序表在前端 GtAProgramConsole 正确渲染（ref_index chip + 步骤展示）

## Phase 2: IPO 专项核查注册 (P2)

- [x] 16. 创建 S32 系列 d-form-table schema YAML（13 个底稿，通用核查字段：核查程序/核查结果/异常情况/结论）
- [x] 17. 创建 S33 系列 d-form-table schema YAML（9 个底稿，综合核查字段集）
- [x] 18. 创建 S34-0 总控表 d-form-table schema YAML（清单式，含各子项完成状态列）
- [x] 19. 创建 S34-1~S34-41 系列 d-form-table schema YAML（41 个底稿，证监会核查字段集）
- [x] 20. 创建 S35 系列 d-form-table schema YAML（5 个底稿，再融资核查字段集）
- [x] 21. 实现 S32~S35 全系列 applicable_when 评估逻辑（前端 evaluateApplicability + 后端 field_overrides 注入）
- [x] 22. 验证 IPO 项目打开 S32~S35 正常展示 + 普通年审项目灰显不适用覆盖层

## Phase 3: address_registry 坐标注册 (P3)

- [x] 23. 创建 `backend/data/s_address_registry_seed.json`，注册 S 类 audit-sheet 底稿关键坐标
- [x] 24. 注册 S15（每股收益/稀释每股收益/加权平均净资产收益率）计算结果坐标
- [x] 25. 注册 S17（非经常性损益合计/扣除非经常性损益后净利润）结果坐标
- [x] 26. 验证 address_registry seed 加载 + custom_query 能正确读取注册坐标

## Phase 4: docx 文件注册 (P4)

- [x] 27. 在 wpPopupDocxConfigs 中注册 S12A（评估专家报告）弹窗配置
- [x] 28. 在 wpPopupDocxConfigs 中注册 S33-REV（综合核查程序修订说明）弹窗配置
- [x] 29. 在 wpPopupDocxConfigs 中注册 S34-1-1（信息披露豁免专项核查意见）弹窗配置
- [x] 30. 验证 3 个 docx 底稿在前端正确打开（word-template componentType 路由 + OnlyOffice 编辑/降级下载）

## Phase 5: 联动 (P5)*

- [x] 31. 实现 `revenue_audited_for_s20` auto_data_source resolver（S20 从 D4 营业收入 trial_balance 读取）*
- [x] 32. 实现 `eps_data_from_tb` auto_data_source resolver（S15 从 trial_balance 读取净利润/股本）*
- [x] 33. 实现 `non_recurring_items_from_tb` auto_data_source resolver（S17 从 trial_balance 读取损益科目）*
- [x] 34. 实现 `cycle_audited_amounts` auto_data_source resolver（S32~S35 从各循环审定表读取数据）*
- [x] 35. 实现 S14（会计估计）→B51 舞弊三因素联动（复用已有 accounting_estimate_b51 resolver）*
- [x] 36. 实现 S→A17 结论汇总联动（A17 ch15"其他特殊考虑"读取 S 类已完成底稿结论）*
- [x] 37. 扩展 `test_auto_data_resolvers.py` 覆盖新增 S 类 4 个 resolver*

## Phase 6: 导入导出 + E2E (P6)

- [x] 38. S 类 d-form-table 底稿导出为 Excel（复用通用导出逻辑）
- [x] 39. S 类 audit-sheet 底稿原生导出（复用通用导出）
- [x] 40. S 类 word-template 底稿原始 docx 下载
- [x] 41. 批量导出 S 类全量打包 zip
- [x] 42. Playwright E2E: S1 程序表打开 + 步骤展示 + ref_index chip 跳转
- [x] 43. Playwright E2E: S14 检查表打开 + 填写"适用/不适用"+ 保存
- [x] 44. Playwright E2E: S15 计算表 OnlyOffice 打开 + 多 sheet Tab
- [x] 45. Playwright E2E: S12A docx 弹窗预览/编辑/降级下载
- [x] 46. Playwright E2E: S32-1 IPO 底稿打开（IPO 项目正常展示 + 普通年审灰显）
- [x] 47. Playwright E2E: S34-0 证监会清单打开 + 子项导航
