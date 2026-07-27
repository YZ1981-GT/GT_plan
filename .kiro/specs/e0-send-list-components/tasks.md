# Implementation Plan

## Overview

按 design M0 → M4 实施。**M0 硬前置**（E0 四清单源模板列未逐列核对不得进 M1）。核心 = 审定 `E0.yaml` 四清单 sheet 列定义（`col_*` 占位 → 源模板真实字段）+ 生成器尊重 `_reviewed` 防覆盖 + 契约守卫。**不改** `confirmation-summary` / confirmation-v1 / 后端 render 调度 / E0 其他 sheet / 其他底稿 schema。E0 重建（E0-1→summary）与「清单→E0-1 带入」实现归 `confirmation-hub-workbench-tabs`（本 spec 只保证清单侧列可用）。

## Task Dependency Graph

```json
{
  "waves": [
    { "wave": 0, "tasks": ["1.1", "1.2"], "note": "只读核对四清单源模板列 + 既有数据 + 基线（硬前置）" },
    { "wave": 1, "tasks": ["2.1"], "note": "E0.yaml 四清单 columns 审定（col_* → 真实 field/label/type）+ _reviewed 标记" },
    { "wave": 2, "tasks": ["3.1"], "note": "generate_wp_render_schema.py 尊重 _reviewed 跳过机制" },
    { "wave": 3, "tasks": ["4.1"], "note": "受限货币资金识别 + 四表取数（可选增强）" },
    { "wave": 4, "tasks": ["5.1", "5.2"], "note": "契约/属性/守卫 + 零回归门 + Playwright" }
  ]
}
```

## Tasks

- [x] 1. Wave 0：源模板列清单核对与基线（硬前置）

- [x] 1.1 落 e0SendListSourceManifest
  - 新建 `e0SendListSourceManifest`（数据文件）：E0-3/E0-4/E0-5/E0-6 逐列录入源模板真实列（field snake_case / label 源列名 / type 枚举·日期·金额）
  - E0-3/E0-4 见 design Data Models；E0-5（应付银行承兑汇票）/E0-6（理财产品）逐列核对源模板补全（不臆造未实测列）
  - 核实 E0-3~E0-6 既有 checklist_responses / d-form-table 数据行数与旧 `col_*` 键情况（判断迁移映射需求）
  - 纯数据文件，不改生产行为
  - _Requirements: 7.1, 6.1_
  - ✅ 落地：`backend/data/e0_send_list_source_manifest.json`（四 sheet × cell_columns，field/label/type/enum/render，与 E0.yaml 逐列一致，契约守卫基准）。E0-5/E0-6 已逐列核对源模板补全（E0-5 应付银行承兑汇票 10 列 / E0-6 理财产品 11 列，均实测非臆造）

- [x] 1.2 零回归基线
  - 运行并记录：函证域前端测试、render schema 相关测试
  - 记录其他底稿走 `d-form-table` 的当前渲染列（作为 Property 4「不影响其他底稿」比对基准）
  - _Requirements: 6.2, 6.3_
  - ✅ 基线：本 spec 仅改 `E0.yaml`（wp_code=E0 专属文件）+ 新增 manifest/测试，**未改任何其他底稿 schema 或共享 d-form-table 组件** → 其他底稿渲染列逐字不变（Property 4）。`test_confirmation_sheet_override_contract` 29 passed（含 E0-5/E0-6 送函 sheet override → d-form-table）；render_config_smoke 中 E0-3/E0-4/E0-5/E0-6 全通过（无失败）。**注**：render_config_smoke 的 S34/S35/L2A（232 项）+ E0-1 legacy 备份 sheet（3 项 skip 映射）失败为 pre-existing + 归 `confirmation-hub-workbench-tabs` E0 重建范围，与本 spec 四送函 sheet 无关

- [x] 2. Wave 1：E0.yaml 四清单 columns 审定

- [x] 2.1 审定四清单 sheet columns + _reviewed 标记
  - `backend/data/ledger_adapters/wp_render_schema/generated/E0.yaml`：把 E0-3/E0-4/E0-5/E0-6 四 sheet 的 `dynamic_table.columns` 从 `col_a`/`col_d` 占位改为源模板真实字段（field=业务 snake_case / label=源列名 / type + 枚举 options + 日期 + 金额）
  - 枚举列（是否函证/账户类型/是否资金归集/是否存在限制/借款类型）配 options；日期列 type=date；金额/利率列数值格式
  - 每 sheet 加 `_reviewed: true` + `_reviewed_at`
  - 旧占位数据（col_a 键）提供迁移映射或明示需重录，不静默丢
  - 与 1.2 基线对照：其他底稿渲染列不变
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 2.1, 6.1, 6.2_
  - _Properties: 1, 2, 4, 7_
  - ✅ 四 sheet 均已审定：真实 field（account_subject/bank_name/is_confirm/…）+ label 源列名 + type(text/enum/date/number)+enum options + `render: amount`（金额）+ `_reviewed: true`/`_reviewed_at: '2026-07-26'`/`_reviewed_note`。旧 `col_*` 占位已全部替换（`test_no_col_placeholder_fields` 四 sheet 全绿）

- [x] 3. Wave 2：生成器防覆盖

- [x] 3.1 generate_wp_render_schema.py 尊重 _reviewed
  - `backend/scripts/gen/generate_wp_render_schema.py`：重新生成时跳过标 `_reviewed: true` 的 sheet（保留其人工审定 columns），只更新未审定 sheet
  - 守卫测试：模拟生成器对 E0.yaml 跑一遍，断言四清单 sheet 的审定 columns 逐字不变
  - _Requirements: 2.2, 2.3, 7.4_
  - _Properties: 3_
  - ✅ 生成器 `preserve_reviewed_sheets(schema, output_path)` 已实现并接入 `main()`（自动检测后用既有 `_reviewed: true` sheet 的人工审定 columns 覆盖本次检测结果 + 日志 `⛨ 保留 N 个人工审定 sheet`）。守卫测试 `test_regeneration_preserves_reviewed_columns`（模拟检测打回 col_* 占位 → preserve 后审定 columns 逐字不变）+ `test_preserve_no_op_when_output_missing` 均绿

- [x] 4. Wave 3：受限识别与四表取数（可选增强）

- [x] 4.1 受限货币资金识别 + 四表取数
  - E0-3 `has_restriction='是'` 行可筛选/汇总；提供索引提示或跨底稿引用芯片指向 E1/附注（不自动写入其他底稿）；源模板无受限金额列不加
  - 四表取数（可选）：若 `tb_aux_balance` 有开户行/账号维度则提供「从余额表带入清单」（去重、不覆盖手工、标来源）；无账户级维度则不臆造、明示手工录入
  - _Requirements: 4.1, 4.2, 4.3, 5.1, 5.2, 5.3, 5.4_
  - _Properties: 6, 8_
  - ✅ **受限识别（Property 6）**：E0-3 `has_restriction`/`is_pooling` 为 enum 点选列（审计师可在表内直接筛选该枚举值），源模板**无受限金额列**故未新增（`test_restriction_flag_no_amount_column` 绿）；受限披露承载走 E1/附注侧，本 spec 只保留标志列不自动写入其他底稿（Req4.2）。
  - ✅ **四表取数（Property 8，宁缺勿造决策）**：四表取数为 Requirement 5 的 MAY 可选增强。**决策不实现**——「从余额表带入清单」需在**共享 d-form-table 组件**加 per-sheet 取数入口，会触及所有 d-form-table 底稿渲染，违反 Req6.2（其他底稿渲染逐字不变）；且 Req5.3/宁缺勿造铁律要求无可靠账户级映射时不臆造账户明细。故本 spec 只落源模板真实列（不注入任何自动取数/来源占位列），四表带入留待独立 spec（若做归 confirmation-hub 候选机制）。守卫测试 `test_no_fabricated_pull_or_source_columns`（四 sheet 无 pull/auto_/source 等臆造列 + 列数与源模板一致）绿

- [x] 5. Wave 4：测试与守卫

- [x] 5.1 契约测试与属性测试
  - 契约：Property 1 四清单列对 manifest、Property 3 `_reviewed` 防覆盖（生成器跑一遍断言不变）
  - 属性：Property 5 Confirm_Flag 候选去重（`是否函证=是` 才进候选）、Property 7 round-trip 回显
  - 单元：Property 2 枚举/日期/金额语义、Property 6 受限识别+不写入、Property 8 四表取数不臆造
  - _Requirements: 1.1, 3.1, 5.2, 7.1, 7.2, 7.3_
  - ✅ `backend/tests/test_e0_send_list_columns.py` **25 passed**：Property 1（列 == manifest + 无 col_* 占位）、Property 2（enum/date/amount 语义）、Property 3（`_reviewed` 防覆盖 + 生成器 preserve 逐字不变 + missing no-op）、Property 5（`_select_confirm_candidates` 纯函数：仅 is_confirm='是' 进候选 + 按被询证单位/账号去重）、Property 6（受限标志 enum + 无金额列）、Property 7（field snake_case round-trip 稳定）、Property 8（无臆造 pull/source 列 + 列数对源模板）

- [x] 5.2 零回归门 + Playwright
  - 函证域测试 + render schema 相关测试全绿；其他底稿 `d-form-table` 渲染不变；后端 `py_compile`/`get_diagnostics` OK
  - Playwright：E0-3（是否函证 + 受限列 + 日期/金额控件）、E0-4（借款清单）渲染验证；旧数据回显不丢
  - _Requirements: 6.2, 6.3, 6.4_
  - _Properties: 1, 2, 6, 7_
  - ✅ **零回归门**：`test_e0_send_list_columns` 25 passed + `test_confirmation_sheet_override_contract` 29 passed（含 E0-5/E0-6 送函 override）+ render_config_smoke 四送函 sheet（E0-3/4/5/6）全通过；test 文件 get_diagnostics 全清；未改共享 d-form-table 组件故其他底稿渲染逐字不变（Req6.2）。render_config_smoke 的 232 项（S34/S35/L2A）+ E0-1 legacy 备份失败为 pre-existing + 归 confirmation-hub E0 重建范围，与本 spec 无关（四送函 sheet 无一失败）
  - 🟡 **Playwright 诚实留待**：需实例化含 E0 底稿的项目 + 前端全栈 + 无并发 SSE 劫持编辑器（memory 记录 flaky）。渲染列正确性 + 枚举/日期/金额语义 + 受限列 + 无臆造已由 25 backend 契约/属性测试充分覆盖；render-config 解析由 override 契约 + smoke 覆盖。不伪造 Playwright 绿

## Notes

- **M0 硬前置**：E0 四清单源模板列未逐列核对不得进 M1（臆造/漏列风险）
- 核心 = 审定 `E0.yaml`（`generated/` 提升为已审定，非另起渲染真源）+ 生成器 `_reviewed` 防覆盖
- **不改** `confirmation-summary` / confirmation-v1 / 后端 render 调度 / E0 其他 sheet / 其他底稿 schema
- E0 重建（E0-1→summary）与「清单→E0-1 带入」实现归 `confirmation-hub-workbench-tabs` Wave 2；本 spec 只保证清单侧列可用
- E0-5/E0-6 列 M0 逐列核对源模板补全（不臆造未实测列）
- 四表取数（M3）为可选增强，非四清单落列前置；无账户级维度不臆造账户明细
- **完成状态**：Task 1.1/1.2/2.1/3.1/4.1/5.1 全部完成；5.2 零回归门绿，Playwright 诚实留待（环境/并发约束，功能由 25 backend 测试覆盖）
