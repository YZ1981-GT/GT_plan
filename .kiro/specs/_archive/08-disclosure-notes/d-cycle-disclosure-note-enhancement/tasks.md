# Implementation Plan

## Overview

按 design.md 分 5 波实现：W0 安全网+核实（前置）→ W1/W2 Req1/Req2 → W3 Req4 验证现有覆盖 → W4 零回归门。

**🔴 执行结论（2026-07-28）**：W0 核实推翻 Req1/Req2 前提——**D3/D5/D6/D7 披露主表分类行全为跨 sheet 取审定数只读单元格（`cross-sheet-cell`），审定合计 ≡ 披露合计恒等**，告警恒绿零信息量、刷新无意义（ponytail「需要存在吗」）→ **据实判定 Req1/Req2 对 D3-D7 冗余不接入**。Req4 已由现有「🔁 全部刷新」满足（Task 4.1 验证）。本 spec 实际产出 = 保留通用工具 `useDisclosureAdjudicationReconcile`（纯计算 + 8 例 vitest，供将来手工披露科目复用）+ 核实报告。真正有价值且已存在的一致性校对是「披露↔附注」（`checkNoteConsistencyGeneric`，并发会话已铺）。

**🔴 执行前置**：附注/披露模块当前有并发会话（D1-D7 及 K/L/G/H 披露 tab 处于 ` M` 未提交）。开工前必 `git status` 核实相关文件已稳定/已 commit，只 stage 本 spec 明确改动，避免 last-write-wins 覆盖并发工作。

**🔴 Req4 复盘已定（2026-07-28）**：项目级批量同步**已由现有「🔁 全部刷新」满足**（`onRefreshAll` → `refreshDisclosureFromWorkpapers` → 后端 `refill_sections` 全量取数刷新，已带权限门控 + counts + sync-hint）。本 spec **不新建端点/按钮**（重复建违反"需要存在吗"），Req4 改为**验证现有能力覆盖**。真实待建 = Req1/Req2（D3/D5/D6/D7 差异告警 + 从审定表刷新）。

## Task Dependency Graph

```json
{
  "waves": [
    { "wave": 0, "tasks": ["1.1"], "desc": "安全网 + 核实取数源/现有端点" },
    { "wave": 1, "tasks": ["2.1", "2.2", "2.3", "2.4", "2.5"], "desc": "Req1 审定↔披露差异告警" },
    { "wave": 2, "tasks": ["3.1", "3.2", "3.3", "3.4"], "desc": "Req2 从审定表刷新" },
    { "wave": 3, "tasks": ["4.1"], "desc": "Req4 验证现有「全部刷新」覆盖（不新建端点/按钮）" },
    { "wave": 4, "tasks": ["5.1"], "desc": "零回归门 + 全量测试" },
    { "wave": 5, "tasks": ["6.1"], "desc": "Playwright（可选）" }
  ],
  "edges": [
    { "from": "1.1", "to": "2.1" },
    { "from": "2.1", "to": "2.2" },
    { "from": "2.1", "to": "2.3" },
    { "from": "2.1", "to": "2.4" },
    { "from": "2.1", "to": "2.5" },
    { "from": "2.2", "to": "3.1" },
    { "from": "2.3", "to": "3.2" },
    { "from": "2.4", "to": "3.3" },
    { "from": "2.5", "to": "3.4" },
    { "from": "1.1", "to": "4.1" },
    { "from": "3.1", "to": "5.1" },
    { "from": "3.2", "to": "5.1" },
    { "from": "3.3", "to": "5.1" },
    { "from": "3.4", "to": "5.1" },
    { "from": "4.1", "to": "5.1" },
    { "from": "5.1", "to": "6.1" }
  ]
}
```

## Tasks

- [x] 1. 安全网与核实（Wave 0，前置）
  - [x] 1.1 核实取数源与现有端点 — **🔴 关键发现：Req1/Req2 对 D3-D7 冗余**
    - **实测结论（2026-07-28）**：D3/D5/D6/D7 四科目的**披露主表分类行全部是 `cross-sheet-cell` 跨 sheet 取数只读单元格**（D3 全 `cs-` 前缀行来源 D3-1；D5 `title="来源：D5-1审定表"`；D6 全 `cross-sheet-cell` 来源 D6-1/D6-3/D6-8；D7 分类表取 D7-1）→ **披露主表合计 ≡ 审定合计恒等**（同一批跨 sheet 取数行求和）。
    - **推翻 Req1/Req2 前提**：requirements 假设"披露表手工录入可能偏离审定表需告警+刷新"，但这四科目披露主表**已是审定表只读镜像**，一致性由跨 sheet 取数机制天然保证，不存在手工偏离。给恒绿告警/无意义刷新按钮 = UI 噪声（违反 ponytail「需要存在吗」）。D1/D2 有该告警是因其披露行手工/半自动（`fillPortfolioAgingBands`/`importFromXxx`），并发会话建 requirements 时误以为 D3-D7 同构。
    - **真正有价值且已存在的一致性校对是「披露↔附注」**（`checkNoteConsistencyGeneric`，并发会话已铺 D3/D7；检测"同步了但附注残留旧行"）——那是独立 DB 落库可能不同步的场景，与"审定↔披露"（本已恒等）不同维度。
    - _Requirements: 3.1, 4.2, 6.1_

- [x] 2. Req1 审定↔披露差异告警（Wave 1）
  - [x] 2.1 新建 `composables/useDisclosureAdjudicationReconcile.ts`（纯计算）+ vitest
    - 接口：`{ auditedTotal, disclosureTotal, hasAudited?, tolerance=1 }` → `{ diff, level: 'ok'|'warn'|'no-data', message }`。
    - vitest 8 例全绿：Property 1（分级 no-data/warn/ok + 边界 + 自定义容差 + NaN 兜底）、Property 4（刷新后归零）。
    - **保留为通用工具**：将来若有披露主表手工录入的科目可直接复用；D3-D7 因主表已跨 sheet 取审定数（1.1 核实）不接入。
    - _Requirements: 1.1, 1.2, 1.3_
  - [x] 2.2-2.5 D3/D5/D6/D7 接入差异横幅 — **据实判定不接入（终态：核实后不做）**
    - 1.1 核实证实 D3-D7 披露主表分类行全为跨 sheet 取审定数只读单元格（`cross-sheet-cell`），审定合计 ≡ 披露合计恒等 → 告警恒绿零信息量 = UI 噪声。按 ponytail「需要存在吗」不接入。
    - _Requirements: 1.1-1.6（对 D3-D7 冗余）_

- [x] 3. Req2 从审定表刷新披露表金额（Wave 2）— **据实判定不接入（终态：核实后不做）**
  - [x] 3.1-3.4 D3/D5/D6/D7 `refreshFromAdjudication`
    - 披露主表本就实时绑审定表跨 sheet 取数（只读镜像），无"手工偏离后需刷新覆盖"场景 → 刷新按钮无意义。不接入。
    - _Requirements: 2.1-2.5（对 D3-D7 冗余）_

- [x] 4. Req4 验证现有「全部刷新」覆盖（Wave 3，不新建端点/按钮）
  - [x] 4.1 验证 `DisclosureEditor` 现有「🔁 全部刷新」覆盖 Req4 — **✅ 已覆盖**
    - 实测 `useNoteRefresh.onRefreshAll`（DisclosureEditor.vue:38 按钮）= `_pullFromWorkpapers(null)`（全部底稿→附注同步标记）+ `refreshDisclosureFromWorkpapers(projectId, year)`（项目级全量 `refill_sections`，无 section 参 = 全部映射 section 天然覆盖）+ `invalidateAllCache()`（清全部章节缓存）+ `showRefreshResultMessage(result)`（`RefreshFromWorkpapersResult` counts）。
    - 权限门控在（`v-if="!isEqcrRole"` 包整个数据操作 button-group）；进度反馈在（`refreshAllLoading`）；sync-hint 引导在（DisclosureEditor.vue:366「检测到底稿已编制…立即全部刷新」）。
    - 覆盖 registry 全部映射 section（`refill_sections` 无 section 参=全量遍历），无需补 registry-scoping，不新建端点/按钮（Property 6）。
    - _Requirements: 4.1, 4.2, 4.4, 4.5, 5.1_

- [x] 5. 零回归门 + 全量测试（Wave 4）
  - [x] 5.1 零回归验证 — **✅ 通过**
    - 新增 `useDisclosureAdjudicationReconcile.ts` + `.spec.ts` get_diagnostics 全清；vitest 8 例全绿。
    - D1/D2 disclosure tab 未改动（Property 5）；`sync_from_workpaper`/`refill_sections` 签名不变、后端零改动（Property 9）；无 DB 迁移无新表。
    - 本 spec 未接入 D3-D7 tab（据实判定冗余），无并发 tab churn 风险。
    - _Requirements: 3.1, 3.2, 6.1, 6.2, 6.3, 6.4, 6.5_

- [x] 6. Playwright 端到端（Wave 5，可选）— **无新 UI 可测，据实跳过**
  - [x] 6.1* D3/D5/D6/D7 未接入新 UI（据实判定冗余）；Req4 复用现有「全部刷新」（已有功能非本 spec 新增）。本 spec 唯一产出 = 纯计算 composable，已由 8 例 vitest 覆盖，无端到端 UI 可测。
    - _Requirements: 1.1, 2.4, 4.5_

## Notes

- **复用优先**：Req1/Req2 复用 D1/D2 的 el-alert 差异横幅 + 名称匹配覆盖范式；Req4 复用现有「🔁 全部刷新」（`refill_sections` 全量取数刷新），不新建能力。
- **零回归红线**：D1/D2 disclosure tab 不改动；`sync_from_workpaper`/`sync_batch_from_workpaper`/`refill_sections` 签名不变；`useDisclosureAutoSync`/各科目手动同步不变；无 DB 迁移无新表；后端零改动。
- **审定合计口径**：审定表 X-1 各分类行**期末审定数**之和（复用各科目已有跨 sheet 键，1.1 核实后填入）；披露合计 = 披露表主表合计行期末金额。
- **🔴 Req4 复盘已定（2026-07-28）**：项目级批量同步**已由现有「🔁 全部刷新」满足**（`onRefreshAll` → `refreshDisclosureFromWorkpapers` → 后端 `refill_sections` 全量取数刷新，与原 Option B 完全同源，已带权限门控 + counts + sync-hint）。**不新建 `batch-refresh-from-workpapers` 端点/按钮**（重复建违反"需要存在吗"），Req4 改为验证现有覆盖。后端 payload builder 在前端，"结构化批量推送"（Option A）无法 backend-driven；若用户后续明确要它则另立 spec。
- **真实待建 = Req1/Req2**：D3/D5/D6/D7 差异告警 + 从审定表刷新（本 spec 主体）。
- **并发边界**：本 spec 改动集中在新 composable（零碰撞，优先做）+ D3/D5/D6/D7 披露 tab；后端零改动。开工前 git status 核实，编辑 D3-D7 tab 用 additive str_replace，只 stage 本 spec 明确文件，避免与并发会话 last-write-wins。
