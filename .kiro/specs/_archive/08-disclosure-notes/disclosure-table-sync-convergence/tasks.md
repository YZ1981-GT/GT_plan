# Implementation Plan

## Task Dependency Graph

```json
{
  "waves": [
    { "wave": 0, "name": "基础设施", "dependsOn": [], "tasks": ["1.1", "1.2", "2.1", "2.2"] },
    { "wave": 1, "name": "存储与读取投影", "dependsOn": [0], "tasks": ["3.1", "3.2", "3.3", "4.1", "4.2", "5.1", "5.2"] },
    { "wave": 2, "name": "前端渲染消费", "dependsOn": [0, 1], "tasks": ["6.1", "6.2"] },
    { "wave": 3, "name": "试点覆盖", "dependsOn": [0, 1], "tasks": ["7.1", "7.2", "8.1", "8.2"] },
    { "wave": 4, "name": "铺开 G/H", "dependsOn": [3], "tasks": ["9.1", "10.1"] },
    { "wave": 5, "name": "铺开 I/K + 守卫", "dependsOn": [3], "tasks": ["11.1", "12.1", "13.1", "13.2"] },
    { "wave": 6, "name": "端到端验证与收尾", "dependsOn": [1, 2, 3, 4, 5], "tasks": ["14.1", "14.2", "14.3", "15.1", "15.2"] }
  ]
}
```

## Overview

目标：让披露表推送的 `sub_table_data` 在附注模块可见、Word 可导出，列头源自组件既有源对齐定义（零自造），零回归既有路径。前序数据销毁修复（空载荷 no-op / sync-html 路由）已完成，仅在 Wave1 补回归测试锁定。铁律：每波完成后跑 get_diagnostics + 相关 Vite transform + 针对性测试；禁止假绿；列头 label 必须取自组件既有 `<el-table-column label>` / schema `columns[].label`，无源对齐来源则该列不接入（宁缺毋滥）。

## Tasks

### Wave 0 — 基础设施

- [x] 1. 后端投影器 `note_sub_table_projector.py` + 纯函数 PBT
  - [x] 1.1 新建 `backend/app/services/note_sub_table_projector.py`，实现 `project_sub_tables(table_data: dict) -> list[dict] | None`（design §Projector 逻辑）：`_source` 非 workpaper → None；sub 空 → []；按子表键序投影；label 列置首；缺字段空单元；额外字段忽略；`is_total` 透传；缺 `_columns` 降级不用英文键当 header。
  - [x] 1.2 `backend/tests/services/test_note_sub_table_projector.py`：PBT 覆盖 P1(纯函数)/P2(列序)/P3(缺字段空单元)/P4(额外字段忽略)/P5(合计行)/P6(多表键序)/P7(来源优先级)/P8(降级不杜撰)，14 passed。
  - _Requirements: 1.1, 1.3, 1.4, 2.2, 2.3, 2.4, 3.3, 6.1, 6.2, 6.4, 7.2_

- [x] 2. 前端 `ColumnDef` 类型 + `defineColumns` 助手 + 客户端兜底投影
  - [x] 2.1 新建 `audit-platform/frontend/src/components/workpaper/composables/disclosureColumnDefs.ts`：导出 `ColumnDef` 类型 + `defineColumns(defs)` 助手 + `projectSubTablesClient(tableData)`（与后端 §Projector 规则一致的客户端兜底投影，供过渡期后端未注入时使用）。
  - [x] 2.2 `disclosureColumnDefs.spec.ts`：断言客户端兜底投影与后端规则一致（12 passed，P2~P8 关键用例）。
  - _Requirements: 2.1, 2.2, 3.1, 3.2, 7.2_

### Wave 1 — 存储与读取投影

- [x] 3. sync 存储 `_sub_table_columns`（浅合并 + 空 no-op）+ 请求体扩展 + 回归锁定
  - [x] 3.1 `wp_disclosure_sync_service.sync_from_workpaper`：接收可选 `sub_table_columns`，按子表 key 浅合并进 `table_data._sub_table_columns`（空 no-op、同 sub_table_data 语义，D3）；`sync_from_html` + batch 同款。
  - [x] 3.2 `wp_disclosure_sync.py`：`SyncFromWorkpaperRequest` / `SyncBatchItem` / `SyncFromHtmlRequest` 加可选 `columns`，透传服务。
  - [x] 3.3 扩 `test_disclosure_sync.py`：P9/P10/P13（14 passed）。
  - _Requirements: 2.1, 2.5, 7.5, 8.1, 8.2, 8.3_

- [x] 4. `get_note_detail` 读时注入投影 `_tables`（D5 优先级，不写库）
  - [x] 4.1 `disclosure_notes.py::get_note_detail`：`projected = project_sub_tables(detail.table_data)`；非空时对返回 `table_data` 副本注入 `_tables`（workpaper 来源权威；非 workpaper 不投影）。只读、不 flush/commit。
  - [x] 4.2 单测：注入语义（workpaper 注入 / engine 不改 / 空 sub 不遮蔽），17 passed。
  - _Requirements: 1.1, 6.1, 6.2, 6.3, 7.1_

- [x] 5. `note_word_exporter` 复用投影器（P12）
  - [x] 5.1 `note_word_exporter.py`：新增 `_effective_table_data`（workpaper 来源投影），`_note_tables` / HTML 预览 / `_has_content` / 主渲染 4 处统一走投影；投影 None/失败回退既有 `_tables`/`rows`。
  - [x] 5.2 `test_note_word_export_sub_table.py`：导出表结构与投影一致（P12），21 passed（含 projector）。
  - _Requirements: 1.2, 6.4, 7.1_

### Wave 2 — 前端渲染消费

- [x] 6. `DisclosureEditor.currentNoteTables` 消费投影 + 客户端兜底
  - [x] 6.1 `currentNoteTables` 消费后端注入 `_tables`；无 `_tables` 但有 workpaper `sub_table_data`+`_sub_table_columns` 时调 `projectSubTablesClient` 兜底。Vite transform 200。
  - [x] 6.2 刷新走 `fetchDetailFresh`（已确认，`fetchDetail: fetchDetailFresh` 传入 useNoteRefresh）。
  - _Requirements: 1.1, 1.3, 1.4, 7.2_

### Wave 3 — `_columns` 覆盖（试点）

- [x] 7. F2 存货披露 listed + soe 接入 `_columns`
  - [x] 7.1 `f2DisclosureSyncPayload.ts`：新增 `buildF2ListedColumns`/`buildF2SoeColumns`（label 逐字取自 F2TabDisclosureListed/Soe el-table-column，两级表头扁平合并保留源语义）；`buildF2SyncPayload` 按 variant 附 `columns`。F2 组件直接 POST 该 payload，columns 自动流转。
  - [x] 7.2 `f2NoteSectionMap.spec.ts`：断言 payload 含 `columns` + 源对齐中文 label（含国企转销列），24 passed。Vite transform 200。
  - _Requirements: 2.1, 2.2, 3.1, 3.4, 4.1_

- [x] 8. `GtCNoteTable` 接入 `_columns`（从 schema 派生）
  - [x] 8.1 `GtCNoteTable.vue::buildSyncColumns`：从 `allSubTables` + `visibleColumns` + `labelColumnField` 派生 `columns`（key=field/label=schema label/is_label 判定/format 由 render 映射），一举覆盖所有 c-note-table 附注表零复制。
  - [x] 8.2 `GtCNoteTable.spec.ts`：断言同步 payload 含 `columns`（来自 schema），16 passed。Vite transform 200。
  - _Requirements: 2.1, 2.2, 3.1_

### Wave 4 — 铺开 G / H

- [x] 9. G 循环全部 `*TabDisclosureListed/SOE` 接入 `_columns`
  - [x] 9.1 G14 信用减值损失/G13 公允价值变动收益/G2 应收利息（3 子表）/G3 应收股利 加 `columns`（含投影器 label 兜底：labelKey 值缺失且≠label 时回退 label，G2 重要逾期利息触发；前后端同步）。g14(9)/g13(7)/g2g3(4) 测试绿。
  - [x] 9.2 G10/G11（先期完成）+ G1（交易性金融资产 listed 中文键+soe 英文键映射）/G6（其他债权投资 soe 内联 columns）/G7（长期股权投资 listed+soe，`buildG7ListedColumns`/`buildG7SoeColumns` 从 section 配置派生）全部完成，`hgDisclosureColumns.spec.ts` 锁定。
  - _Requirements: 2.1, 3.1, 3.4, 4.1, 5.1_

- [x] 10. H 循环全部 `*TabDisclosure*` 接入 `_columns`
  - [x] 10.1 H9 租赁负债（五、47/八、52，live-affected 2aa00f57）+ H10 资产处置收益（三、资产处置收益，live-affected 2aa00f57，含试运行明细）+ F3 应付票据（五、36/八、36，live-affected 0ec33ac9）先期完成，列头逐字取自各组件 el-table-column。
  - [x] 10.2 H1 固定资产（listed 变动表随类别动态 `buildH1ListedColumns`+英文键子表映射/soe `H1_SOE_COLUMNS`）/H2 在建工程（两级表头扁平合并）/H6 固定资产清理（listed/soe 清理表按 variant）/H8 使用权资产（listed 动态 `buildH8ListedColumns`/soe 静态）全部完成。
  - _Requirements: 2.1, 3.1, 3.4, 4.1, 5.1_

### Wave 5 — 铺开 I / K + 守卫

- [x] 11. I 循环全部 `*TabDisclosure*` 接入 `_columns`
  - [x] 11.1 I1/I2/I3 + I4/I5/I6 披露组件补 `_columns`。
    - I4 长期待摊/I5 其他非流动资产/I6 研发费用（简单变动/余额表）；I1 无形资产（listed 动态类别 `buildI1ListedColumns`+数据资源/摊销归属子表/soe 英文键）、I2 开发支出（两级表头扁平合并，源取自 I2TabDisclosure）、I3 商誉（被投资单位/资产组假设/业绩承诺）全部完成，`iDisclosureColumns.spec.ts` 锁定。
  - _Requirements: 2.1, 3.1, 3.4, 4.1, 5.1_

- [x] 12. K 循环披露组件接入 `_columns`
  - [x] 12.1 K1 经 sync-from-workpaper 的披露组件补 `_columns`。
    - K1 其他应收款 listed（9 子表）+soe（12 子表）中文键行→columns 键=中文键、标签列头账龄/款项性质/单位名称等源对齐，`k1DisclosureListed/Soe.spec.ts` 锁定。K11/K13 无 sync-from-workpaper 调用点（不适用，非本 spec 渲染路径）。
  - _Requirements: 2.1, 3.1, 3.4, 4.1, 5.1_

- [x] 13. CI 覆盖守卫
  - [x] 13.1 新建 `check_disclosure_columns_coverage.py`：扫描全部 `sync-from-workpaper` 调用点核对 `columns` 覆盖（识别 `columns:` 字段邻近 sub_table_data / build*Columns / 已登记构造器）；精确列出 backlog；`--strict` 未覆盖非 0。
  - [x] 13.2 挂 `governance-checks.yml` job `disclosure-columns-coverage`；全部 43 调用点迁移完成后已切 **--strict**（阻断新增未覆盖同步调用点）。
  - _Requirements: 5.1, 5.2, 5.3_

### Wave 6 — 端到端验证与收尾

- [x] 14. Playwright 端到端实测
  - [x] 14.1 上市版披露表录入 → 推送 → 附注模块可见完整表格（中文列头 + 合计行）→ Word 导出含表；国企版同验（不同 note_section 各自正确）。
  - [x] 14.2 二次空载荷同步 → 附注表格不丢失；`fetchDetailFresh` 后不命中旧缓存。
  - [x] 14.3 未接入 `_columns` 的历史记录 → 降级呈现不 crash、不清空（Req7.2）。
  - _Requirements: 1.1, 1.2, 4.1, 4.4, 7.2, 8.1_

- [x] 15. Coverage_Ledger 全绿 + 文档
  - [x] 15.1 `check_disclosure_columns_coverage.py --strict` 全绿（43/43 覆盖，0 allowlist 豁免）。
  - [x] 15.2 更新 `.kiro/specs/INDEX.md`；开发指南记录"披露表列头随 `_columns` 携带 + 后端单点投影"范式（可选收尾）。
  - _Requirements: 5.1, 5.2_

## Notes

- 本规格聚焦**渲染断裂**（`sub_table_data` 对附注模块/Word 导出不可见），不重写既有 DisclosureEngine 模板填充路径。
- 前序已完成并纳入回归锁定：`sync_from_workpaper`/`sync_from_html` 空载荷 no-op、`sync-html` 路由死链修复。
- **范围外**：底稿侧 `GtCNoteTable` 自身渲染（不受影响）；改版底稿 workpaper 侧 item_id 迁移（另属独立问题）；A9-1/A9-2 缺陷函数据源（不受影响）。
- **铁律**：列头 label 必须取自组件既有源对齐定义，禁止英文字段键当列头或凭常识杜撰；无来源则该列不接入。
- 分波推进 `_columns` 覆盖，每波不破坏未接入组件（降级不 crash、不清空）。
- 完成判定：Coverage_Ledger CI 全绿 + Playwright 上市/国企端到端可见并可导出 + 全部针对性测试通过（禁止假绿）。
- **🔴 数据驱动优先级（PostgreSQL 只读实证 2026-07-24）**：全库 398 附注仅 **4 条**有非空 `sub_table_data`（F3 五、36/八、36、H9 五、47、H10 三、资产处置收益），其余 46 组件在真实项目中从未同步过 sub_table_data（表格主要来自 Engine_Fill_Path 的 `_tables`/`rows`，167+284 条）。故 Wave4/5 **按 live-affected 优先**：F3+H9+H10 已完成（覆盖全部 4 条实际受影响记录），其余 G/H1/H2/H6/H8/I/K 为 speculative-future（无 live 数据，用户点同步时才产生）。**守卫覆盖 8/52**。
- **🔴 存量数据说明**：现有 4 条受影响 note 存的是"无 `_sub_table_columns`"的旧数据，代码修复后需**重新点「同步到附注」**才会带上 columns 完整渲染；在此之前经降级路径只显示标签列（`_needs_columns`），不空白不报错。
- **🔴 复盘再定位**：用户报"很多附注表格丢失"若指 Engine_Fill_Path（`_tables`/`rows`，占绝大多数）的表在改版后变空/错，则属 DisclosureEngine 模板绑定/refill 问题，**不在本 spec 范围**，需另立排查（本 spec 只解 sub_table_data 渲染断裂）。
