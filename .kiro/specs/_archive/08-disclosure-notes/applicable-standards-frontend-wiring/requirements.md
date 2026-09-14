# Requirements Document

## Introduction

平台级缺陷：**披露 Tab 的「适用准则」门控在前端恒为空**，导致两类相反的错误同时存在 ——
一部分循环（D3）对**所有**项目显示「当前项目不适用上市公司附注披露格式」而用户不可达；
另一部分循环（约 90 个已接同步链路的 Tab）门控恒开，允许在国企项目上编辑上市披露 Tab，
而 `sync_from_workpaper` 的定位键只有 `(project_id, year, note_section)`、`current_standard`
不参与匹配 → **数据会写进错误章节**（国企项目的「五、38」是另一套压缩编号）。

链路现状（2026-07-30 实证）：

| 环节 | 现状 | 后果 |
|------|------|------|
| DB | `projects.applicable_standard_v2 = {entity_type, scope, stage}`（8 个在册项目全 `soe/standalone/normal`） | 权威源存在且已回填 |
| 后端服务 | `StandardUnificationService.get_standard()` 永不返回 None | 读取入口已就绪 |
| render-config | 各 render 策略**各写一份** `_load_project_context`（60+ 份）：多数根本不下发；I1~I6 下发的是**原始 v2 对象** | 前端拿不到 / 拿到不认识的形状 |
| 前端归一 | `normalizeApplicableStandards`（`useF2FormData.ts`）只认 `type/code/value`，不认 `{entity_type, scope}` | 即便后端下发也返回 `[]` |
| 前端宿主 | `GtD3PrepaidAccounts` 从 `htmlData.project_context.applicable_standards` 取 → 恒 `''` | 门控恒关 → 用户不可达 |

## Requirements

### Requirement 1: render-config 统一下发适用准则

**User Story:** 作为审计助理，我打开任意底稿时，前端都应该知道本项目适用哪套准则，
这样披露 Tab 才能正确显示对应版本。

#### Acceptance Criteria

1. WHEN 调用 `GET /api/workpapers/{wp_id}/render-config` THEN 响应顶层含
   `applicable_standards: string[]`
2. WHEN 响应含 sheets THEN 每个 sheet 的 `html_data.project_context.applicable_standards`
   为同一个字符串列表（**统一形态**，不再出现原始 v2 对象）
3. WHEN 项目 `applicable_standard_v2 = {entity_type: "soe", scope: "standalone"}` THEN
   下发 `["soe_standalone", "soe", "standalone"]`（组合值 + 两个维度值，
   兼容按子串匹配与按精确值匹配两类既有判定）
4. WHEN 项目 v2 字段缺失 THEN 走 `StandardUnificationService` 的推断回退，仍下发非空列表
5. WHEN 注入失败（DB 异常等）THEN 不阻断 render-config 返回（降级为不注入）

### Requirement 2: 前端归一函数认识 v2 对象

**User Story:** 作为开发者，我不希望后端换个字段形状就让门控静默失效。

#### Acceptance Criteria

1. WHEN `normalizeApplicableStandards({entity_type: "soe", scope: "standalone"})` THEN
   返回 `["soe_standalone", "soe", "standalone"]`
2. WHEN 传入 `{"entity_type": "listed", "scope": "consolidated", "stage": "ipo"}` THEN
   返回含 `listed_consolidated` / `listed` / `consolidated`（`stage` 不入列表）
3. WHEN 传入 JSON 字符串形式的 v2 对象 THEN 与对象形式结果一致
4. WHEN 传入既有形态（字符串 / 数组 / `{type}` / `{code}` / `{standards: []}`）THEN
   结果与修改前**完全一致**（零回归）
5. WHEN 前后端各自派生 THEN 两侧口径一致（同一份维度组合规则）

### Requirement 3: 宿主组件正确接收并透传

**User Story:** 作为审计助理，D3 预收款项的两个披露 Tab 必须能打开。

#### Acceptance Criteria

1. WHEN 打开 D3 底稿披露 Tab THEN 不再显示「当前项目不适用…」（国企项目显示国企版、
   上市项目显示上市版）
2. WHEN 宿主组件读到 `html_data.project_context.applicable_standards` THEN 经
   `normalizeApplicableStandards` 归一为 `string[]` 后透传给子组件
3. WHEN `applicable_standards` 缺失 THEN 保持既有「全部适用」的宽松回退
   （不得因缺字段把用户挡在外面）

### Requirement 4: 守卫

**User Story:** 作为质量控制复核合伙人，这条链路必须有自动化守卫，防止再次静默失效。

#### Acceptance Criteria

1. WHEN 运行后端测试 THEN 覆盖派生函数的四类输入（完整 v2 / 缺字段 / 非法值 / None）
   与 render-config 注入（顶层 + 每 sheet）
2. WHEN 运行前端测试 THEN 覆盖 R2 的全部 Acceptance Criteria，含零回归样本
3. WHEN 有 render 策略把原始 v2 对象塞进 `project_context.applicable_standards` THEN
   守卫能发现（统一注入应覆盖之）

### Requirement 5: 浏览器实测

**User Story:** 作为业务合伙人，我要确认门控在真实项目里按预期生效，而不只是测试绿。

#### Acceptance Criteria

1. WHEN 在真实国企项目打开 D3 披露 Tab THEN 国企版正常渲染、上市版显示不适用
2. WHEN 检查 render-config 响应 THEN `applicable_standards` 为预期字符串列表

## Glossary

| 术语 | 含义 |
|------|------|
| v2 对象 | `projects.applicable_standard_v2 = {entity_type, scope, stage}` |
| 组合值 | `{entity_type}_{scope}`，如 `soe_standalone`（前端 `resolveXCurrentStandard` 的判定基准） |
| 门控 | 披露 Tab 的 `isXDisclosureApplicable`，决定显示表格还是「当前项目不适用」空态 |
| 宿主组件 | `Gt{Cycle}*.vue`，从 render-config 的 `html_data` 取值并透传给各 Tab 子组件 |
