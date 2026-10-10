# 公式推送附注跳过减少 · 任务清单

## Task 1: 修复 `locate_table` 的 `_source` 判断（缺陷 B，需求 1.1–1.3，design §二）

- [ ] 1.1 改 `note_writer.py` `locate_table`：把 `_source not in WORKPAPER_SOURCES` 的一刀切拦截改为分级判断——仅 `_source in _KNOWN_NON_WORKPAPER` 时拦截，`_source=NULL` 时放行
- [ ] 1.2 `locate_table` 增加旧格式兜底：无 `sub_table_data` 但有顶层 `rows` 时，返回 `NoteTable(rows=rows, value_keys=[], section_locked=False)`
- [ ] 1.3 写测试 `test_locate_table_source_null_with_sub_table`：`_source=None` + `sub_table_data` 存在 → 正常返回 NoteTable
- [ ] 1.4 写测试 `test_locate_table_source_null_old_format_rows`：`_source=None` + 无 sub + 有 `rows` → 返回旧格式 NoteTable
- [ ] 1.5 写测试 `test_locate_table_source_template_rejected`：`_source="template"` → 返回 None + "模板取数维护"
- [ ] 1.6 变异验证：回退 1.1 改动 → 1.3/1.4 打红
- [ ] 1.7 跑现有 formula_push 测试套件确认无回归

## Task 2: 首次推送后标记 `_source`（需求 1.4，design §二）

- [ ] 2.1 改 `engine.py` `_push_note`：当 `table_data` 被修改且 `_source is None` 时，赋值 `table_data["_source"] = "workpaper"`（在 `note.table_data = table_data` 之前）
- [ ] 2.2 写测试 `test_source_marked_after_first_push`：推送前 `_source=None` → 推送后 `_source="workpaper"`；第二次推送走正常路径不再触发旧格式兜底

## Task 3: 修复 `has_obscured_data` 误报（缺陷 F，需求 4.1–4.2，design §五）

- [ ] 3.1 改 `note_writer.py` `has_obscured_data`：`values` 键走列表递归检查（内部元素全 None/0/""/\"0\" → 非遮挡）；`_` 前缀键跳过
- [ ] 3.2 写测试 `test_has_obscured_data_values_all_none`：`values=[None, None]` → 返回 None（无遮挡）
- [ ] 3.3 写测试 `test_has_obscured_data_values_has_real_data`：`values=[100.5, None]` → 返回中文原因字符串
- [ ] 3.4 写测试 `test_has_obscured_data_skip_underscore_keys`：含 `_cell_meta`/`_cell_modes`/`_legacy_row` → 返回 None
- [ ] 3.5 变异验证：删掉 `k == "values"` 分支 → 3.2 打红

## Task 4: 单科目合计行兜底（缺陷 A，需求 2.1–2.4，design §三）

- [ ] 4.1 改 `engine.py` `_push_note`：在现有"遍历 note_rows → find_row"循环之后，增加合计行兜底——当 `len(binding.account_prefixes)==1` 且无数据行命中时，找合计行（`find_total_row`）并用 is_total 行的汇总值写入
- [ ] 4.2 兜底写入时设标记跳过后续 `_push_note_total`（避免合计行被重算覆盖）
- [ ] 4.3 写测试 `test_total_row_fallback_single_account`：单科目底稿 + 附注子表无同名行 + 有合计行 → 值写入合计行
- [ ] 4.4 写测试 `test_total_row_fallback_not_triggered_multi_account`：多科目底稿 → 不走兜底，行为不变
- [ ] 4.5 写测试 `test_total_row_fallback_not_triggered_when_row_matched`：单科目但精确匹配命中 → 不走兜底
- [ ] 4.6 变异验证：删掉合计行兜底逻辑 → 4.3 打红

## Task 5: 章节号动态定位（缺陷 D，需求 3.1–3.4，design §四）

- [ ] 5.1 改 `engine.py` `_push_note`：在 `section_title` 比对失败后，按 `section_title == _title_check_name` 反查 `disclosure_notes`（限同项目同年度同前缀"五"/"八"），唯一命中时替换 `note` 和 `section`
- [ ] 5.2 反查命中时记录 INFO 日志 `formula_push: 章节号动态定位 {table_name} → {found_section}（规则声明 {rule_section}）`
- [ ] 5.3 写测试 `test_section_dynamic_lookup_on_mismatch`：规则章节号 五、22 → 实际标题"固定资产" ≠ "递延所得税负债" → 反查到 五、30 → 推送成功
- [ ] 5.4 写测试 `test_section_dynamic_lookup_ambiguous_skip`：同 section_title 有 2 条匹配 → 不替换，走原逻辑跳过
- [ ] 5.5 写测试 `test_section_dynamic_lookup_not_triggered_when_match`：硬编码章节号 section_title 匹配 → 不触发反查
- [ ] 5.6 变异验证：删掉反查逻辑 → 5.3 打红

## Task 6: 跑现有测试全套 + 真库回归

- [ ] 6.1 跑 `python -m pytest backend/tests/test_formula_push_*.py -v --tb=short` 全套，确认 0 red（需求 5.3）
- [ ] 6.2 写真库守卫 `test_formula_push_note_skip_pg.py`：在重药控股安徽项目上重跑推送，断言 `skipped_count <= 45`（需求 5.2）
- [ ] 6.3 真库守卫断言 `written_count + unchanged_count + kept_count >= 330`（覆盖率下限）
- [ ] 6.4 真库守卫断言修复前 unchanged 项的值不变（幂等不变量，需求 5.4）

## Task 7: 清理

- [ ] 7.1 清理一次性探针脚本（如有）
- [ ] 7.2 更新 memory.md dev-history 记录本 spec 完成状态
