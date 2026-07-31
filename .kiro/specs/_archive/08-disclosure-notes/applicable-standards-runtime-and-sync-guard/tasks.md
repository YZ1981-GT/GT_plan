# Implementation Plan: applicable_standards runtime provide + 同步端跨准则守卫

## Overview

前端段（1~4）与后端段（5~6）互不依赖，可并行；回归与实测放最后。

## Task Dependency Graph

```json
{
  "waves": [
    { "wave": 1, "tasks": ["1", "5"], "desc": "leaf 归一模块 + 后端纯函数守卫", "depends_on": [] },
    { "wave": 2, "tasks": ["2", "6"], "desc": "scaffold 字段与两条路径 + 服务/路由接线", "depends_on": [1, 5] },
    { "wave": 3, "tasks": ["3"], "desc": "宿主收敛到 composable", "depends_on": [2] },
    { "wave": 4, "tasks": ["4", "7"], "desc": "守卫改写 + 回归与浏览器实测", "depends_on": [3, 6] }
  ]
}
```

## Tasks

- [x] 1. 抽 leaf 归一模块
  - [x] 1.1 新建 `composables/applicableStandards.ts`：`normalizeApplicableStandards`
        （从 `useF2FormData.ts` 原样迁出，含 `firstNonEmpty` / `dedupeNonEmpty`），零依赖
  - [x] 1.2 `useF2FormData.ts` 改为 `export { normalizeApplicableStandards } from './applicableStandards'`
        （存量 20+ import 零改动，`normalizeApplicableStandards.spec.ts` 29 例仍绿）
    _Requirements: R3.3_

- [x] 2. scaffold 提供 applicableStandards
  - [x] 2.1 `useWorkpaperScaffold`：`UseWorkpaperScaffoldOptions.applicableStandards?`
        + `WorkpaperRuntimeContext.applicableStandards: Ref<string[]>`（computed 归一，
        缺省 `[]`），随 runtime 一起 provide
  - [x] 2.2 `GtWpRenderer`：传 `computed(() => renderConfig.value?.applicable_standards)`
  - [x] 2.3 `GtWorkpaperShell`：新增 `applicableStandards?: unknown` prop 并透传
  - [x] 2.4 `composables/__tests__/useWorkpaperScaffold.spec.ts` 追加 Property 1/2（6 例全绿）
    _Requirements: R1.1~R1.4, R2.1~R2.3_

- [x] 3. 宿主取值收敛
  - [x] 3.1 `hostApplicableStandards.ts` 增 `useHostApplicableStandards({explicit, htmlData})`
        （setup 作用域 inject runtime，返回 ComputedRef，按 R3.2 顺序）
  - [x] 3.2 改造 **21 个宿主**：G1/G2/G3/G4/G5/G6/G8/G9/G11/G12/G13/G14、H8/H10、
        I2/I3/I5/I6、F1/F2/F3 —— 删掉各自 5 种写法的取值链；I3/I5/I6 的
        `(runtime as any)?.applicableStandards?.value` 死 fallback 一并清除
        （上一轮守卫正则只匹配 `runtime?.applicableStandards`，被 `as any` 绕过）；
        H8 保留 `template_type` 派生兜底（后端注入失败时才用）；I3 顺带删掉只服务旧
        取值链的死变量 `runtimeCtx`
  - [x] 3.3 21 个宿主 + 6 个基础设施文件 `get_diagnostics` 零问题、Vite transform 27/27 = 200
    _Requirements: R3.1, R3.2, R3.4_

- [x] 4. 前端守卫改写
  - [x] 4.1 `__tests__/hostApplicableStandards.spec.ts`：原「不得读 runtime」断言扩为
        「含 `as any` 强转也不得读」+「凡 computed 出 applicableStandards 的宿主必须接
        共享 composable」+ composable 三层优先级用例（Property 3，16 例）
  - [x] 4.2 新增断言：`GtWpRenderer` / `GtWorkpaperShell` 源码必须向 scaffold 传
        `applicableStandards`（防未来重构悄悄摘掉）
    _Requirements: R5.1_

- [x] 5. 后端纯函数守卫
  - [x] 5.1 `standard_unification_service.detect_standard_conflict(project_standard, requested)`
        （只判 entity 维度；空/非准则字面量/无准则/项目侧脏数据 → None）
  - [x] 5.2 `tests/test_standard_conflict_guard.py`：Property 4/5 + 3×2×2 entity/scope 矩阵参数化
    _Requirements: R4.1~R4.5_

- [x] 6. 服务与路由接线
  - [x] 6.1 `wp_disclosure_sync_service`：`StandardMismatchError(ValueError)` +
        `_resolve_project_sync_context`（**一次查询**取 audit_year + 准则四列，异常 fail-open；
        无任何准则字段返回 `None` 而非被 `_normalize_standard` 补成默认 soe → 不误杀上市推送）
        + `sync_from_workpaper` 在所有写入前 `_guard_standard_matches_project`
  - [x] 6.2 `wp_disclosure_sync.py` 两端点：`except StandardMismatchError` → 409
        结构化 detail（在 `except ValueError` 之前）+ OpenAPI `responses` 登记
  - [x] 6.3 补测：Property 6（拒绝时 `db.add`/`db.commit`/`db.flush` 零调用、`execute`
        仅 1 次）+ 反向自检（准则一致时继续走新建）+ 源码顺序断言 + 批量端点 409
        + 既有 fake DB 适配（`test_wp_disclosure_sync_revive._make_db` 改回项目行形态，
        `test_manual_override_hook._DiscFakeDB` 显式 `first()->None` 走 fail-open）
    _Requirements: R4.1, R4.6, R4.7, R5.2_

- [x] 7. 回归与浏览器实测
  - [x] 7.1 后端 122 绿（新守卫 61 + 同步回归 55 + 派生/注入 6 复跑）；
        前端 `workpaper/__tests__` 8982 例 8906 绿（73 失败全在 b23×3 / GtG0 基线文件），
        `workpaper/composables/__tests__` 8050 例 8042 绿（8 失败 = L4×2/F3/F5/H4 既有基线
        + K1 sheet 名括号漂移与 columnsPending 2 例属并发 K 系 spec）
  - [x] 7.2 CI job `applicable-standards-runtime-guard`（后端）
        + `applicable-standards-runtime-frontend`（前端）
  - [x] 7.3 浏览器 / API 实测（国企项目 `2aa00f57-1df4-4fe8-9840-2d65d0fd8749`）：
        - render-config 顶层 `["soe_standalone","soe","standalone"]`，10 个 sheet 逐个同值
        - I6 底稿「附注披露（国有企业）」正常渲染（1 表 52 输入框、banner 指向 八、67）；
          「附注披露（上市公司）」按 `disclosureVis.listed=false` 回退底稿目录 → 门控生效
        - 点「同步到附注 八、67」→ `last_sync_at` 16:15:27 → 17:21:00（allow 路径通）
        - 直接 POST `current_standard=listed_standalone` → **409**
          `{code: STANDARD_MISMATCH, project_standard: soe_standalone, allowed: [...]}`，
          且探测用章节 `五、999%` 落库 **0 行**（Property 6 活体复验）
    _Requirements: R5.3_

## Notes

- **不改**任何 `isXDisclosureApplicable` / `resolveXCurrentStandard` 判定逻辑
- **不碰** N1/N2/N4/K8~K13/`kPlDisclosureShared.ts`（并发会话在飞）
- 409 被前端 `catch` 静默吞是有意为之（宁可不写也不写错章节），用户可见提示另立
- **遗留（需用户确认才能动）**：国企项目 `2aa00f57` 上仍有一条上市章节 `五、66`
  （I6 上市披露，`_current_standard=listed_standalone`，2026-07-30 写入）——
  正是本守卫要防的污染，但**存量清理属破坏性 DB 操作**，未执行
