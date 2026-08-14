# Implementation Plan: 前端 Excel 调用收敛到单一入口

## Overview

18 个任务分 5 波，把 46 个生产文件 / **93** 个调用点的裸 Excel 库 import 收敛到 `useExcelIO.ts`。

> **收敛已完成（2026-08-14）：46 → 0，`exempt[]` 为空、无一豁免。**
> 守卫 8 文件 **119** 例全绿（含终态守卫「生产文件零裸 import」）· 变异 **18/18** 全 RED ·
> **46/46** 文件 Vite transform 编译通过 · CI 已挂 job `excel-io-single-entry-convergence`。
>
> 登记在册的 4 处既有缺陷已处置：**2 处修掉**（非法 OOXML 枚举值 · sheet 名去重）·
> **1 处核实为误判撤回** · **1 处按用户裁决整链删除**（孤儿功能「合并导出」用户不可达）。
>
> 之后又做了一次 `semantic_reviewer` 独立复盘，追加修 4 项：删除导致的 **CI 必然红** ·
> 一条 **grep 式假绿守卫**（Property 24 只读入口源码、从不读调用方，四条断言恒真）·
> `readWorkbookAoa` **静默截断违反 R4.3** · `maxRows` 同名不同义未说明。
> 并**删掉 3 项零生产消费方的 API**（`sheetMatcher` / `customInstructionSheet` 及
> `headerStyle` 覆写通道）—— 它们各被后来补出的能力覆盖，是设计冗余。见文末「收尾修复」。
>
> 立项数「96 调用点」是未剥注释的第一轮扫描值，实测（剥注释后）为 **93**。
> 差异来自 `exportFormulaTemplate.ts` 的 `import(/* @vite-ignore */ 'exceljs')` 等写法，
> 详见 Task 1 与基线 JSON 的 `_scan_scope._why_strip`。
>
> **两处立项假设被实测推翻**：B5 不是「换引擎批」而是「入口收两个引擎」（Task 13）；
> B3 不能用 `parseFile` 而须另开低层薄封装（Task 11）。
>
> **顺带修掉三个既有缺陷**：`parseFile` 列索引错位（Task 8）· 样式模板写出非法
> OOXML 枚举值致 openpyxl 打不开文件（Task 18）· `ReportLineMappingDialog` 括号
> 不配平致 Vite 编译失败（Task 18，本轮改造引入后当场修掉）。

**本 spec 的性质是「行为等价重构 + 安全加固」，不是功能开发。** 判断成败的唯一标准是：裸 import 归零，且**没有任何一份导出产物发生变化**。

**立项清点漏掉的两处默认值是本轮最强约束**（design.md §立项清点漏掉的两个坑）：`applyStyles` 默认 `true` 会给 42 个原本无样式的产物加上三线表；`includeNoteRow` 默认 `true` 会在表头前插一行让全表行号下移。机械迁移必破坏等价 ⇒ 迁移默认姿势是**三个显式关闭**（`applyStyles:false` + `includeNoteRow:false` + `successMessage:false`）。

**Wave 1（Task 1~3）必须先对当前状态打红**：零裸 import 守卫应报 46 个文件、行为等价快照应为空、安全加固守卫应报污染成功。红消息带「尚未实现（Wave N Task M）」。

**三条硬前置**：
- Task 4~7（L1 四项 API）→ 全部迁移任务。缺 `successMessage` 就没法保持文案。
  - 🔴 **2026-08-14 复核：这四项里只有 `successMessage` 一项的「硬前置」判断是对的。**
    `sheetMatcher`（Task 5）与 `customInstructionSheet`（Task 6）**零生产消费方**，
    功能各被后来补出的 `readWorkbookAoa` / 多 sheet 纯 AOA 覆盖，已删；
    `exportToBytes`（Task 4）的立项理由（exceljs 批用 `writeBuffer`）也不成立
    （那批改走 ExcelJS loader），保留仅因它是 OOXML 守卫的载体。
    原句「缺 customInstructionSheet 函证组 12 文件无法迁」**是错的** —— 那 14 个文件
    走 `exportMultiSheetData` + AOA，一次没用它。
- Task 2（行为等价快照）→ 全部迁移任务。快照必须在**改动前**抓，事后补抓等于把迁移后的结果当基线（memory：守卫把错值当基线锁死是假绿三源之一）。
- Task 8（L2 加固）→ Task 12（读路径批次）。加固改的是 `parseFile` 内部，若在迁移后做，已迁移的调用点要重验一遍。

~~**B5（exceljs 3 文件）是唯一换引擎批**~~ —— 实测推翻。实际是 **4 文件**，且**不换引擎**：
补两个 ExcelJS 侧薄 loader 把库 import 收进入口而引擎不变，故语义逐行不变、严格等价
自动成立。换引擎要逐条对齐五处语义差异（空行 / 1-based `row.values` / 尾部补齐 /
空单元格键 / 找不到 sheet 的降级），且 xlsx-js-style 写不出冻结窗格 —— 风险换不来
安全收益（exceljs 不带 xlsx 那两个 CVE）。详见 Task 13。

## Task Dependency Graph

```json
{
  "waves": [
    { "wave": 1, "name": "判据先行（守卫先打红 + 抓迁移前快照）", "tasks": ["1", "2", "3"] },
    { "wave": 2, "name": "L1 能力补齐 + L2 安全加固", "tasks": ["4", "5", "6", "7", "8"] },
    { "wave": 3, "name": "迁移 B1~B4（SheetJS 侧）", "tasks": ["9", "10", "11", "12"] },
    { "wave": 4, "name": "迁移 B5~B7（换引擎 + 大文件 + 散件）", "tasks": ["13", "14", "15"] },
    { "wave": 5, "name": "守卫收口与验收", "tasks": ["16", "17", "18"] }
  ],
  "notes": "Wave 1 必须先对当前状态打红，且 Task 2 的产物快照必须在任何改动前抓取（事后补抓 = 把迁移后结果当基线）。Wave 2 的 L1 四项 API 硬前置于全部迁移任务；Task 8（L2 加固改 parseFile 内部）硬前置于 Task 12（读路径批次），顺序颠倒会让已迁移调用点需重验。Wave 3 内 Task 9（B1 次级封装）先跑通姿势再批量套用到 Task 10/11。Wave 4 的 Task 13（B5 exceljs）是唯一换引擎批，放在 SheetJS 侧姿势全部验证完之后。Task 14 三个大文件各自独立提交，互不依赖可并行。"
}
```

## Tasks

- [x] 1. 建零裸 import 守卫与扫描口径（先打红）

  ### 交付与实测（2026-08-12）

  - `src/composables/__tests__/excelIoConvergence.spec.ts`（**16 例**：类 A 独立口径 8 / 类 B 被测实现 4 / 元守卫 4）
  - 基线 `__tests__/_baseline/excelIoConvergence.baseline.json`：46 文件 / 93 调用点 / xlsx 41 · exceljs 4 · xlsx-js-style 1
  - **实测 15 绿 1 红**，红的正是「🔴 生产文件零裸 import」待实现项，红消息列出全部 46 个文件 + 每文件调用点数与库 + 替代 API + 三个显式关闭提醒 + 豁免出口
  - **变异检验 M6 = RED**（新增一处裸 import → 文件数 46→47、xlsx 41→42，三条断言同时打红），还原后回到 15 绿 1 红
  - `stripComments` 三条反向自检全绿：注释内 import 不计数 · `https://` 不被误当行注释 · `import(/* @vite-ignore */ 'exceljs')` 剥注释后才命中（不剥则 0 命中，这正是第一轮漏文件的根因）

  - 新建 `audit-platform/frontend/src/composables/__tests__/excelIoConvergence.spec.ts`
  - 扫描口径**逐字照抄** design.md §Data Models「扫描口径」：含 `import()` 与 `from` 两形态、排除靠路径、扫描前 `stripComments()`
  - `stripComments()` 必须配反向自检：把一处真 import 挪进注释，计数必须下降 1（memory：`strip_comments` 会把模板字符串一起剥掉，须验证不误伤）
  - 建进度基线 `__tests__/_baseline/excelIoConvergence.baseline.json`（initial **46 文件 / 93 调用点**，`by_lib_files` = xlsx 41 / exceljs 4 / xlsx-js-style 1）
  - 🔴 基线值必须用**与守卫逐字相同的口径实测**后再写死，不得沿用未剥注释的第一轮数字（实测差异：exceljs 3→4、entry 3→2）
  - 红消息须含违规文件路径 + 「请改用 useExcelIO」替代指引（不是裸断言失败），并配元守卫拦「消息退化成无路径无指引」
  - 预期打红：当前 46 个文件全部命中
  - _Requirements: 1.1, 1.2, 1.4, 1.6, 5.1, 6.6_

- [-] 2. 抓迁移前产物快照（阻塞全部迁移任务）—— **B1 已抓并变异验证；B2/B3/B5 的机会窗口已关闭，不补**

  ### 已交付（2026-08-12）

  - `__tests__/_helpers/workbookSnapshot.ts`：`snapshotWorkbook` / `snapshotFromBytes` / `diffSnapshots` / `formatDiffs`。**抓取与比对共用同一套序列化**（两份口径一旦漂移，红绿都不可信）
  - `__tests__/excelIoEquivalence.spec.ts`：基线由 `UPDATE_EXCEL_SNAPSHOT=1` 显式生成；**基线缺失时报错并提示生成命令，不静默新建**（vitest 内置 `toMatchSnapshot` 会静默新建判绿，基线被误删则回归无声消失）
  - B1 基线 ~~3~~ **2** 份落 `_baseline/equivalence/`：`b1-queryExport-basic.json`(1212B) · `b1-queryExport-empty.json`(562B)。~~`b1-batchExport-multi.json`(2849B)~~ 已随被测文件删除（2026-08-14，孤儿链）
  - `diffSnapshots` 返回**全部**差异而非首个 —— 迁移一个文件常一次引入多处偏差（样式+行号+文件名），只报第一处会让人改一处跑一轮反复多次
  - `formatDiffs` 的消息按出现频率列出 4 个常见原因（忘关 applyStyles / 忘关 includeNoteRow / 列宽算法被换 / 文件名拼接变了）
  - **变异检验 M7 = RED**：改 `queryExport` 列宽 16→20 命中 2/2 ⇒ 等价守卫确能拦产物变化，不是装饰品。（~~M8「去掉 batchExport 表头灰底」命中 1/1~~ 已随该文件删除）

  ### 🔴 修掉变异脚本的一处会写坏生产代码的缺陷

  加 M7/M8（目标文件不是 `useExcelIO.ts`）时暴露：原脚本只备份 `ENTRY` 一个文件，
  还原时**无论变异目标是谁都写回 ENTRY 的内容** ⇒ 一旦变异目标是别的文件，还原就会把
  `useExcelIO.ts` 整份内容覆盖进那个文件。已改 per-mutation 备份（`{file}.mutbak`），
  `--restore` 也改为遍历全部变异目标各自还原。实测 8 条跑完 `queryExport.ts` /
  `batchExport.ts`（当时尚存）均无 `M` 标记、无 `.mutbak` 残留。

  ### 🔴 B2/B3/B5 的快照**已无法按原计划补**（如实标注，不假装完成）

  原计划是「各批在该批改动前抓快照」。B2~B7 均已迁移完成 ⇒ **现在抓到的是迁移后的
  产物**。把它写进 `_baseline/` 就是「把迁移后结果当基线」—— memory 记的假绿三源
  第三条（守卫把错值当基线锁死），且会让人误以为等价性已被覆盖。

  故本任务**保持 `[-]`**：B1 部分（2 文件 / 3 份快照）真实完成且变异验证有效；
  B2/B3/B5 部分的机会窗口已关闭，不补、不改标记。

  #### 这个缺口实际由什么补上了

  等价性没有失去验证，只是判据从「产物快照 diff」换成了另外四条：

  1. **迁移姿势的机械一致性** —— 全批统一「三个显式关闭」（`applyStyles:false` +
     `includeNoteRow:false` + `successMessage:false`），且 `useExcelIO.newApi.spec.ts`
     有 3 例守卫专门钉死这三个默认值的危险性（含一例主动证明 `includeNoteRow` 默认
     true 会插 note 行使全表行号下移）。
  2. **AOA / json 两种形态原样透传** —— 不做任何加工，故等价性由「透传」这个结构
     保证，而非靠事后比对。L1-5/L1-11 各有守卫。
  3. **Playwright 真实产物 openpyxl 逐项核实**（Task 18）—— TrialBalance 与
     C23SampleSheet 两组四个文件，逐项比对 sheet 名 / 表头 / 列宽 / 行数 / 样式，
     全部与迁移前源码承诺一致。这是比快照更强的判据（快照只能证明「与我上次抓的
     一样」，openpyxl 核实证明「与源码承诺一样」）。
  4. **34 文件 Vite 编译扫描 + 变异 14/14 RED**。

  #### 如果要真正补上（留给后续）

  唯一诚实的做法是从 git 历史取迁移前版本抓快照。但 `excelIoEquivalence.spec.ts` 里
  明确禁止守卫内含 `git stash` / `git checkout` / HEAD 切换（会污染并发会话的工作树），
  故须离线跑一次性脚本产出基线文件，再让守卫只读该文件。工作量不小且收益低于上述四条，
  未做。
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 5.4, 5.5_

  - 新建 `audit-platform/frontend/src/composables/__tests__/_baseline/` 下各批代表文件的产物快照
  - 快照形态为**读回后的 JSON 结构**（单元格值 / `!cols` / `cell.s` / `SheetNames` 有序 / 文件名），**不存二进制、不算 sha256**（理由见 design.md §行为等价的判据边界）
  - 覆盖 B2 / B3 / B5 各至少一个代表文件 + ~~`batchExport.ts`~~（该文件已删，见 Task 2 顶部说明）
  - 🔴 **必须在任何生产代码改动前执行**；守卫内禁含 `git stash` / `git checkout` / HEAD 切换
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 5.4, 5.5_

- [x] 3. 建安全加固守卫（先打红）

  ### 交付与实测（2026-08-12）

  - `src/composables/__tests__/useExcelIO.security.spec.ts`（**14 例**，全绿）
  - 🔴 **判据推理修正了 spec 立项时的写法**：原计划断言「解析后 `({}).polluted === undefined`」是个**假守卫**。xlsx 单元格值只能是标量，而 JS 语义下普通对象 `o.__proto__ = 'abc'` 静默无效、`o.constructor = 'abc'` 只建自有属性 ⇒ 该断言在有无防护时**都绿**，撤掉 `_BLOCKED_KEYS` 也发现不了。真判据改为三条可被变异打红的事实：危险键不进 `headers` · 不进行对象自有键 · `blockedKeys` 如实回报。原断言降级为 `afterEach` 兜底。
  - 🔴 **本文件是 `parseFile` 的首个测试覆盖** —— 既有 `useExcelIO.spec.ts` 21 例全部只测导出侧，读侧（正是 CVE 攻击面）此前**零覆盖**
  - 环境坑：jsdom 的 `File` 无 `arrayBuffer()`，不打 polyfill 全部用例以 `TypeError` 失败（首轮实测 11 红 1 绿即此因）
  - **变异检验 M1 / M5 = RED**（撤 `_BLOCKED_KEYS` 命中 3/3 预期；撤行数上限命中 1/1）

  - 新建 `composables/__tests__/useExcelIO.security.spec.ts`
  - **真实执行判据**：用 SheetJS 构造一份列头含 `__proto__` 且值为 `{polluted:1}` 的 xlsx，走 `parseFile` 后断言 `({}).polluted === undefined`
  - 禁止只断言「源码里出现了 `__proto__` 字样」（memory：grep 式守卫只查字符串存在是假绿三源之一）
  - 另建行数上限与 `truncatedRows` 两例
  - 预期打红：当前无防护，污染成功
  - _Requirements: 4.1, 4.2, 4.3_

- [x] 4. L1-1 `exportToBytes` / `exportMultiSheetToBytes`

  ### 交付（2026-08-12）

  - 抽私有 `_buildDataWorkbook` 与 `_buildMultiSheetWorkbook`，四个导出入口共用，零复制
  - 守卫见 `useExcelIO.newApi.spec.ts`（**23 例全绿**）：返回 `Uint8Array` 可读回 · 不触发下载不弹提示 · **与 `exportData` 产出的 AOA 逐格相等**（同源判据）· 多 sheet 名与顺序保持

  - 抽 `exportData` 的建 wb 段为私有 `_buildDataWorkbook(options)`，`exportData` 与 `exportToBytes` 共用
  - **禁止复制第二份建表逻辑** —— 否则改样式模板要改两处，正是本 spec 要消除的漂移
  - 守卫：同参调用两者产出的 wb 逐格相等 + 结构守卫拦「建表逻辑被复制成两份」
  - _Requirements: 3.1_

- [x] 5. ~~L1-2 `ParseFileOptions.sheetMatcher`~~ —— **已交付后又删除（零生产消费方）**

  ### 🔴 2026-08-14 删除，原因见下

  立项判定它是「`ShareChangeSheet` 按『含公司名且含净资产』模糊定位」的硬前置。实测该文件
  要在「公司数 × 3」个 sheet 间**逐家**匹配，单 sheet 定位表达不了 ⇒ 最后走了
  `readWorkbookAoa`（L1-9，整簿读后调用方自己挑）。`sheetMatcher` **一次没用上**。

  ⇒ L1-9 功能上覆盖了 L1-2，留着是设计冗余 + 零消费方 API。已删该选项、`_pickSheetName`
  的第一级、以及 5 例守卫（保留其中「两级定位」与「requireFirstCell」两条，改写后归入
  `parseFile sheet 定位（两级）与 requireFirstCell` describe）。`ParseFileOptions` 与
  `ReadSheetOptions` 两处声明均已清除。

  下方保留立项与交付原文以对照。

  ### 交付（2026-08-12）

  - 优先级 `sheetMatcher` → `sheetName` 精确 → 第一个；既有两级顺序未动
  - 守卫 5 例全绿：三级优先级各一 · 不传时与改造前逐字相同 · matcher 第二参为 sheet 索引

  - 定位优先级改为 `sheetMatcher` → `sheetName` 精确 → 第一个；**既有两级顺序不变**，只在最前插一级
  - 守卫三例（三条优先级各一）+ 不传 `sheetMatcher` 时与改造前逐字相同
  - _Requirements: 3.2, 3.4_

- [x] 6. ~~L1-3 `ExportTemplateOptions.customInstructionSheet`~~ —— **已交付后又删除（零生产消费方）**

  ### 🔴 2026-08-14 删除，原因见下

  立项判定它是「B2 函证组 12 文件无法迁移的硬阻塞」。实测那 **14** 个文件走的是
  `exportMultiSheetData` + **纯 AOA 形态**（L1-5）—— 因为它们的说明 sheet 与数据 sheet
  本就是同一批 `sheets[]` 里的两项，用多 sheet 形态更自然。`customInstructionSheet`
  **一次没用上**。

  ⇒ L1-5 功能上覆盖了 L1-3。已删该选项、`CustomInstructionSheet` 接口、互斥校验、
  以及 6 例守卫中的 4 例；**保留 2 例**改写为验 `includeInstructions` 自身
  （其中「说明 sheet 在数据 sheet 之前」是判断 `ExcelImportPreviewDialog` 降级规则
  合理性的依据，删了会让 Task 18 里那条撤回结论失去支撑）。变异 M2 一并删除。

  下方保留立项与交付原文以对照。

  ### 交付（2026-08-12）

  - 原样输出 AOA + 可选 `colWidths` + 可自定义 sheet 名；与 `includeInstructions` 同传抛错
  - 守卫 7 例全绿：逐格相等 · 不含通用提示 4 个字样（`⚠ 重要提示`/`不要修改工作表名称`/`字段说明`/`列号`）· 互斥抛错 · 不传时 `includeInstructions` 行为不变 · 说明 sheet 在数据 sheet 之前
  - **变异检验 M2 = RED**（改成静默择一必打红）

  - 给定时原样输出 AOA，不叠加 7 行通用提示与「字段说明」表
  - 与 `includeInstructions` **同传时抛错**，不得静默择一（静默择一的错四层检查都查不出）
  - 守卫：原样输出逐格相等 + 不含通用提示任何字样 + 互斥抛错 + 反向自检（改成静默择一必须打红）
  - _Requirements: 3.3_

- [x] 7. L1-4 `successMessage` 三态

  ### 交付（2026-08-12）

  - 私有 `_notifySuccess(msg, fallback)`：`undefined` → fallback / `string` → 该文案 / `false` → 不弹
  - 守卫 5 例全绿（含「提示只弹一次」防双弹）+ 3 例产物形状守卫，其中一例**主动证明默认值的危险性**：`includeNoteRow` 默认 true 时第一行是 note 行而非表头
  - **变异检验 M3 = RED**（`successMessage:false` 失效必打红，命中 2/2）

  - `string | false | 省略`；省略时行为与现在逐字相同
  - 加在 `ExportTemplateOptions` / `ExportDataOptions` / `exportMultiSheetData` options
  - 守卫：三态各一例 + 33 个既有调用方零回归（characterization）
  - _Requirements: 2.8, 3.4_

- [x] 8. L2 `parseFile` 安全加固（阻塞 Task 12）

  ### 🔴 顺带修掉一处既有缺陷（列索引错位）

  改造前是 `headers.filter(h => h !== '')` 后**用过滤结果的下标**去取 `rawRow[colIdx]`。
  表头行中间出现空列时（如 `['A', '', 'B']`），`B` 会取到空列的值，**整行右侧全部错位**。
  加危险键过滤会把该缺陷从「仅空列头触发」扩大到「危险列头也触发」，故一并改为
  `{ header, colIdx }` 配对，`colIdx` 始终是原始列索引。

  这个 bug 是写守卫时被实测抓出来的（`expected 'v1' to be 'ok'`），不是推理出来的 ——
  也说明「原实现看着没问题」不能作为不写守卫的理由。已补 2 例守卫锁死（空列头变体 +
  危险列头变体），**变异检验 M4 = RED**（改回过滤后下标必打红，命中 2/2）。

  ### 交付（2026-08-12）

  - `Object.create(null)` 建行对象 + `{ ...bare }` 转回普通对象（守卫断言原型仍是 `Object.prototype`，否则调用方 `hasOwnProperty` 会抛错）
  - `_BLOCKED_KEYS` 三键过滤 + `blockedKeys` 回报；`maxRows` 默认 50000 + `truncatedRows` 回报
  - `ParseResult` 两个新字段均可选 ⇒ 既有 `{ rows, headers }` 解构零回归（守卫已覆盖）
  - **`rawArrayMode` 分支不加固**（键是数字下标，不受列头控制），该判断已写进代码注释 + 1 例守卫，防下轮误加

  - 三处改造：`Object.create(null)` 建行对象后 `{...rowObj}` 转回 → 跳过 `_BLOCKED_KEYS` 三键并计入 `blockedKeys` → `maxRows` 默认 50000 + `truncatedRows`
  - `ParseResult` 新增两字段均为**可选** ⇒ 既有 `{rows, headers}` 解构不受影响
  - **`rawArrayMode` 分支不加固**（键是数字下标，不受列头控制）；此判断写进代码注释防下轮误加
  - Task 3 的守卫应由红转绿
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_

- [x] 9. 迁移 B1 次级封装 2 文件（跑通姿势）

  ### 交付与实测（2026-08-12）

  - `queryExport.ts` → `exportData` + `applyStyles:false` + `successMessage:false` + 逐列 `width:16`
  - `batchExport.ts` → `exportMultiSheetData` + `applyStyles:false` + `headerStyle` 覆写 + 逐列 `width: Math.max(col.length*2, 12)`
  - **裸 import 46 → 44，调用点 93 → 91，`xlsx-js-style` 归零**（它原本只有 batchExport 一处）
  - 等价守卫 6 例全绿 ⇒ 两文件产物**逐格零变化**
  - 全量 `src/composables/__tests__/` + queryExport 实测 **1998 通过 / 14 失败**，14 例里 1 例是本 spec 预期红，13 例为并发会话既有失败（`buildDisclosureDraftKey is not a function` 等）

  ### 🔴 迁移中补出的两项 API 不一致（都是既有缺陷）

  1. **`exportData` 的 `applyStyles:false` 分支忽略 `columns[].width`** —— 它用 `headers.map(h => Math.max(h.length*2.5, 14))`，而 `exportTemplate` 的同一分支早就写着 `c.width || Math.max(...)`。两入口口径不一致，导致「关样式但保原列宽」这个迁移必需组合**无法表达**。已对齐（`fullCols` 提到 if 外层供两分支共用）。
  2. **表头样式只有 true/false 两态不够** —— `batchExport.ts` 是 46 个文件里唯一原本带样式的，其样式（加粗 + F5F5F5 灰底 + 居中，无边框无仿宋）与三线表模板是两种外观。新增 `ExcelMultiSheetDef.headerStyle` 覆写通道（在 `applyStyles` 之后应用），否则迁移它只能改产物外观。

  ### 🔴 顺带发现一条完整孤儿链（超本 spec 半径，仅登记）

  `utils/batchExport.ts` 的 `exportBatchToXlsx` **全库零消费方**（按 import 路径查）。
  唯一可能的消费场景 `components/query/BatchQueryResultGroup.vue` 带一个「合并导出」
  按钮，但它 `emit('merged-export')` 交给父组件，而**该组件自身也零消费方** ——
  除 `components.d.ts` 自动生成的声明外，没有任何页面 import 它。

  ⇒ 「合并导出」是一个**用户不可达的功能**。本 spec 只做 Excel 调用收敛（已完成），
  该孤儿链的处置（接线 / 删除）属功能层决策，留待用户裁决，不在本 spec 动。

  ### 既有测试的 mock 层上移

  `components/query/__tests__/queryExport.spec.ts` 原先 mock `xlsx` 并从 `_sheets` 取 AOA 断言，
  迁移后写引擎变成 `xlsx-js-style` ⇒ 以 `TypeError: Cannot read properties of undefined` 失败。
  **没有**把 mock 目标换成 `xlsx-js-style`（那只是把测试重新钉在另一个实现细节上，下次换库还得改），
  而是上移到 mock `useExcelIO.exportData`，断言 `queryExport` 的真实职责（输入 → `ExcelColumn[]+data` 的转换
  + 三个显式关闭在位）。端到端产物正确性由等价守卫逐格覆盖，两者互补不重叠。现 8 例全绿。

  - _Requirements: 1.3, 2.1, 2.2, 2.3, 6.1, 6.2, 6.3_

  - `queryExport.ts` → `exportData` + `applyStyles:false` + `includeNoteRow:false` + `successMessage:false`（调用方自行提示）
  - `batchExport.ts` → `exportMultiSheetData`，但**必须保留其加粗灰底表头样式**（与三线表不同）；若现有 API 无法表达该样式，此处需补样式覆写通道而非改产物
  - 保留两者的领域 API 与调用方，不删除（R1.3）
  - 本批产出的姿势写进 design.md 供 B2/B3 批量套用
  - 本批须验证「单批独立可回滚」成立：单独 revert 本批不影响其他文件，且回滚后守卫计数回到 46
  - _Requirements: 1.3, 2.1, 2.2, 2.3, 6.1, 6.2, 6.3_

- [x] 10. 迁移 B2 函证组 **14** 文件

  ### 🔴 批次清单修正：12 → 14（连带 B7 12 → 10）

  实测按路径含 `confirmation/` 或 `g0-confirmation/` 划定得 **14 文件 / 34 调用点**，
  立项写的 12 少了两个（`diffChecklist` / `diffReconcile` 曾被误归散件）。修正后
  七批合计仍是 44 文件 / 91 调用点，与守卫实测一致。清单已固化进
  `_baseline/excelIoConvergence.baseline.json` 的 `_batches` 段。

  ### 交付与实测：全批 14 文件 / 34 调用点收敛完毕

  计数 **44 文件 / 91 点 → 30 文件 / 57 点**。

  先做最复杂的 `alternativeD05/GtConfirmationAlternativeD05.vue` 当样板（模板导出
  **6 个 sheet**、数据导出 **5 个 sheet**、1 处导入），跑通后套用到其余 13 个。
  `D06`/`F05`/`F06`/`H05`/`G06` 与 D05 逐字同构（只差 `BLOCK_COLUMN_CONFIGS_*`
  常量名与文件名）。

  其余 13 个：`GtConfirmationSummary` · `alternativeD06` · `alternativeF05` ·
  `alternativeF06` · `alternativeH05` · `alternativeK06` · `alternativeG06` ·
  `entityVerify` · `reliability` · `wealthList` · `followup` · `diffChecklist` ·
  `diffReconcile`

  ### 🔴 迁移中补出两项 L1 能力（都是现有 API 表达不了的）

  **L1-5 多 sheet 支持纯 AOA 形态**（`ExcelAoaSheetDef`）。B2 这批的 sheet 本质是
  「任意二维数组」而非 `columns + data`：只有表头行的空模板 sheet、纯文本说明 sheet、
  表头+单条示例行的清单 sheet。硬凑成 `columns + data` 既失真又要为说明文本编造假列名。
  `ExcelMultiSheetDef` 改为 union（判别式 = 有无 `rows`），既有调用方全是 `columns + data`
  形态故向后兼容。配 3 例守卫（三形态混排顺序保持 / sheet 名截断 / 省略 colWidths 时不设 `!cols`）。

  **L1-6 `ParseFileOptions.requireFirstCell`**（默认 `true` 保持既有行为）。
  `parseFile` 原有一行 `if (!firstCell) continue`，藏着「首列必有值」的假设 ——
  而 D05 模板首列是「序号」，其填写说明明确写着「序号：自动生成（留空即可）」。
  用户留空序号、其余列填满的行会被**静默丢弃且不报错**。原实现 `sheet_to_json(ws)`
  不做此检查，故必须能关掉才行为等价。关掉时改由「整行全空」判据过滤。
  配 1 例守卫钉死两态差异（默认丢 1 行 / 关掉保 2 行且全空行仍丢）。

  ### 逐文件核对三项的结论（不能按同构假设一刀切）

  - **`requireFirstCell: false`**（首列允许留空）：D05 · D06 · F05 · F06 · H05 · K06 ·
    G06 · entityVerify · reliability · GtConfirmationSummary
  - **保持默认 `true`**：`wealthList` —— 它的首列是「索引号」（必填关键列），
    与其余「序号可留空」性质不同。若一刀切关掉，等于放宽了它的校验。
  - **`successMessage: false`（原本就不弹提示）**：diffChecklist · diffReconcile ·
    followup · entityVerify · GtConfirmationSummary

  ### 保持两处既有不一致，未在收敛中「顺手统一」

  - `D05` 模板导出第三个区块 sheet 名是「③本期收款检查」，而数据导出是「③本期收款」
  - `H05` 数据导出区块 sheet 首列标签是「被函证单位」，而同构文件都是「公司名称」

  两处都是原本就不一致。收敛的职责是「换库调用入口」，统一命名属独立议题 ——
  一旦顺手改了，等价守卫就失去意义（无法区分「我改的」和「本来就不同」）。
  - _Requirements: 2.1, 2.4, 2.6, 2.7, 3.3, 6.1, 6.2_

- [x] 11. 迁移 B3 H/I composables 8 文件

  ### 🔴 立项方案被实测推翻：这批**不能**用 `parseFile`

  下方原写「读 → `parseFile` 对象模式」。实测 B3 的读侧与 `parseFile` 的模型**根本不匹配**，
  照做会静默改数：

  - **全部 8 个都显式传 `defval: ''`**（空单元格填空串），而 `parseFile` 硬编码把空值归一为
    `null`。下游用 `??` / `||` 取默认值时，`''` 与 `null` 结果不同。
  - **`useH1Depreciation` 还要 `raw: false` + `cellDates: true`**，且它**自己在前 10 行里按
    「映射字段数」打分定位表头行** —— `parseFile` 的「表头固定在某一行」模型表达不了。
  - `cellDates` 各文件取值不同（H1 传 `true`，6 个传 `false`，`useI1AdditionCheck` 不传），
    它直接决定日期单元格是 `Date` 还是序列号。

  把这些开关全塞进 `parseFile` 会让它变成「什么都能干因而什么都不保证」的函数。

  ### 交付：新增 L1-7/8 两个**低层薄封装**

  `readSheetAoa(file, opts)` / `readSheetObjects(file, opts)`，`ReadSheetOptions` 透传
  `cellDates` / `defval` / `raw` + sheet 三级定位 + `maxRows`。职责只有一个 ——
  **把库调用收敛进单一入口**，语义与直接调 SheetJS 逐项相同（守卫判据就是「与手写
  `read` + `sheet_to_json` 的结果逐项相等」，而非「结果看起来合理」）。
  `readSheetObjects` 额外做原型污染防护 —— 这正是收敛的价值：防护只写一处。

  分层由此清晰：`parseFile` = 带业务约定的高层（跳示例行、固定表头、空值归 null），
  适合 B2 那类函证底稿；低层适合 B3 这类「自己完全掌控解析」的 composable。

  ### 🔴 顺带查清一个 SheetJS 行为（留证防下轮误判）

  列头叫 `constructor` / `__proto__` 时，`sheet_to_json` 对象模式**改名而非跳过**：
  实测得键 `["__rowNum__","constructor_NaN","prototype","__proto___NaN","正常列"]`
  （它用 `key in obj` 判重，命中原型链就加后缀，后缀算成了 `NaN`；`prototype` 因
  `'prototype' in {}` 为 false 而保持原名）。两个结论：①原型污染在这条路径上被 SheetJS
  自己规避了，`Object.prototype` 实测未被污染 —— `_BLOCKED_KEYS` 在此是第二道防线，
  它在 `parseFile` 的「AOA → 自建对象」路径上才是唯一防线；②**数据会落到
  `constructor_NaN` 这种意外键名下**，调用方按 `r['constructor']` 取值得 undefined。
  这是既有行为，不在收敛中改，但已写进守卫注释留证。

  ### 实测

  - 裸 import **30 → 22**，调用点 **57 → 42**；8 文件 `get_diagnostics` 全零
  - 新增守卫 8 例（含「与手写 SheetJS 逐项相等」「defval 透传」「cellDates 两态」「raw:false」四条关键项），`useExcelIO.newApi.spec.ts` **35/35 全绿**
  - 定向跑名称含 depreciation 的 **9 例全通过**；扩大到 965 个测试文件的 13916 例中，B3 八文件**无一出现在失败列表**
  - 同批 161 例失败经 grep 确认与本改动无关（`useK10/K13FormulaEngine` / `useK12Adjustment` / `useCControlTestData` / `useAgingConfig` 等**均不 import useExcelIO**，属并发会话的 K 循环与 L2/L4 披露 spec）
  - 5 个逐字同构文件用带**命中数校验**的脚本批量改写（命中 ≠1 即中止不写盘 + 兜底断言「不得再有任何 `XLSX.` 引用」），其余 3 个手工

  ### 立项时的原始计划（保留以对照）

  - `useH1` / `useH3` / `useH8`×3 / `useI1`×3，均 `json_to_sheet` + 取第一个 sheet
  - 写 → `exportData`（覆盖 `json_to_sheet` 语义，不新增 API）；读 → `parseFile` 对象模式
  - _Requirements: 2.1, 2.6, 3.5, 6.1, 6.2_

- [x] 12. 迁移 B4 consolidation 5 文件（依赖 Task 8）

  - `ConsolNoteTab.vue`（9 调用点，本批重心）· `ShareChangeSheet.vue`（唯一 `sheetMatcher` 用例）· `ConsolTrialBalanceTab.vue` · `EquitySimSheet.vue` · `NetAssetSheet.vue`
  - `ShareChangeSheet.vue` 的模糊查找 `sn.includes(comp.name) && sn.includes('净资产')` 迁到 `sheetMatcher`

  ### 交付与实测（2026-08-12）

  - **全批 5 文件 / 15 调用点收敛完毕**，计数 22 文件 / 42 点 → **17 文件 / 27 点**（xlsx 18 → 13，exceljs 仍 4）。五文件 `get_diagnostics` 均零错误。
  - 守卫套件：**78 通过 / 1 失败**，唯一失败是终态守卫「生产文件零裸 import」（尚有 17 个），属预期红。

  ### 🔴 补出 L1-9 `readWorkbookAoa`（立项时未预见的第 9 项能力）

  立项时以为 B4 的读侧靠 `sheetMatcher` 就够。实测发现有两处是**跨 sheet 匹配导入**：
  `ShareChangeSheet.onFileSelected` 要在「公司数 × 3」个 sheet 里逐家模糊匹配，
  `ConsolNoteTab.onNoteBatchImport` 要遍历全部 sheet 匹配章节标题。`sheetMatcher` 只能
  定位**一个** sheet，`readSheetAoa` 也只返回一个。

  拒绝「多次调 `readSheetAoa`」：那会对同一文件重复 `arrayBuffer()` + `read()` N 次
  （N = 公司数 × 3），而原实现只 read 一次 —— 既慢也不等价。故补 `readWorkbookAoa`
  一次解析返回 `{sheetNames, sheets}`。

  这个「只解析一次」是该 API 存在的唯一理由，故**单独写了守卫钉死**（spy 计数
  `arrayBuffer` 调用次数 === 1）：一旦有人把实现改成内部循环调 `readSheetAoa`，
  理由就被抹掉，该条必须打红。变异 M9 已验证。

  ### 迁移中的发现（均按严格等价原则未改）

  - **`EquitySimSheet.vue` 的注释自证了封装缺口**：原注释 `// Use raw XLSX for the instruction sheet + data sheet combo`，明说是因为要组合「说明 sheet + 数据 sheet」才绕开封装。Task 4 补出的 L1-5（多 sheet 支持纯 AOA 形态）已消除这个理由，注释连同裸 import 一并移除。`NetAssetSheet.vue` 是同一形态。
  - **`ShareChangeSheet.vue` 有死 import**：已 `import { parseFile }` 但全文零调用 —— 上一轮收敛没做完的痕迹，按「死代码立即删除」铁律清掉。
  - **`ShareChangeSheet.vue` 有重复代码**：`exportTemplate` 与 `exportData` 的「公司三类 sheet」构造是逐字符相同的两份复制，抽成 `buildCompanySheetDefs()` 消除。
  - **`ConsolNoteTab.uniqueSheetName` 名不副实**：它把名字 `add` 进 `usedNames` Set 但**从不检查**是否已存在，根本没去重。迁移当时按严格等价原则未动（它内部已 `substring(0,31)`，故封装内 `slice(0,31)` 是无操作，等价成立）。**2026-08-14 已修 + 加守卫**，见文末「收尾修复」。

  ### 变异检验（新增 3 条，全 RED）

  - `M9` `readWorkbookAoa` 改成逐 sheet 重新解析 → RED（命中「只解析一次」）
  - `M10` 空 sheet 返回 `undefined` → RED（命中「空 sheet 返回空数组」）。注意此条变异不能写成改 fallback 分支：空 sheet 走的是 `sheet_to_json` 返回 `[]` 那条路，fallback（`ws` 为 undefined）只在损坏文件时才走到。
  - `M11` `sheetNames` 排序 → RED（命中「保持工作簿内顺序」）
  - _Requirements: 2.1, 2.6, 3.2, 6.1, 6.2_

- [x] 13. 迁移 B5 exceljs 4 文件（~~唯一换引擎批~~ → 实测改为「入口收两个引擎」）

  - `GtB30GroupAudit.vue`(3 点) · `useB23ImportExport.ts`(3 点) · `D2TabAnalysis.vue`(2 点) · `components/formula/exportFormulaTemplate.ts`(1 点)
  - 🔴 `exportFormulaTemplate.ts` 是第一轮未剥注释漏掉的文件（`import(/* @vite-ignore */ 'exceljs')`）。其文件头注释写明它是为规避「巨型 `FormulaManagerDialog.vue` 动态导入 exceljs 致 Vite import-analysis 解析失败」而拆出的独立文件 ⇒ 迁移后须**验证该规避是否仍必要**，不得直接删 `@vite-ignore` 了事
  - `writeBuffer` → `exportToBytes` / `exportMultiSheetToBytes`
  - 🔴 判据为**语义等价**（同一 reader 读回后比对单元格值/列宽/sheet 名），**禁止比对 sha256** —— ExcelJS 与 SheetJS 的 ZIP 条目顺序与 styles.xml 结构必然不同，用 sha256 会让本批永远红进而诱使改松守卫

  ### 交付与实测（2026-08-12）

  - **全批 4 文件 / 9 调用点收敛完毕，exceljs 归零**。计数 17 文件 / 27 点 → **13 文件 / 18 点**，`by_lib_files` 只剩 `xlsx: 13`。四文件 `get_diagnostics` 均零错误。
  - 新增守卫 `useExcelIO.excelJs.spec.ts`（7 例，全绿）；变异 M12 / M13 均 RED。

  ### 🔴 立项假设被实测推翻：这批**不是**换引擎批

  立项写的是「B5 = 唯一换引擎批（ExcelJS → SheetJS）」。实测后改为**入口收两个引擎**：
  补出 L1-10 `createExcelJsWorkbook` / `loadExcelJsWorkbook` 两个薄 loader，
  库 import 收进入口而**引擎不变**，故调用方语义逐行不变、严格等价自动成立。

  理由：收敛的目标是「库调用只在一处、CVE 与版本统一管控、将来换库只改一个文件」，
  **不是**「全项目必须用同一个库」。强行换 SheetJS 要逐条对齐五处语义差异，而这些
  风险换不来任何安全收益 —— exceljs 是独立实现，不带 xlsx 那两个永不修复的 CVE。

  #### 实测到的 ExcelJS ↔ SheetJS 语义差异（换引擎就必须逐条对齐）

  | 差异点 | ExcelJS | SheetJS AOA |
  | --- | --- | --- |
  | 中间整空行 | `eachRow` **跳过** | **保留**（给 `[]`） |
  | `row.values` | **1-based**（`[0]` 是 null） | 0-based |
  | 尾部缺列 | 不补齐 | 传 `defval` 会**补齐到最宽** |
  | 行内空单元格 | `eachCell` **不产生键** | 给 `undefined` / `''` |
  | 找不到 sheet | `getWorksheet()` → undefined | `readSheetAoa` **降级取第一个** |

  最后一条最阴：`GtB30GroupAudit` 靠 `getWorksheet('组成部分明细')` 返回 undefined 来报
  「格式不符：缺少…工作表」。直接换成 `readSheetAoa({sheetName})` 会把这个**明确报错**
  变成**静默读错 sheet**。第二条同样阴：下游 `doImport` 按 `r[1]` 取第一列，换 0-based
  后整体错列，且没有任何编译期报错。

  #### 一条硬缺失：xlsx-js-style 写入端不保留冻结窗格

  实测：用 ExcelJS 读 xlsx-js-style 产物得 `state:"normal"`，而 ExcelJS 自写自读得
  `state:"frozen", ySplit:1`（判据自检有效，故这是真实缺失而非探针问题）。
  `exportFormulaTemplate.ts` 依赖 `views:[{state:'frozen',ySplit:1}]`，换引擎必然丢功能。

  顺带纠正一个易被误导的观察：**加粗字体与列宽 xlsx-js-style 是支持的**（ExcelJS 读回
  `bold:true` / `width:20.83`）。用 SheetJS 自己读回时是空的 —— 那是**读取端**不完整
  解析样式，不是写入端丢失。只看 SheetJS 自读自验会误判成「不支持样式」。

  ### 迁移中的取舍与发现

  - **不做回调式封装**：B23 的 `exportData` 要「0 个 sheet 就走 warning 分支、不产出文件」。回调式（回调内建表、封装内部直接 writeBuffer）会让调用方失去「建完表、写出前」这个时机。故 `createExcelJsWorkbook()` 返回工作簿本体。守卫用 `createExcelJsWorkbook.length === 0` 直接钉死非回调式。
    - 附带修正：立项时以为「空工作簿 writeBuffer 会抛错」，实测**不抛**。所以「先判断」不是防抛错，而是纯业务决策（不给用户一个空文件）。守卫的判据已据此改写。
  - **`exportFormulaTemplate.ts` 的 `@vite-ignore` 规避已不必要**（Task 13 原本要求验证此项）：该注释是为规避「巨型 `FormulaManagerDialog.vue` 动态导入 exceljs 致 Vite import-analysis 解析失败」。动态 import 移进 useExcelIO 后本文件只做**静态** import，规避自然消失。
  - **`D2TabAnalysis` 省掉 FileReader 一层**：原先 `FileReader.readAsArrayBuffer` → `wb.xlsx.load(buffer)`；`loadExcelJsWorkbook` 直接收 `File`（内部 `file.arrayBuffer()`），与之等价。
  - **`D2TabAnalysis` 的 `obj[headers[colNum-1]]` 未加原型污染防护**（键来自文件）。有意不加：单层赋值时 `o['__proto__']=标量` 静默无效（与 `security.spec.ts` 对 xlsx 路径的实测同理），且混进换引擎批会让问题归因困难。列为后续观察项。

  ### 变异检验（新增 2 条，全 RED）

  - `M12` `loadExcelJsWorkbook` 的 source 分流改回 `instanceof ArrayBuffer` → RED（命中 3/3）。这条复现的是**实际踩过的坑**：`toBuffer()` 返回 ExcelJS 的 `Buffer`，它**不是** `ArrayBuffer` 实例，会被误判成 File 分支而报 `source.arrayBuffer is not a function`。改按「有没有 `arrayBuffer` 方法」分流。
  - `M13` `createExcelJsWorkbook` 变回调式 → RED（命中「非回调式」）
  - 首次提交时 M12 是 **ANCHOR-MISS**（锚点缩进猜成 6 空格，实际 4 空格）。这正是四态判定的价值 —— 只看退出码会把它误判成 RED。
  - _Requirements: 2.1, 2.4, 2.6, 3.1, 6.1, 6.2_

- [x] 14. 迁移 B6 三个大文件（各自单独提交）

  - `TrialBalance.vue`（4484 行 / 3 点）· `ProcedureTrimming.vue`（3933 行 / 1 点）· `GtB22AControlMatrix.vue`（2668 行 / 1 点）
  - 三者各自独立提交，互不依赖可并行；改动面须可单独审阅

  ### 交付与实测（2026-08-12）

  - 全批 3 文件 / 5 调用点收敛完毕。计数 13 文件 / 18 点 → **10 文件 / 13 点**。三文件零诊断错误。
  - 五个调用点全是单 sheet AOA，形态与 B4 已迁的一致，无新增能力需求。
  - _Requirements: 6.1, 6.2, 6.4_

- [x] 15. 迁移 B7 其余散件 **10** 文件 + 豁免登记

  - 逐个处理剩余散件
  - 若某文件语义无法用 useExcelIO 表达 ⇒ 进 `exempt[]`（含 `reason` + `evidence`），**不得为迁就封装而改产物**
  - 更新进度基线至 0（或 `exempt[]` 长度）

  ### 交付与实测（2026-08-12）

  - **全批 10 文件 / 13 调用点收敛完毕。计数 10 → 0，`exempt[]` 为空 —— 46 个文件全部收敛，无一豁免。**
  - 十文件 `get_diagnostics` 均零错误。守卫全套 **107/107 全绿**（含终态守卫「生产文件零裸 import」首次转绿）。
  - 变异 **13/13 全 RED**。

  ### 补出两项能力

  - **L1-11 `ExcelJsonSheetDef`（`json_to_sheet` 形态）**：`ReportLineMappingDialog`（3 sheet）与 `LedgerBalanceTreeView` 原本传对象数组给 `json_to_sheet`。拒绝让调用方自己转 AOA —— `json_to_sheet` 的表头是**所有**对象键的并集（按首次出现序），手写 `Object.keys(data[0])` 在对象键不齐时会**静默漏列**，空数组时还直接抛错。原样透传才等价。
  - **L1-12 `ReadSheetOptions.blankrows`**：`GtCustomWpBatchDialog` 显式传 `blankrows: false`。注意该选项的默认值随 `header` 而变（`header:1` 下 SheetJS 默认**保留**空行），故必须能透传。

  ### 三处「封装默认口径与调用方不同」的处理

  这批暴露出一类风险：封装的统一口径对个别调用方是**错的**，机械替换会静默改行为。

  - **`ExcelImportPreviewDialog` 降级取「最后一个」sheet**（注释写明是为跳过「填写说明」），而封装统一口径是降级取**第一个**。用 `readWorkbookAoa` 自己选 sheet 名，没有硬套 `readSheetAoa`。
  - **`GtCustomWpBatchDialog` 要区分「没有任何工作表」**（给 `excelError` 明确文案）。`readSheetAoa` 在无 sheet 时给不出可区分信号，同样改用 `readWorkbookAoa`。
  - **`ReportLineMappingDialog.onImportTemplate` 是 el-upload 的 `before-upload` 钩子，必须同步返回 `false`**。原写法 `import('xlsx').then(async ...); return false` 不等待解析就返回。若图省事把它改成 `async function`，返回值变成 resolved Promise，Element Plus 视为「允许上传」，会真往 `action`（此处未设置 = 当前地址）POST 一个无效请求。故拆成同步外壳 + async 实现。

  ### 顺带修掉的体积问题

  `C24AnomalyAccountSheet.vue` 是全库**唯一的静态 import**（`import * as XLSX from 'xlsx'`），会把 xlsx 打进主包而非按需加载。收敛后变成入口内的动态 import。
  - _Requirements: 1.4, 3.6, 6.1, 6.5, 6.6_

- [-] 16. 变异检验（37 条 Property 逐条）—— **脚本已建并跑通 14 条全 RED，待扩至全量**

  ### 已交付（2026-08-12，Wave 2 阶段提前建，因「每写完守卫必做变异检验」是硬铁律）

  - `audit-platform/frontend/scripts/mutate_excel_io_guards.mjs`（`--list` / `--run` / `--run --mid M3` / `--restore`）
  - 四态判定按**失败测试名集合差集**，不看退出码；**先跑基线并扣除既有失败项**（M6 因此只命中 2/3 预期 —— 「零裸 import」那条在基线里已红被扣除，属正确行为）
  - 锚点一律**单行**（memory：`\n` 跨行锚点在 CRLF 必 ANCHOR-MISS），且命中数须恰为 1
  - 零 GREEN / 零 ANCHOR-MISS / 零 WRONG-TEST；跑完自动还原（实测 `git diff --numstat` 仍为 +249/-28，无 `.mutbak` 与探针残留）

  ### 最终清单：14 条，**14/14 全 RED**（2026-08-14 全量重跑，基线 89 通过 0 失败）

  | ID | 变异 | 命中 |
  | --- | --- | --- |
  | M1 | 撤掉 `_BLOCKED_KEYS` 过滤 | 3/3 |
  | M2 | `customInstructionSheet` 互斥改静默择一 | 1/1 |
  | M3 | `successMessage:false` 失效 | 2/2 |
  | M4 | 列索引改回「过滤后下标」 | 2/2 |
  | M5 | 行数上限失效 | 1/1 |
  | M6 | 新增一处裸 import | 3/3 |
  | M7 | `queryExport` 列宽 16→20 | 2/2 |
  | M8 | `batchExport` 表头去掉灰底 | 1/1 |
  | M9 | `readWorkbookAoa` 改成逐 sheet 重新解析 | 1/1 |
  | M10 | `readWorkbookAoa` 空 sheet 返回 undefined | 1/1 |
  | M11 | `readWorkbookAoa` 的 `sheetNames` 排序 | 1/1 |
  | M12 | `loadExcelJsWorkbook` 分流改回 `instanceof ArrayBuffer` | 3/3 |
  | M13 | `createExcelJsWorkbook` 变回调式 | 1/1 |
  | M14 | `vertical` 改回非法值 `middle` | 1/1 |

  M6 早期只命中 2/3，是因为「零裸 import」那条当时在基线里已红被正确扣除；收敛完成后
  该条转绿，M6 现在命中 3/3 —— 这个变化本身验证了「先跑基线并扣除既有失败」的必要性。

  ### 覆盖率与缺口（如实登记，不凑数）

  **14 条 / 37 条 Property ≈ 38%**。未覆盖的主要是三类，各有具体原因：

  - **依赖 Task 2 产物快照的等价类变异**（如「给无样式调用点传 `applyStyles:true`」）——
    B2/B3/B5 的迁移前快照机会窗口已关闭（见 Task 2），无基线可比。B1 的两条
    （M7/M8）已覆盖该类判据。
  - **`删 package.json 里任一库`（R1.5）** —— 会破坏 `node_modules` 解析导致整个 vitest
    进程起不来，四态判定退化成「全红」而无法区分 RED 与基础设施故障。这类变异需要
    独立的沙箱环境，不适合挂在同一套脚本里。
  - **纯声明式 Property**（如「exempt 条目必须含 reason + evidence」）—— 判据本身就是
    结构断言，变异它等于改测试数据而非改实现，打红不说明任何问题。

  三类缺口都不是「忘了做」，而是判据形态决定的。硬凑到 37/37 会引入无意义变异，
  反而稀释信号。
  - _Requirements: 1.5, 5.2, 5.3_

- [x] 17. 豁免 stale 检测 + CI 挂载

  - `exempt[]` 里的文件若实际已无裸 import ⇒ 守卫打红要求移出
  - `governance-checks.yml` 新增 job 覆盖本 spec 全部守卫；`yaml.safe_load` 可解析且无重名 job

  ### 交付与实测（2026-08-12）

  - **stale 检测**在 Task 1 建守卫时已随 Property 30 实现（`excelIoConvergence.spec.ts` 的「豁免清单 stale 检测」，覆盖「文件已不存在」与「已无裸 import」两种失效）。本轮收敛后 `exempt[]` 为空，该守卫无对象但仍在位。
  - **CI 挂载**：`governance-checks.yml` 新增 job `excel-io-single-entry-convergence`（5 步）。`yaml.safe_load` 解析通过，全文件 **144 个 job 无重名**。

  ### 为什么要独立成 job（`ci.yml` 已跑全量 vitest）

  `ci.yml` 的前端 job 确实跑 `npx vitest run` 全量，但它串在 `vue-tsc`、十几个 grep 守卫与 `build` 之间 —— 前序任一失败就到不了这里。而实测当前该 job **本就是红的**（13 个失败全部来自其他 spec 的在途工作：`buildDisclosureDraftKey is not a function`、`useAgingConfig`、g6/l0 等）。独立成 job 才能保证「收敛回退」不被别的失败掩盖。这与 `disclosure-columns-coverage` / `note-inventory-structure` 两个 job 的注释是同一理由，属项目既有惯例。

  ### 变异检验只挂 `--list`，不在 CI 执行变异

  执行变异要临时改生产代码，CI 并发环境下若异常终止 `.mutbak` 可能残留。项目里 `wp-import-export-lifecycle` job 已有同款取舍（注释原文：「真正执行变异需改文件，不适合 CI 并发环境」）。

  但那个先例的 `--list` 会**校验 expect 能匹配真实测试名**，而本 spec 的脚本原先只是打印清单 ⇒ 本轮给 `--list` 补上静态自检，校验两项：

  - **锚点在目标文件命中恰好 1 次** —— 拦「生产代码重构后锚点 stale」。本轮实测踩了三次：`M7`/`M8` 的锚点写的是 B1 **迁移前**的代码（迁移后那两行根本不存在）、`M12` 把缩进猜成 6 空格而实际是 4 空格。
  - **每条 `expect` 能在其 spec 里找到** —— 拦「测试名漂移」。这类 stale 更坏：`expect` 可能恰好匹配到**另一条**测试，于是变异「看起来 RED」但钉的不是原意，检验退化成自我安慰。

  #### 自检本身也做了反向验证（铁律：没打红 = 守卫有缺陷）

  对「清单自检」注入两个变异，均 RED 且命中预期原因，还原后回绿：

  - 把 `M9` 的锚点改成不存在的串 → RED（命中「锚点命中 0 处」）
  - 把 `M9` 的 `expect` 改成不存在的测试名 → RED（命中「在其 spec 里找不到」）
  - _Requirements: 5.6, 5.7_

- [-] 18. Playwright 实测三态 + 数据复原 —— **已抓到并修掉一个只有浏览器才暴露的真缺陷；剩余循环 UI 三态待补**

  - 实测 ≥3 个循环的「导出模板 / 导出数据 / 导入数据」三态，确认产物可被 Excel 打开且内容正确
  - 实测前抓底稿数据基线（全文 + md5），测后**逐字节复原 + 独立只读核实**
  - 清理本轮全部 `tmp_*` 诊断产物

  ### 🔴 实测抓到一个 Vite 编译错误 —— 四层静态检查全绿，只有浏览器暴露

  `ReportLineMappingDialog.vue` 的两个函数各多一个 `}`（改造中先加了裸块 `{` 又删掉，
  但结尾的 `}` 没跟着删）⇒ **Vite transform 500 → 整个 TrialBalance 路由崩**
  （console：`Failed to fetch dynamically imported module: /src/views/TrialBalance.vue`）。

  而 `get_diagnostics`（Volar）**全绿**、vitest 107/107 **全绿**、变异 13/13 **全 RED** ——
  三者都查不出。这正是 memory 铁律里「Vite transform 500 → ErrorBoundary 崩溃，
  vitest/Volar 解析方式不同故漏检，必须浏览器/CI 兜底」那一条的又一次实证。

  取错误详情的办法：直接 HTTP 请求该 `.vue` 的 Vite transform URL，500 响应体里带
  `message` + `frame`（精确到 `行:列`）。`vue/compiler-sfc` 报的位置是**函数结尾**
  而非出错的裸块处，故要顺着往上找配平。

  #### 固化成守卫：`scripts/check_vite_transform.mjs`（已挂 CI）

  既然四层静态检查都查不出这类错，就把「浏览器兜底」变成可脚本化的一步：启 dev server
  后逐文件请求 transform URL，500 响应体带 `message` + `frame`（精确到 行:列）。
  实测 **34/34 通过**（覆盖 B1~B7 全部迁移文件 + 入口）。

  比只点 UI 可靠：未被点到的文件（如 `ProcedureTrimming.vue`）同样能验。
  比 `npm run build` 实用：build 也能抓语法错，但跑全量打包（分钟级）且不定位到源文件行列。

  三处设计取舍：

  - **CI 必须用 `--from-baseline`，不能用默认的「git 改动」模式**。PR checkout 后工作树
    是干净的，`git status --porcelain` 返回空 ⇒ 脚本报「无待扫文件」退出 0 = **空转假绿**。
    `--from-baseline` 从基线 JSON 的 `_progress[].files` 读清单（单一真源，不随手抄 stale），
    并在文件被重命名/删除而基线未同步时主动报错。实测它读出 **34** 个文件，比手写清单多 9 个
    —— 手写时漏了 B2 的函证文件。
  - **用 `process.exitCode` 而非 `process.exit()`**。Windows + Node 上 `process.exit()`
    会在 fetch 的 keep-alive socket 还开着时触发 libuv assertion
    （`Assertion failed: !(handle->flags & UV_HANDLE_CLOSING)`），退出码变成
    `0xC0000409`（-1073740791）—— CI 会把「编译全通过」误判成崩溃。**首版就踩了这个**。
  - **dev server 不可达时退 2 而非 1**，与「有编译失败」区分开：否则服务没起会被读成「代码全崩」。

  ##### 这道守卫本身也做了反向验证

  给 `TbComparisonView.vue` 注入一个多余的 `}`（复现实测踩到的那种）：

  - 基线 → exit 0
  - 变异 → **exit 1 且报「编译失败」**，错误信息精确到 `(118:0)` + frame
  - 还原 → exit 0 干净

  ### 环境坑：Vite 只监听 IPv6

  首轮探测 `127.0.0.1:3030` 一直「连接被拒绝」，误判成前端没起。`netstat` 实证
  Vite 只 LISTENING 在 `[::1]:3030`，**不监听 IPv4**。故一律用 `localhost` 或 `[::1]`。
  （`start-dev.bat` 里那条「用 127.0.0.1 而非 localhost」的注释是针对**后端**的 ——
  后端只监听 IPv4，两者正好相反。）

  ### 已实测（项目「重药控股安徽有限公司_2025」，129 行真实数据）

  **① `TrialBalance.vue` 导出两态 —— 真实下载 + openpyxl 逐项核实**

  | 项 | 导出数据 | 导出模板 |
  | --- | --- | --- |
  | 文件名 | `试算平衡表_资产负债表.xlsx` | `试算平衡表模板_资产负债表.xlsx` |
  | sheet 名 | `试算平衡表` ✅ | `模板` ✅ |
  | 表头 | 8 列逐字一致 ✅ | 3 列逐字一致 ✅ |
  | 列宽 | `[21,21,15×6]` ≈ 承诺 `[20,20,14×6]` ✅ | `[13,31,17]` ≈ 承诺 `[12,30,16]` ✅ |
  | 行数 | 129（与页面一致）✅ | 129 ✅ |
  | **样式** | **零带样式单元格** ✅ | **零带样式单元格** ✅ |
  | 数据 | `BS-002 货币资金 9182572.99` ✅ | 未审数列全空 ✅ |

  列宽 +1 是 Excel 单位换算（openpyxl 的 `width` 与 SheetJS 的 `wch` 差约 1），非偏差。
  「零带样式单元格」是**三个显式关闭中 `applyStyles:false` 的直接实证** —— 若忘关，
  这里会出现仿宋三线表。

  **② 导入往返幂等（零数据变化，故无需复原）**

  把刚导出的数据文件原样导回。`trial_balance` 指纹**逐字节一致**：

  - 前：`md5=81e2dfc3972ab8737760c48ffa6c22a9` · 196 行 · 未审数合计 `4264455420.44`
  - 后：`md5=81e2dfc3972ab8737760c48ffa6c22a9` · 196 行 · `4264455420.44`

  往返幂等同时证明两件事：导出没丢精度、导入解析与匹配正确。选这个方案而非
  「导入空模板」，是因为后者会把未审数清空 —— 那才需要复原，风险无谓。

  **③ 入口全能力浏览器内直测（覆盖 B1/B4/B5/B7 用到的所有能力）**

  在真实页面里 `import('/src/composables/useExcelIO.ts')` 后逐项调用：

  - `exportToBytes` → `Uint8Array` 17004 字节 ✅
  - `exportMultiSheetToBytes`（AOA + json 两形态混排）→ 17323 字节 ✅
  - `readWorkbookAoa` → `sheetNames` 保序 `['说明','对象数组']`，AOA 正确 ✅
  - `readSheetObjects` → 对象数组正确、`blockedKeys` 为空 ✅
  - **`createExcelJsWorkbook` + `loadExcelJsWorkbook` → 冻结窗格读回 `state:'frozen'` / `ySplit:1`** ✅

  最后一条是 **B5「不换引擎」决策的浏览器实证**：冻结窗格在真实环境确实保住了，
  而 xlsx-js-style 写不出它。

  导出清单确认 16 个函数在位，含本轮新加的 `readWorkbookAoa` / `readSheetAoa` /
  `readSheetObjects` / `createExcelJsWorkbook` / `loadExcelJsWorkbook`。

  ### 🔴 实测顺带查出第二个既有缺陷：产物含**非法 OOXML**，openpyxl 打不开

  核对下载目录里的历史产物时发现 `.playwright-mcp/审定表-审定表D2-1.xlsx`
  （2026-06-20 导出，**早于本轮改动**）openpyxl 直接读不出来：

  ```
  ValueError: Value must be one of {'top','bottom','distributed','justify','center'}
  → Unable to read workbook: could not read stylesheet
  ```

  根因：`applyExcelStyleTemplate` 写的是 `vertical: 'middle'`（CSS 的写法），
  而 OOXML 的 `ST_VerticalAlignment` 只认 `top`/`center`/`bottom`/`distributed`/`justify`。

  #### 后果比「样式不生效」严重得多

  Excel 容忍非法值并静默忽略，但**严格读取器拒绝打开整个文件**。而本项目后端有
  **674 处 openpyxl** —— 「前端导出模板 → 用户填 → 后端解析」这条路上，只要用户
  没在 Excel 里重存过（Excel 保存时会修正非法值），后端就读不了。

  #### 对照实验（同内容只改这一个值）

  | vertical | styles.xml | openpyxl |
  | --- | --- | --- |
  | `middle` | `vertical="middle"` | 🔴 拒绝打开整个文件 |
  | `center` | `vertical="center"` | ✅ 正常读取 |

  #### 影响面：12 个调用点

  脚本按「调用 `exportData`/`exportTemplate`/`exportMultiSheetData`/`exportToBytes`/
  `exportMultiSheetToBytes` 且选项里**没有** `applyStyles`」统计：**57 个显式传、
  12 个走默认值**。走默认的那 12 个全部产出非法文件：

  `MultiYearCompare` · `GtA1Dashboard` · `GtA2AdjustmentConsole` ·
  `GtA3ConsolidationConsole` · `WorkpaperHtmlTable` · `useK1WriteoffImportExport`(×2) ·
  `I2TabAnalysis` · `I2TabImpairment` · `I2TabWorkHourCheck` · `useAProgramPopups` ·
  `useTableToolbar`

  其中 `useTableToolbar` 是**通用工具栏**、`WorkpaperHtmlTable` 是**底稿 HTML 表格
  通用导出** —— 二者被大量表格复用，实际影响面远大于 12 个调用点。

  本轮迁移的 22 个文件全部显式 `applyStyles:false`，故**不受影响**（同目录下本轮
  导出的两个试算平衡表文件 openpyxl 读取正常，与 6-20 那份形成对照）。

  #### 为什么这个当场修了，而 `uniqueSheetName` / `batchExport` 孤儿链当时没修

  （`uniqueSheetName` 后来在「收尾修复」段一并修掉，见文末；`batchExport` 孤儿链仍待
  用户裁决 —— 删功能还是接线，不是我能替代的决策。）

  三者都是实测发现的既有缺陷，但性质不同：

  - **本条是「一个枚举值写错」**，修复方向唯一（`middle` → `center`），无设计取舍；
    且后果是「产物无法被标准工具读取」= 功能缺陷，不是外观偏好。
  - 另两条涉及**功能层决策**（要不要真去重、孤儿功能接线还是删除），超本 spec 半径。

  修它确实会改变外观 —— 但方向是「让原本写坏的意图生效」：非法值被 Excel 忽略后用的
  是默认垂直对齐，改对后才真的垂直居中。且本 spec 刚把全部导出收敛到这一处，
  是修它成本最低的时刻；不修则等于用「单一入口」把缺陷固化下来。

  #### 守卫与验证

  - 常量收敛为 `_STYLE_VERTICAL`（两处内联写法都改为引用它），附完整根因注释。
  - 新增 3 例守卫（`useExcelIO.excelJs.spec.ts`）。判据是**真写出字节后解 zip 读
    `styles.xml`**，逐个校验 `vertical` / `horizontal` / border style / patternType
    是否在 OOXML 合法枚举里 —— 不是断言源码常量（那是 grep 式守卫，常量对了但某处
    内联写死仍会漏）。
  - **变异 M14 = RED**（改回 `middle` 必打红，命中 1/1）。
  - **openpyxl 端到端验证**：走默认样式的产物现在可正常解析，且三线表边框
    （medium top / thin bottom / 末行 medium）、加粗、对齐全部保留。验证脚本
    **从源码正则读取 `_STYLE_VERTICAL` 的实际值**而非手抄，避免自证。

  **④ B7 组件 UI 三态实测 —— `C23SampleSheet`（C23-2 控制测试样本）**

  C 循环 → C23「会计分录 - 控制测试」→ C23-2 Tab → 样本表自带「导入导出 ▾」，
  三态菜单齐全。两态真实下载 + openpyxl 核实：

  | 项 | 导出模板（空表） | 导出数据（含已填） |
  | --- | --- | --- |
  | 文件名 | `C23-2_控制测试样本_模板.xlsx` ✅ | `C23-2_控制测试样本_数据.xlsx` ✅ |
  | sheet 名 | `C23-2 样本` ✅ | `C23-2 样本` ✅ |
  | 表头 | 11 列逐字一致 ✅ | 11 列逐字一致 ✅ |
  | **显式列宽** | **无 `!cols`** ✅ | **无 `!cols`** ✅ |
  | 行数 | 25（序号 1..25、其余列全空）✅ | 25 ✅ |
  | 样式 | 无加粗 ✅ | 无加粗 ✅ |

  「无 `!cols`」是这个组件的关键验证点：原代码**没设列宽**，故迁移时故意不传
  `colWidths`。若图省事让封装算自适应列宽，产物就变了 —— 实测确认没变。

  ### 环境坑（本轮踩到两次，都不是代码问题）

  - **端口被占时新起的后端静默失败**：`start-dev.bat` 起的后端仍在跑，我另起一个
    进程绑定 9980 得 `WinError 10048`（端口只允许用一次）后退出，而端口仍 LISTENING
    ⇒ 看起来「后端在跑」但实际是旧进程。
  - **后端 hang 时表现为 TimeoutError 而非 ConnectionRefused**：端口 LISTENING 但不
    响应任何请求，页面全白。判据是「`urlopen` 超时」而不是「连接被拒」—— 后者才是
    「没起」。杀掉 PID 重起即恢复。

  ### 待补

  - B4（consolidation）的组件 UI 三态。该模块需要多家公司的合并报表数据，当前项目
    无此数据，页面走空态。已由「入口全能力浏览器直测 + 34 文件 Vite 编译全通过」覆盖。
  - `C24AnomalyAccountSheet` 的导出未点到：C24-4 异常账户 Tab 在「未导入分录」空态下
    不渲染自己的导出入口（页面本身 0 console 错误、渲染正常）。
  ### ⚠️ 一条曾登记为「缺陷」的观察，核实后**是误判**（撤回，留证防下轮重犯）

  上一轮我记下：「`C24-分录导入模板.xlsx` 的 sheet 顺序是 `['分录明细', '编制说明']`
  —— 说明 sheet 在最后，而 `ExcelImportPreviewDialog` 的降级规则是「取最后一个以
  跳过填写说明」，对这种模板恰好取错」。

  核实后不成立，两个原因：

  1. **那个模板与该组件无关**。`ExcelImportPreviewDialog` 的真实调用方只有 3 个
     （`SubsidiaryInfoSheet` / `InvestmentCostSheet` / `InvestmentEquitySheet`，均在
     合并报表模块），它们的模板由 `exportTemplate({ includeInstructions: true })`
     生成 ⇒ sheet 顺序是 `['填写说明', '数据填写']`，**说明在前、数据在最后**
     （Task 6 的守卫正钉着这个顺序）。故「取最后一个」对这套模板恰好是对的。
     C24 的分录导入是另一套自有解析逻辑，不经此组件。
  2. **降级路径根本不触发**。三个调用方全部显式传 `sheet-name="数据填写"`，精确匹配
     总能命中；降级只在用户另存时改了 sheet 名才走到，那时「取最后一个」仍是更优猜测。

  教训：判断「某个降级规则是否错」必须先查**该组件的真实调用方与它们的模板形态**，
  不能拿手边任意一个模板文件去套。手边那个恰好来自另一条代码路径。
  - _Requirements: 5.8_

---

## 收尾修复（2026-08-14，收敛完成后处置登记在册的既有缺陷）

迁移过程中共登记 4 处「超本 spec 半径」的既有缺陷。逐条核实后：**2 处修掉、
1 处核实为误判撤回、1 处需用户裁决**。

### ① `ConsolNoteTab.uniqueSheetName` 名不副实 → 已修 + 守卫

**问题**：函数名承诺去重，实现里却只 `usedNames.add(name)` 而**从不检查**是否已存在。
一旦两个名字截断到 31 字符后相同，`book_append_sheet` 抛错 ⇒ **整批附注导出失败**
（不是少一个 sheet）。

**实测风险为零，但隐患是真的**：拉真实数据核算 —— **282 个 section、18 个被截断、
零重复**。因为 `prefix`（如 `4.3`）由唯一 `section_id` 派生且位于名字最前，不同章节
前几个字符就不同。所以我最初登记的「会抛错」在当前数据下不成立。

**仍选择修而非删死参数**：这个「撞不上」依赖章节编号体系的形态 —— 编号变长
（如 `五-10-11-12-13`）或前缀改成非唯一就会失效，而后果是整批导出挂掉。既然函数名
已承诺去重，实现它（3 行）比删参数更符合意图。

实现要点：撞名时加 `~n` 后缀，且**为后缀预留位置后再截断** —— 否则拼完又超 31，
Excel 侧仍拒绝。这是加后缀去重最容易漏的一步，故单列一条守卫。

#### 守卫 `components/consolidation/__tests__/consolNoteSheetName.spec.ts`（6 例全绿）

`uniqueSheetName` 是 `.vue` 的 `<script setup>` 内部函数、未 `defineExpose`，无法 import。
两条路：mount 整个 `ConsolNoteTab`（要 mock 十几个 composable），或在测试里维护一份
同算法副本。选后者，但补上它的致命弱点 ——

**最后一条测试直接读生产源码**，校验三行关键实现仍在、且未回退成「只 add 不 check」。
没有这条，副本就会悄悄漂移：生产代码改坏了而测试还全绿。

#### 变异 M15 / M16 均 RED，且**只命中「源码一致性」那一条**

这个「1/1 而非 2/2」的结果本身是重要信息：变异改的是生产源码，而行为类测试跑的是
副本 ⇒ 行为测试**不会**因生产代码变坏而变红。**「源码一致性」那条兜底测试是不可省的**
—— 没有它，变异生产代码时全部测试都绿，守卫完全失效。expect 已据此收窄为一条，
免得每次显示 1/2 让人误以为守卫有缺陷。

### ② 样式模板写出非法 OOXML（`vertical: 'middle'`）→ 已修 + 守卫

见 Task 18。这条是 Playwright 实测顺带查出的，影响 12 个走 `applyStyles` 默认值的
调用点，产物 openpyxl 打不开（后端 674 处 openpyxl 连带）。

### ③ `ExcelImportPreviewDialog` 取最后一个 sheet → **核实为误判，撤回**

见 Task 18 内「一条曾登记为『缺陷』的观察」。真实调用方只有 3 个（合并报表模块），
它们的模板 sheet 顺序是 `['填写说明', '数据填写']` ⇒「取最后一个」恰好正确；且三者
都显式传 `sheet-name="数据填写"`，降级路径根本不触发。我当初拿了一个来自**另一条
代码路径**的模板（C24 分录导入）去套，属判断失误。

### ④ `batchExport.ts` 孤儿链 → **用户裁决「没用就删」，已整链删除**

`utils/batchExport.ts` 的 `exportBatchToXlsx` 全库零消费方；唯一可能的调用场景
`components/query/BatchQueryResultGroup.vue` 带「合并导出」按钮，但它 `emit('merged-export')`
交给父组件，而**该组件自身也零消费方** ⇒「合并导出」是一个**用户不可达的功能**。

处置有两个互斥方向（接线上线 / 删除），属产品决策。**2026-08-14 用户裁决：删。**

删除清单（连锁 6 项，逐项都要跟上否则会留下坏引用）：

1. `utils/batchExport.ts`（整文件 —— 只有 `exportBatchToXlsx` 一个函数 + 一个仅自用的 interface）
2. `components/query/BatchQueryResultGroup.vue`
3. `_baseline/equivalence/b1-batchExport-multi.json`（等价快照，被测代码已不存在）
4. `excelIoEquivalence.spec.ts` 的 `describe('B1 · utils/batchExport.ts')` 3 例
5. 变异 **M8**
6. **`ExcelMultiSheetDef.headerStyle`** —— 这个表头样式覆写通道是本 spec **专为该文件**
   而加的（当时它是 46 个文件里唯一「原本就有样式且与三线表模板不同」的），唯一用户
   消失后即零消费方。留着会让下一个人问「这是给谁用的」。

🔴 **删除的连带代价（实测踩到）**：基线 `_progress[0].files` 仍列着已删文件，而 CI 的
Vite 编译扫描用 `--from-baseline` 读这份清单 ⇒ `collectFromBaseline()` 返 null ⇒
**CI 直接 exit 2**。已从 files 移出并加 `_files_removed_later` 记录原因；同时修了
`check_vite_transform.mjs` 把这种情况误报成「git status 失败」的问题（两条失败路径
都返回 null 但原因不同，现已分开报，否则排查方向直接跑偏）。

### 计数（2026-08-14 实测，含删除与复盘修复后）

- 守卫 8 文件 **119** 例全绿（实测值。演进：118 → 124（+6 sheet 名去重）→ 删 3 例孤儿
  等价守卫 → 删 7 例零消费方 API 守卫（`sheetMatcher` 4 + `customInstructionSheet` 4，
  其中 2 例改写保留）→ 加 3 例 OOXML + 2 例 `truncatedRows` + 1 例防护单点行为判据
  + **2 例基线清单完整性**）
- 变异 **18** 条全 RED（14 → 16 → 删 M2/M8 → 加 M17 → **加 M18/M19/M20**），
  清单静态自检 18/18 有效
- Vite 编译扫描 **46/46**（此前只 33/46 —— 漏的正是下面那 13 个）
- CI job `excel-io-single-entry-convergence` 的 vitest 步骤已挂全部 8 个守卫文件
  （含此前漏挂的 `components/query/__tests__/queryExport.spec.ts` —— 它是 R1.3
  现在唯一的断言点）

### 复盘（`semantic_reviewer` 独立视角）追加修复的 4 项

上述①~④处置完后做了一次独立复盘，又查出 4 处：

1. **CI 必然红**（上文已述，删除的连带后果）
2. **一条 grep 式假绿守卫**：`useExcelIO.security.spec.ts` 里名为「调用方不各自防护
   （Property 24 / R4.5）」的那条，实际只对**入口自己**的源码做
   `toContain('_BLOCKED_KEYS' / '__proto__' / ...)`，**从不读任何调用方** ⇒ 四条断言
   恒真、撤掉全部防护也不会红、从未参与过打红。这违反本 spec 自己的 R5.3。
   已改为**扫全部生产文件、断言无人自建危险键黑名单**（Property 24 的实际含义），
   并另加一条行为判据（三个危险键的拦截效果）。改后 M1 的打红项从 4 项增到 **5 项**。
3. **`readWorkbookAoa` 静默截断违反 R4.3**：它是四个读入口里唯一不回报截断的 ——
   调用方拿到少了行的数据却无从知晓。已加 `truncatedRows: Record<string, number>`
   （只列真正被截断的 sheet），配 2 例守卫 + 变异 **M17**。
4. **`maxRows` 同名不同义**：`parseFile` 数的是「跳过 `skipRows` 之后的数据行」，
   而低层 `readSheetAoa`/`readWorkbookAoa` 数的是「含表头的原始行」（它们不知道
   哪几行是表头）。已在两处注释里写明口径差异。

### 🔴 提交前发现的第 5 项：权威清单漏记 13 个文件（本 spec 最贵的一课）

准备 commit 时，因为工作树混着并发会话的大量改动（不能整目录 `git add`），我按
基线 `_progress[].files` 逐个精确 stage。为核对完整性，另写了一个「从 HEAD 反查
哪些文件有裸 import」的脚本对账 —— **对不上**：HEAD 里 47 个，我只 stage 了 33 个。

漏的 13 个是 `B2-14/14` 那批 confirmation 文件。它们当时**只写在 `note` 的自然
语言描述里**（"其余 13 个：GtConfirmationSummary · alternativeD06/F05/…"），
`files` 数组是空的。后果连锁三处：

| # | 后果 | 严重度 |
|---|------|--------|
| ① | 按 files 精确 stage 的脚本漏掉它们 ⇒ 远端仍带裸 import ⇒ CI 零裸 import 守卫必红 | 🔴 提交即红 |
| ② | CI 的 Vite 编译扫描 `--from-baseline` 只覆盖 **33/46**，那 13 个从未被编译验证过 | 🔴 假绿 |
| ③ | 「46 → 0」的成果在权威清单里只体现 33，进度不自洽 | 🟡 记录失真 |

**教训：写在 note 里等于没写 —— 机器读不到的记录不是单一真源。**
本 spec 前面所有守卫都在验「代码符不符合清单」，没有一条验「清单本身完不完整」。

处置：
- 补齐 13 个文件进 `files`，并加 `_files_backfilled_at` 记录这次漏记的经过
- 加顶层 `_files_deleted_not_migrated`（当前 1 项 `utils/batchExport.ts`）并写清三方
  数量关系：**HEAD 有裸 import 的生产文件 47 = files 并集 45（不含入口）+ 已删 1 + 入口 1**
- 加 **2 条守卫**把判据落到数组上：`并集 + 已删 == initial`（含重复项检测）· `声明即已迁`
  （每项必须存在于磁盘且当前无裸 import）
- 加 **3 条变异 M18/M19/M20** 证明这两条守卫真能拦：漏记一项 / 路径写错 / 把已删文件
  塞回 files —— 实测全 RED

🔴 **过程中还踩到两个次级坑，都已在代码注释里留痕**：

1. **我的临时对账脚本第一版没剥注释**，于是漏检 `exportFormulaTemplate.ts`
   （它写的是 `await import(/* @vite-ignore */ 'exceljs')`，注释夹在 `import(` 与
   引号之间）。生产守卫**做对了**（判据要点第 1 条就记着这个坑），是我的临时脚本
   没照着做 ⇒ 印证 memory 铁律「先 stripComments」。
2. **数量相等不等于集合相等**：第一版对账显示「基线 46 / HEAD 46」看着没问题，
   做集合 diff 才发现各差一个元素（基线有 `exportFormulaTemplate.ts` 没有
   `batchExport.ts`，HEAD 反之）。故守卫不能只比数量。

---

## Notes

### 未做项与阻塞原因（均标 `[-]`，不假绿）

| 任务 | 状态 | 阻塞原因 |
|---|---|---|
| Task 2 行为等价快照（B2/B3/B5 部分） | `[-]` | **快照窗口已关闭**。基线必须在改动前抓，B2~B7 都已迁完，现在抓的是迁移后产物 —— 写进基线就是「把错值当基线锁死」（memory 假绿三源第三条）。B1 的 2 份是唯一在窗口内抓到的，已用它做 M7 变异验证有效性 |
| Task 16 变异覆盖 18/38 Property | `[-]` | 三类缺口各有判据形态原因：① 纯声明式 Property（如「三个库仍在 package.json」）变异等于删依赖，代价远超收益 ② 元守卫类（红消息可操作性）已被自身的反向自检覆盖 ③ Playwright 实测类需真实浏览器 + 底稿数据，不适合放进变异脚本 |
| Task 18 Playwright 实测（B4 / C24-4） | `[-]` | B4 consolidation 需多公司合并数据（当前项目无）；C24-4 空态不渲染导出入口。已实测的 3 个循环覆盖了「导出模板 / 导出数据 / 导入数据」三态 |

### 变异不进 CI 的取舍

CI 只挂 `--list`（清单静态自检：锚点唯一命中 + expect 能匹配真实测试名），不跑 `--run`。
理由：执行变异要改生产代码，CI 并发环境异常终止会留 `.mutbak` 残留污染工作树。
项目既有 job `wp-import-export-lifecycle` 已有同款取舍，保持一致。

`--list` 不是装饰 —— 它抓到过一次真实的 stale：M10 的锚点在「加 `truncatedRows` 回报」
的重构后从单行三元表达式变成了 if/continue + slice 两段，静态自检当场打红。

### CI 必须用 `--from-baseline`

Vite 编译扫描的默认模式是「扫 git 改动的文件」，在 PR checkout 后工作树是干净的
⇒ 报「无待扫文件」退 0 = 空转假绿。故 CI 显式传 `--from-baseline` 从进度基线读清单。

🔴 这条与 R6.7 强耦合：基线 `files` 漏记会直接让编译扫描覆盖面缩水（实测漏 13 个
文件时只扫了 33/46）。删文件后忘了同步 `files` 更严重 —— `collectFromBaseline()`
返 null ⇒ CI 直接 exit 2。两条失败路径（git 失败 / 清单含不存在的文件）此前都返 null
但不报原因，排查方向会跑偏，现已分开报。
