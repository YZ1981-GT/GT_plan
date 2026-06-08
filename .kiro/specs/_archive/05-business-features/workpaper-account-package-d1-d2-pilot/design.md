# 设计文档：D1/D2 科目工作包试点

## 概述

本 spec 将销售循环的 D1 应收票据和 D2 应收账款从“底稿文件/sheet 集合”升级为“科目工作包”。D1 用于验证语义契约和状态持久化的技术闭环；D2 用于验证多文件、多程序、多模块联动的业务闭环。

## 核心设计

### 0. 实证前提：D1/D2 schema 真源分层

本试点必须以 D1/D2 inventory 为输入。当前实证结论：

- `generated/D1.yaml` 包含 D1 完整 sheet 清单，但仍是自动生成草稿，字段名和 cross-ref 未人工审核。
- `generated/D2.yaml`、`generated/D2-1.yaml`、`generated/D2-5.yaml`、`generated/D2-6.yaml` 包含 D2 多文件 sheet 清单，但同样是自动生成草稿。
- 当前 `WpRenderSchemaService` 不加载 `generated/` 目录。
- `load_schema("D1")` 会命中 `C-D1-disclosure.yaml`。
- `load_schema("D2")` 会命中 `C-D2-disclosure.yaml`。
- `D2A.yaml`、`D-D2-8.yaml`、`D-D2-13.yaml` 是根目录下较高质量的人工/专项 schema，应优先作为 D2 工作包的生产 schema 输入。

因此，工作包注册表只从 generated schema 抽取 sheet inventory 和迁移建议，不直接引用 generated schema 作为生产渲染配置。

### 1. AccountPackageRegistry

新增配置文件：

- `backend/data/account_package_registry.json`
- 或按循环拆分：`backend/data/account_packages/D-sales.yaml`

示例：

```json
{
  "account_package_id": "D2_accounts_receivable",
  "cycle": "D",
  "account_code": "1122",
  "account_name": "应收账款",
  "report_row": null,
  "note_section": null,
  "mapping_status": "pending_inventory_reconciliation",
  "primary_wp_code": "D2",
  "control_panel_sheet": "D2A",
  "source_wp_codes": ["D0", "D2", "D2-5", "D2-6"],
  "schema_refs": ["D2A.yaml", "D-D2-8.yaml", "D-D2-13.yaml", "C-D2-disclosure.yaml"],
  "sheets": [
    { "sheet_name": "应收账款实质性程序表D2A", "sheet_type": "control_panel", "schema_ref": "D2A.yaml" },
    { "sheet_name": "审定表D2-1", "sheet_type": "audit_sheet", "source_wp_code": "D2" },
    { "sheet_name": "明细表D2-2", "sheet_type": "detail_table", "source_wp_code": "D2" },
    { "sheet_name": "坏账准备明细表D2-3", "sheet_type": "analysis", "source_wp_code": "D2" },
    { "sheet_name": "调整分录汇总表D2-4", "sheet_type": "adjustment", "source_wp_code": "D2" },
    { "sheet_name": "应收账款分析表D2-5", "sheet_type": "analysis", "source_wp_code": "D2-5" },
    { "sheet_name": "关联方及交易检查表D2-6", "sheet_type": "procedure", "source_wp_code": "D2-6" },
    { "sheet_name": "应收账款检查表D2-7", "sheet_type": "procedure", "source_wp_code": "D2-6" },
    { "sheet_name": "坏账准备计提会计政策检查D2-8", "sheet_type": "procedure", "schema_ref": "D-D2-8.yaml" },
    { "sheet_name": "应收坏账准备测算D2-9", "sheet_type": "analysis", "source_wp_code": "D2-6" },
    { "sheet_name": "预期信用损失的计量测试D2-10", "sheet_type": "analysis", "source_wp_code": "D2-6" },
    { "sheet_name": "应收账款业务模式分析D2-13", "sheet_type": "analysis", "schema_ref": "D-D2-13.yaml" },
    { "sheet_name": "应收账款附注披露信息", "sheet_type": "disclosure", "schema_ref": "C-D2-disclosure.yaml" },
    { "sheet_name": "D2-C 科目结论", "sheet_type": "conclusion" }
  ],
  "external_cards": ["confirmation_summary", "adjustment_impact", "note_disclosure"],
  "downstream": ["report", "disclosure_note", "sign_off"]
}
```

注册表只定义结构和默认关系；项目级完成状态由 `account_package_program_status` 保存。

### 2. AccountPackageSummaryService

新增后端服务：

- `backend/app/services/account_package_registry_service.py`
- `backend/app/services/account_package_summary_service.py`
- `backend/app/services/account_package_program_status_service.py`

职责：

- 读取注册表。
- 解析 `wp_code` 到项目内 `wp_id`。
- 聚合 sheet 列表、字段来源、程序状态、函证摘要、调整影响和 stale 状态。
- 输出工作包首页和控制台所需摘要。
- 对函证相关指标只聚合 `confirmation_service` 暴露的 summary/metrics，不作为函证事实真源，不在底稿侧重新维护函证明细状态。

### 3. API 草案

- `GET /api/projects/{project_id}/account-packages?cycle=D`
- `GET /api/projects/{project_id}/account-packages/{package_id}`
- `GET /api/projects/{project_id}/account-packages/{package_id}/summary`
- `PATCH /api/projects/{project_id}/account-packages/{package_id}/program-status/{program_code}`
- `GET /api/projects/{project_id}/account-packages/{package_id}/confirmation-summary`

### 4. 前端工作包入口

前端新增或扩展：

- `WorkpaperAuditNav.vue`：销售循环下展示 D1/D2 工作包入口。
- `AccountPackageView.vue`：工作包首页。
- `AccountPackageControlPanel.vue`：程序状态与数据状态。
- `AccountPackageEvidenceCard.vue`：函证、附件、调整、附注等摘要卡片。

初期可以复用现有 `WorkpaperEditor` 路由：工作包入口展示聚合页，点击具体 sheet 后进入现有底稿编辑器并定位 sheet。

### 5. D1 技术闭环设计

D1 包含：

- D1A 程序控制台。
- D1-1 审定表。
- D1-2 原值明细表（按类别）。
- D1-3 原值明细表（按客户）。
- D1-4 坏账准备明细表。
- D1-5 调整分录汇总表。
- D1-6 业务模式分析。
- D1-8 贴现、已背书未到期明细表。
- D1-12 质押检查表。
- 附注披露信息（上市公司 / 国企）。
- D1-C 结论与复核。

D1 验证：

- `sheet_type` 导航。
- 程序状态持久化。
- 字段来源面板。
- AI 结论草稿接入。
- sign_off gate 阻断。

D1 工作包的首要目标是“语义标注 + 附注来源 + 状态持久化”闭环，不在 P0 重做所有 D1 sheet 的 HTML 化。

### 6. D2 业务闭环设计

D2 包含：

- D2A 程序控制台。
- D2-1 审定表。
- D2-2 明细表。
- D2-3 坏账/ECL。
- D2-4 调整分录汇总。
- D2-5 分析程序。
- D2-6 关联方及交易检查。
- D2-7 应收账款检查。
- D2-8 坏账准备计提会计政策检查。
- D2-9 坏账准备测算。
- D2-10 预期信用损失计量测试。
- D2-11 坏账准备转回/核销检查。
- D2-12 质押出售情况检查。
- D2-13 业务模式分析。
- C-D2-disclosure 附注披露。
- 函证摘要卡片（外部卡片，来自 D0 / ConfirmationHub）。
- D2-C 科目结论。

D2 重点验证：

- 多 sheet / 多来源收敛为一个工作包。
- 函证模块摘要联动。
- 调整分录影响审定表、报表、附注 stale。
- 结论引用结构化来源。

D2 工作包的首要目标是“多文件工作包 + 函证 + 坏账/ECL + 附注/报表联动”闭环。D2 的坏账与 ECL 内容应按分组展示：

```text
坏账与 ECL
  - D2-3 坏账准备明细
  - D2-8 坏账政策检查
  - D2-9 坏账准备测算
  - D2-10 预期信用损失计量测试
  - C-D2-disclosure 坏账披露
```

### 7. 函证边界

事实真源：

```text
ConfirmationHub / confirmation_service
```

底稿侧定位：

```text
D0 = 销售循环函证底稿汇总视图
D1/D2 = 函证摘要卡片 + 程序结论，不维护函证明细
```

`confirmation:received` 等事件触发后：

1. 函证服务更新函证状态。
2. 函证服务或其 summary API 提供覆盖率、差异金额、未解决事项等指标。
3. D2 render-config / summary API 返回更新后的摘要。
4. 前端卡片刷新。

`account_package_summary_service` 的职责是把函证 summary 转成工作包卡片展示结构，并补充跳转、stale、程序状态等工作包上下文；它不得复制维护函证明细，也不得与函证模块形成第二套业务口径。

## 不在范围

- 不重写函证业务流。
- 不实现全部销售循环工作包。
- 不替代现有 `WorkpaperEditor`。
- 不把工作包状态放到前端本地存储。

## 现有代码锚点

### 后端

- `backend/app/services/wp_render_schema_service.py`
- `backend/app/services/deliverable_service.py`（仅参考聚合模式）
- `backend/app/routers/confirmations.py`
- `backend/app/services/confirmation_service.py`
- `backend/tests/test_d2_d0_confirmation_callback.py`

### 前端

- `audit-platform/frontend/src/components/workpaper/WorkpaperAuditNav.vue`
- `audit-platform/frontend/src/views/WorkpaperEditor.vue`
- `audit-platform/frontend/src/components/workpaper/GtWpRenderer.vue`
- `audit-platform/frontend/src/composables/useDSalesCycleSheetGroups.ts`
- `audit-platform/frontend/src/composables/useWorkpaperRefresh.ts`
- `audit-platform/frontend/src/views/ConfirmationHub.vue`

## 迁移策略

1. 先消费 `workpaper-content-semantic-contract` 输出的 D1/D2 inventory 与口径对账表。
2. D1 先接入注册表和状态服务，只做语义标注、附注来源和状态持久化闭环。
3. 修正前端静态 D1/D2 文案错配：D1=应收票据，D2=应收账款，D4=营业收入。
4. D1 验收通过后，D2 接入多 sheet 聚合。
5. D2 函证摘要先读现有 callback 和函证服务，不复制状态。
6. D2 调整/附注 stale 复用平台联动契约。
7. 总结注册表字段，推广到 D4/F/H。

## 风险与回滚

- 风险：工作包入口与现有底稿列表冲突。  
  回滚：工作包入口作为销售循环增强导航，不替换原底稿列表。
- 风险：D2 多来源聚合复杂度过高。  
  回滚：先只展示 D2 审定表、明细和函证摘要三类卡片。
- 风险：函证摘要计算与函证模块口径不一致。  
  回滚：摘要只展示函证模块返回值，不做底稿侧二次计算。
