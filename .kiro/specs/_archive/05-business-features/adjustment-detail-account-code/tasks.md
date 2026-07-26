# Implementation Plan

## Overview
在 `adjustment_entries` 新增可空 `detail_account_code`（明细科目码），一级 `standard_account_code` 及其下游（校验/recalc/报表/审定）零变更。纯增量、灰度安全、历史零回归。

## Task Dependency Graph
```json
{
  "waves": [
    { "wave": 0, "tasks": ["1.1", "1.2"], "desc": "安全网 characterization 基线（零回归锚点）" },
    { "wave": 1, "tasks": ["2.1", "2.2"], "desc": "数据层：迁移 V126 + ORM/schema 字段" },
    { "wave": 2, "tasks": ["3.1", "3.2"], "desc": "服务层：create/update 持久化 + 响应序列化" },
    { "wave": 3, "tasks": ["4.1"], "desc": "导入解析保留明细码（一级归一不变）" },
    { "wave": 4, "tasks": ["5.1"], "desc": "前端明细表联动优先明细码 + NULL 回退" },
    { "wave": 5, "tasks": ["6.1", "6.2"], "desc": "说明/手册对齐 + 导出序列化 additive" },
    { "wave": 6, "tasks": ["7.1", "7.2", "7.3"], "desc": "属性测试 + 契约零影响 + 零回归门" }
  ]
}
```

## Tasks

- [x] 1. 安全网 characterization 基线
- [x] 1.1 后端锁定「不提供明细码」基线
  - 新建 `tests/test_adjustment_detail_account_code_characterization.py`
  - 锁定：现有导入（旧模板/无明细码）→ 分录 line_items 结果、`standard_account_code` 归一值、`_build_group_response` 序列化字段集与现状一致
  - _Requirements: 1.3, 9.1_
- [x] 1.2 recalc parity 基线
  - 锁定：一批分录 recalc 后 `aje_adjustment/rje_adjustment/audited_amount` 数值（作为 Wave1-3 前后对比锚点）
  - 断言 recalc 调整聚合 SQL 仍 `group_by adjustments.account_code`（源码/AST 断言，不引用 detail_account_code）
  - _Requirements: 6.1, 6.2, 9.1_

- [x] 2. 数据层
- [x] 2.1 迁移 V127 + 回滚（V126 已被 audit_check_signoff 占用 → 用 V127）
  - 新建 `migrations/V127__add_adjustment_entry_detail_account_code.sql`：information_schema 守护幂等加列
  - 新建对应 `R127` 回滚
  - 应用迁移（`python -m app.core.migration_runner`，cwd=backend）+ 验证 drift=0
  - _Requirements: 1.1, 7.3_
- [x] 2.2 ORM + schema 字段
  - `models/audit_platform_models.py::AdjustmentEntry` 加 `detail_account_code: Mapped[str | None]`
  - `models/audit_platform_schemas.py::AdjustmentLineItem` 加 `detail_account_code: str | None = None`
  - _Requirements: 1.1, 1.2, 7.2_

- [x] 3. 服务层
- [x] 3.1 create_entry / update_entry 持久化
  - `adjustment_service.py::create_entry`（~142）与 `update_entry`（~284）写 `detail_account_code=li.detail_account_code`
  - _Requirements: 3.1, 3.2, 3.3_
- [x] 3.2 分录组响应序列化
  - `_build_group_response`（~932）line_items 序列化补 `detail_account_code`
  - 单测：response line 含字段，NULL→null
  - _Requirements: 4.1, 4.3, 8_

- [x] 4. 导入解析
- [x] 4.1 _import_adjustments 保留明细码
  - `routers/import_templates.py::_import_adjustments`：解析出原始明细码（`sub_code` 或名称反查的 client 二级码），当 `明细码 ≠ 归一后一级码` 时放入 line_item `detail_account_code`；`standard_account_code` 归一逻辑逐字节不变
  - 明细码为空/等于一级 → NULL（Req2.3）；异常 → fallback NULL 不阻断
  - 单测：P2（归一不变）/P3（明细保留）/P4（等于一级不冗余）/P5（校验只认一级）
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 6.4_

- [x] 5. 前端明细表联动
- [x] 5.1 优先明细码匹配 + NULL 回退
  - `composables/useAdjustmentDetailPropagation.ts`：`AdjustmentLineMatch` 加 `detail_account_code?`；`load()` 从 `li.detail_account_code` 读；`matchByAccount` 用 `effectiveCode = detail_account_code || standard_account_code` 经 `accountMatches` 判定
  - vitest：P9（有明细码精确匹配不上卷到全部同级）/P10（NULL 回退等价现状）/空值安全
  - _Requirements: 5.1, 5.2, 5.3, 5.4_

- [x] 6. 说明与导出
- [x] 6.1 模板说明 + 手册对齐
  - `routers/adjustments.py::export_adjustment_template` 关注事项补明细码语义；`views/adjustments/handbooks/adjustments-module-handbook.md` 补说明
  - 不改模板列结构/导入解析
  - _Requirements: 8.1, 8.2_
- [x] 6.2 导出序列化 additive（listAdjustments line_items 经 model_dump 自动含 detail_account_code；导出汇总 Excel 列不新增以保导入兼容）
  - `routers/adjustments.py::_adj_to_dict` line 序列化补 `detail_account_code`（供前端），Excel 列顺序不变
  - _Requirements: 4.2, 4.3_

- [x] 7. 验证
- [x] 7.1 属性/单元测试汇总
  - 覆盖 P1-P8/P11/P12（后端）+ P9/P10（前端）
  - _Requirements: 9.1, 9.2_
- [x] 7.2 契约零影响门
  - 断言 recalc 聚合不引用 detail_account_code（P7）；report/审定带入按 standard 聚合结果不变（P12）
  - _Requirements: 6.1, 6.3_
- [x] 7.3 零回归门 + get_diagnostics（test_adjustments+test_adjustment_sync 41 + test_trial_balance 13 全绿；新测 14 + 前端 16 全绿；Vite 200；diagnostics 清）
  - 既有 `test_adjustments`/`test_adjustment_sync`/`test_trial_balance` 全绿；改动前端文件 Vite transform 200 + get_diagnostics 全清
  - _Requirements: 6.2, 7.1_
- [x] 7.4* 端到端 HTTP round-trip（替代 Playwright）
  - 已用鉴权 HTTP round-trip 实测（重药控股安徽 0ec33ac9/2025）：创建带 detail_account_code 分录 → GET line_items 明细码=100101 落库/序列化正确、另一行 NULL 回退 → DELETE 清理无污染。后端 --reload 已加载全链路
  - _Requirements: 5.2_

## Notes
- **零影响红线**：`standard_account_code` 一级码语义/约束/下游（校验/recalc/报表/审定带入）绝不变；`detail_account_code` 纯增量可空，仅提升推送精度。
- **零影响的架构保证**：recalc 从 `adjustments` 头表 `account_code`（一级）聚合，从不读 `adjustment_entries` 明细行 → 加列天然零影响（Property 6/7 锁定）。
- **历史零回归**：历史行 `detail_account_code=NULL`，前端匹配回退现有一级前缀上卷（Property 10）。
- **迁移取号**：执行 2.1 前以 migration_status/磁盘复核最高号（当前 V125=AdjustmentCollaboration），本 spec 用 V126；幂等 information_schema 守护。
- **各底稿 syncToCentral 带明细码**为可选增强（默认 NULL 回退零回归），本 spec 不强制改全部底稿，仅 E1 等已知带明细入口可试点。
```
