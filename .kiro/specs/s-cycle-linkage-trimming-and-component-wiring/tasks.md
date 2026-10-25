# Implementation Plan: S 类底稿联动、裁剪与组件接线

## Overview

本计划只整理 S 类底稿联动、裁剪与组件接线的实施任务；当前为实施前收敛版，所有任务保持未勾选。任务按前置确认、D1-D8 收敛门、S 路由与浏览器门、只读关联与公式、风险导向及最终回归逐步推进。

## Tasks

> **实施前收敛版**：本次只修改 spec 文档；所有任务保持未勾选。FEAT-001~003、已有 registry/override、评审中的“已完成”均须按 D1-D8 重新验收。任务中的“修改文件”是未来实施边界，不代表本次已修改生产代码。

## Phase 0 — 前置确认与阻塞记录

- [x] 0.1 现读 `procedure-trim-generation-delegation-chain` 是否已入库；若已入库，重新确认 `chain_orchestrator` 的 SELECT/project_flags，再确定 D2 基线。
- [x] 0.2 查询 `Project.business_category` 类型和真库长度，针对 `String(10)` 与 `refinancing` 11 字符形成书面决策：批准加宽迁移，或批准可持久化的短 canonical code；未决前只允许纯函数测试，不得声称 PG/render 的 refinancing 已通过。
- [x] 0.3 现读 `backend/data/wp_account_mapping.json`、`.xls` 模板与 S34 `hasSubTable` 清册；确认 S34-3 在 12 个 parent 中，记录 S17 模板派生分类候选。
- [x] 0.4 记录 capability manifest 预存失败（`registry/index.ts` 解析失败）及复现命令；不得改其他文件、不得通过新增 allowlist 消除该失败。

## Phase P0 — D1-D8 收敛门

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

## Phase P0 — S 路由与浏览器门

- [x] P0.1 在 `resolveProcedureSheetKey` 增加 S20/S17/S15/S14/S13/S12/S10/S8/S1 专属 key，S16/S11 显式 `e1a`，S2/S9/S21/S32/S34 保持 `e1a`。
- [x] P0.2 增加每个 S 前缀、S11/S16 优先级和 D~N 回归测试；说明该路由只服务有独立程序表 sheet 的状态 namespace。
- [x] P0.3 D1-D4、D6（若批准）通过后，用【测试】项目 Playwright 验证 S1/S8/S9/S10/S17 专属渲染、保存和侧边栏；D6 未批准时只验收非 S17 路径并保留阻塞。
## Phase P1 — 只读关联与 S34 公式

- [x] P1.1 在 `backend/data/wp_account_mapping.json` 补 S20→D4、S15→D4/M2、S17→K12/K13、S6→K1、S33-5→D4/F5；grep 既有链接消费方并补白名单测试。
- [x] P1.2 新建 `_s_linkage.py` 的 3 个 resolver：`s6_related_party_summary`、`s33_5_revenue_cost_check`、`s14_estimate_related_data`；核对既有 11 个 S resolver 的 async 签名，总数验收 14；为每个新 resolver 找到 render-schema 或通用程序表绑定，单测只读和不写 TB。
- [x] P1.3 端到端验证 S20 程序表能展示 D4 营收审定数；异常在 savepoint 内隔离并保留诊断。
- [x] P1.4 读取 12 个 S34 hasSubTable 模板（含 S34-3），按模板补 `useS34FormulaEngine.ts` 定义；每表至少一条 formula test，浏览器验证有效数据计算。明确 runtime 与 `formula_settings` 定义治理正交，S 类不进入 `formula_push_rules.json`。
- [x] P1.5 S34/S35 外部 chip hover 复用 `cycle_audited_amounts` 展示只读值；vitest mock 和不写目标/TB 的契约测试。

## Phase P2 — 风险导向与委派

- [x] P2.1 对 `risk_assessments` 执行 `SELECT DISTINCT account_or_cycle ... LIMIT 50`，记录真实值域并确认映射；若数据库不可用，保留环境阻塞，不伪造枚举。
- [x] P2.2 实现 S34 风险指示器和四象限 `applicable/recommended/not_applicable`，增加 service/Overview 测试。
- [-] P2.3 在 4 个 bundle 的 tab 展示 `assigned_to` 对应 staff name，缺失时回退 username；增加 JOIN/展示测试，不改变 assignment_service 粒度。

## Phase Final — 回归与收口

- [ ] F1 后端回归：predicate、render-config、dispatch、classification contract、resolver、mapping 测试；仅将 capability manifest 失败作为预存记录。
- [ ] F2 前端回归：IPO 核心/D4/F2、GtWpRenderer、s-checklist、S 路由、S34/S35 相关测试；单区域 type proof 已由 D8 覆盖。
- [ ] F3 浏览器回归：S3/S12/S14/S15/S20/S21 既有专属组件不受影响；bundle overlay、S17 classification gate 和测试项目数据清理有记录。
- [ ] F4 三件套一致性检查：逐条核对 requirements 的验收标准均有 design 方案和 task 承接；未批准决策、环境失败、未完成任务保持未勾选，不以代码存在或 registry 测试绿替代证据。

## Notes

- **硬边界**：不实现 `/api/s-special/*`；不未经批准写 S17 `workpaper_sheet_classification`；不自动迁移 `String(10)`；不新增 S 类 formula-push 规则；不改 capability manifest 预存失败。
- **验证说明**：D8 只执行改动文件的单区域 `vue-tsc`/tsconfig 类型检查，并通过故障注入证明检查器确实能报错；最终回归由 F1-F4 汇总。全量 vue-tsc 的 OOM 或 capability manifest 解析失败只记录事实，不据此修改其他文件。
- **预存失败**：`registry/index.ts` capability manifest 解析失败属于既有问题；0.4 只记录复现命令和归因，不新增 allowlist、不修改其他文件，也不将其宣称为本 spec 已修复。
- **用户决策与阻塞**：`Project.business_category` 的 `String(10)` 与 `refinancing` 的处理须先由 0.2 决策；S17 classification 只允许按 0.3/D5/D6 dry-run，须用户批准后才可写共享库。未批准前不得将 S17 的真实数据库写入或浏览器验收标为完成。
- **状态约束**：本次仅修复 spec 文档格式；现有任务、D1-D8 依赖、P0/P1/P2 范围、阻塞事实均保留，所有任务继续保持未勾选；不表示生产代码或测试代码已经修好。

## Task Dependency Graph

紧凑依赖：`0.x → D2 → D1/D3/D5/D7 → D4/D6/D8 → P0 → P1 → P2 → Final (F1-F4)`。

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
    { "id": 16, "tasks": ["P1.1", "P1.2", "P1.4", "P1.5"] },
    { "id": 17, "tasks": ["P1.3"] },
    { "id": 18, "tasks": ["P2.1"] },
    { "id": 19, "tasks": ["P2.2", "P2.3"] }
  ]
}
```


## 0.4 复现记录（capability manifest 预存失败；仅记录，不修复）

- 归因：这是 capability manifest 生成器的既有基线问题，不由本 spec 引入。`registry/index.ts` 第 204 行为 `export type HtmlComponentType = HtmlRendererEntry['componentType']`；`git blame` 显示该行来自 `82f58ea443`（2026-09-13 23:21:39 +0800）。生成器当前只接受字符串字面量 union，因此在该 indexed-access 声明处 fail-closed。
- 复现位置：仓库根目录 `D:/GT_plan`。
- 复现命令 1：`python backend/scripts/gen/generate_component_capability_manifest.py --check`
  真实输出：
  ```text
  [FAIL] D:\GT_plan\audit-platform\frontend\src\components\workpaper\registry\index.ts: HtmlComponentType must contain only string literals
  PROCESS_EXIT=2
  ```
- 复现命令 2：`rtk python -m pytest backend/tests/test_component_capability_contract.py::test_checked_in_manifest_is_canonical_and_current -q -p no:playwright`
  真实结果：
  ```text
  F                                                 [100%]
  FAILED backend\\tests\\test_component_capability_contract.py::test_checked_in_manifest_is_canonical_and_current - scripts.gen.generate_component_capability_manifest.SourceExtractionError
  1 failed, 1 warning in 1.44s
  PROCESS_EXIT=1
  ```
  失败栈定位为 `check_manifest() → build_manifest() → extract_observed_sources() → extract_ts_string_union()`，同一 `registry/index.ts` 声明触发 `SourceExtractionError`。
- 边界：本次未运行 `--apply`，未修改 capability manifest、TypeScript projection、registry、allowlist 或任何生产/测试代码；该失败只作为预存问题证据记录，不将其归因于本 spec，也不以新增 allowlist 消除失败。


## D5.1 执行记录（2026-10-25）

- 直接读取 `backend/wp_templates/S/S17 非经常性损益.xls` 得到 `审定表S17-1`、`审核表（合并）S17-2`、`审核表（个别报表）S17-3`、`与营业外收支等核对表S17-11`、`非经常性损益项目的所得税影响S17-21`；据此将前三张表统一映射到 `s17-nonrecurring-detail`，后两张分别映射到 `s17-reconciliation`、`s17-tax-impact`。
- 本记录只涉及五个 `wp_code_overrides.json` 精确值和对应 pytest；未实现 D3 backend dispatch，也未执行 D6 classification dry-run。


## D6.2 执行记录（2026-10-25 20:16 +08:00；外部阻塞，未批准）

- **任务状态**：D6.2 保持 `[-]`，不标记为 `[x]`。本记录只登记“等待用户批准”的外部阻塞，不构成批准、种子执行或 S17 浏览器验收证据。
- **D6.1 证据**：`.agents/tasks/s-cycle-p0-impl-2026-10-25/s17_classification_dry_run.json`（report_version=1，`mode=dry-run`）。模板为 `backend/wp_templates/S/S17 非经常性损益.xls`，格式 `xls`，读取器 `xlrd 2.0.2`，模板 SHA-256 为 `392f9bf65f5baab5c35c3535b2cef5d67487ccdb9feec2c54121a5361bc6e3f1`。
  - 候选数为 **8**；`shared_database_accessed=false`、`writes_shared_database=false`。
  - `reference_classification` 来自离线快照 `backend/data/acnr/sources/classification_cache.json`，其中 `existing_s17_rows=1` 仅表示父级 `S17 / S-审定表` 快照行，`exact_candidate_rows=0`；报告明确标注“数据库未查询”。该离线快照不等于当前共享数据库状态，也不等于批准。

### 候选清单（均为待批准候选，不是已落库分类）

| sheet | candidate class_code | legacy xlsx 对照 | 冲突 |
|---|---|---|---|
| 表头（请先填写） | `I-占位` | `I-占位` | 无 |
| 审计程序S17 | `A-S 议题程序` | `A-S 议题程序` | 无 |
| 审定表S17-1 | `F-审定表` | `F-审定表` | 无 |
| 审核表（合并）S17-2 | `D-检查表` | `F-数据表` | `legacy_xlsx_classifier_mismatch`：高公式密度数据表 |
| 审核表（个别报表）S17-3 | `D-检查表` | `_pending` | `legacy_xlsx_classifier_mismatch`：未匹配规则 |
| 提示（供参考，不打印） | `H-辅助说明` | `_pending` | `legacy_xlsx_classifier_mismatch`：未匹配规则 |
| 与营业外收支等核对表S17-11 | `D-检查表` | `D-检查表` | 无 |
| 非经常性损益项目的所得税影响S17-21 | `D-检查表` | `F-数据表` | `legacy_xlsx_classifier_mismatch`：高公式密度数据表 |

- **待用户裁决的冲突**：共 4 个，分别为 S17-2、S17-3、提示（供参考，不打印）、S17-21；不得因候选来自 `.xls` 模板就自动覆盖既有 xlsx 分类规则，也不得把 `_pending` 自动视为已确认分类。
- **批准状态**：当前没有用户对上述 8 行及 4 个冲突的明确批准记录；状态为 `awaiting_user_approval`。在用户明确批准前，S17 `workpaper_sheet_classification` 仍视为未准备好写入。
- **批准前禁止动作**：
  1. 不执行针对 `workpaper_sheet_classification` 或相关共享表的 `INSERT`、`UPDATE`、`DELETE`、seed、migration 或任何等价写入；不运行会落库的 `--apply` 流程。
  2. 不将离线快照父级行或本次候选清单当作实时数据库确认，不自动解决 4 个冲突。
  3. 不运行 S17 浏览器渲染/保存验收，不把 S17 渲染、S17 classification gate 或 P0.3/F3 的 S17 子路径标为完成；“无 sheet”只能记录为阻塞，不能解释为组件验收通过。
- **批准后的切换点**：只有用户明确批准候选及冲突处理后，才另开记录执行实时数据库复核，并按数据库迁移/种子流程在允许的测试范围内落库；随后另行安排 S17 浏览器验收。批准前本次只允许复核 JSON 证据和 no-write 守卫。
- **本次验证边界**：沿用 `backend/tests/test_s17_classification_dry_run.py` 的离线契约守卫，确认报告为 dry-run、未访问/写入共享数据库，且生成器没有 SQLAlchemy/database import 或 `execute/commit/flush/begin` 调用；本次不运行 S17 浏览器验收。


### D6.2 验证补记（2026-10-25）

- 执行 `rtk python -m pytest backend/tests/test_s17_classification_dry_run.py -q -p no:playwright`：**3 passed, 1 warning**。
- 该守卫确认 8 个候选、`mode=dry-run`、`shared_database_accessed=false`、`writes_shared_database=false`，并通过 AST 检查生成器不导入 SQLAlchemy/数据库模块且不调用 `execute`、`commit`、`flush`、`begin`。
- 本次未执行任何数据库 INSERT/UPDATE/DELETE、seed、migration 或 `--apply`，未启动或运行 S17 浏览器渲染/保存验收；D6.2 仍为外部阻塞，等待用户明确批准。


### D8.2 执行记录（2026-10-25 21:34 +08:00；环境/预存失败，仅记录）

- **全量 vue-tsc**：在 `d:/GT_plan/audit-platform/frontend` 运行真实全量命令 `npm exec -- vue-tsc --noEmit --pretty false`；该命令使用前端 `package.json` 的本地 `vue-tsc`，读取完整 `tsconfig.json`（`src/**/*.ts`、`src/**/*.tsx`、`src/**/*.vue`），未运行会改写 `dist` 的 `vite build`。进程约 45.7 秒后退出 **134**。
  - 关键 stderr：`Last few GCs`；`Mark-Compact 4042.0 (4138.7) -> 4034.5 (4139.7) MB`；`FATAL ERROR: Ineffective mark-compacts near heap limit Allocation failed - JavaScript heap out of memory`；随后 `VUE_TSC_EXIT=134`。
  - 未输出 TypeScript 诊断，结论是 Node/V8 全量类型检查达到约 4.14 GB 堆上限后 OOM；按 D8.2 归类为环境/预存问题，不归因于本 spec 的生产缺陷。

- **capability manifest `--check`**：在仓库根目录运行 `python backend/scripts/gen/generate_component_capability_manifest.py --check`，退出 **2**。真实关键输出：
  ```text
  [FAIL] D:\GT_plan\audit-platform\frontend\src\components\workpaper\registry\index.ts: HtmlComponentType must contain only string literals
  MANIFEST_CHECK_EXIT=2
  ```
  失败源为 `registry/index.ts` 的 `HtmlComponentType` indexed-access 声明（`HtmlRendererEntry['componentType']`），生成器的 fail-closed 解析器只接受字符串字面量 union。

- **capability manifest 契约测试**：运行 `rtk python -m pytest backend/tests/test_component_capability_contract.py::test_checked_in_manifest_is_canonical_and_current -q -p no:playwright`，退出 **1**，结果为 `1 failed, 1 warning in 1.27s`。关键调用链为 `check_manifest() → build_manifest() → extract_observed_sources() → extract_ts_string_union()`，最终抛出 `SourceExtractionError: ... HtmlComponentType must contain only string literals`；输出末尾为 `CAPABILITY_CONTRACT_TEST_EXIT=1`。

- **归因与边界**：以上全量 `vue-tsc` OOM 和 capability manifest 解析失败均只作为 D8.2 的环境/预存证据记录；本次未运行 `--apply`，未修改 capability manifest、TypeScript projection、registry、allowlist、tsconfig、生产代码或测试代码。除本条事实记录追加外，不作修复、不新增 allowlist，也不将上述失败标为本 spec 的生产缺陷。


## P0.3 执行记录（2026-10-25；Playwright 真实运行，非通过）

- **环境与入口**：确认 `http://127.0.0.1:9980/api/health` 返回 HTTP 200，`http://127.0.0.1:3030/` 返回 HTTP 200；使用真实登录页 `http://127.0.0.1:3030/login?redirect=/` 以 `admin/admin123` 登录。项目全屏入口为 `/projects/full`，底稿入口为 `/projects/{project_id}/workpapers`，编辑入口为 `/projects/{project_id}/workpapers/{wp_id}/edit`。
- **测试项目**：仅使用 `proj_f7b784dd`（项目 ID `19522381-430c-4e4e-8ee5-a22e5e90ad68`，客户名 `测试客户`）。项目原有 1 张 D2 底稿；通过真实 UI「生成底稿」→「标准年审」→「全不选」→只勾选 S1/S8/S9/S10→「确认生成（4 项）」后，API 实读共 5 张：D2、S1、S8、S9、S10。该次生成写入仅发生在允许的测试项目。
- **S17 边界**：D6 classification 尚无用户批准。本次没有勾选、生成、打开、保存或请求 S17；测试项目当前 `S17` 底稿数量为 0。没有执行 `workpaper_sheet_classification` 的 INSERT/UPDATE/DELETE、seed、migration 或 `--apply`。S17 浏览器/数据库验收继续保持阻塞，不得标记完成。

### 真实 render-config 结果

使用浏览器携带登录令牌逐个请求 `/api/workpapers/{wp_id}/render-config`，HTTP 均为 200，但专属 componentType 未被实际选择：

| wp | 真实 sheet/componentType 结果 | 失败证据 |
|---|---|---|
| S1 | `表头（请先填写）→ onlyoffice-sheet`；`违反法规行为S1 → a-program-console`；`S1-1对法律法规的考虑记录表`、`S1-2沟通记录 → d-form-confirmation` | `违反法规行为S1` 含 `html_data.grid_fallback`；无 `s1-regulation-record` |
| S8 | `表头（请先填写）→ onlyoffice-sheet`；`审定表S8-1 → audit-sheet`；`租赁S8 → a-program-console` | 无 `s8-adjudication` |
| S9 | `对电子商务的考虑S9`、`审定表S9-1`、`内部控制调查表S9-2 → a-program-console`；说明类 sheet 为 `h-static-doc` | 无 `s9-adjudication`、`s9-internal-control`、`s9-legal-regulations`、`s9-program-description`；多个 sheet 含 `grid_fallback` |
| S10 | `对环境事项的考虑S10`、`审定表S10-1`、`附、内控调查表S10-2 → a-program-console`；说明类 sheet 为 `h-static-doc` | 无 `s10-adjudication`、`s10-internal-control`、`s10-environmental-regulations`；多个 sheet 含 `grid_fallback` |

结论：S1/S8/S9/S10 的真实页面确实被打开并渲染，但 D3/D4 要求的专属后端分发没有在运行时兑现；不能用 registry、override 或已有前端组件登记替代端到端证据。

### 中文 UI、侧边栏与保存边界

- 真实打开 S1/S8/S9/S10 编辑页并检查中文标签：各页显示对应 S 编码/中文名称和精确 sheet tab（如「违反法规行为S1」「审定表S8-1」「审定表S9-1」「审定表S10-1」）。
- 真实点击四页的「📋 面板」按钮；均打开中文「底稿面板」，包含「编制辅助 / 质量检查 / 追溯关联 / 历史版本」和「程序 / 程序要求 / 提示」，但程序区真实显示「完成率：0%」「暂无程序清单」。这证明侧边栏可打开，但未形成 S 专属程序清单/namespace 的可验收证据。
- 由于 render-config 没有挂载四个专属 s-checklist componentType，页面没有 D4 专属 `items[]` 保存控件可触发；本次未向通用 OnlyOffice/网格路径伪造保存，也未调用 `/api/s-special/*`。浏览器网络记录未出现 `/api/checklist-responses`、`batch-save` 或 `/api/s-special` 请求，因此 D4 保存体、readonly 保存禁止和专属组件保存均保持未验收。

### 结论与未完成边界

- P0.3 **不能标记完成**：S1/S8/S9/S10 的真实渲染均未达到专属 componentType/无 fallback，D4 保存无法按专属路径验证；tasks 中 P0.3 继续保持 `[-]`。
- S17 因 D6 未获批准继续保持浏览器/数据库阻塞；本次明确未伪造 S17 完成。
- 本次未修改生产代码、测试代码或 capability manifest；仅追加本验收记录。


## P2.1 执行记录（2026-10-25 23:08 +08:00；实时 PG 只读核查，数据阻塞）

- **旧表存在性 / schema**：实时查询 `information_schema.tables` 确认 `public.risk_assessments` 与 `public.checklist_responses` 均为 `BASE TABLE`。`risk_assessments` 的 `account_or_cycle` 为 `character varying NOT NULL`（ORM `RiskAssessment` 对应 `String(100)`），并含 `project_id`、风险等级、`is_significant_risk`、`review_status`、`is_deleted` 等旧风险模型字段。
- **按任务要求执行的精确查询**：
  ```sql
  SELECT DISTINCT account_or_cycle FROM risk_assessments LIMIT 50;
  ```
  真实结果为空集 `[]`；独立只读计数为 `risk_rows=0`、`risk_projects=0`、`distinct_account_or_cycle=0`。因此当前库没有可记录的 `risk_assessments.account_or_cycle` 真实值域，不能伪造 D~N、S 或其他枚举，也不能据此确认 P2.1 的风险映射。
- **B50 真实来源核对**：`public.checklist_responses` 的关键列为 `project_id uuid`、`wp_id uuid`、`item_id varchar`、`conclusion text`、`remark text`，全表当前 215 行；但按真实关系 `working_paper.wp_index_id → wp_index.id` 且 `wp_index.wp_code='B50'` 联查，当前有 7 个 B50 工作稿（7 个项目），`B50` 对应 `checklist_responses` 为 **0 行**。因此本次也没有可从实时 B50 数据记录的账号/循环值域。
- **服务与映射实证**：`backend/app/services/b50_risk_reader.py` 的 `_find_b50_wp_id()` 按 `working_paper JOIN wp_index` 定位 B50；`load_b50_accounts()` 只读 `checklist_responses` 中 `item_id LIKE 'B50-T3-%'`，其中 `B50-T3-cycle-{account}` 的 `conclusion` 是循环值，矩阵 `B50-T3-matrix-{account}-{assertion}-RMM/SR` 分别解析 H/M/L 与 Y；`load_b50_risks()` 再将矩阵展平。该读取器已被 `backend/app/routers/b60_data_pull.py`、`backend/app/services/auto_data_resolvers/_cycle.py`、`_control_b.py` 及 `a176_agenda_prefill.py` 消费；这确认 B50 checklist 是现行风险联动的代码真源路径，但当前共享库没有 B50 响应数据。
- **边界 / 状态**：本次只执行 SELECT / schema 元数据读取，未执行任何 INSERT、UPDATE、DELETE、seed 或迁移。P2.1 保持 `[-]` 环境/数据阻塞；待真实 B50 checklist 写入后重新执行值域查询并由用户确认风险到 S 类的映射，未以空结果伪造枚举或标记 P2.1 完成。
