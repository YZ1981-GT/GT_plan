# Design Document

## Overview

本设计把「前端 Excel 调用收敛」拆成**四层**：能力补齐层（useExcelIO 新增 API）→ 安全加固层（单点防护）→ 迁移层（7 批次）→ 守卫层（防漂回）。

核心原则：**行为等价优先于代码优雅**。93 个调用点里没有一个是「写得不好需要改进」的，它们只是「散」。任何让产物发生变化的重构都要停下来登记，而不是顺手改好。

> **2026-08-14 交付实况**：46 → 0 收敛完成，`exempt[]` 为空。守卫 8 文件 114 例全绿 ·
> 变异 15/15 全 RED · 33 文件 Vite 编译通过 · CI 已挂 job。
> 本文档已按实测回写；凡带 ~~删除线~~ 或 🔴 标记处均为「立项假设被推翻」的留证，
> 保留原文以便对照，不直接改写成结论 —— 那样会丢掉「当初为什么想错」这个信息。

### 立项清点漏掉的两个坑（本设计的最强约束）

Task 1 的清册只看了「调用了哪些 API」，漏了「useExcelIO 的默认值会主动改变产物」这一面。逐字读 `useExcelIO.ts` 后发现两处默认值会让机械迁移**必然破坏行为等价**：

| 默认值 | 位置 | 机械迁移的后果 |
|---|---|---|
| `applyStyles = true` | `exportTemplate` / `exportData` / `exportMultiSheetData` | 42 个 xlsx 文件原本**无任何样式**，迁移后全被加上仿宋_GB2312 + Arial Narrow + 三线表边框 ⇒ 违反 R2.3 |
| `includeNoteRow = true` | `exportTemplate` | 原本 `aoa_to_sheet([headers, ...data])` 只有表头行，迁移后会在表头前**插入一行 note 行** ⇒ 行号整体下移，违反 R2.1 |

第三处是文案：`exportTemplate` / `exportData` 内部硬写 `ElMessage.success('模板已导出')` / `'数据已导出'`，调用方无法关闭或改写。R2.8 要求文案逐字保持，且有些调用点**本就不弹提示**（如 `queryExport.ts` 由调用方自行提示），机械迁移会产生重复弹窗。

⇒ 迁移的默认姿势是**三个显式关闭**：`applyStyles: false` + `includeNoteRow: false` + `successMessage: false`。只有原本就带样式的 `batchExport.ts` 例外。

### 行为等价的判据边界（语义等价，非二进制等价）

~~3 个 exceljs 文件迁到 useExcelIO 等于**换写引擎**（ExcelJS → SheetJS）~~。

> 🔴 **2026-08-14 实测推翻**：那 **4** 个文件最终**不换引擎** —— 补两个 ExcelJS 侧薄 loader
> 把库 import 收进入口而引擎不变。理由：换 SheetJS 要逐条对齐五处语义差异（中间空行是否
> 跳过 · `row.values` 1-based vs 0-based · 尾部缺列是否补齐 · 空单元格是否产生键 ·
> 找不到 sheet 时 undefined vs 降级取第一个），且 xlsx-js-style **写不出冻结窗格**
> （`exportFormulaTemplate.ts` 依赖它）—— 这些风险换不来任何安全收益，因为 exceljs 是
> 独立实现、不带 xlsx 那两个 CVE。
>
> **但下面这条判据边界仍然成立且仍在用**：即使不换引擎，同一份数据经不同调用路径
> （`writeFile` vs `write` 取字节）产出的二进制也可能不同，故守卫一律比语义不比 sha256。

两个引擎产出的 xlsx 二进制必然不同（ZIP 条目顺序、`docProps` 内容、styles.xml 结构都不同），但语义可以相同。

⇒ R2.1~R2.5 的守卫判据一律是「**用同一个 reader 把两份产物读回来后比对**」：单元格值逐格、`!cols` 逐列、`cell.s` 逐格、`SheetNames` 逐个有序、文件名字符串。**禁止**比对文件 sha256 —— 那会让 exceljs 批永远无法通过，进而诱使人把守卫改松。

## Architecture

### 四层与依赖

> 🔴 **2026-08-14 实测回写：L1 最终是 10 项而非立项设想的 4 项，且 4 项里有 2 项从未被用到。**
>
> 下面这张「新增 4 项」的图保留立项原貌以便对照，实际交付见本节末尾的 §L1 能力最终清单。
> 两条主要偏差：
> - **立项的 4 项里，`sheetMatcher` 与 `customInstructionSheet` 零生产消费方**（各被后来补出的
>   `readWorkbookAoa` / 多 sheet 纯 AOA 形态覆盖），已于 2026-08-14 删除。
> - **真正解决问题的 6 项立项时都没预见**：多 sheet 纯 AOA（L1-5）· `requireFirstCell`（L1-6）·
>   低层 `readSheetAoa`/`readSheetObjects`（L1-7/8）· 整簿 `readWorkbookAoa`（L1-9）·
>   ExcelJS 侧两个 loader（L1-10）· `ExcelJsonSheetDef`（L1-11）· `blankrows`（L1-12）。

```
L1 能力补齐（立项设想：useExcelIO 新增 4 项）
   ├─ exportToBytes / exportMultiSheetToBytes      ← R3.1，exceljs 批的前置
   ├─ ParseFileOptions.sheetMatcher                ← R3.2，ShareChangeSheet 的前置
   ├─ ExportTemplateOptions.customInstructionSheet ← R3.3，函证组 12 文件的前置
   └─ successMessage?: string | false              ← R2.8，全批次的前置
        ↓ 硬前置（无 L1 则迁移必破坏等价）
L2 安全加固（单点防护，在 parseFile 内部）
   ├─ 原型污染键过滤                                ← R4.1 / R4.2
   └─ 行数上限 + 截断计数                            ← R4.3
        ↓ 可并行（L2 只碰 parseFile，L3 各批只碰调用方）
L3 迁移 7 批次
   B1 次级封装 2 → B2 函证组 14 → B3 H/I composables 8
   → B4 consolidation 5 → B5 exceljs 4 → B6 大文件 3（各自单独）
   → B7 其余散件 10
        ↓ 每批完成即更新进度基线
L4 守卫层
   ├─ 零裸 import（按路径）+ 变异检验                ← R5.1 / R5.2
   ├─ 行为等价（快照对照）                           ← R5.4 / R5.5
   ├─ 豁免清单 stale 检测                            ← R5.6
   └─ CI 挂载                                        ← R5.7
```

**L1 是全局硬前置**：三个显式关闭里的 `successMessage` 不存在于现有 API，不先加就没法在迁移时保持文案。

### L1 能力最终清单（2026-08-14 交付实况）

| ID | 能力 | 立项预见 | 生产消费方 | 备注 |
|---|---|---|---|---|
| L1-1 | `exportToBytes` / `exportMultiSheetToBytes` | ✅ | **0**（保留） | 立项理由「exceljs 批用 writeBuffer」不成立（那批改走 ExcelJS loader）。保留是因为它们是 **OOXML 合法性守卫的载体** —— 只有拿到真实字节才能解 zip 读 `styles.xml`；mock `writeFile` 拿到的内存 wb 里 `cell.s` 未经序列化，验不出实际写入值（`vertical:'middle'` 缺陷靠这条路径发现） |
| ~~L1-2~~ | ~~`ParseFileOptions.sheetMatcher`~~ | ✅ | **0** ⇒ **已删** | 立项理由「ShareChangeSheet 模糊定位」不成立：它要跨「公司数×3」个 sheet 逐家匹配，单 sheet 定位表达不了 ⇒ 被 L1-9 覆盖 |
| ~~L1-3~~ | ~~`customInstructionSheet`~~ | ✅ | **0** ⇒ **已删** | 立项理由「函证组说明 sheet 是手写长文本」不成立：那 14 个文件走 `exportMultiSheetData` + AOA ⇒ 被 L1-5 覆盖 |
| L1-4 | `successMessage` 三态 | ✅ | 多处 | 唯一「立项判断正确且真被用上」的 |
| L1-5 | `ExcelAoaSheetDef`（多 sheet 纯 AOA 形态） | ❌ | 多处 | B2 全批 + B4/B6/B7 的主力形态 |
| L1-6 | `ParseFileOptions.requireFirstCell` | ❌ | 10 处 | 原实现藏着「首列必有值」的假设，会**静默丢行** |
| L1-7/8 | `readSheetAoa` / `readSheetObjects` | ❌ | 13 处 | B3 推翻「用 parseFile」后补出的低层薄封装 |
| L1-9 | `readWorkbookAoa`（整簿） | ❌ | 4 处 | 跨 sheet 匹配导入；带 `truncatedRows` 回报（R4.3） |
| L1-10 | `createExcelJsWorkbook` / `loadExcelJsWorkbook` | ❌ | 4 处 | B5 推翻「换引擎」后补出 |
| L1-11 | `ExcelJsonSheetDef`（`json_to_sheet` 形态） | ❌ | 2 处 | 表头须按**所有对象键的并集**生成，手写 AOA 会静默漏列 |
| L1-12 | `ReadSheetOptions.blankrows` | ❌ | 1 处 | 默认值随 `header` 而变，必须能透传 |

**这张表本身是个教训**：立项阶段判定「某能力是某批文件的硬阻塞」时，如果没先把那批文件的
目标写法落到具体代码，判断很容易错 —— 4 项里错了 2 项（判成硬阻塞但从未用到），
而真正需要的 8 项一项都没预见到。

**L3 批次顺序的依据**：B1 最小（2 文件、109 行合计）先跑通姿势；B2/B3 是最大两批但同构度最高，姿势一旦定死可批量套用；B5（exceljs）涉及换引擎，风险最高，放在 SheetJS 侧姿势全部验证完之后；B6 三个大文件各自单独成批（R6.4），因为它们的 Excel 代码嵌在数千行业务逻辑里，改动面必须可单独审阅。

## Components and Interfaces

### L1-1 `exportToBytes` / `exportMultiSheetToBytes`（R3.1）

现有 `exportData` / `exportMultiSheetData` 末尾直接 `XLSX.writeFile(wb, fileName)` 触发下载，调用方拿不到字节。3 个 exceljs 文件需要字节（`writeBuffer` 后自行拼 Blob 或走别的分发路径）。

```ts
/** 与 exportData 同参，但返回字节而不触发下载；不弹提示 */
export async function exportToBytes(
  options: Omit<ExportDataOptions, 'fileName'> & { fileName?: string },
): Promise<Uint8Array>

export async function exportMultiSheetToBytes(
  options: Omit<Parameters<typeof exportMultiSheetData>[0], 'fileName'>,
): Promise<Uint8Array>
```

实现要点：抽出现有 `exportData` 的「建 wb」段为私有 `_buildDataWorkbook(options)`，`exportData` 与 `exportToBytes` 共用它，前者 `writeFile` 后者 `XLSX.write(wb, { type: 'array', bookType: 'xlsx' })`。**不复制第二份建表逻辑** —— 否则将来改样式模板要改两处，正是本 spec 要消除的漂移。

### L1-2 `ParseFileOptions.sheetMatcher`（R3.2）

```ts
export interface ParseFileOptions {
  // ...既有字段不变
  /** sheet 定位谓词；优先级高于 sheetName。返回 true 的第一个 sheet 被选中 */
  sheetMatcher?: (sheetName: string, index: number) => boolean
}
```

定位优先级改为：`sheetMatcher` → `sheetName` 精确匹配 → 第一个 sheet。**既有两级顺序不变**，只在最前面插一级 ⇒ 33 个既有调用方零回归（R3.4）。

### L1-3 `ExportTemplateOptions.customInstructionSheet`（R3.3）

现有 `includeInstructions: true` 会强制生成三段固定内容：7 行通用提示 → `instructionRows`（可选追加）→ 「字段说明」表（列号/字段名/说明/示例）。12 个函证文件的说明 sheet 是手写业务长文本，三段都不要。

```ts
export interface ExportTemplateOptions {
  // ...既有字段不变
  /**
   * 完整自定义说明 sheet：给定时原样输出 AOA，不叠加通用提示与字段说明表。
   * 与 includeInstructions 互斥；两者同时给出时抛错而非静默择一。
   */
  customInstructionSheet?: {
    sheetName?: string   // 默认「填写说明」
    rows: any[][]
    colWidths?: Array<{ wch: number }>
  }
}
```

**互斥必须抛错**：若静默择一，将来有人两个都传会得到一份自己没预期的说明 sheet，且四层检查都查不出（memory：Vue 传不存在的 prop / 静默择一是假绿高发区）。

### L1-4 `successMessage`（R2.8）

```ts
/** 成功提示：省略 = 保持各函数现有默认文案；string = 用该文案；false = 不弹 */
successMessage?: string | false
```

加在 `ExportTemplateOptions` / `ExportDataOptions` / `exportMultiSheetData` 的 options 上。省略时行为与现在逐字相同 ⇒ 33 个既有调用方零回归。

### L2 `parseFile` 安全加固（R4.1~R4.5）

加固点在 `parseFile` 的对象模式分支，即现有这段：

```ts
const rowObj: Record<string, any> = {}
cleanHeaders.forEach((header, colIdx) => {
  const val = rawRow[colIdx]
  rowObj[header] = val != null && val !== '' ? val : null
})
```

`rowObj[header] = ...` 里 `header` 来自**用户上传文件的列头**。列头为 `__proto__` 时这行就是原型污染的写入点。

改造三处：
1. `Object.create(null)` 建行对象（无原型可污染）；返回前 `{ ...rowObj }` 转回普通对象，使调用方的 `Object.keys` / 展开 / `JSON.stringify` 行为不变。
2. 显式跳过 `__proto__` / `constructor` / `prototype` 三个列头（常量 `_BLOCKED_KEYS`），并计入 `ParseResult.blockedKeys: string[]` 供调用方感知。
3. 行数上限 `maxRows`（默认 50000），超限截断并回 `ParseResult.truncatedRows: number`。

`ParseResult` 新增两个**可选**字段 ⇒ 既有解构 `{ rows, headers }` 不受影响（R4.4）。

**rawArrayMode 分支不需要加固**：它用 `Object.fromEntries(rawRow.map((v, idx) => [String(idx), v]))`，键是数字下标，不受列头控制。这一点要写进守卫注释，否则下轮有人会「顺手也给它加一遍」。

## Data Models

### 迁移批次登记表（7 批 / 46 文件 / 96 调用点）

| 批 | 名称 | 文件数 | 调用点 | 同构度 | 迁移姿势 | 风险 |
|---|---|---|---|---|---|---|
| B1 | 次级封装 | 2 | 3 | 低（两者不同构） | `queryExport.ts` → `exportData` + `applyStyles:false` + `successMessage:false`（调用方自行提示）。~~`batchExport.ts` → `exportMultiSheetData` + `headerStyle` 覆写通道~~ ⇒ **该文件是零消费方孤儿链，2026-08-14 经用户裁决整文件删除**，连带删除 `headerStyle` 通道（专为它而加） | 中→已消解 |
| B2 | 函证组 | **14**（立项 12） | **34** | **高**（3 调用点/多 sheet/writeFileXLSX 全同） | **实际走法**：导模板/导数据均 → `exportMultiSheetData` + **纯 AOA 形态（L1-5）**，说明 sheet 与数据 sheet 是同一批 `sheets[]` 里的两项；导入 → `parseFile` + `requireFirstCell`（L1-6）逐文件核对。~~立项设想的 `exportTemplate` + `customInstructionSheet` 一次没用到~~ | 中：14 份说明 sheet 内容各异需逐份搬运 |
| B3 | H/I composables | 8 | 15 | **高**（均 `json_to_sheet` + 取第一个 sheet） | 写 → `exportMultiSheetData` + AOA；读 → **`readSheetAoa` / `readSheetObjects`（L1-7/8 低层薄封装）**。~~立项设想的「读 → `parseFile` 对象模式」被实测推翻~~：这 8 个文件全都显式传 `defval:''`（而 `parseFile` 硬编码归一为 `null`，下游 `??` 取默认值时结果不同），`useH1Depreciation` 还要 `raw:false` + `cellDates:true` 且**自己在前 10 行按打分定位表头行** —— `parseFile` 的固定表头模型表达不了 | 低 |
| B4 | consolidation | 5 | 15 | 中 | 含 `ShareChangeSheet.vue` 唯一 `sheetMatcher` 用例；`ConsolNoteTab.vue` 9 个调用点为本批重心 | 中 |
| B5 | exceljs | 4 | 9 | 中 | 🔴 **实测推翻「换引擎」**：改为**入口收两个引擎** —— 补 `createExcelJsWorkbook` / `loadExcelJsWorkbook` 两个薄 loader（L1-10），库 import 收进入口而**引擎不变**，故调用方语义逐行不变、严格等价自动成立。~~立项设想的 `exportToBytes`~~ 一次没用到。`exportFormulaTemplate.ts` 的 `@vite-ignore` 规避**已不必要**（动态 import 移进入口后本文件只做静态 import） | 低（不换引擎故风险消解） |
| B6 | 大文件（各自单独） | 3 | 5 | 无 | `TrialBalance.vue`(4484 行/3 点) · `ProcedureTrimming.vue`(3933 行/1 点) · `GtB22AControlMatrix.vue`(2668 行/1 点) | 中：Excel 代码嵌在大量业务逻辑中 |
| B7 | 其余散件 | **10**（立项 12，两个函证文件归入 B2） | 13 | 低 | 逐个处理。补出 L1-11 `ExcelJsonSheetDef` 与 L1-12 `blankrows`。🔴 **三处「封装默认口径对该调用方是错的」**：`ExcelImportPreviewDialog` 降级取**最后一个** sheet（封装口径是第一个）· `GtCustomWpBatchDialog` 要区分「无任何工作表」· `ReportLineMappingDialog.onImportTemplate` 是 el-upload 的 `before-upload` **必须同步返回 false**（改 async 会让 Element Plus 视为允许上传，真发一个无效 POST） | 低 |

合计 **46 文件 / 93 调用点**（口径：prod 桶，已排除 `useExcelIO.ts` 与 3 个测试文件）。B1~B7 的文件清单落地时固化进 `_baseline/` 快照。

**B5 从 3 增到 4 的原因**见 requirements.md §不剥注释会漏文件 —— `exportFormulaTemplate.ts` 的 `import(/* @vite-ignore */ 'exceljs')` 被未剥注释的第一轮扫描漏掉。该文件的文件头注释写明它是「独立文件避免在巨型 `FormulaManagerDialog.vue` 中动态导入 exceljs 导致 Vite import-analysis 解析失败」⇒ 迁移时须验证走 useExcelIO 后该规避是否仍必要，**不得直接删掉 `@vite-ignore` 了事**。

### 进度基线（R6.6，单调下降）

```json
{
  "bare_import_files": { "initial": 46, "current": 46, "target": 0 },
  "bare_import_calls": { "initial": 93, "current": 93, "target": 0 },
  "by_lib_files": { "xlsx": 41, "exceljs": 4, "xlsx-js-style": 1 },
  "exempt": [],
  "note": "current 只许下调；exempt 每条含 reason + evidence。口径 = prod 桶（排除 useExcelIO.ts 与测试文件），stripComments 前置"
}
```

落 `audit-platform/frontend/src/composables/__tests__/_baseline/excelIoConvergence.baseline.json`。守卫读它做单调性断言。

### 扫描口径（守卫与诊断脚本共用，必须逐字一致）

```
包含：audit-platform/frontend/src/**/*.{vue,ts}
排除：**/__tests__/**  ·  **/*.spec.ts  ·  composables/useExcelIO.ts  ·  exempt[] 中的路径
正则：(?:from|import\()\s*['"](xlsx|xlsx-js-style|exceljs)['"]
```

三个必须写死的口径细节：
- **`import('xlsx')` 与 `from 'xlsx'` 都要算**。只扫 `from` 会漏掉 91 个动态 import 里的绝大多数（实测动态形式占压倒多数）。
- **排除靠路径不靠符号名**（R1.2）。曾有 spec 因按符号名判定导致「只加一个 spec 文件的 import 就让基线缩短」的假绿。
- **注释里的 import 不算**。扫描前须 `stripComments()`，且该剥离函数本身要有反向自检（把一处真 import 挪进注释，计数必须下降 1）。

## Correctness Properties

### Property 1: 生产文件零裸 import

扫描口径按 §Data Models 逐字执行，裸 import 文件数为 0（`exempt[]` 除外）。反向自检：在任一生产文件注入一处 `await import('xlsx')` 必须打红。

**Validates: Requirements 1.1**

### Property 2: 豁免判据按路径

`__tests__/` 与 `*.spec.ts` 按路径豁免。反向自检：仅改测试文件里的符号名不改路径，判定结果不得变化。

**Validates: Requirements 1.2**

### Property 3: 次级封装保留领域 API

`queryExport.ts` 的 `exportQueryResultToXlsx` / `sanitizeExportName` 两个导出符号仍存在且签名不变；其原有调用方数量不减。

> 🔴 **2026-08-14 修正**：原文还含 `batchExport.ts` 的 `exportBatchToXlsx`。该文件经实测是
> 零消费方孤儿链，已按用户裁决删除 ⇒ 断言它「仍存在」会让本 Property 永久打红。
> 本 Property 的意图（有真实调用方的领域封装不得被拆掉）由 `queryExport.ts` 承载，
> 断言点在 `components/query/__tests__/queryExport.spec.ts`（8 例，已挂 CI）。

**Validates: Requirements 1.3**

### Property 4: 豁免清单有据且只减

`exempt[]` 每条含非空 `reason` 与 `evidence`；条目数写死上限，只许下调。

**Validates: Requirements 1.4, 6.6**

### Property 5: 三个库仍在 package.json

`xlsx` / `xlsx-js-style` / `exceljs` 三者仍在 `dependencies`。反向自检：删任一条必须打红（防「看起来没人用了」而误删）。

**Validates: Requirements 1.5**

### Property 6: 单元格值逐格等价

迁移前抓的产物快照与迁移后产物，用同一 reader 读回后全部单元格值逐格相等。

**Validates: Requirements 2.1**

### Property 7: 列宽逐列等价含「原本无列宽」

`!cols` 逐列相等；原本 `!cols` 为 undefined 的产物迁移后仍为 undefined。反向自检：给一个原本无列宽的调用点传 `applyStyles:true` 必须打红。

**Validates: Requirements 2.2**

### Property 8: 样式不被凭空添加

原本无 `cell.s` 的产物迁移后仍无；原本有的逐格相等。这条专门拦 `applyStyles` 默认 true 的坑。

**Validates: Requirements 2.3**

### Property 9: sheet 名与顺序等价

`SheetNames` 数组逐个有序相等，含两 sheet 结构（数据 sheet + 说明 sheet）的顺序。

**Validates: Requirements 2.4**

### Property 10: 文件名逐字等价

下载文件名字符串逐字相等。判据取调用 `writeFile` 时的实参（守卫 mock `writeFile` 捕获），不靠人眼看下载目录。

**Validates: Requirements 2.5**

### Property 11: 导入行集等价

同一份输入 xlsx 迁移前后解析出的行集相等：行数、每行字段名集合、字段值与类型。

**Validates: Requirements 2.6**

### Property 12: 示例行规则逐文件显式传参

每个迁移后的 `parseFile` 调用点，其 `skipRows` / `skipExamplePrefix` / `headerRowIndex` 三参与迁移前该文件的实际行为一致。反向自检：`GtConfirmationWealthList.vue` 的示例行首列是 `'E0-6-1'`，若套用默认 `skipExamplePrefix:'示例'` 则该示例行会进 rows，守卫必须打红。

**Validates: Requirements 2.7**

### Property 13: 提示文案逐字保持且不重复

迁移后每个调用点弹出的 `ElMessage` 文案与迁移前逐字相同，且条数相同（不得因封装内部也弹而出现两条）。

**Validates: Requirements 2.8**

### Property 14: exportToBytes 与 exportData 同源

两者共用私有建表函数，产出的工作簿结构一致。判据：同参调用，`exportToBytes` 的字节读回后与 `exportData` mock 捕获的 wb 逐格相等。反向自检：把建表逻辑复制成两份必须被结构守卫打红。

**Validates: Requirements 3.1**

### Property 15: sheetMatcher 优先级且既有两级不变

定位优先级 `sheetMatcher` → `sheetName` → 第一个。三条各一例；不传 `sheetMatcher` 时行为与改造前逐字相同。

**Validates: Requirements 3.2, 3.4**

### Property 16: customInstructionSheet 原样输出且与 includeInstructions 互斥

给定 `customInstructionSheet` 时说明 sheet 的 AOA 与传入值逐格相等，且不含通用提示与字段说明表的任何字样；两者同传时抛错。反向自检：改成静默择一必须打红。

**Validates: Requirements 3.3**

### Property 17: 既有 33 文件零回归

33 个已走 useExcelIO 且零裸 import 的文件，其产物在 L1 改造前后逐格相等（characterization 快照）。

**Validates: Requirements 3.4**

### Property 18: json_to_sheet 语义由 exportData 覆盖

9 个 `json_to_sheet` 调用点迁移后均走 `exportData`，且未新增专门 API。

**Validates: Requirements 3.5**

### Property 19: 93 个调用点语义全覆盖

清册 93 个调用点逐个映射到某个 useExcelIO API 或 `exempt[]`，无未表态者。

> 立项写 96 是**未剥注释**的第一轮扫描值，剥注释后实测 93。
> **实际结果：93 个全部收敛，`exempt[]` 为空、无一豁免。**

**Validates: Requirements 3.6**

### Property 20: 原型污染键不入结果

列头含 `__proto__` / `constructor` / `prototype` 时该列不入行对象，且计入 `blockedKeys`。

**Validates: Requirements 4.1**

### Property 21: Object.prototype 未被污染且守卫可打红

构造列头含 `__proto__` 且值为 `{polluted:1}` 的 xlsx，解析后 `({}).polluted === undefined`。反向自检：撤掉 `_BLOCKED_KEYS` 过滤必须打红。

**Validates: Requirements 4.2**

### Property 22: 行数上限截断并回报条数

超过 `maxRows` 时截断且 `truncatedRows` 等于被丢弃行数；不抛错、不 OOM。

**Validates: Requirements 4.3**

### Property 23: 合法输入解析结果不变

加固前后对合法 xlsx 的解析结果逐项相等（与 Property 11 同一 fixture 集）。

**Validates: Requirements 4.4**

### Property 24: 防护在单点

`_BLOCKED_KEYS` 过滤只存在于 `useExcelIO.ts`；扫全部调用方源码，不得出现各自的原型键过滤代码。

**Validates: Requirements 4.5**

### Property 25: 守卫按 import 路径扫描

守卫扫描口径与 §Data Models 逐字一致，含 `stripComments()` 前置。反向自检：把一处真 import 挪进注释，计数必须下降 1。

**Validates: Requirements 5.1**

### Property 26: 变异四态判定

按「失败测试名集合差集」判 RED / GREEN / ANCHOR-MISS / WRONG-TEST，不看退出码；锚点命中数必须为 1。

**Validates: Requirements 5.2**

### Property 27: 收敛判据是行为不是字符串

判「某调用点已收敛」须同时满足：该文件不再 import 真实库 **且** 其导出/导入函数仍可调用并产出正确结果。反向自检：把某文件的导出函数体删空但去掉 import，守卫必须仍打红。

**Validates: Requirements 5.3**

### Property 28: 行为等价覆盖至少三批

行为等价守卫覆盖 B2 / B3 / B5 各至少一个代表文件（含唯一换引擎批 B5）。

> 🔴 **本 Property 已永久不可满足，如实登记不假装（2026-08-14）**：
>
> 它依赖「在**该批改动前**抓产物快照」。B2~B7 均已迁移完成 ⇒ 现在抓到的是**迁移后**的
> 产物，写进基线就是「把迁移后结果当基线」（memory 假绿三源第三条）。**故不补、无守卫。**
>
> 另外前提也变了：B5 最终**不换引擎**（见批次表），「含唯一换引擎批」这个理由本身不成立。
>
> 等价性没有失去验证，只是判据换成了另外四条（详见 tasks.md Task 2）：迁移姿势机械一致
> （三个显式关闭 + 3 例守卫钉死其危险性）· 两种 sheet 形态原样透传（等价由结构保证而非事后比对）·
> **Playwright 真实产物 openpyxl 逐项核实**（比快照更强：快照只证明「与上次抓的一样」，
> openpyxl 核实证明「与源码承诺一样」）· 34 文件 Vite 编译扫描 + 变异 15/15 RED。

**Validates: Requirements 5.4**

### Property 29: 基线用快照不用 HEAD-swap

行为等价基线为迁移前抓取的真实产物快照文件；守卫不得含任何 `git stash` / `git checkout` / HEAD 切换操作。

**Validates: Requirements 5.5**

### Property 30: 豁免清单 stale 检测

`exempt[]` 里的文件若实际已无裸 import，守卫打红要求移出。

**Validates: Requirements 5.6**

### Property 31: CI 挂载

`governance-checks.yml` 新增 job 覆盖本 spec 全部守卫；`yaml.safe_load` 可解析且无重名 job。

**Validates: Requirements 5.7**

### Property 32: 浏览器实测且数据复原

Playwright 实测 ≥3 个循环的导出模板/导出数据/导入数据三态；实测前抓基线（全文 + md5），测后逐字节复原 + 独立只读核实。

**Validates: Requirements 5.8**

### Property 33: 批次划分与清册一致

7 个批次的文件并集等于清册 46 个生产文件，且两批之间无交集。

**Validates: Requirements 6.1**

### Property 34: 每批自洽

每批完成时该批文件 `get_diagnostics` 零错误、相关 vitest 全绿、裸 import 计数按该批文件数下降。

**Validates: Requirements 6.2, 6.3**

### Property 35: 大文件单独成批

`TrialBalance.vue` / `ProcedureTrimming.vue` / `GtB22AControlMatrix.vue` 三者各自单独成批，不与其他文件混批。

**Validates: Requirements 6.4**

### Property 36: 无法表达时进豁免而非改产物

若某文件语义无法用 useExcelIO 表达，该文件进 `exempt[]` 且其产物快照与迁移前逐格相等（证明没为迁就封装而改产物）。

**Validates: Requirements 6.5**

## Error Handling

收敛的性质是行为等价重构，所以错误处理的设计原则是「**不改变调用方看到的失败形态**」——
原本静默失败的不许改成抛错（会让页面白屏），原本抛错的不许改成静默（会掩盖问题）。

| 失败场景 | 入口内的处置 | 为什么这样定 |
|---|---|---|
| 上传文件不是合法 xlsx | 抛 `Error`，消息含「文件解析失败」 | 46 个调用点原本都用 `try/catch` + `ElMessage.error` 包着，抛错能被原样接住 |
| 目标 sheet 不存在 | 两级降级：`sheetName` 精确 → 第一个 sheet | 原代码就是这个顺序。改成抛错会让「模板 sheet 名微调」直接变成用户可见故障 |
| 行数超 `maxRows` | 截断并**如实回报**（`droppedRows` / `truncatedRows`） | R4.3。静默截断是最坏形态：调用方拿到少了行的数据却无从知晓 |
| 列头含 `__proto__` / `constructor` / `prototype` | 丢弃该列，`blockedKeys` 回报 | R4.5 单点防护。不抛错是因为恶意文件属可预期输入，抛错会让正常用户的误操作也炸页面 |
| 表头中间有空列 | 保留原列索引，不重排 | 原代码用「过滤后下标」导致后续列错位，这是**既有缺陷**；修它属行为改善而非等价破坏（变异 M4 锁死） |
| ExcelJS 写出前需判断 | `createExcelJsWorkbook` 返回 wb 而非回调式 | 回调式会剥夺调用方「写出前根据内容决定是否继续」的时机（变异 M13 锁死） |
| 基线清单与实现不符 | 守卫打红，红消息列出差异项与常见原因 | R6.7 / Property 38。清单漏记会让下游三处同时失效（stage 漏文件 / 编译扫描缩水 / 进度失真） |

**红消息可操作性**（R1.6 / Property 37）：所有守卫的失败消息须含违规文件路径 + 替代指引，
使人无需读 spec 即可修正。元守卫反向验这一点 —— 把消息改成裸断言必须被打红。

## Testing Strategy

| 层 | 文件 | 形态 |
|---|---|---|
| 零裸 import + 豁免 + 清单完整性 | `composables/__tests__/excelIoConvergence.spec.ts` | 源码扫描（含 stripComments 自检） |
| L1 新增 API 契约 | `composables/__tests__/useExcelIO.newApi.spec.ts` | 单元 + 互斥抛错 |
| L2 安全加固 | `composables/__tests__/useExcelIO.security.spec.ts` | 真实执行（构造污染 xlsx） |
| 行为等价 | `composables/__tests__/excelIoEquivalence.spec.ts` | 快照对照（读回比对，非 sha256） |
| 既有零回归 | 扩展 `composables/__tests__/useExcelIO.spec.ts` | characterization |
| 变异检验 | `audit-platform/frontend/scripts/mutate_excel_io_guards.mjs` | 四态判定 |
| 浏览器实测 | Playwright，测后数据复原 | 三态 × ≥3 循环 |

**基线快照目录**：`composables/__tests__/_baseline/`，含 `excelIoConvergence.baseline.json`（进度）与各批代表文件的产物快照（读回后的 JSON 结构，非二进制）。

### Property 38: 进度清单完整且声明即已迁

`_progress[].files` 并集（不含单一入口自己）+ `_files_deleted_not_migrated` 的数量等于 `bare_import_files.initial`；并集内每一项都存在于磁盘、且当前扫不出裸 import；并集内无重复项；已删清单与并集无交集。

**为什么需要这条**：其余全部守卫都在验「代码符不符合清单」，没有一条验「清单本身完不完整」。清单一旦漏记，下游三处同时失效 —— 按 files 精确 stage 会漏文件（远端仍带裸 import，CI 必红）、CI 的 `--from-baseline` 编译扫描覆盖面缩水（漏记的文件从未被编译验证）、进度计数失真。2026-08-14 真实发生：B2 那批 13 个 confirmation 文件只写在 `note` 的自然语言里，`files` 是空数组，编译扫描因此只覆盖 33/46。

**判据不能只比数量**：实测曾出现「基线 46 / HEAD 46」看着自洽，集合 diff 才发现各差一个元素。故 Property 断言的是集合关系与逐项状态，不是 count。

**排除单一入口**：`useExcelIO.ts` 会出现在「横切修复」批的 `files` 里（那批确实改了它 —— 修 `applyExcelStyleTemplate` 的非法 OOXML 枚举值），但它是迁移的目的地而非待迁散点，既不计入「迁移了 N 个文件」，也不受「当前无裸 import」约束（它是唯一允许持有裸 import 的文件）。

**反向自检**：变异 M18（漏记一项）/ M19（路径写错）/ M20（把已删文件塞回 files）须全部打红。

**Validates: Requirements 6.7**

### Property 37: 守卫红消息可操作

裸 import 守卫打红时，消息须含违规文件路径与「请改用 useExcelIO」的替代指引，使新人无需读 spec 即可修正。反向自检：把消息改成裸断言失败（无路径无指引）必须被元守卫打红。

**Validates: Requirements 1.6**
