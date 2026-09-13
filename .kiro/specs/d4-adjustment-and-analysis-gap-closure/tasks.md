# Implementation Plan

## Overview
本 spec 承接总纲矩阵明确 owner 为本 spec 的 D4-4、D4-8、D4-12。三者已有结构化能力不重做；
本 spec 补双向 identity、公式/DAG、冲突和逐表验收。

本轮已交付「公式管理打通上下游」的后端 backbone（能力快照端点 + 有效公式单一真源治理），
双向回写在入口级已具备（`useD4EntryDualMode` 覆盖 D4-4/8/12），导入导出 D4-4/8/12 已支持。

## Tasks

- [x] 1. C0模板/identity：只读核定 D4-4/8/12 真实 sheet、区域、wp_id 稳定身份并反向去重 owner；记录已有能力，不重做。
  - **identity 核定**（只读实证，render 策略 `_d4_operating_revenue.py` + 前端 `GtD4OperatingRevenue.vue` dispatch）：
    wp_code base=`D4`（`working_paper` 无 wp_code，在 `wp_index`）；sheet=`D4-{code}`；持久化 `checklist_responses`，item_id 前缀 `D4-{sheetCode}-{field}`。
    - D4-4 调整分录汇总（10 列动态行）→ `<D4TabAdjustment>`，store `D4-4-rows`。
    - D4-8 重要产品毛利分析（产品×月）→ `<D4TabProductMargin>`，`sub_table_data` 规范 `{key:list[dict]}`。
    - D4-12 合同检查表（20 字段×10 合同矩阵）→ `<D4TabContract>`，store `D4-12-contracts-v2`。
  - **owner 去重**（Req 1.2）：三表结构能力均已由**归档 spec** 交付（全 `[x]`）——
    D4-4/D4-8=`_archive/05-business-features/d4-operating-revenue`；D4-4 集中登记=`workpaper-adjustment-centralization`；
    D4-12=`_archive/05-business-features/d4-12-contract-inspection`。本 spec **不重做结构**，仅 own identity/formula/sync/DAG backbone 层（与 Introduction 一致）。
  - _Requirements: 1.1, 1.2_
- [-] 2. C1sync：为确认纳管表接入共享服务、字段合并、同字段冲突和 applied 确认。
  - 入口级 HTML↔OnlyOffice 双模式已由 `useD4EntryDualMode`（wrap `useWorkpaperEntryDualMode`）覆盖 D4-4/8/12；
    深度 unified-path materialize 由 `workpaper-html-onlyoffice-bidirectional-writeback-closure` owner，非本 spec。
  - _Requirements: 2.1, 2.2_
- [x] 3. C2formula：冻结 wp_id 公式 key、preset/custom、F-SHELL、真实 DAG 及缺失/损坏/stale/blocked。
  - 补 `GET /api/workpapers/{wp_id}/capability-snapshot`（backend backbone，前端 formula shell 挂载依赖）：
    `app/services/workpaper_capability_matrix.py`（9 键 role→capability 真源，fail-closed，owner-epoch 竞态门）
    + `app/routers/wp_capability_snapshot.py`（已注册「数据」组）。
  - 有效公式单一真源治理：`app/services/formula_management/effective_formula.py`
    （key = `wp_id∷stable_sheet_key∷row_key∷field_key∷custom`；6 态；custom 优先/删 custom 回落 preset/
    预设升级不覆盖 custom；schema 白名单禁 eval/外链）。
  - 守卫：`backend/tests/test_workpaper_capability_matrix.py`（13）+ `backend/tests/formula_management/test_effective_formula.py`（22），全绿。
  - _Requirements: 2.3_
- [x] 4. C3linkage：保留已有 A13/调整、产品计算、合同 OCR/AI，只补真实联动接收端；公式同步不发布 TB/A13。
  - 既有联动链保留不动：`substantive:adjudicated`（TB 回写，显式审定触发）/ `adjustment:created`（A13）/ `analytical:significant-change`（A1-13），接收端在披露/A13 侧已订阅。
  - 公式路径**不发布 TB/A13**（Req 2.4/3.2）以否定式承诺守卫：`backend/tests/test_d4_gap_formula_no_tb_a13_publish.py`
    双判据（源码禁词 + 行为 audit kind）+ **变异实证 RED**（注入 `substantive:adjudicated` 到 effective_formula 源码 → 守卫打红，已回退）。
  - _Requirements: 2.4, 3.2_
- [-] 5. C4逐表验收与变异：roundtrip、权限、Playwright、owner 去重、公式/冲突和发布确认；只门控本 spec 相关产物。
  - 导入导出：D4-4/8/12 已在 `_d4_import_export.py::_SUPPORTED_SHEETS` 且有专属列头/导出映射，功能可用（既有 `test_d4_import_export_pbt.py` 覆盖）。
  - 已完成：owner 去重（Task 1）、公式单一真源守卫（Task 3，13+22 例）、公式不发布 TB/A13（Task 4，4 例 + 变异 RED）、
    **端点集成守卫**（`test_wp_capability_snapshot_endpoint.py` 3 例，ASGITransport 打真实注册路由，验 200 + 9 键 wire 形状 + 角色分权，代替浏览器实测后端半）。
  - ✅ **Playwright 实测通过**（2026-09-13，后端 9980 + 前端 3030 起）：打开 D4 底稿（wp `c581bffb…`/proj `5e193c68…`）→
    `GET /api/workpapers/{wpId}/capability-snapshot?...&ownerEpoch=1` **200 OK ×2**；响应体经 ResponseWrapper 为
    `{code,message,data}`，data 含 `snapshotVersion:1.0`/64 位 subjectDigest/ownerEpoch/issuedAt/expiresAt(30min)/role:admin + 9 键 decision 全 allowed；
    公式壳层「公式管理/批量AI复核」按钮渲染启用（未 fail-closed）。4 个控制台报错均为无关 `guidance` 端点 422/503。
  - **待做**：① CI job 挂载本 spec 产物；② 产物 `git add` 入库（当前 6 个 `??`：3 后端 + 3 测试）。
  - _Requirements: 3.1, 3.2_

## Task Dependency Graph
```json
{"waves":[{"wave":1,"tasks":["1"],"rationale":"C0先核定模板与owner"},{"wave":2,"tasks":["2","3"],"rationale":"sync与formula并行"},{"wave":3,"tasks":["4"],"rationale":"linkage依赖前序契约"},{"wave":4,"tasks":["5"],"rationale":"C4最后"}],"blocking":{"1":"未核定不得新增owner","2":"sync未冻结不得roundtrip","3":"formula未冻结不得接入公式"}}
```

## Notes
- 后端已通过 `python -c "import app.main"` 冒烟；`workpaper_capability.py`（并发会话新建，`??` 未跟踪）为 backbone 依赖。
- 本 spec 新增 3 个后端产物 + 2 个测试文件均为 `??` 未跟踪，收口须 `git add`。
- formula_management 既有套件 21 例失败为**既有环境失败**（`no such table: working_paper` DB fixture + inventory 漂移），与本轮改动无关。
