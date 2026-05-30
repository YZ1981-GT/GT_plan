# Spec 覆盖矩阵：template-library-coordination

自动生成于 `backend/scripts/build_spec_coverage_matrix.py`，扫描：
- requirements.md：22 个需求
- design.md：17 个 Property
- tasks.md：41 个 task（已完成 41）
- 测试文件：4 个，53 个测试函数带 Validates 标签

## 四向映射表（按需求编号横向展开）

| 需求 | 标题 | 关联 Tasks | 关联 Properties | 关联 Tests |
|---|---|---|---|---|
| 1 | 统一管理页面入口 | 2.5 ✓, 2.6 ✓ | P1, P16 | test_seed_all_requires_admin（via P16）, test_property_16_backend_mutat（via P16） |
| 2 | 底稿模板库浏览 | 1.3 ✓, 2.8 ✓ | P2, P3, P4 | test_property_2_template_list_（via P2）, test_property_3_cycle_sort_ord（via P3）, test_property_4_template_count（via P4） |
| 3 | 底稿模板详情与文件管理 | 4.7 ✓ | P2, P11 | test_property_2_template_list_（via P2）, test_property_11_file_count_ac（via P11） |
| 4 | 底稿模板树形完善（WorkpaperWorkbench 集成 | 1.14 ✓, 2.1 ✓ | P10, P12 | test_property_10_generated_fie（via P10）, test_property_12_progress_calc（via P12） |
| 5 | 底稿模板搜索与筛选 | 2.8 ✓ | P5 | test_property_5_search_filter_（via P5） |
| 6 | 预填充公式查看（D13 ADR：JSON 源只读） | 2.9 ✓, 3.1 ✓, 3.6 ✓ | P16, P17 | test_mutation_endpoints_return（via P17）, test_seed_all_requires_admin（via P16）, test_property_16_backend_mutat（via P16）, test_property_17_json_source_r（via P17）, test_property_17_actual_endpoi（via P17） |
| 7 | 报表公式管理 | 3.2 ✓ | P6, P15 | test_formula_coverage_calculat（via P6）, test_property_6_coverage_calcu（via P6）, test_property_15_invalid_formu（via P15） |
| 8 | 公式覆盖率统计仪表盘 | 3.4 ✓ | P6, P7 | test_formula_coverage_calculat（via P6）, test_property_6_coverage_calcu（via P6）, test_property_7_coverage_color（via P7） |
| 9 | 审计报告模板查看（D13 ADR：JSON 源只读） | 3.7 ✓, 4.1 ✓ | P16, P17 | test_mutation_endpoints_return（via P17）, test_seed_all_requires_admin（via P16）, test_property_16_backend_mutat（via P16）, test_property_17_json_source_r（via P17）, test_property_17_actual_endpoi（via P17） |
| 10 | 附注模板管理 | 4.2 ✓ | — | — |
| 11 | 致同编码体系展示 | 4.3 ✓ | P1, P4, P16 | test_seed_all_requires_admin（via P16）, test_property_4_template_count（via P4）, test_property_16_backend_mutat（via P16） |
| 12 | 报表行次配置管理 | 4.4 ✓ | — | — |
| 13 | 种子数据一键加载 | 0.2 ✓, 1.1 ✓, 1.4 ✓, 3.6 ✓, 4.5 ✓, 5.5 ✓ | P9, P14, P16 | test_seed_all_savepoint_isolat（via P9）, test_seed_all_requires_admin（via P16）, test_property_9_seed_load_resi（via P9）, test_property_14_seed_load_his（via P14）, test_property_16_backend_mutat（via P16） |
| 14 | 模板版本管理 | 0.2 ✓, 1.1 ✓, 1.4 ✓, 1.6 ✓, 2.5 ✓, 4.8 ✓, 5.1 ✓, 5.2 ✓ | P14 | test_property_14_seed_load_his（via P14） |
| 15 | 模板与项目关联展示 | 4.7 ✓ | — | — |
| 16 | 模板列表 API 完善 | 1.3 ✓, 1.6 ✓ | P2, P3, P10, P11 | test_list_endpoint_response_ti, test_property_2_template_list_（via P2）, test_property_3_cycle_sort_ord（via P3）, test_property_11_file_count_ac（via P11）, test_property_10_generated_fie（via P10） |
| 17 | 公式管理全局 API | 0.2 ✓, 1.1 ✓, 1.2 ✓, 1.5 ✓, 2.7 ✓ | P6 | test_formula_coverage_calculat（via P6）, test_property_6_coverage_calcu（via P6） |
| 18 | 种子数据状态 API | 0.2 ✓, 1.1 ✓, 1.5 ✓, 1.6 ✓, 2.7 ✓ | P8 | test_seed_status_derivation_pu（via P8）, test_property_8_seed_status_de（via P8） |
| 19 | 仅有数据筛选兼容 | 2.3 ✓ | P13 | test_property_13_only_with_dat（via P13） |
| 20 | 循环进度统计 | 1.14 ✓, 2.1 ✓, 2.2 ✓ | P7, P12 | test_property_12_progress_calc（via P12）, test_property_7_coverage_color（via P7） |
| 21 | 全局枚举字典管理 | 5.6 ✓, 6.1 ✓, 6.2 ✓, 6.3 ✓, 6.7 ✓ | P16 | test_seed_all_requires_admin（via P16）, test_property_16_backend_mutat（via P16） |
| 22 | 自定义查询管理 | 6.4 ✓, 6.5 ✓, 6.6 ✓, 6.7 ✓ | — | — |

## 漏报检查

- ✓ 全部需求都有对应 task
- ⚠ 1 个 Property 无自动化测试（[Pending/Skipped]）：[1]

## 汇总

- 需求 → Task 覆盖：22/22 = 100%
- Property → Test 覆盖：16/17 = 94%