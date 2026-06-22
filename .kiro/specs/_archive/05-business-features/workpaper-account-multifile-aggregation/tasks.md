# 实施计划：科目底稿多文件聚合、联动与行业可扩展

## Sprint 1：消费注册表实现聚合 + 前端格式选型（需求 1/2）

- [x] 1. 新建 `AccountPackageResolver` 消费已有注册表
  - [x] 1.1 创建 `backend/app/services/wp_account_package_resolver.py`，定义 `_SHEET_TYPE_TO_CLASS` 映射（sheet_type → class_code，确保 HTML 类 componentType）。映射的每个 class_code 必须经 `class_code_to_component` 返回非 None 且为 HTML 白名单类型（已核验：control_panel/procedure→`A-*`→a-program-console；audit_sheet→`F-审定表`、detail_table/analysis→`F-明细表`→audit-sheet；adjustment→`D-调整`→d-form-table；disclosure→`C-*`→c-note-table；conclusion→`D-政策检查`→d-form-paragraph，禁止映射到 `F-`/`G-` 等 fallback univer 的键）
    - _需求: 2.1-2.5_
  - [x] 1.2 实现 `resolve_package_sheets(db, wp_code, project_id)`：读 `account_package_registry_service`，每 sheet 按 sheet_type 映射 class_code/componentType，解析 source_wp_code → 模板文件，返回 `list[ClassificationResult]`（含 source_files）；无条目返回 None
    - _需求: 1.1, 1.2, 1.3_
  - [x] 1.3 GT_Custom / 占位跳过；无注册表条目返回 None
    - _需求: 1.4, 1.5_

- [x] 2. `get_render_config` 接入
  - [x] 2.1 Step 4 后调 `resolve_package_sheets`，命中则替换 classifications；未命中走原逻辑（零回归）。**忽略 registry 的 `mapping_status` 字段**（当前为 `pending_inventory_reconciliation`），只要 package 存在即直接消费其 `sheets`，不得用 mapping_status 做门控
    - _需求: 1.1, 1.4, 7.2_
  - [x] 2.2 `RenderContext` 加 `source_files` 字段，dispatch 时填充
    - _需求: 3.1_
  - [x] 2.3 验证每 sheet componentType 落在已注册 HTML 渲染白名单（analysis→audit-sheet 非 univer）
    - _需求: 2.3, 2.6, 2.7_

- [x] 3. `test_account_package_resolver.py`：D2 返回 14 sheet；每 componentType 为 HTML 类（无 univer/无空白）；GT_Custom skip；新增断言遍历 `_SHEET_TYPE_TO_CLASS` 全部值经 `class_code_to_component` 返回非 None 且 ∈ HTML 白名单
  - _需求: 1.1, 1.2, 2.1-2.5_

## Sprint 2：同名内容合并（需求 3）

- [x] 4. 多源 sheet 合并工具
  - [x] 4.1 创建 `backend/app/services/wp_multifile_sheet_merge.py`：`content_hash`（单元格 md5 + LRU）
    - _需求: 3.2_
  - [x] 4.2 `merge_or_dedup`：哈希同去重 / 不同合并 source_files
    - _需求: 3.2, 3.3_
  - [x] 4.3 `merge_sheet_content`：c-note-table 披露多源拼接 + 来源标识行；audit-sheet 纵向拼接
    - _需求: 3.1_
  - [x] 4.4* 内容哈希幂等 Property-Based 测试
    - _需求: 3.2_

- [x] 5. 渲染策略接入合并
  - [x] 5.1 `_c_note.py` / `_audit_sheet.py`：`source_files`>1 时调 `merge_sheet_content`
    - _需求: 3.1, 3.4_
  - [x] 5.2 各策略从 sheet 的 source_files 读内容（替代全局单 template_path）
    - _需求: 1.2, 3.1_

- [x] 6. `test_multifile_sheet_merge.py`：同名披露多源合并含来源标识；GT_Custom 去重；tab 不重复
  - _需求: 3.1, 3.3, 3.4_

## Sprint 3：底稿间联动完善（需求 4）

- [x] 7. 四表库取数联动
  - [x] 7.1 验证聚合后审定表(audit-sheet)/明细表触发四表库取数；确认 `wp_account_mapping.json` 含 D2 应收账款码(1122)
    - _需求: 4.1, 4.2_
  - [x] 7.2 明细表合计 → 审定表行 ref_index 引用联动
    - _需求: 4.3_
  - [x] 7.3 取数失败友好降级（空值+提示不报错）
    - _需求: 4.8_

- [x] 8. 审定/调整/披露联动
  - [x] 8.1 验证审定表保存 → `_on_d_audit_determination_saved` 回写 trial_balance（聚合后 sheet 名匹配 `[D-N]\d+-1`）
    - _需求: 4.4_
  - [x] 8.2 调整分录汇总表 D2-4 引用项目级 AJE/RJE 本科目分录；审定表调整列反映
    - _需求: 4.5_
  - [x] 8.3 披露表引用审定金额 + sync-to-disclosure-notes；stale 提示
    - _需求: 4.6, 4.7_

- [x] 9. `test_account_package_linkage.py`：取数预填 / 审定回写 / 调整引用 / 披露同步
  - _需求: 4.1, 4.4, 4.5, 4.6_

## Sprint 4：行业可扩展 + 用户自定义模板（需求 6）

- [x] 10. 注册表行业维度
  - [x] 10.1 `account_package_registry.json` 每 package 加 `industry` 字段（默认 ["通用"]）
    - _需求: 6.1_
  - [x] 10.2 `resolve_package_sheets` 按优先级解析（项目>事务所>行业>通用）+ 行业回退
    - _需求: 6.5, 6.7_

- [x] 11. 导出/导入自定义模板
  - [x] 11.1 迁移 `custom_account_packages` 表（scope/scope_id/wp_code/industry/package_json）+ R 回滚
    - _需求: 6.3, 6.4_
  - [x] 11.2 `GET /api/account-packages/{wp_code}/export-template`：导出可编辑模板（xlsx/YAML 含 sheet_type+字段定义）
    - _需求: 6.2_
  - [x] 11.3 `POST /api/account-packages/import-template`：解析+校验（sheet_type/componentType/必填）→ 写 custom 表
    - _需求: 6.3, 6.4_
  - [x] 11.4 导入校验失败返回明确错误清单（不静默）
    - _需求: 6.6_
  - [x] 11.5 `resolve_package_sheets` 先查 custom 表再读内置 registry
    - _需求: 6.4, 6.5_

- [x] 12. `test_custom_account_package.py`：导出→编辑→导入往返；非法拒绝；优先级解析；行业回退
  - _需求: 6.2, 6.3, 6.5, 6.6, 6.7_

## Sprint 5：美观/前端 + 实测（需求 5/7）

- [x] 13. 底稿目录与 tab 美化
  - [x] 13.1 `GtBArchitectureTree` 聚合后 4 阶段分类（检查表/分析表归实质性程序）
    - _需求: 5.2_
  - [x] 13.2 标题纯科目名；tab 按审计逻辑顺序；多源单一 tab
    - _需求: 5.1, 5.3_
  - [x] 13.3 sheet 间 ref_index chip 跳转（审定↔明细↔披露）
    - _需求: 5.4, 5.5_

- [x] 14. 通用性零回归
  - [x] 14.1 D4 营业收入等多文件科目聚合验证（补 registry 条目如缺）
    - _需求: 7.1_
  - [x] 14.2 render-config smoke + cycle 验证零回归
    - _需求: 7.3_
  - [ ] 14.3* 聚合性能 LRU+mtime 缓存命中验证
    - _需求: 7.4_

- [x] 15. Playwright 实测
  - [x] 15.1 D2 三项目：14 sheet 全 HTML 渲染无空白；标题"应收账款"；底稿目录 4 阶段
    - _需求: 1.2, 2.6, 5.1, 5.2_
  - [x] 15.2 联动实测：审定表取数 / 审定→TB 回写 / 披露合并含来源 / 跳转 0 error
    - _需求: 3.1, 4.1, 4.4_
  - [x] 15.3 自定义往返实测：导出 D2→加 sheet→导入→渲染生效
    - _需求: 6.2, 6.3, 6.4_

## 验收门槛

- [x] V1 D2 render-config 返回全部 sheet（≥14），每个 componentType 为可渲染 HTML 类（无 univer 空白）
- [x] V2 同名披露含多文件合并内容 + 来源标识；GT_Custom 去重
- [x] V3 审定表四表库取数 + 审定→TB 回写 + 调整/披露联动生效
- [x] V4 导出→编辑→导入自定义模板往返成功，渲染生效；非法校验拒绝
- [x] V5 行业分层解析（项目>事务所>行业>通用）+ 通用回退
- [x] V6 单文件底稿零回归；cycle 验证 + smoke 全绿
- [x] V7 Playwright D2 三项目实测 0 组件级 error
