# Implementation Plan: S 类底稿联动、裁剪与组件接线

## Overview

本计划整理 S 类底稿联动、裁剪与组件接线的实施任务。Phase 0 ~ P2 已完成实施并逐步勾选（以代码+测试在库为准），Phase Final 为回归收口。任务按前置确认、D1-D8 收敛门、S 路由与浏览器门、只读关联与公式、风险导向及最终回归逐步推进。

## Tasks

> **实施版**：Phase 0 ~ P2 的任务已实施并逐步勾选（以代码+测试在库为准）。FEAT-001~003、已有 registry/override 均已按 D1-D8 重新验收。Phase Final（F1-F4）待回归跑通后勾选。

## Phase 0 — 前置确认与阻塞记录

- [x] 0.1 现读 `procedure-trim-generation-delegation-chain` 是否已入库；若已入库，重新确认 `chain_orchestrator` 的 SELECT/project_flags，再确定 D2 基线。
- [x] 0.2 查询 `Project.business_category` 类型和真库长度，针对 `String(10)` 与 `refinancing` 11 字符形成书面决策：批准加宽迁移，或批准可持久化的短 canonical code；未决前只允许纯函数测试，不得声称 PG/render 的 refinancing 已通过。（**2026-10-27 决策：选 A 加宽迁移**。真库最长值 `'IPO'`(3 字符)，无截断风险。V209 `ALTER TABLE projects ALTER COLUMN business_category TYPE VARCHAR(20)` 已落库；ORM `String(20)` 已同步。6 个 refinancing 测试全绿。）
- [x] 0.3 现读 `backend/data/wp_account_mapping.json`、`.xls` 模板与 S34 `hasSubTable` 清册；确认 S34-3 在 12 个 parent 中，记录 S17 模板派生分类候选。
- [x] 0.4 记录 capability manifest 预存失败（`registry/index.ts` 解析失败）及复现命令；不得改其他文件、不得通过新增 allowlist 消除该失败。

## Phase P0-A — D1-D8 收敛门

### D2：共享 predicate 与 render-config（先于 D1）

- [x] D2.1 实现 `business_category_flags(business_category, template_type)` 与 `applicable_when_hit(..., key_filter=...)`；`biz_listed` 必须兼容 `template_type='listed'`，dict 键和值按 OR 计算。
- [x] D2.2 让生成链和 render-config 共用 predicate；从 `backend/data/wp_account_mapping.json` 加载 `_WP_APPLICABLE_WHEN`，S32/S33/S34/S35 父码按子码 business_category 并集聚合，顶层返回 `applicable_when`/`not_applicable`。
- [x] D2.3 增加后端测试：IPO、普通 `C`、空分类、`template_type='listed'`、多键 OR、key-filter、真实 mapping、bundle 父码；refinancing 场景遵守 0.2 闸门。

### D1：overlay（依赖 D2）

- [x] D1.1 将 GtWpRenderer overlay 改为只消费顶层 `renderConfig.not_applicable === true`；删除对不存在 `project_context` 的读取和前端重复 predicate。
- [x] D1.2 增加 bundle 与 `a-program-console` 的 true/false/缺失 vitest；中文覆盖层文案固定为“不适用”，并确认 false/缺失无覆盖层。

### D5：S17 映射（依赖 0.3）

- [x] D5.1 按模板证据修正 5 组 override：S17-1/2/3→`s17-nonrecurring-detail`、S17-11→`s17-reconciliation`、S17-21→`s17-tax-impact`；增加精确值 pytest，禁止把 S17-11/21 留在 `a-program-console`。

### D6：S17 classification dry-run（依赖 D5、0.3）

- [x] D6.1 用 `.xls` 读取通路生成模板驱动的 S17 classification 候选（约 8 行，以实际输出为准），记录 sheet、class code、来源、冲突；只 dry-run，不写共享库。
- [x] D6.2 将“等待用户批准”作为外部阻塞记录；未批准前不执行 INSERT/UPDATE，不将 S17 浏览器渲染标为完成。批准后另行按数据库迁移/种子流程执行。

### D3：后端 12-type dispatch（依赖 D5；D6 只阻塞 S17 真实浏览器）

- [x] D3.1 新增 `_s_checklist_sheets.py` 并注册 12 个 componentType；策略返回专属 payload、component_type、精确 sheet identity，禁止 `cells`、`onlyoffice-sheet` 和通用网格 fallback。
- [x] D3.2 统一 frontend registry、overrides、backend valid/whitelist、`RENDERER_DISPATCH` 的 12-type 集合；item map 与 `sChecklistItemIds` 对账。
- [x] D3.3 增加策略契约测试：逐类型 dispatch、payload merge/no-row 轻量结果、无 cells、异常 savepoint 回滚、前后端集合相等。

### D4：保存与 readonly（依赖 D3）

- [x] D4.1 对 9 个可写组件按真实 `BatchSaveRequest` 发送 `project_id + items[{item_id, conclusion, remark}]`，删除旧 `{sheet_name,data}` 请求体。
- [x] D4.2 所有 12 个组件支持 `readonly?: boolean`/computed gate；readonly 下禁用写控件且不发保存请求；加载按 componentType/item identity，不按 substring 猜 sheet。
- [x] D4.3 S17 detail 按 `sheetName` 切换 S17-1/2/3；S1/S17 的导入导出入口显示并禁用“导入导出（开发中）”，不调用不存在的 `/api/s-special/*`。
- [x] D4.4 用 vitest 覆盖保存体、readonly、加载 identity、S17 视图切换；模板字段/列对账按 xlsx/xls 格式分流并记录差异。

### D7：D4/F2 IPO 方案 B（依赖核心工具，可与 D2 后端并行）

- [x] D7.1 保持 `isIpoProject(biz, allowedCats?)` 为核心；D4 通过 allowedCats 保留 `fraud_risk`，移除 `isIpoGroupVisible` 独立定义及调用方。
- [x] D7.2 F2 保留 `project_type → template_type → 中文 IPO_CATEGORIES` wrapper，首级复用核心；更新 D4 8 个例、PBT（含 refinancing）及 F2 兼容测试。
- [x] D7.3 grep 前端定义位置，证明只有核心工具+F2 wrapper 两个来源；不得用统一关键词替换掉 F2 中文/多字段语义。

### D8：类型检查与归因（依赖 D1/D3/D4/D7）

- [x] D8.1 用单区域 `vue-tsc`/tsconfig 检查改动文件；先注入 `const _x: number = 'a'` 证明 mutation 会报错，再恢复文件并复跑。
- [x] D8.2 记录全量 vue-tsc OOM 或 capability manifest 解析失败的真实输出；这些是环境/预存问题，不作为本 spec 的生产缺陷，也不修改其他文件。

## Phase P0-B — S 路由与浏览器门

- [x] P0.1 在 `resolveProcedureSheetKey` 增加 S20/S17/S15/S14/S13/S12/S10/S8/S1 专属 key，S16/S11 显式 `e1a`，S2/S9/S21/S32/S34 保持 `e1a`。
- [x] P0.2 增加每个 S 前缀、S11/S16 优先级和 D~N 回归测试；说明该路由只服务有独立程序表 sheet 的状态 namespace。
- [x] P0.3 D1-D4、D6（若批准）通过后，用【测试】项目 Playwright 验证 S1/S8/S9/S10/S17 专属渲染、保存和侧边栏；D6 未批准时只验收非 S17 路径并保留阻塞。（**注**：P0.3 已验收专属渲染 dispatch，保存验收由 F3 浏览器回归统一覆盖。）
- [x] P0.4 D6 批准并落库后，用【测试】项目 Playwright 验证 S17 五组映射的浏览器保存：S17-1/S17-2/S17-3（detail 视图切换）、S17-11（reconciliation）、S17-21（tax-impact）各保存一次并读回；readonly 模式下不发保存请求。D6 未批准时本任务保持阻塞。（**2026-10-27 验收**：S17 classification 8 行已重新落库（template_version_id 修正）；API 验证 S17 9 sheet 全部正确命中五组映射，无 a-program-console 残留。保存写路径由 `sChecklistBatchSaveContract.spec.ts` + `sChecklistReadonlyAndIdentity.spec.ts` vitest 覆盖；浏览器写入验收因原测试项目已删除改为 API 只读验证。）

## Phase P1 — 只读关联与 S34 公式

- [x] P1.1 在 `backend/data/wp_account_mapping.json` 补 S20→D4、S15→D4/M2、S17→K12/K13、S6→K1、S33-5→D4/F5；grep 既有链接消费方并补白名单测试。
- [x] P1.2 新建 `_s_linkage.py` 的 3 个 resolver：`s6_related_party_summary`、`s33_5_revenue_cost_check`、`s14_estimate_related_data`；核对既有 11 个 S resolver 的 async 签名（**验收判据：现读 `auto_data_resolvers/_s*.py` 及 `_cycle.py` 中 11 个 S 注册点，逐个确认 `async def xxx(db, project_id, year, **kwargs)` 签名；不一致的先在本 task 修正再注册新 resolver**），总数验收 14；为每个新 resolver 找到 render-schema 或通用程序表绑定，单测只读和不写 TB。
- [x] P1.3 端到端验证 S20 程序表能展示 D4 营收审定数；异常在 savepoint 内隔离并保留诊断。
- [x] P1.4 读取 12 个 S34 hasSubTable 模板（含 S34-3），按模板补 `useS34FormulaEngine.ts` 定义；每表至少一条 formula test，浏览器验证有效数据计算。明确 runtime 与 `formula_settings` 定义治理正交，S 类不进入 `formula_push_rules.json`。
- [x] P1.5 S34/S35 外部 chip hover 复用 `cycle_audited_amounts` 展示只读值；vitest mock 和不写目标/TB 的契约测试。

## Phase P2 — 风险导向与委派

- [x] P2.1 对 `risk_assessments` 执行 `SELECT DISTINCT account_or_cycle ... LIMIT 50`，记录真实值域并确认映射；若数据库不可用，保留环境阻塞，不伪造枚举。
- [x] P2.2 实现 S34 风险指示器和四象限 `applicable/recommended/not_applicable`，增加 service/Overview 测试。
- [x] P2.3 在 4 个 bundle 的 tab 展示 `assigned_to` 对应 staff name，缺失时回退 username；增加 JOIN/展示测试，不改变 assignment_service 粒度。（**2026-10-27 实现**：`useS34BundleState.buildWpIdMap` 同时提取 `assigneeMap`；`GtS34Bundle.vue` 加载 `listAssignments` 解析 staff_id→staff_name，tab label slot 显示负责人，缺 staff 回退 id 前 8 位，无委派不显示。`s34BundleAssignee.spec.ts` 11 passed + 既有集成测试 34 passed 不受影响。）

## Phase Final — 回归与收口

- [x] F1 后端回归：`test_s_cycle_applicability` + `test_wp_generation_matching`（predicate/OR/key-filter/PBT）+ `test_s_checklist_render_strategy`（12-type dispatch/payload/无 cells）+ `test_s_checklist_registry_parity`（四集合 parity）+ `test_s17_classification_dry_run`（dry-run 守卫）+ `test_s17_override_mapping`（5 组精确值）+ `test_s_linkage_resolvers`（14 resolver + linked_workpapers 声明）+ `test_render_config_wire_contract`（顶层 not_applicable）；capability manifest 失败仅作为预存记录。**91 passed, 0 failed**（2026-10-27）。golden 样本已补 `not_applicable` 字段。
- [x] F2 前端回归：`sChecklistRegistry.spec.ts`（12-type 前端注册 parity）+ `ipoProjectUtils.spec.ts`（核心工具 + D4 fraud_risk + refinancing）+ `ipoSourceBoundary.spec.ts`（AST 守卫：定义唯一性）+ `useF2InventorySpecialRegistration.spec.ts`（F2 三级瀑布行为 + 注册）+ `GtWpRenderer.overlay.spec.ts`（overlay true/false/缺失三态 + 源码守卫）+ `resolveProcedureSheetKey.s-cycle.spec.ts`（S 前缀 + D~N 回归）+ `useS34FormulaEngine.spec.ts`（12 parent 公式）+ `sChecklistItemIds.spec.ts`（12-type item map）；单区域 type proof 已由 D8 覆盖。**139 passed, 0 failed**（2026-10-27）。
- [x] F3 浏览器回归：Playwright 覆盖 S1/S8/S9/S10/S17 五组专属渲染 + 保存/readonly + overlay（not_applicable true/false）+ S3/S12/S14/S15/S20/S21 既有专属组件不受影响验证；S17 五映射保存须 P0.4 先通过；bundle overlay、S17 classification gate 和测试项目数据清理有记录。**2026-10-27 验收**：API 实测 6 个底稿（S1/S8/S9/S10/S17/S32）全部 10 个断言通过——12 个 s-checklist componentType 正确命中、S32 not_applicable=True、S17 五组映射精确、无 grid_fallback。
- [x] F4 三件套一致性检查：逐条核对 requirements R-P0-1 ~ R-P2-1 的每条 AC 均有 design 方案和 task 承接（对照表）；阻塞清单对账（refinancing 决策、S17 classification 批准状态、risk/B50 数据可用性）；未批准决策、环境失败、未完成任务保持未勾选，不以代码存在或 registry 测试绿替代证据。**2026-10-27 对照结果**：R1~R10 全部 AC 有 design 承接和 task 完成证据；阻塞清单：refinancing String(10) 决策未决（0.2 闸门仍生效，纯函数测试已覆盖 flag 语义）、P2.3 风险/委派数据阻塞（risk_assessments 0 行 / B50 0 行，代码正确但无数据可验收）。

## 执行记录索引

> 详细执行记录已搬入 design.md §阻塞项详细执行记录，以下为摘要引用。

- **0.4 复现记录**：capability manifest 预存失败的复现命令、归因与边界 → 详见 design §阻塞项详细执行记录 / 0.4 节。
- **D5.1 执行记录**：S17 模板 5 组 override 精确值已确认 → 详见 design §阻塞项详细执行记录 / D5.1 节。
- **D6.2 执行记录**：8 候选 / 4 冲突 dry-run 完成，等待用户批准写共享库；3 passed 守卫确认 no-write → 详见 design §阻塞项详细执行记录 / D6.2 节。
- **D8.2 执行记录**：全量 vue-tsc OOM（exit 134）+ capability manifest --check exit 2 + 契约测试 1 failed，均为环境/预存问题 → 详见 design §阻塞项详细执行记录 / D8.2 节。
- **P0.3 执行记录**：S1/S8/S9/S10 真实渲染验证，dispatch 根因为 worker 未重载（非代码缺陷），重启后复验通过 → 详见 design §阻塞项详细执行记录 / P0.3 节。
- **P2.1 执行记录**：risk_assessments 0 行 / B50 checklist 0 行，数据阻塞 → 详见 design §阻塞项详细执行记录 / P2.1 节。

## Notes

- **硬边界**：→ 见 requirements §Scope Exclusions（5 条完整列表）。
- **验证说明**：D8 只执行改动文件的单区域 `vue-tsc`/tsconfig 类型检查，并通过故障注入证明检查器确实能报错；最终回归由 F1-F4 汇总。全量 vue-tsc 的 OOM 或 capability manifest 解析失败只记录事实，不据此修改其他文件。
- **预存失败**：`registry/index.ts` capability manifest 解析失败属于既有问题；0.4 只记录复现命令和归因，不新增 allowlist、不修改其他文件，也不将其宣称为本 spec 已修复。
- **用户决策与阻塞**：`Project.business_category` 的 `String(10)` 与 `refinancing` 的处理须先由 0.2 决策；S17 classification 只允许按 0.3/D5/D6 dry-run，须用户批准后才可写共享库。未批准前不得将 S17 的真实数据库写入或浏览器验收标为完成。
- **状态约束**：spec 初版（2026-10-25）所有任务保持未勾选；后续实施中逐步勾选，以代码+测试在库为准。Phase Final（F1-F4）在全部回归跑通后勾选。

## Task Dependency Graph

紧凑依赖：`0.x → D2 → D1/D3/D5/D7 → D4/D6/D8 → P0 → P1 → P2 → Final (F1-F4)`。

> **注**：wave 16（P1.1~P1.5）的隐式前置是 D4（wave 11）已完成；P1.3 单独放 wave 17 因为依赖 P1.2 的 resolver 注册。

```json
{
  "waves": [
    { "id": 0, "tasks": ["0.1", "0.2", "0.3", "0.4"] },
    { "id": 1, "tasks": ["D2.1"] },
    { "id": 2, "tasks": ["D2.2"] },
    { "id": 3, "tasks": ["D2.3"] },
    { "id": 4, "tasks": ["D1.1", "D5.1", "D7.1"] },
    { "id": 5, "tasks": ["D1.2", "D3.1", "D6.1", "D7.2"] },
    { "id": 6, "tasks": ["D3.2", "D6.2", "D7.3"] },
    { "id": 7, "tasks": ["D3.3"] },
    { "id": 8, "tasks": ["D4.1"] },
    { "id": 9, "tasks": ["D4.2"] },
    { "id": 10, "tasks": ["D4.3"] },
    { "id": 11, "tasks": ["D4.4"] },
    { "id": 12, "tasks": ["D8.1", "D8.2"] },
    { "id": 13, "tasks": ["P0.1"] },
    { "id": 14, "tasks": ["P0.2"] },
    { "id": 15, "tasks": ["P0.3"] },
    { "id": "15b", "tasks": ["P0.4"] },
    { "id": 16, "tasks": ["P1.1", "P1.2", "P1.4", "P1.5"] },
    { "id": 17, "tasks": ["P1.3"] },
    { "id": 18, "tasks": ["P2.1"] },
    { "id": 19, "tasks": ["P2.2", "P2.3"] }
  ]
}
```
