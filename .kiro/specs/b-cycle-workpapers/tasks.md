# B 类底稿（承接与计划）— 任务清单

## Phase 0: 注册与分类基础 (P0)

- [x] 1. 在 `wp_account_mapping.json` 中注册所有 B 类 wp_code（约 60 条新增），包含 wp_name/audit_cycle="B"/must_have 标记
- [x] 2. 在 `_WP_CODE_OVERRIDE` 中添加 B 类 componentType 映射（B1A~B60 约 40 个映射）
- [x] 3. 在 `VALID_COMPONENT_TYPES` 白名单中添加 `redirect-materiality`（B15 专用）
- [x] 4. 更新 render-config 冒烟测试 `test_render_config_smoke.py` 覆盖新增 B 类 wp_code
- [x] 5. 运行 `test_render_config_smoke.py` + `test_auto_data_resolvers.py` 全绿

## Phase 1: 程序表类 (P1)

- [ ] 6. 在 `procedure_table_templates.json` 中添加 B1A 程序表模板（逐步骤从 xlsx 提取）
- [ ] 7. 在 `procedure_table_templates.json` 中添加 B1B 程序表模板
- [ ] 8. 在 `procedure_table_templates.json` 中添加 B2 程序表模板
- [ ] 9. 在 `procedure_table_templates.json` 中添加 B10 程序表模板（从 xlsx 提取所有步骤）
- [ ] 10. 在 `procedure_table_templates.json` 中添加 B11/B12/B13 程序表模板
- [ ] 11. 在 `procedure_table_templates.json` 中添加 B18/B19 程序表模板
- [ ] 12. 在 `procedure_table_templates.json` 中添加 B30 集团审计程序表模板
- [ ] 13. 在 `procedure_table_templates.json` 中添加 B40/B50 程序表模板
- [ ] 14. 验证所有 B 类程序表在前端 GtAProgramConsole 中正确渲染（手动/Playwright）

## Phase 2: 表单类 — D-Form Schema (P2)

- [ ] 15. 创建 B1-1 风险评估表 render schema YAML（`wp_render_schema/B1-1.yaml`）
- [ ] 16. 创建 B1-2 风险评估表 render schema YAML（结构同 B1-1，保持场景）
- [ ] 17. 创建 B2-5 前任沟通评价 render schema YAML
- [ ] 18. 创建 B22A-1~5 企业层面控制 render schema YAML（5 份，结构相似可共用基础模板）
- [ ] 19. 创建 B22B 控制矩阵 render schema YAML（d-form-table + risk_badge 列）
- [ ] 20. 创建 B22C 评价设计有效性 render schema YAML
- [ ] 21. 创建 B23 通用 schema YAML（`B23-generic.yaml`）+ 参数化 cycle 适配 14 组
- [ ] 22. 实现 `_schema_service.load_schema` 对 B23 模式匹配（B23-1~14 共用 generic schema）
- [ ] 23. 创建 B50-1~4 风险汇总表 render schema YAML
- [ ] 24. 创建 B51 舞弊三因素分析 render schema YAML
- [ ] 25. 创建 B52 管理层凌驾风险 render schema YAML
- [ ] 26. 验证 B 类 d-form-table 底稿渲染正确（GtDFormTable 多列+着色）

## Phase 3: Word 文档类 (P3)

- [ ] 27. 将 B 类所有 docx wp_code 注册到 WpPopupDocxEditor 配置（DOCX_CONFIGS）
- [ ] 28. B1-3/B1-4/B1-7 docx 弹窗可打开+OnlyOffice 编辑/降级下载
- [ ] 29. B2 系列 docx（B2-1/B2-3/B2-6/B2-8/B2-11/B2-12）注册
- [ ] 30. B3-1 独立性声明书 docx — 预填项目组成员名单（占位符替换）
- [ ] 31. B5 系列约定书 docx — 按 business_category 自动推荐版本
- [ ] 32. B23-{n}-2 流程图及描述 docx（14 份）注册
- [ ] 33. B30 集团审计系列 docx 注册
- [ ] 34. B40-1/B40-2/B60/B60A~D 等 docx 注册
- [ ] 35. 验证任意 3 个 B 类 docx 底稿可正常打开预览/编辑

## Phase 4: 联动与自动取数 (P4)

- [ ] 36. 实现 `b15_materiality_summary` auto_data_source resolver
- [ ] 37. 实现 `b19_related_party_count` auto_data_source resolver
- [ ] 38. 实现 `b22_entity_control_status` auto_data_source resolver
- [ ] 39. 实现 `b23_walkthrough_progress` auto_data_source resolver
- [ ] 40. 实现 `b50_risk_summary` auto_data_source resolver
- [ ] 41. 实现 B15 重定向逻辑（render-config 返回 redirect + 前端跳转 Materiality）
- [ ] 42. 实现 B3→A17-7 联动（独立性完成→声明书状态更新）
- [ ] 43. 实现 B23→C 类联动（穿行测试结论→控制测试底稿 auto_data_source）
- [ ] 44. 实现 B50-3→D~N 联动（认定层次风险→各循环程序表展示）
- [ ] 45. auto_data_resolvers 测试覆盖（扩展 test_auto_data_resolvers.py）

## Phase 5: LLM 辅助与增强 (P5)*

- [ ] 46. B60 总体审计策略 LLM 生成（联动 TSJ/B60 提示词 + 项目上下文）*
- [ ] 47. B10 行业理解 AI 辅助填充（从知识库+公开信息提取行业要点）*
- [ ] 48. B51 舞弊风险三因素 AI 辅助评估建议*

## E2E 验证

- [ ] 49. Playwright E2E: B1A 程序表打开+步骤渲染+ref_index chip 可点击
- [ ] 50. Playwright E2E: B22A-1 企业层面控制表单渲染+保存
- [ ] 51. Playwright E2E: B23-1 穿行测试多 sheet 切换+编辑+保存
- [ ] 52. Playwright E2E: B50 风险汇总程序表+auto_data_source 实时取值
- [ ] 53. Playwright E2E: B60 docx 预览/OnlyOffice 编辑
