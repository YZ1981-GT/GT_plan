# 附录 C：写在配置文件里的规则

> 由脚本扫描 `backend/data` 与 `backend/app/data` 下的 JSON 生成；「条数」取文件顶层列表长度，
> 或 rules / entries / mappings / templates / sections 等键下的条数（列了取自哪个键）。
> 写在数据库表里的规则（`report_config`、`formula_setting`、`account_mapping`、`qc_rule_definitions` 等）不在本附录，见正文。

JSON 文件共 1149 个；按目录：

| 目录 | 文件数 | 大小 |
|---|---:|---:|
| `backend/data/wp_guidance` | 404 | 901 KB |
| `backend/data/wp_fine_rules` | 344 | 894 KB |
| `backend/data` | 228 | 82913 KB |
| `backend/data/workpaper_sync_contracts` | 94 | 3099 KB |
| `backend/data/acnr/catalog_snapshots` | 14 | 13852 KB |
| `backend/data/guidance/contracts/gc0/fixtures` | 10 | 19 KB |
| `backend/data/acnr` | 9 | 1498 KB |
| `backend/app/data` | 9 | 3186 KB |
| `backend/data/audit_report_templates` | 8 | 732 KB |
| `backend/data/acnr/sources` | 5 | 1347 KB |
| `backend/data/authz` | 4 | 909 KB |
| `backend/data/formula_presets` | 3 | 1022 KB |

YAML 渲染配置：`backend/data/acnr/sources` 8 个；`backend/data/ledger_adapters/wp_render_schema` 115 个；`backend/data/ledger_adapters/wp_render_schema/generated` 363 个；`backend/app/data/wp_render_schema` 3 个

## 规则类配置文件（顶层目录）

| 文件 | 大小 | 条数 |
|---|---:|---:|
| `backend/data/a16_version_matrix.json` | 1 KB | 2 |
| `backend/data/a17_consistency_rules.json` | 2 KB | 8 |
| `backend/data/account_package_registry.json` | 87 KB | 5 |
| `backend/data/account_to_report_line_seed.json` | 113 KB | 4（mappings） |
| `backend/data/address_label_overrides.json` | 1 KB | 2 |
| `backend/data/address_registry_l2_semantic.json` | 19701 KB | 181 |
| `backend/data/address_registry_l3_dependencies.json` | 9902 KB | 4 |
| `backend/data/address_registry_resolved_refs.json` | 90 KB | 5 |
| `backend/data/amount_input_migration_status.json` | 375 KB | 7 |
| `backend/data/audit_log_rules_seed.json` | 1 KB | 5 |
| `backend/data/audit_report_templates_seed.json` | 18 KB | 8（templates） |
| `backend/data/b5_version_matrix.json` | 1 KB | 3 |
| `backend/data/bcas_cycle_validation_rules.json` | 9 KB | 25（rules） |
| `backend/data/c22_address_registry_seed.json` | 2 KB | 8 |
| `backend/data/cf_verification_formulas.json` | 16 KB | 9 |
| `backend/data/consol_note_section_mapping.json` | 379 KB | 2（mappings） |
| `backend/data/consol_note_sections_listed.json` | 687 KB | 422 |
| `backend/data/consol_note_sections_soe.json` | 387 KB | 251 |
| `backend/data/cross_account_rules.json` | 3 KB | 8（rules） |
| `backend/data/cross_check_preset_rules.json` | 2 KB | 6（rules） |
| `backend/data/cross_wp_references.json` | 290 KB | 6 |
| `backend/data/custom_query_presets.json` | 4 KB | 3 |
| `backend/data/d_address_registry_seed.json` | 5 KB | 15（entries） |
| `backend/data/d_cycle_validation_rules.json` | 18 KB | 25（rules） |
| `backend/data/docx_placeholder_registry.json` | 677 KB | 4 |
| `backend/data/e2e_formula_manifest.json` | 1 KB | 5（accounts） |
| `backend/data/e_address_registry_seed.json` | 5 KB | 19（entries） |
| `backend/data/efghijklmn_cycle_validation_rules.json` | 21 KB | 36（rules） |
| `backend/data/f_address_registry_seed.json` | 19 KB | 61（entries） |
| `backend/data/f_cycle_validation_rules.json` | 4 KB | 4（rules） |
| `backend/data/formula_push_coverage.json` | 33 KB | 81（entries） |
| `backend/data/formula_push_note_row_aliases.json` | 2 KB | 5 |
| `backend/data/formula_push_rules.json` | 227 KB | 268（rules） |
| `backend/data/g_address_registry_seed.json` | 7 KB | 16（entries） |
| `backend/data/g_cycle_validation_rules.json` | 6 KB | 4（rules） |
| `backend/data/gt_template_library.json` | 95 KB | 331（templates） |
| `backend/data/h_address_registry_seed.json` | 5 KB | 11（entries） |
| `backend/data/h_cycle_validation_rules.json` | 4 KB | 4（rules） |
| `backend/data/i_address_registry_seed.json` | 5 KB | 9（entries） |
| `backend/data/i_cycle_validation_rules.json` | 3 KB | 3（rules） |
| `backend/data/j_address_registry_seed.json` | 3 KB | 5（entries） |
| `backend/data/j_cycle_validation_rules.json` | 3 KB | 3（rules） |
| `backend/data/k_address_registry_seed.json` | 5 KB | 9（entries） |
| `backend/data/k_cycle_validation_rules.json` | 5 KB | 3（rules） |
| `backend/data/l_address_registry_seed.json` | 3 KB | 6（entries） |
| `backend/data/l_cycle_validation_rules.json` | 5 KB | 3（rules） |
| `backend/data/ledger_recognition_rules.json` | 10 KB | 3 |
| `backend/data/m_address_registry_seed.json` | 3 KB | 4（entries） |
| `backend/data/m_cycle_validation_rules.json` | 3 KB | 2（rules） |
| `backend/data/multi_standard_note_templates.json` | 6 KB | 2 |
| `backend/data/n_address_registry_seed.json` | 4 KB | 6（entries） |
| `backend/data/n_cycle_validation_rules.json` | 3 KB | 2（rules） |
| `backend/data/note_account_mappings_seed.json` | 70 KB | 280（entries） |
| `backend/data/note_binding_registry.json` | 8 KB | 4 |
| `backend/data/note_check_preset_formulas.json` | 902 KB | 2 |
| `backend/data/note_columns_rules.json` | 180 KB | 2（rules） |
| `backend/data/note_disclosure_balance_rules.json` | 2 KB | 6（rules） |
| `backend/data/note_guidance_rules.json` | 107 KB | 2（rules） |
| `backend/data/note_row_label_aliases.json` | 5 KB | 2 |
| `backend/data/note_table_header_library.json` | 667 KB | 7 |
| `backend/data/note_table_header_vocabulary.json` | 12 KB | 23 |
| `backend/data/note_template_bindings.json` | 2869 KB | 10 |
| `backend/data/note_template_listed.json` | 1585 KB | 206（sections） |
| `backend/data/note_template_soe.json` | 994 KB | 190（sections） |
| `backend/data/note_template_variant_matrix.json` | 34 KB | 101（accounts） |
| `backend/data/note_template_word_alignment_allowlist.json` | 264 KB | 689 |
| `backend/data/note_template_workpaper_alignment_allowlist.json` | 23 KB | 4 |
| `backend/data/note_templates_seed.json` | 3 KB | 4 |
| `backend/data/note_workpaper_sync_registry.json` | 24 KB | 78（entries） |
| `backend/data/note_wp_mapping_rules.json` | 4 KB | 34（mappings） |
| `backend/data/note_write_ownership_matrix.json` | 92 KB | 6 |
| `backend/data/placeholder_mapping_registry.json` | 1 KB | 3 |
| `backend/data/prefill_formula_mapping.json` | 450 KB | 306（mappings） |
| `backend/data/prev3_prefill_locator.json` | 97 KB | 83（entries） |
| `backend/data/project_tags_seed.json` | 1 KB | 8 |
| `backend/data/qc_rule_definitions_seed.json` | 9 KB | 22 |
| `backend/data/ratio_formulas.json` | 12 KB | 35 |
| `backend/data/report_config_seed.json` | 424 KB | 22 |
| `backend/data/report_excel_formulas.json` | 289 KB | 2 |
| `backend/data/review_checklist_templates.json` | 9 KB | 8（templates） |
| `backend/data/s_address_registry_seed.json` | 1 KB | 2（entries） |
| `backend/data/sheet_mapping_rules.json` | 16 KB | 8 |
| `backend/data/soe_listed_mapping_preset.json` | 17 KB | 6 |
| `backend/data/step_sheet_mapping.json` | 349 KB | 179（mappings） |
| `backend/data/t_address_registry_seed.json` | 46 KB | 66（entries） |
| `backend/data/voucher_check_verdict_vocab.json` | 1 KB | 2 |
| `backend/data/workpaper_ac_coverage_matrix.json` | 421 KB | 17 |
| `backend/data/workpaper_render_registry.json` | 13 KB | 59（entries） |
| `backend/data/workpaper_resolver_migration_matrix.json` | 123 KB | 13 |
| `backend/data/workpaper_sync_alert_rules.json` | 14 KB | 17（rules） |
| `backend/data/workpaper_sync_k11_frozen_cross_cycle_keys.json` | 5 KB | 10 |
| `backend/data/workpaper_sync_migration_paradigm.json` | 48 KB | 9 |
| `backend/data/wp_account_mapping.json` | 308 KB | 1025（mappings） |
| `backend/data/wp_parse_rules.json` | 32 KB | 20 |
| `backend/data/wp_parse_rules_extended.json` | 8 KB | 28 |
| `backend/data/wp_template_metadata_b_seed.json` | 53 KB | 19（entries） |
| `backend/data/wp_template_metadata_cas_seed.json` | 196 KB | 71（entries） |
| `backend/data/wp_template_metadata_dn_seed.json` | 592 KB | 89（entries） |
| `backend/data/wp_template_metadata_seed.json` | 54 KB | 86（entries） |
| `backend/app/data/b1_5_kaa_presets.json` | 6 KB | 2（sections） |
| `backend/app/data/b1_risk_assessment_presets.json` | 40 KB | 2 |
| `backend/app/data/component_host_declarations.json` | 2 KB | 4 |
| `backend/app/data/formula_manager_all_pages_denominator.json` | 2947 KB | 7182（items） |
| `backend/app/data/formula_manager_gate_exemptions.json` | 4 KB | 3 |
| `backend/app/data/wp_code_overrides.json` | 53 KB | 1531 |

## 代码里的静态注册表

| 文件 | 名称 | 静态条数 |
|---|---|---:|
| `core/audit_decorator.py` | `_MODEL_REGISTRY` | 6 |
| `routers/wp_step_mapping.py` | `CYCLE_PREREQUISITES_REGISTRY` | 2 |
| `services/capacity_slots.py` | `_REGISTRY` | 运行时注册 |
| `services/cycle_review_context.py` | `_REGISTRY` | 18 |
| `services/export_surface_registry.py` | `EXPORT_SURFACE_REGISTRY` | 18 |
| `services/role_workbench_facade.py` | `ROLE_SECTION_REGISTRY` | 5 |
| `services/workpaper_summaries_service.py` | `SUMMARY_REGISTRY` | 5 |
| `services/wp_action_registry.py` | `ACTION_REGISTRY` | 6 |
| `services/audit_chain/call_sites.py` | `CALL_SITE_REGISTRY` | 45 |
| `services/auto_data_resolvers/__init__.py` | `_REGISTRY` | 运行时注册 |
| `services/bulk_tab/single_tab_adapter.py` | `IE_ADAPTER_REGISTRY` | 运行时注册 |
| `services/custom_query/version_registry.py` | `BUILDER_VERSION_REGISTRY` | 运行时注册 |
| `services/workpaper_sync/store_item_registry.py` | `STORE_MERGE_REGISTRY` | 67 |
| `services/formula_push/bindings/__init__.py` | `_REGISTRY` | 81 |

路由端点：`backend/app/routers` 下 613 个文件、2495 个端点（静态数装饰器）。

