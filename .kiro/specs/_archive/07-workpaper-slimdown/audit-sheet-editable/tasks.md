# Tasks: 审定表可编辑升级 (GtAuditSheet)

## Overview

按 design 分 5 组增量实施：① 后端行提取+数据准备 → ② 分类映射+注册 → ③ 前端 GtAuditSheet 核心 → ④ TB 取数+自动计算 → ⑤ 导入导出+行操作+收尾。每组可独立验证。

## Tasks

### 组 ① 后端行提取 + 数据准备

- [x] 1. 新建 `wp_audit_sheet_extract.py` — 审定表行项目提取纯函数
  - 新建 `backend/app/services/wp_audit_sheet_extract.py`
  - `extract_audit_rows(file_path, sheet_name) -> list[dict]`：从 xlsx 模板提取行项目名+缩进+粗体+分节+合计标记
  - 解析策略：定位"项目"/"科目"表头行 → 逐行取 A 列非空值 → 缩进从前导空格/「  」推断 → 分节行(一、二、三)/合计行(含"合计"/"小计") 标记







  
  - 降级：文件不存在/解析失败 → 返回 []
  - _Requirements: 2.1, 2.2, 2.3, 2.4_

- [x] 2. `wp_render_config.py` 新增 `_generate_audit_sheet_data()`
  - 持久化优先：若 `html_data.get("audit_rows")` 已有且非空 → 直接返回
  - 否则调 `extract_audit_rows` 从模板生成默认行
  - 返回 `{ "audit_rows": [...], "tb_values": {} }`（TB 取数在组④补）
  - _Requirements: 2.1, 4.3_

- [x] 3. 单元测试 `test_wp_audit_sheet_extract.py`
  - 正常审定表模板解析（D1-1 应收票据）→ 行数>0 + 含分节/合计/缩进
  - 空模板/文件不存在 → 返回 []
  - _Requirements: 2.2, 2.3_

- [x] 4. 检查点 — 后端行提取测试通过

### 组 ② 分类映射 + componentType 注册

- [x] 5. `wp_classification_service.py` 拆分 F-审定表 → audit-sheet
  - 仿 `_D_SUB_ROUTING` 精确匹配模式,新增 `_F_SUB_ROUTING = {'F-审定表': 'audit-sheet'}`
  - 在 `derive_component_type` 中:当 `class_code.startswith("F-")` 时,先查 `_F_SUB_ROUTING`(精确命中返回),未命中 fallback 到 `"univer"`
  - **不改** `_CLASS_TO_COMPONENT["F-"]`（前缀循环保留给 G- 等其他类）
  - 其余 `F-` class_code（F-明细表/F-分析表/F-汇总表/G-*）仍返回 `univer`
  - _Requirements: 7.2, 7.4_

- [x] 6. `htmlRendererRegistry.ts` 注册 `audit-sheet`
  - 追加 HtmlComponentType `'audit-sheet'`
  - REGISTRY_LIST 追加 `{ componentType: 'audit-sheet', component: GtAuditSheet(lazy), icon: '📊', label: '审定表', emits: ['save','field-change'] }`
  - `useWpRenderer.ts` 的 HtmlComponentType 联合类型同步
  - `useEditorMode.spec.ts` 类型列表同步
  - _Requirements: 7.1, 7.3_

- [x] 7. `wp_render_config.py` 对 `audit-sheet` componentType 走新数据准备
  - 在 sheet_configs 组装循环中：`if component_type == "audit-sheet"` → 调 `_generate_audit_sheet_data`
  - _Requirements: 7.3_

- [x] 8. 检查点 — 分类映射+注册正确（getDiagnostics 无类型错误）

### 组 ③ 前端 GtAuditSheet 核心渲染+编辑+保存

- [x] 9. 新建 `GtAuditSheet.vue` — 核心可编辑表格
  - el-table + 固定列（序号/项目/期初未审/期初审定/本期未审/账项调整/重分类/审定数/变动额/变动率/原因）
  - 可编辑列：账项调整(el-input-number) / 重分类(el-input-number) / 原因(el-input)
  - 只读列：期初未审/期初审定/本期未审（从 tb_values 填）/ 审定数/变动额/变动率（computed）
  - 自动计算：审定=未审+调整+重分类 / 变动额=审定-期初审定 / 变动率=变动额÷期初审定
  - 自动计算列紫色标识（GT 紫 `--gt-color-primary`）
  - 项目列缩进渲染（paddingLeft: indent * 12px）+ 粗体
  - 分节行/合计行样式区分
  - GT 紫设计令牌全局
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5_

- [x] 10. GtAuditSheet 保存功能
  - 工具栏保存按钮 → emit('save', { sheet_name, audit_rows })
  - **仅持久化用户编辑列**:audit_rows 中只写 adj_amount/reclass_amount/reason + 自定义新增行的完整数据
  - **不持久化 TB 实时值**:opening_unadjusted/current_unadjusted/sys_aje/sys_rje 在保存前从 row 中剔除（下次加载重新从 trial_balance 查）
  - 父组件 GtWpRenderer/WorkpaperEditor 调 POST /api/workpapers/{id}/save 将 audit_rows 写入 parsed_data.html_data[sheet].audit_rows
  - 保存后 touch_after_parsed_data_commit 缓存失效（复用现有链路）
  - _Requirements: 4.1, 4.2, 4.3, 4.4_

- [x] 11. GtAuditSheet 工具栏（全屏/公式按钮/还原）
  - useFullscreen composable（复用 NetAssetSheet 模式）
  - 公式按钮 → emit('open-formula')（后续接 FormulaEditDialog）
  - 还原按钮 → 重新从后端获取模板默认行
  - _Requirements: 6.3_

- [x] 12. 检查点 — GtAuditSheet 可渲染+编辑+保存（Playwright 或手动验证）

### 组 ④ TB 取数 + 自动计算联动

- [x] 13. 后端 `_generate_audit_sheet_data` 补 TB 取数逻辑
  - 根据 wp_code 查 `wp_account_mapping.json` 获取 `account_codes`（如 D1 → ["1121"]）
  - 根据 audit_rows 中每行的 `account_code` 字段,直接 SQL 查 `trial_balance` 表:
    - `opening_unadjusted` ← `trial_balance.opening_balance`
    - `current_unadjusted` ← `trial_balance.unadjusted_amount`
    - `sys_aje` ← `trial_balance.aje_adjustment`（系统汇总参考值）
    - `sys_rje` ← `trial_balance.rje_adjustment`（系统汇总参考值）
  - 期初审定数 = `opening_balance`（简单方案:上年结转余额通常含审计调整）
  - 精确方案（跨项目查上年 `audited_amount`）作为后续增强,当前不做
  - 填充 `tb_values: { "row-{n}": { opening_unadjusted, current_unadjusted, sys_aje, sys_rje } }`
  - TB 不存在（项目未导入账套）→ tb_values 对应键为 null,不影响编辑
  - _Requirements: 3.1, 3.2, 3.3_

- [x] 14. 前端 GtAuditSheet 消费 tb_values + 用户覆盖逻辑
  - 加载时将 tb_values 合并到 tableData 对应行（作为只读展示字段,不写入 v-model）
  - 自动计算公式:
    - `audited = current_unadjusted + (adj_amount ?? sys_aje ?? 0) + (reclass_amount ?? sys_rje ?? 0)`
    - 即用户未编辑调整数时,用系统汇总的 AJE/RJE 作参考值;用户填了则覆盖
    - `opening_audited = opening_unadjusted`（简单方案）
    - `change = audited - opening_audited`
    - `rate = change / opening_audited`（分母≠0 时）
  - 自动计算列随 TB/用户编辑联动
  - _Requirements: 3.1, 3.4, 1.4_

- [x] 15. 检查点 — TB 取数+自动计算验证

### 组 ⑤ 导入导出 + 行操作 + 收尾

- [x] 16. GtAuditSheet 导入导出
  - 导出模板：生成 xlsx（行项目名 + 列标题）供离线填写
  - 导入 Excel：按行名匹配 → 预览弹窗（匹配/跳过数） → 确认导入
  - 复用 `useExcelIO` composable
  - _Requirements: 5.1, 5.2, 5.3_

- [x] 17. GtAuditSheet 行操作
  - +新增行（尾部追加空行）
  - 多选+批量删除
  - 合计行自动汇总明细行（isComputed=true computed 求和）
  - _Requirements: 6.1, 6.2, 6.4_

- [x] 18. 最终检查点 — 全链路验证
  - 后端测试通过 + 前端 getDiagnostics 无错
  - D1 应收票据审定表 sheet → componentType=audit-sheet → GtAuditSheet 可编辑+计算+保存
  - 其余 F-明细表/G-测算 仍走 univer/GtGridSheet 不受影响
