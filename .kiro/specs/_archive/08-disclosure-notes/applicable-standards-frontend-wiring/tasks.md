# Implementation Plan: applicable_standards 前端全链接通

## Overview

三段链路各自独立，可并行；实测放最后。判定逻辑（`isXDisclosureApplicable` /
`resolveXCurrentStandard`）一行不改 —— 本 spec 只让它们拿到数据。

## Task Dependency Graph

```json
{
  "waves": [
    { "wave": 1, "tasks": ["1", "2"], "desc": "后端派生函数 + 前端归一（前后端同口径）", "depends_on": [] },
    { "wave": 2, "tasks": ["3"], "desc": "render-config 统一注入", "depends_on": [1] },
    { "wave": 3, "tasks": ["4"], "desc": "宿主取值与透传", "depends_on": [2] },
    { "wave": 4, "tasks": ["5"], "desc": "回归与浏览器实测", "depends_on": [3, 4] }
  ]
}
```

## Tasks

- [x] 1. 后端派生函数
  - [x] 1.1 `standard_unification_service.derive_applicable_standards(standard)` →
        `[f"{entity}_{scope}", entity, scope]`（去重保序、非法值复用
        `_normalize_standard` 按 `DEFAULT_STANDARD` 补齐、`stage` 不入列表、永不返回空）
  - [x] 1.2 `backend/tests/test_applicable_standards_derive.py`（20 测试）：
        `SHARED_SAMPLES` 与前端 spec 逐条对应 + Property 1/2 + 大小写 + stage 排除
        _Requirements: R1.3, R1.4_

- [x] 2. 前端归一函数认 v2 对象
  - [x] 2.1 `normalizeApplicableStandards` 增加 `{entity_type, scope}` 分支
        （含 camelCase 键与大写值归一），与后端同口径
  - [x] 2.2 `composables/__tests__/normalizeApplicableStandards.spec.ts`（29 测试）：
        Property 3（同口径样本表）+ Property 4（19 条既有形态零回归样本）
        _Requirements: R2.1~R2.5_

- [x] 3. render-config 统一注入
  - [x] 3.1 `wp_render_config.get_render_config`：Step 9.5 注入 —— 响应顶层
        `applicable_standards` + 逐 sheet `html_data.project_context.applicable_standards`；
        整体 try/except 只记 warning，不阻断渲染
  - [x] 3.2 注入抽为纯函数 `wp_render_config_helpers.inject_applicable_standards`
        （**覆盖式**，不是 setdefault —— I1~I6 残留的原始 v2 对象必须被替换）；
        `backend/tests/test_render_config_applicable_standards.py`（6 测试：
        Property 5 + 「不得残留 dict」+ 逐 sheet 独立列表 + 主流程接线源码断言）
        _Requirements: R1.1, R1.2, R1.5, R4.3_

- [x] 4. 宿主取值与透传
  - [x] 4.1 `GtD3PrepaidAccounts`：`applicableStandards` 改 `ref<string[]>`，取值经
        `normalizeApplicableStandards`；**并修掉一个隐藏 bug** —— 原赋值写在
        `responses_snapshot` 早返回**之后**，有快照的项目根本走不到
  - [x] 4.2 新建共享 helper `composables/hostApplicableStandards.ts`
        （`project_context` > `projectContext` > 顶层 snake/camel > 显式 fallback，
        统一经归一函数）；清掉 **11 个宿主**里 `runtime?.applicableStandards?.value`
        的死 fallback（`WorkpaperRuntimeContext` 无此字段，vue-tsc 亦报错）：
        G13/G14/H10/I2 整段改用 helper，G4/G5/G6/G8/G9/G11/G12 删死 fallback 行 +
        收尾由「只认数组」改为 `normalizeApplicableStandards(raw)`
  - [x] 4.3 守卫 `__tests__/hostApplicableStandards.spec.ts`（8 测试）：helper 取值优先级
        + v2 对象/逗号串兼容 + **扫全部 `Gt*.vue` 断言不得再读 `runtime?.applicableStandards`**
        _Requirements: R3.1, R3.2, R3.3_

- [x] 5. 回归与浏览器实测
  - [x] 5.1 后端 26 绿（派生 20 + 注入 6）；前端 37 绿（归一 29 + 宿主 8）；
        14 个改动前端文件 Vite transform 200；CI job `applicable-standards-wiring`
  - [x] 5.2 浏览器实测（国企项目 `2aa00f57`）：
        - render-config 顶层与逐 sheet 均下发 `["soe_standalone","soe","standalone"]`
        - **D3 国企版正常渲染 2 张表**（修复前显示「当前项目不适用…」）
        - **D3 上市版显示「当前项目不适用上市公司附注披露格式」** ← 门控真正生效
  - [x] 5.3 回归抽样：F2 国企披露 Tab 正常渲染 3 张表（`f2-disclosure-soe`，无「不适用」）
        _Requirements: R5.1, R5.2_

## Notes

- **不改**任何 `isXDisclosureApplicable` / `resolveXCurrentStandard` 判定逻辑 ——
  本 spec 只补数据供给
- **门控从「恒空 → 有值」的行为变化**（预期）：国企项目上的上市披露 Tab 由「可编辑」
  变为「显示不适用」。这正是要的效果（否则数据会写进错误章节）。实测已确认
  D3/F2 国企侧不受影响
- **预存在失败**：`useF2DisclosureSoe.spec.ts` 有 1 条失败（合并原材料 220 vs 300），
  该断言与适用准则无关，且 `useF2DisclosureSoe.ts` 已被前序 F2 spec 修改而测试未同步 —— 
  非本 spec 引入
- **已另立并完成** → `.kiro/specs/applicable-standards-runtime-and-sync-guard/`：
  给 `WorkpaperRuntimeContext` 补 `applicableStandards` 字段让 scaffold 统一 provide
  （21 个宿主取值链收敛到 `useHostApplicableStandards`）；
  `sync_from_workpaper` 跨主体类型守卫（entity 冲突 → 409 `STANDARD_MISMATCH`）。
  该 spec 另修掉本 spec 守卫的一个漏洞：I3/I5/I6 用 `(runtime as any)?.applicableStandards`
  绕过了「不得读 runtime」正则，死 fallback 当时并未清干净
