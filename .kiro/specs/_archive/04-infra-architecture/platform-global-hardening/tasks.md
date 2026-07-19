# Implementation Plan · 全局工程加固与机制沉淀（platform-global-hardening）

## Overview

本任务清单把 `design.md` 的 **M0→M3 渐进迁移策略**转化为可执行编码步骤，严格遵循「非破坏、增量、fail-open、单一真源」原则。任务按里程碑（M0 地基/止血 → M1 Shell 与迁移 → M2 收敛翻转 → M1 P1 组件与 SDK → M3 P2 降本）组织。

- **P0 止血（Req 1/2/3）= 关键路径**，位于 Wave 0–6，必做。
- **P1 沉淀（Req 4/5）= Wp_Kit + AuditData SDK**，位于 Wave 7–10，必做。
- **P2 降本（Req 6/7/8/9）= 巨型文件拆分/权限矩阵/溯源抽屉/AI 工厂**，位于 Wave 11–13，全部子任务标 `*`（optional，排期靠后但仍需完成）。
- 每条 Correctness Property（P1–P12）都有对应的 PBT 任务：前端用 **fast-check `{ numRuns: 100 }`**，后端 Python 守卫用 **hypothesis `@settings(max_examples=100)`**。
- 前端唯一路径 `audit-platform/frontend/`；CI 守卫脚本 `backend/scripts/check/`；codemod `backend/scripts/refactor/`。

### 工程铁律（贯穿所有任务）

- 新 CI 守卫脚本：**零依赖 + 正则匹配 + `--strict`/`--check` 双 flag + 顶部 `sys.stdout.reconfigure(encoding='utf-8')` + 对不可读文件 fail-open**；先以 **REPORT 模式**挂 `.github/workflows/governance-checks.yml`，全量迁移完成后翻 strict。
- codemod / 任何 Vue 文件改写：**只用结构化文本替换 + 显式 UTF-8 读写，禁止 PowerShell `Set-Content`/`-replace`**（会把中文写成 U+FFFD → 铁律）。
- Vite transform 冒烟 + render 冒烟是**反假绿硬门槛**：任何底稿改动/迁移后必须通过冒烟才算完成，不以单测绿为准。
- ~200 个存量 tab **按循环分批（D→E→F→…）**迁移，每批合入前必须 Playwright render 冒烟 0 console error。

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2", "1.3", "2.1", "2.3", "2.5", "2.7"] },
    { "id": 1, "tasks": ["1.4", "1.5", "2.2", "2.4", "2.6"] },
    { "id": 2, "tasks": ["2.8", "3.1", "3.4", "3.7"] },
    { "id": 3, "tasks": ["3.2", "3.5", "3.6"] },
    { "id": 4, "tasks": ["3.3"] },
    { "id": 5, "tasks": ["4.1", "4.2", "4.3", "4.4"] },
    { "id": 6, "tasks": ["5.1", "5.2", "5.3"] },
    { "id": 7, "tasks": ["6.1", "6.2", "6.3", "6.4", "6.5", "6.6"] },
    { "id": 8, "tasks": ["6.7", "6.8", "6.9"] },
    { "id": 9, "tasks": ["7.1", "7.2", "7.3", "7.4", "7.5"] },
    { "id": 10, "tasks": ["7.6", "7.7", "7.8", "7.9"] },
    { "id": 11, "tasks": ["8.1", "8.2", "8.4", "9.1", "9.3", "10.1", "11.1"] },
    { "id": 12, "tasks": ["8.3", "8.5", "9.2", "9.4", "10.2", "10.3", "11.2", "11.3", "11.4"] },
    { "id": 13, "tasks": ["11.5"] }
  ]
}
```

## Tasks

### M0 · 地基与止血（Wave 0–1，P0，关键路径）

- [x] 1. DisplayPrefs 收敛到单一真源
  - [x] 1.1 新增类型化 InjectionKey `displayPrefsKey.ts`
    - 在 `audit-platform/frontend/src/components/workpaper/composables/displayPrefsKey.ts` 定义 `DisplayPrefs_Key: InjectionKey<DisplayPrefsContract>` 与 `DisplayPrefsContract = ReturnType<typeof useDisplayPrefsStore>`
    - 不改 `stores/displayPrefs.ts` 的持久化结构（localStorage key `gt_display_prefs` 不变）
    - _Requirements: 1.1, 1.2, 1.3_

  - [x] 1.2 主入口 provide 值替换为真 store（M0 最高 ROI 止血点）
    - 将 `GtD2AccountsReceivable.vue:343` / `GtD1NotesReceivable.vue:743` / `GtD3PrepaidAccounts.vue:293` 等所有底稿主入口的 `provide('displayPrefs', {硬编码闭包})` 的**值**替换为 `useDisplayPrefsStore()` 实例（**字符串 key 暂留**以兼容未迁移 tab）
    - 此步不依赖 1.1，独立完成即可让所有存量 tab 立即获得正确单位/字号/负数行为
    - 改后对每个改动主入口跑 render 冒烟确认无回退
    - _Requirements: 1.2, 1.4_

  - [x] 1.3 新增导出单位口径纯函数 `applyExportUnit`
    - 在导出工具模块新增 `applyExportUnit(rawYuan: number, divisor: number): number`（= rawYuan / divisor），表头标注 `（单位：{unitSuffix}）`
    - 各底稿导出路径读取 `displayPrefs.unitDivisor` / `displayPrefs.unitSuffix` 复用此纯函数，杜绝「屏幕万元、导出元」
    - _Requirements: 1.6_

  - [x]* 1.4 编写属性测试 P5 · 导出单位换算可还原
    - **Property 5: 导出单位换算可还原（度量关系）**
    - **Validates: Requirements 1.6**
    - fast-check `{ numRuns: 100 }`；断言 `applyExportUnit(rawYuan, divisor) * divisor` 在浮点误差内等于 rawYuan（divisor ∈ {1, 1000, 10000}），且表头单位后缀与 divisor 对应（元/千元/万元）
    - 注释：`Feature: platform-global-hardening, Property 5`

  - [x] 1.5 CSS 变量 `--wp-font-size` 传播
    - 底稿根容器绑定 `:style="{ '--wp-font-size': displayPrefs.fontConfig.tableFont }"`
    - 底稿内表格样式统一改为 `font-size: var(--wp-font-size, 13px)`，替换散落的 `font-size: 13px` 字面量
    - 仅用结构化编辑工具改写，禁止 PowerShell
    - _Requirements: 1.5_

- [x] 2. 工程纪律 CI 守卫（报告模式）
  - [x] 2.1 新增 `check_utf8_integrity.py`
    - `backend/scripts/check/check_utf8_integrity.py`：`raw = path.read_bytes(); count = raw.count(b'\xef\xbf\xbd')`，`count > 0` 记违规并列出文件
    - 零依赖 + `--strict`/`--check` flag + 顶部 `sys.stdout.reconfigure(encoding='utf-8')` + 不可读文件 `except (UnicodeDecodeError, OSError)` fail-open
    - `.vue` 命中 U+FFFD → 报告额外标注「疑似 shell 文本替换破坏，禁用 PowerShell Set-Content/-replace」
    - _Requirements: 3.1, 3.7_

  - [x]* 2.2 编写属性测试 P4 · U+FFFD 完整性检查
    - **Property 4: U+FFFD 完整性检查当且仅当含替换字符时失败**
    - **Validates: Requirements 3.1, 3.7**
    - hypothesis `@settings(max_examples=100)`；对任意字节内容，判定失败 iff `raw.count(b'\xef\xbf\xbd') > 0`；`.vue` 命中时报告含「疑似 shell 文本替换破坏」标注
    - 注释：`Feature: platform-global-hardening, Property 4`

  - [x] 2.3 新增 `check_displayprefs_contract.py`
    - `backend/scripts/check/check_displayprefs_contract.py`：参照 `check_wp_ref_contract.py` 的零依赖/正则/`--strict` 结构
    - 拦截反模式 A：`inject(...'displayPrefs'...{...toLocaleString/fmtAmount 本地实现...})`；反模式 B：底稿 `<style>`/模板内 `font-size: 13px`（及 11/12/14px）硬编码字面量
    - 放行 `inject(DisplayPrefs_Key, ...)` 与 `var(--wp-font-size)`；白名单 `displayPrefs.ts`/`formatters.ts` 的 `FONT_SIZES` 定义处
    - fail-open + utf-8 header
    - _Requirements: 1.3, 1.7_

  - [x]* 2.4 编写属性测试 P2 · DisplayPrefs 守卫检出/放行
    - **Property 2: DisplayPrefs 守卫检出反模式、放行合规写法**
    - **Validates: Requirements 1.3, 1.7**
    - hypothesis `@settings(max_examples=100)`；对任意源码片段，`--strict` 判定违规（退出码 1）iff 含反模式 A 或 B；合规写法放行
    - 注释：`Feature: platform-global-hardening, Property 2`

  - [x] 2.5 新增 `vite_transform_smoke.mjs`（Vite 全树冒烟）
    - `backend/scripts/check/vite_transform_smoke.mjs`：Node 脚本以 vite middleware mode 启动 → 对底稿源码树每个 `.vue`/`.ts` 调 `transformRequest(url)` 遍历，收集抛错文件
    - 任一文件 transform 失败（等价 HTTP 500）→ 退出码非 0 并列出文件路径
    - _Requirements: 3.2_

  - [x] 2.6 确认既有 ref/import 守卫为阻断态
    - 确认 `check_wp_ref_contract.py --strict` 与 `fix_wp_composables_import_depth.py --check` 已在 `governance-checks.yml` job `wp-ref-contract-check` 以 blocking 挂载
    - 补测试用例验证二者对新增违规能阻断
    - _Requirements: 3.3, 3.4_

  - [x] 2.7 render 冒烟测试集骨架（Playwright，数据驱动）
    - 新建 `audit-platform/frontend/tests/render-smoke/`：从 `wp_code_overrides.json` + registry 生成 wp_code 清单，参数化用例
    - 每 wp_code：登录（admin/admin123）→ 导航底稿 → 断言 `page.on('console','error')` 计数为 0 且关键区块选择器（`.gt-wp-root` 等）存在；失败报告 wp_code + 错误摘要
    - _Requirements: 3.5, 3.6_

  - [x] 2.8 挂载全部新守卫到 `governance-checks.yml`（REPORT 模式）
    - 新增 job：`displayprefs-contract-check` / `utf8-integrity-check` / `vite-transform-smoke` / `coverage-drift-check` / `render-smoke`（先报告模式，退出码恒 0，复用 `GOVERNANCE_ENFORCE_DATE` 灰度）
    - `check_utf8_integrity.py` 同时挂 `.git-hooks/pre-commit`
    - _Requirements: 3.1, 3.2, 3.5, 3.6, 3.7_

- [x] 3. Checkpoint · M0 地基
  - Ensure all tests pass, ask the user if questions arise. 确认止血 provide 已生效、四个新守卫报告模式无崩溃。

### M1 · Shell 与 codemod（Wave 2–5，P0，关键路径）

- [x] 4. Workpaper_Shell 骨架与 Coverage_Ledger
  - [x] 3.1 实现 `useWorkpaperScaffold` composable
    - `audit-platform/frontend/src/components/workpaper/composables/useWorkpaperScaffold.ts`：一次性 provide displayPrefs（`DisplayPrefs_Key`）/agingConfig（`useAgingConfig`）/版本链工具栏/复核 provide/AI provide/jumpToSection/reload
    - `import.meta.env.DEV` 下校验 `wpCode`/`wpId`/`projectId`/year，缺失时 `console.error('[GtWorkpaperShell] 缺少必要上下文：{名称}')`，生产不 throw
    - 返回 `{ displayPrefs, agingConfig, versionToolbar, fontStyle }` 供模板绑定
    - _Requirements: 2.1, 2.6_

  - [x] 3.2 实现 `GtWorkpaperShell.vue` 套壳组件
    - `audit-platform/frontend/src/components/workpaper/GtWorkpaperShell.vue`：props `wpCode/wpId/projectId/year?/agingSubject?/readonly?`；slots `#toolbar/#objective/#guidance/#default`；emits `jump-to-section/navigate-sheet/save/reload`
    - `<script setup>` 内部调用 `useWorkpaperScaffold`（与 composable 共享实现，保证两条路径接线一致）；根 `<div class="gt-wp-root">` 绑 `--wp-font-size`
    - `#toolbar` 默认渲染版本链工具栏 + 导入导出 dropdown 占位
    - _Requirements: 2.1, 2.2_

  - [x] 3.3 D2 试点套壳并 render 冒烟验证
    - 将 D2 主入口改为套 `GtWorkpaperShell`（或调用 `useWorkpaperScaffold`），跑 render 冒烟子集断言等价（0 console error + 审定表/明细表容器存在）
    - _Requirements: 2.2_

  - [x] 3.4 Coverage_Ledger 数据模型 + 生成器
    - 新增 `audit-platform/frontend/src/components/workpaper/coverage-ledger.json`（结构：`capabilities` / `entries[wpCode].shellWrapped` / `.detected` / `.exemption`）
    - 生成器脚本静态扫描主入口，正向检出各能力接线状态写入 `detected`
    - _Requirements: 2.3_

  - [x] 3.5 实现 `check_coverage_ledger.py`（CI_Drift_Guard，fail-open）
    - `backend/scripts/check/check_coverage_ledger.py`：枚举全部 wp_code；`shellWrapped==true` → auto-covered 放行；已登记 `exemption` → 放行；正向检出「应接却未接」且无豁免 → 阻断（fail-closed）；无法判定接线状态 → 放行（fail-open）
    - 零依赖 + `--strict`/`--check` + utf-8 header + 异常文件 fail-open
    - 输出漂移报告 `{wp_code}: 应接 {capability} 未接线`
    - _Requirements: 2.4, 2.5, 2.7, 2.8_

  - [x]* 3.6 编写属性测试 P3 · CI_Drift_Guard 仅正向检出时阻断
    - **Property 3: CI_Drift_Guard 仅在正向检出时阻断、在不确定时放行**
    - **Validates: Requirements 2.4, 2.5, 2.7, 2.8**
    - hypothesis `@settings(max_examples=100)`；对任意接线状态组合（shellWrapped/detected/exemption/可解析）验证 fail-open 与 fail-closed 判定正确
    - 注释：`Feature: platform-global-hardening, Property 3`

  - [x] 3.7 实现 codemod `migrate_displayprefs_inject.py`
    - `backend/scripts/refactor/migrate_displayprefs_inject.py`：把 tab 的 `inject<{fmtAmount}>('displayPrefs', {硬编码})` 改写为 `inject(DisplayPrefs_Key, null) ?? useDisplayPrefsStore()`，`font-size: 13px` 改为 `var(--wp-font-size, 13px)`
    - **仅结构化文本替换 + 显式 UTF-8 读写，禁止 PowerShell**；支持 `--check`（预演）/`--apply`（写回），沿用 `fix_wp_composables_import_depth.py` 范式
    - _Requirements: 1.3, 1.5_

- [x] 5. 分批迁移存量底稿 tab（每批 render 冒烟验证）
  - [x] 4.1 迁移批次 D/E/F 循环 tab
    - 对 D/E/F 循环 tab 跑 codemod `--apply`，Playwright render 冒烟子集实测 0 console error 才合入
    - _Requirements: 1.3, 1.5_

  - [x] 4.2 迁移批次 G/H/I 循环 tab
    - codemod `--apply` + 该批 render 冒烟实测
    - _Requirements: 1.3, 1.5_

  - [x] 4.3 迁移批次 J/K/L 循环 tab
    - codemod `--apply` + 该批 render 冒烟实测
    - _Requirements: 1.3, 1.5_

  - [x] 4.4 迁移批次 M/N/S 循环 tab
    - codemod `--apply` + 该批 render 冒烟实测
    - _Requirements: 1.3, 1.5_

- [x] 6. Checkpoint · M1 迁移
  - Ensure all tests pass, ask the user if questions arise. 确认全部 tab 已迁移到 `DisplayPrefs_Key`，各批 render 冒烟 0 error。

### M2 · 收敛与翻转（Wave 6，P0，关键路径）

- [x] 7. 收敛旧路径并翻转守卫为 strict
  - [x] 5.1 Coverage_Ledger 全量登记
    - 运行生成器扫描全部 wp_code + 手工补齐非套壳底稿的 `exemption` 原因
    - _Requirements: 2.3, 2.5_

  - [x] 5.2 移除主入口字符串 `provide('displayPrefs')`
    - 全部 tab 迁移完成后，移除主入口的字符串 key provide，只留 `DisplayPrefs_Key`；仅结构化编辑
    - _Requirements: 1.2, 1.3_

  - [x] 5.3 守卫翻转 `--strict` / blocking
    - `displayprefs-contract-check` / `coverage-drift-check` 加 `--strict`；`render-smoke` 从 `continue-on-error` 转 blocking（编辑 `governance-checks.yml`）
    - _Requirements: 1.7, 2.4, 3.5, 3.6_

- [x] 8. Checkpoint · M2 收敛
  - Ensure all tests pass, ask the user if questions arise. 确认字符串 provide 已清除、守卫 strict 全绿。

### M1 · P1 沉淀 · Wp_Kit 组件库（Wave 7–8，Req 4）

- [x] 9. Wp_Kit 组件库与 ESLint 规则
  - [x] 6.1 实现 `<WpSection>` 与 `<WpFormulaCell>`
    - `components/workpaper/kit/WpSection.vue`：标题行 + 审计目标 el-alert + 编制提示 details + 右侧 AI/复核按钮（slots `#actions`/`#default`）
    - `WpFormulaCell.vue`：虚线下划线 + `cursor:help` + 来源 tooltip（props `value/formula/source`）
    - _Requirements: 4.1, 4.2_

  - [x] 6.2 实现 `<WpAmountCell>`
    - `components/workpaper/kit/WpAmountCell.vue`：内部 `inject(DisplayPrefs_Key)`，金额格式统一走 store（单位/小数/负数红字）；props `value/priorValue?/rawUnit?`
    - _Requirements: 4.2, 4.7_

  - [x] 6.3 实现 `<WpOpinionCard>`
    - `WpOpinionCard.vue`：内置 `autosize {minRows:5}` textarea + AI 辅助按钮 + 复核按钮；props `modelValue/section/wpCode`
    - _Requirements: 4.3_

  - [x] 6.4 实现 `<WpImportExport>`
    - `WpImportExport.vue`：「导入导出▾」el-dropdown（导出模板/导出数据/导入数据），复用 `useXImportExport` 范式；props `wpId/endpoints`
    - _Requirements: 4.4_

  - [x] 6.5 实现 `<WpDynamicTable>`
    - `WpDynamicTable.vue`：`var(--wp-font-size)` 字体、紧凑密度、auto-calc-col 计算列、合计行、动态增删行、账龄动态列；金额单元格反映 DisplayPrefs_Store；props `columns/rows/agingBands?/readonly?`
    - _Requirements: 4.5, 4.7_

  - [x] 6.6 新增 ESLint 规则 `no-adhoc-wp-structure`
    - `audit-platform/frontend/eslint-rules/`：检出可用 Wp_Kit 组件的等价手写结构（autosize textarea 结论区 / 含「导入/导出」文案的 el-dropdown / 直接 `toLocaleString` 渲染金额）时报错；先 `warn` 级
    - _Requirements: 4.6_

  - [x]* 6.7 编写属性测试 P1 · 金额格式化与单一真源一致
    - **Property 1: 金额格式化输出与单一真源一致**
    - **Validates: Requirements 1.4, 4.7**
    - fast-check `{ numRuns: 100 }`；对任意金额值（含 null/0/负/超大）与任意显示设置组合，`<WpAmountCell>`/`<WpDynamicTable>` 渲染文本等于 `useDisplayPrefsStore().fmtAmount(v)` 同设置输出
    - 注释：`Feature: platform-global-hardening, Property 1`

  - [x]* 6.8 Wp_Kit 组件挂载/snapshot 单元测试
    - Vitest 对 6.1–6.5 各组件挂载断言结构与关键交互
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_

  - [x]* 6.9 ESLint 规则 RuleTester 例集
    - `no-adhoc-wp-structure` 的 valid/invalid 例集
    - _Requirements: 4.6_

- [x] 10. Checkpoint · Wp_Kit
  - Ensure all tests pass, ask the user if questions arise.

### M1 · P1 沉淀 · useAuditData SDK（Wave 9–10，Req 5）

- [x] 11. 统一取数 SDK
  - [x] 7.1 实现 `useAuditData` 骨架
    - `audit-platform/frontend/src/composables/useAuditData.ts`：签名 `useAuditData(projectId, year?)`，语义方法 `getTbAmount/getAging/getLedgerEntries/getPrevYear` + `loading`/`error`
    - year 未传时从 projectContext 解析，调用方无需手传（杜绝漏 year → 422）
    - _Requirements: 5.1, 5.2_

  - [x] 7.2 实现字段归一化层
    - 集中一处的别名归一（`debit_amount ?? debitAmount ?? debit` 范式），返回稳定语义字段，屏蔽后端字段名差异
    - _Requirements: 5.3_

  - [x] 7.3 实现三口径 `resolveKoujing`（按数据域）
    - 资产/负债/权益余额遵循方向铁律（v1 借正贷负 / v2 正数），损益类返回 `pl_occurrence` 发生额；口径按数据域返回，不强制统一
    - _Requirements: 5.4_

  - [x] 7.4 缓存复用与错误降级
    - `getLedgerEntries` 委托 `useLedgerCache().getEntries` 命中缓存不重复拉取；所有方法 try/catch，失败返回降级值（0/null）+ 置 `error`，绝不抛未捕获异常导致白屏；请求带 `{_silent:true}`
    - _Requirements: 5.5, 5.6_

  - [x] 7.5 约束底稿仅调语义方法
    - 底稿改为仅调 AuditData_SDK 语义方法；配套 ESLint/守卫检测底稿内直接 `api.get('/...ledger...')` 裸取数 URL
    - _Requirements: 5.7_

  - [x]* 7.6 编写属性测试 P6 · year 自动解析后请求永不缺失 year
    - **Property 6: year 自动解析后底层请求永不缺失 year**
    - **Validates: Requirements 5.2**
    - fast-check `{ numRuns: 100 }`；对任意有效年度与任意调用方式，底层请求 year 恒为有效整数，不出现 undefined/缺失
    - 注释：`Feature: platform-global-hardening, Property 6`

  - [x]* 7.7 编写属性测试 P7 · 字段归一化在任意别名组合下稳定
    - **Property 7: 字段归一化在任意别名组合下产出稳定语义字段**
    - **Validates: Requirements 5.3**
    - fast-check `{ numRuns: 100 }`；对任意别名子集组合，归一化产出相同稳定语义值
    - 注释：`Feature: platform-global-hardening, Property 7`

  - [x]* 7.8 编写属性测试 P8 · 取数口径按数据域正确解析
    - **Property 8: 取数口径按数据域正确解析**
    - **Validates: Requirements 5.4**
    - fast-check `{ numRuns: 100 }`；对覆盖资产/负债/权益/损益四域的科目代码，`resolveKoujing` 返回该域约定口径，不强制单一口径
    - 注释：`Feature: platform-global-hardening, Property 8`

  - [x]* 7.9 编写属性测试 P9 · 取数失败返回降级值且不抛异常
    - **Property 9: 取数失败时返回降级值且不抛未捕获异常**
    - **Validates: Requirements 5.6**
    - fast-check `{ numRuns: 100 }`；对任意失败注入模式（reject/空数据/畸形响应），语义方法 resolve 到明确降级结果，不抛未捕获异常
    - 注释：`Feature: platform-global-hardening, Property 9`

- [x] 12. Checkpoint · AuditData SDK
  - Ensure all tests pass, ask the user if questions arise.

### M3 · P2 降本（Wave 11–13，Req 6/7/8/9，全部 optional `*`，排期靠后）

- [x] 13. 巨型文件拆分与 composable 工厂化（Req 6）
  - [x]* 8.1 按域拆分前端巨型文件
    - 拆分 `LedgerPenetration.vue`（3,706 行）、`TrialBalance.vue`（2,683 行），按域边界而非固定行数硬切，对外行为不变
    - _Requirements: 6.1, 6.3_

  - [x]* 8.2 按域拆分后端巨型文件
    - 拆分 `_d1_import_export.py`（2,989 行）、`event_handlers.py`（1,725 行）、`consistency_gate.py`（2,141 行），按域边界拆分，行为不变
    - _Requirements: 6.2, 6.3_

  - [x]* 8.3 CI size guard 行数上限
    - 对上述文件类别设置行数上限，超限使构建失败（挂 `governance-checks.yml`）
    - _Requirements: 6.4_

  - [x]* 8.4 composable 参数化工厂
    - 实现 `createCycleFormData`/`createDualMode`/`createImportExport`/`createDetailTable`，用于收敛现有同构底稿 composable
    - _Requirements: 6.5, 6.6_

  - [x]* 8.5 拆分后回归验证
    - 拆分后跑既有测试 + render 冒烟回归（行为不变）、size guard 例测
    - _Requirements: 6.1, 6.2, 6.3, 6.4_

- [x] 14. 单一权限矩阵（Req 7）
  - [x]* 9.1 实现 `Permission_Matrix.can(action, resource, context)`
    - 单一入口，前后端共享同一权限定义；支持 5 角色项目级权限区分
    - _Requirements: 7.1, 7.2, 7.3, 7.6_

  - [x]* 9.2 前端权限判定走 Permission_Matrix
    - `isReadonly`/按钮禁用/字段可编辑统一调 `can()`，替换分散的 `canEditInProject`/`BUILDER_ROLES` 判断
    - _Requirements: 7.2, 7.3_

  - [x]* 9.3 后端 deps 层安全边界校验
    - 后端 deps 层强制校验权限作为安全边界（复用 `require_wp_edit_permission`），前端判定仅体验优化；不一致时后端生效
    - _Requirements: 7.4, 7.5_

  - [x]* 9.4 编写属性测试 P10 · 权限判定与共享定义一致
    - **Property 10: 权限判定与共享定义一致（覆盖 5 角色）**
    - **Validates: Requirements 7.1, 7.6**
    - fast-check `{ numRuns: 100 }`；对任意 (role∈5角色, action, resource, context) 组合，`can()` 返回与共享定义表一致的确定布尔值
    - 注释：`Feature: platform-global-hardening, Property 10`

- [x] 15. 统一溯源抽屉与刷新链回归（Req 8）
  - [x]* 10.1 实现 `Trace_Drawer` 组件
    - 对任意金额展示「四表→报表→审定→底稿→调整→附注」完整链，每一跳可点击跳转到对应底稿/单元格/调整分录
    - _Requirements: 8.1, 8.2_

  - [x]* 10.2 收敛 ReportTracePanel 与 GtIndexChip 为单一入口
    - 将两套溯源入口收敛为单一 Trace_Drawer 入口
    - _Requirements: 8.3_

  - [x]* 10.3 draft-refresh 5 角色端到端回归（Playwright）
    - 覆盖：合伙人点刷新 → 助理看初稿 → 经理复核 → 附注同步 → EQCR 抽查；Playwright 实测断言链路成功，任一环节下游未标脏/未刷新则失败并报断点
    - 与 Trace_Drawer（10.1/10.2）保持相互独立：Trace_Drawer 不完整不应导致本回归失败（Req 8.7）
    - _Requirements: 8.4, 8.5, 8.6, 8.7_

- [x] 16. AI 上下文工厂（Req 9）
  - [x]* 11.1 实现 `buildAiContext(wpCode, sheet)`
    - 自动附带该底稿的联动数据/审定数/账龄/异常项/源模板方法论；底稿触发 AI 时经此构建上下文随请求提交，不传空 context
    - _Requirements: 9.1, 9.2_

  - [x]* 11.2 实现 AI 三段式流程（生成→预览 diff→确认）
    - 状态机：生成完成先展示 diff 预览，用户确认前不填入；确认后立即填入无额外延迟
    - _Requirements: 9.3, 9.4, 9.6_

  - [x]* 11.3 diff 预览不覆盖已填内容
    - 目标区已有内容时预览 diff 标示差异并要求确认，不直接覆盖
    - _Requirements: 9.5_

  - [x]* 11.4 编写属性测试 P11 · AiContext 工厂产出非空且含约定键集
    - **Property 11: AiContext 工厂产出非空且含约定键集**
    - **Validates: Requirements 9.1, 9.2**
    - fast-check `{ numRuns: 100 }`；对任意 (wpCode, sheet) 与可用数据源，`buildAiContext` 返回非空 context 且含约定键集（该底稿实际具备的项）
    - 注释：`Feature: platform-global-hardening, Property 11`

  - [x]* 11.5 编写属性测试 P12 · AI 确认前不覆盖已有内容
    - **Property 12: AI 确认前不覆盖已有内容**
    - **Validates: Requirements 9.5, 9.6**
    - fast-check `{ numRuns: 100 }`；对任意已有内容 c0 与任意生成输出 g，确认前目标 model 恒等于 c0，仅确认后变为选定内容
    - 注释：`Feature: platform-global-hardening, Property 12`

- [x] 17. Final Checkpoint · P2 降本
  - Ensure all tests pass, ask the user if questions arise. 确认拆分后行为不变、权限矩阵/溯源/AI 工厂属性测试全绿。

## Notes

- 标 `*` 的子任务为 optional：Wp_Kit/SDK 测试子任务与全部 P2（Req 6/7/8/9）子任务；顶层任务（epic/checkpoint）不标 `*`。按平台约定 optional(*) 任务仍需完成，仅排期靠后。
- 每条任务引用具体 requirements 子条款以保证可追溯；每个 Correctness Property 对应独立 PBT 子任务并标注属性号 + 验证的需求条款。
- **反假绿硬门槛**：Vite transform 冒烟（2.5）+ render 冒烟（2.7）是本 spec 交付验收的必过项，不以单测绿为准。
- **迁移安全**：M0 换回旧 provide 值即可回滚；codemod 有 `--check` 预演 + git 单 commit 可 `git revert`；守卫报告模式期间零上线风险，全量迁移后（Wave 6）才翻 strict。
- 所有新 CI 守卫脚本零依赖/正则/双 flag/utf-8 header/fail-open；Vue 文件改写禁用 PowerShell（U+FFFD 铁律）。
