# L3 双模式切换器实现笔记（供 reviewer 查阅）

迭代：第 1 次（`review.json` 不存在）。
本步骤范围：仅前端宿主改线（plan 第 1~4 步），即给 `GtL3LongTermLoans.vue` 补齐
HTML↔OnlyOffice 模式切换器，一比一照抄 L1 范式。**未**做红基线重算/manifest 翻转/真 OO/真浏览器
（那是后续独立步骤，plan 第 5~9 步）。

## 改动文件（唯一）

`audit-platform/frontend/src/components/workpaper/GtL3LongTermLoans.vue`

### 1. 模板
- `<template v-else>` 内、sheet 分发链之前插入 `<div v-if="isProcedureSheet" class="l3-procedure-toolbar">`：
  内含 `<el-segmented>`（绑 `procedureDualMode.currentMode/modeOptions/onModeChange`）、
  `<GtEntrySyncCapabilityNotice entry-id="xlsx/gt-l3-long-term-loans" />`、
  `<el-tag v-if="!procedureDualMode.isOoAvailable.value" …>OO不可用</el-tag>`（照抄 L1，保留 BP-7 诚实披露注释）。
- 分发链最前插入 OO 挂载块 `<GtOnlyOfficeSheet v-if="isProcedureSheet && …=== 'onlyoffice'" … :sheet-name="props.sheetName || 'L3A'" …>`。
- 原 `<L3TabIndex v-if="currentSheet === 'L3'">` 的 `v-if` 改为 `v-else-if`（OO 块已占链首 `v-if`）。
- **保留** 原 `<GtAProgramConsole v-else-if="currentSheet === 'L3A'" …>` 作为 HTML 模式分支（未改成 CycleTabProcedure，按任务要求）。
- 分发链顺序：OO(v-if) → L3TabIndex(v-else-if 'L3') → GtAProgramConsole(v-else-if 'L3A' HTML) → L3-1…L3-9/附注(v-else-if) → GtOnlyOfficeSheet(v-else fallback)。

### 2. script
- `import { useCycleHtmlOoDualMode } from './composables/useCycleHtmlOoDualMode'`（顶部 import 区）。
- `import GtEntrySyncCapabilityNotice from './sync/GtEntrySyncCapabilityNotice.vue'`（Shared 区，静态 import，与 L1 一致）。
- `GtOnlyOfficeSheet` L3 原已 `defineAsyncComponent` 导入，保留。
- 紧跟 `currentSheet` computed 之后新增：
  `const isProcedureSheet = computed(() => currentSheet.value === 'L3A')`、
  `const procedureDualMode = useCycleHtmlOoDualMode({ wpId: toRef(props, 'wpId') as any, storagePrefix: 'l3-proc:' })`。
  storagePrefix 用 `'l3-proc:'`（非 l1/l2）。
- `computed` / `toRef` L3 顶部原已 import，无需重复。

### 3. CSS
- 新增 `.l3-procedure-toolbar`（照抄 L1：display flex / gap 8px / align-items center / margin-bottom 8px / flex-wrap wrap）。

## 签名核对（未凭名字猜）
- `useCycleHtmlOoDualMode({ wpId: Ref<string>, storagePrefix: string, reloadAll? })` 返回
  `currentMode` / `isOoAvailable` / `modeOptions` / `onModeChange` 等 —— 与模板用名一致。
- `GtEntrySyncCapabilityNotice` 接 `entryId` prop（kebab `entry-id`） —— 一致。

## 类型/编译自检
本仓库全量 vue-tsc 会 OOM（记忆铁律㉔），用限定范围 tsconfig 只查改动文件及其依赖闭包：
`audit-platform/frontend/tsconfig._l3-dual-mode.json`（本次新建的临时自检配置）。

命令（cwd=audit-platform/frontend）：
```
npx vue-tsc --noEmit -p tsconfig._l3-dual-mode.json
```

结果（`GtL3LongTermLoans.vue` 行）：
- 本次改动引入新错误：**0 个**。
- 残留 2 个**预存**错误（改动前即存在，已用 `git stash` 回滚本文件复跑验证归因）：
  - `(46,37) TS2353 'schema' does not exist in type 'AProgramHtmlData'` —— 原 GtAProgramConsole 的 `:html-data` 内含 schema（原代码，行号因上方插入 22 行从 24→46）。
  - `(143,10) TS2322 'string | undefined' not assignable to 'string'` —— 原 fallback `GtOnlyOfficeSheet` 的 `:sheet-name="props.sheetName"`（原代码，行号从 121→143）。
  - stash 复跑证据：原始文件在 (24,37) 与 (121,10) 报同样两错。

### 变异证明（确认检查真生效）
把 `storagePrefix: 'l3-proc:'` 临时改为 `storagePrefix: 12345` 后复跑，
新增报错 `GtL3LongTermLoans.vue(254,3) TS2322 Type 'number' is not assignable to type 'string'`
—— 命中 `useCycleHtmlOoDualMode` 的 `storagePrefix: string` 签名，证明限定范围检查确实在检查 L3 文件
对 composable 的调用。随后已撤销变异，恢复 `'l3-proc:'`。

闭包内其余错误（AdjudicationBringInDialog / useAdjustmentCentralSync / GtAProgramConsole /
stores/project.ts / noteDisclosureReverseJump 等）均为既有预存错误，与本次改动无关。
