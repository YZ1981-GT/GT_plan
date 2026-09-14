# C 类底稿（控制测试）— 任务清单

## Phase 0: 注册与分类基础 (P0)

- [x] 1. 在 `wp_account_mapping.json` 中注册全部 36 个 C 类 wp_code（wp_name/audit_cycle="C"/must_have 标记）
- [x] 2. 在 `_WP_CODE_OVERRIDE` 中添加全部 C 类 componentType 映射（36 个条目）
- [x] 3. 在 `_PATTERN_SCHEMA_MAP` 中添加 C 类 pattern matching 规则：`^C(\d{1,2})$` → C-generic.yaml、`^C(\d{1,2})-2$` → C-deviation-generic.yaml
- [x] 4. 更新 `_resolve_schema_path` 范围校验逻辑（C pattern n∈[2,15]）
- [x] 5. 更新 `test_render_config_smoke.py` 覆盖新增 36 个 C 类 wp_code
- [x] 6. 运行 `test_render_config_smoke.py` + `test_auto_data_resolvers.py` 全绿

## Phase 1: 循环控制测试 (P1)

- [x] 7. 创建 `backend/data/ledger_adapters/wp_render_schema/C-generic.yaml`（2 sheets：控制测试汇总表 + 控制测试过程记录）
- [x] 8. 创建 `backend/data/ledger_adapters/wp_render_schema/C-deviation-generic.yaml`（1 sheet：评价控制偏差，含 7 步评价 + 结论）
- [x] 9. 实现 `_inject_c_cycle_name` 参数化注入逻辑（参照 B23 模式，C2~C15 注入 cycle_name 默认值）
- [x] 10. 实现样本量自动推荐逻辑（前端根据 frequency 字段 → 推荐 sample_size 映射表）
- [x] 11. 验证 pattern matching 正确加载 C-generic.yaml 和 C-deviation-generic.yaml（单元测试）

## Phase 2: 企业层面控制测试 (P2)

- [x] 12. 从 C1 xlsx 模板提取全部 136 行程序步骤结构
- [x] 13. 在 `procedure_table_templates.json` 中注册 C1 程序表模板（136 步 + ref_index）
- [x] 14. 实现 `b22_entity_control_list` auto_data_source resolver（读取 B22A-1~5 + B22B 已识别控制清单）
- [x] 15. 验证 C1 程序表在前端 GtAProgramConsole 正确渲染（手动或 Playwright）

## Phase 3: IT 控制测试 (P3)

- [x] 16. 注册 C22 为 `audit-sheet` componentType（确认 OnlyOffice 可打开 34 sheet）
- [x] 17. 在 `address_registry` 中注册 C22 关键单元格坐标（主程序表结论列 + 各步骤 sheet 结论 + SA/PE/PM/NS 领域汇总）
- [x] 18. 创建 C21 d-form schema YAML（IT专业人员资质）
- [x] 19. 创建 C21-1 d-form schema YAML（IT审计发现汇总表：发现编号/来源/领域/描述/风险等级/回复/状态）
- [x] 20. 创建 C26 d-form schema YAML（信息处理控制测试：系统名/控制编号/描述/类型/依赖ITGC/方法/结果/结论）
- [x] 21. 实现 `itgc_test_result` auto_data_source resolver（读取 C22 各领域结论，返回 sa/pe/pm/ns/overall/finding_count）

## Phase 4: 会计分录测试 (P4)

- [x] 22. 创建 C23 d-form schema YAML（3 sheets：程序表 + 有权录入人员清单测试 + 分录控制测试记录）
- [x] 23. 创建 C24 d-form schema YAML（2 sheets：分录筛选标准及结果 + 细节测试记录）
- [x] 24. 创建 C25 d-form schema YAML（利用内审工作：评价维度/内容/结论/范围/拟实施程序）
- [x] 25. 实现 `je_filter_from_ledger` auto_data_source resolver（从 tb_ledger 按条件筛选候选分录）
- [x] 26. 实现 C24→sampled_vouchers 集成（一键将细节测试分录添加到已抽样凭证表，source='C24'）
- [x] 27. 实现 `internal_audit_reliance` auto_data_source resolver（读取 C25 评价结论）

## Phase 5: 联动 (P5)*

- [x] 28. 实现 `_on_c_control_test_saved` EventBus handler（C2~C15 保存→写入 field_overrides scope=control_test_result:{cycle}）*
- [x] 29. 实现 `control_test_result_for_cycle` auto_data_source resolver（D~N 读取对应循环控制测试结论）*
- [x] 30. 实现 C 偏差→issue_tickets 自动创建（step7="是"→创建 IssueTicket category=control_deficiency）*
- [x] 31. 实现 C22→C21-1 发现自动创建（步骤结论"无效"→C21-1 新增发现记录）*
- [x] 32. 实现 C 偏差评价结论联动更新 control_test_result（结论"无效"→更新 scope 为"部分有效/无效"）*
- [x] 33. 扩展 `test_auto_data_resolvers.py` 覆盖新增 C 类 resolver（control_test_result_for_cycle / b22_entity_control_list / itgc_test_result / je_filter_from_ledger / internal_audit_reliance）*

## Phase 6: 导入导出 + E2E (P6)

- [x] 34. C 类 d-form-table 底稿导出为 Excel（复用通用 d-form-table 导出逻辑）
- [x] 35. C22 OnlyOffice 原生导出（复用 audit-sheet 通用导出）
- [x] 36. 从 Excel 导入填充已有结构化 C 类底稿
- [x] 37. 批量导出 C 类全量打包 zip（项目归档场景）
- [x] 38. Playwright E2E: C2 循环控制测试打开 + 多 sheet 切换 + 汇总表填写 + 保存
- [x] 39. Playwright E2E: C1 企业层面程序表 136 步渲染 + 步骤执行 + ref_index chip
- [x] 40. Playwright E2E: C22 IT 一般控制 OnlyOffice 打开 + 34 sheet Tab 展示
- [x] 41. Playwright E2E: C24 会计分录细节测试 + 从序时账筛选 + 抽凭联动
- [x] 42. Playwright E2E: C2-2 偏差评价 7 步填写 + 结论保存
