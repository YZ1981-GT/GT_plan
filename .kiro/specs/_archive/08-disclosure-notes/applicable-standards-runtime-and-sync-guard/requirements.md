# Requirements Document

## Introduction

前序 spec `applicable-standards-frontend-wiring` 接通了「DB → render-config → 宿主」的数据供给，
但留下两项另立：

1. **前端**：`WorkpaperRuntimeContext` 里始终没有 `applicableStandards` 字段。上一轮只是把
   11 个宿主里恒 `undefined` 的死 fallback 删掉，取值链仍是各宿主自己从 `props.htmlData`
   逐层摸（22 份实现、5 种写法）。`GtWorkpaperShell` 这条不经 render-config 的路径根本
   拿不到准则。另有 3 个宿主（I3/I5/I6）用 `(runtime as any)?.applicableStandards?.value`
   绕过了守卫正则，死 fallback 仍在。
2. **后端**：`sync_from_workpaper` 的定位键只有 `(project_id, year, note_section)`，
   请求体里的 `current_standard` **完全不参与匹配也不做校验**。国企项目上若打开上市披露
   Tab 编辑，数据会写进上市章节号对应的记录（国企项目的「五、xx」是另一套压缩编号，
   实测项目 `2aa00f57`：`五、19`=应付职工薪酬 / `五、20`=应交税费）→ 静默污染错误章节。
   前端门控已生效，但门控是「客户端可绕过」的，服务端必须自己守住。

## Glossary

| 术语 | 含义 |
|------|------|
| applicable_standards | 项目适用准则字符串列表，如 `["soe_standalone","soe","standalone"]` |
| v2 准则 | `projects.applicable_standard_v2` = `{entity_type, scope, stage}`，DB 权威源 |
| entity 维度 | `entity_type` ∈ `soe` / `listed` / `private`，决定附注模板变体（listed vs soe） |
| scope 维度 | `scope` ∈ `standalone` / `consolidated` |
| runtime context | `WorkpaperRuntimeContext`，由 `useWorkpaperScaffold` provide 的底稿运行时上下文 |
| 宿主 | `Gt{Cycle}*.vue`，一个循环底稿的顶层组件 |
| current_standard | 披露同步请求体字段，前端 `resolveXCurrentStandard` 的结果 |

## Requirements

### Requirement 1: runtime context 提供适用准则

**User Story:** 作为底稿开发者，我希望「当前项目适用哪套准则」像 `projectId` / `year`
一样由 scaffold 统一 provide，这样新增循环时不必再抄一遍取值链，也不会因为宿主漏抄
而让门控恒空。

#### Acceptance Criteria

1.1. WHEN `useWorkpaperScaffold` 被调用 THEN 返回的 `WorkpaperRuntimeContext` SHALL 含
     `applicableStandards: Ref<string[]>` 字段，且该字段被 provide 给后代组件
1.2. WHEN 调用方传入 `applicableStandards`（可为数组 / 字符串 / v2 对象 / Ref）
     THEN scaffold SHALL 经 `normalizeApplicableStandards` 归一后暴露
1.3. WHEN 调用方未传 THEN 该字段 SHALL 为 `[]`（不是 `undefined`），保持各循环
     「空 = 全部适用」的既有宽松回退
1.4. WHEN 祖先已 provide runtime context THEN 嵌套 scaffold SHALL 复用祖先实例
     （含其 `applicableStandards`），不产生第二份

### Requirement 2: 两条渲染路径都注入准则

**User Story:** 作为审计助理，无论底稿走 HTML 渲染器还是套壳 Shell，披露 Tab 的
适用性判定都要一致，不能一条路径能用、另一条恒空。

#### Acceptance Criteria

2.1. WHEN `GtWpRenderer` 初始化 scaffold THEN SHALL 传入 render-config 响应顶层的
     `applicable_standards`（后端 Step 9.5 统一注入的字段）
2.2. WHEN `GtWorkpaperShell` 被使用 THEN SHALL 暴露 `applicableStandards` prop 并透传给 scaffold
2.3. WHEN render-config 尚未加载完成 THEN 该字段 SHALL 为 `[]` 且随 render-config 到达
     自动更新（响应式，不是一次性快照）

### Requirement 3: 宿主取值收敛到单一入口

**User Story:** 作为维护者，我希望宿主取准则只有一种写法，便于守卫，也便于未来
改数据来源时一处生效。

#### Acceptance Criteria

3.1. WHEN 宿主需要适用准则 THEN SHALL 调用共享 composable `useHostApplicableStandards`
     （setup 作用域内 inject runtime，返回 `ComputedRef<string[]>`）
3.2. 取值优先级 SHALL 为：显式来源（prop / 自有 projectContext）> `props.htmlData`
     （`project_context` > `projectContext` > 顶层 snake/camel）> runtime context > `[]`
3.3. WHEN 任一来源是 v2 对象 / 逗号串 / JSON 串 THEN SHALL 经归一函数处理
3.4. 宿主源码 SHALL NOT 出现 `(runtime as any)?.applicableStandards` 这类绕过类型系统的
     直接读取（必须经 composable）

### Requirement 4: 服务端拒绝跨主体类型的披露同步

**User Story:** 作为质量控制复核合伙人，我要求国企项目的附注里绝不能出现上市版章节
写入的数据 —— 即使前端门控被绕过或旧版本前端仍在运行。

#### Acceptance Criteria

4.1. WHEN 披露同步请求的 `current_standard` 的 entity 维度与项目 v2 准则的
     `entity_type` 不一致 THEN 系统 SHALL 拒绝写入并返回 409，detail 含
     `code=STANDARD_MISMATCH` / 项目准则 / 请求准则 / 允许值列表
4.2. WHEN `current_standard` 命中项目派生的 `applicable_standards` 任一值
     THEN 系统 SHALL 放行
4.3. WHEN `current_standard` 的 entity 维度合法且与项目一致、但 scope 维度不同
     （如 `soe_consolidated` vs `soe_standalone`）THEN 系统 SHALL 放行并记 warning
     （合并报表口径另有流程，此处不误杀）
4.4. WHEN 项目查不到 / 无任何准则字段 / DB 异常 THEN 系统 SHALL fail-open 放行
     并记 warning（绝不因守卫本身让存量同步全断）
4.5. WHEN `current_standard` 是既有非准则字面量（如 `general` / `default`）
     THEN 系统 SHALL 放行（零回归；只拦真正的跨 entity 冲突）
4.6. 批量同步端点 SHALL 与单章节端点同守卫（守卫落在服务层，任一调用方都覆盖）
4.7. 守卫 SHALL NOT 引入额外 DB 往返（与既有 `audit_year` 查询合并为一次）

### Requirement 5: 守卫与实测

**User Story:** 作为维护者，我要能防住「新增宿主又抄一份取值链」和「守卫被 `as any`
绕过」这两类回归。

#### Acceptance Criteria

5.1. 前端 SHALL 有守卫断言：scaffold 确实 provide 该字段、两条路径都传值、
     全部 `Gt*.vue` 不得出现 `as any` 绕过读取、composable 取值优先级
5.2. 后端 SHALL 有守卫覆盖 R4 全部分支（含 fail-open 与 scope 放行）+ 路由 409 形状
5.3. SHALL 浏览器实测：国企项目上市披露 Tab 显示不适用；直接 POST 上市
     `current_standard` 被 409 拒绝且附注库无新增记录
