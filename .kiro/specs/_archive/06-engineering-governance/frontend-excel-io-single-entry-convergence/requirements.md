# Requirements Document

## Introduction

把前端散落各处的裸 Excel 库调用收敛到 `composables/useExcelIO.ts` 单一入口。

**动因不是「封装更好看」，而是一条无法通过升级消除的存量债**：`xlsx@0.18.5` 是 SheetJS 在 npm 上的最后一版（SheetJS 已撤出 npm 改为 CDN 分发），它带 CVE-2023-30533（prototype pollution，上游 0.19.3 修复）与 CVE-2024-22363（ReDoS，上游 0.20.2 修复），而这两个修复版**永远不会进 npm**。项目当前有 **25 处** `read(buf, { type: 'array' })` 在读用户上传的 xlsx，散落 25 个文件，每一处都是独立的攻击面入口。收敛到单一入口后，防护只需做一次。

### 实证台账（2026-08-12 两轮扫描，`audit-platform/frontend/src`）

口径：`.vue` + `.ts`，**先 `stripComments()` 再匹配** `(?:from|import\()\s*['"](xlsx|xlsx-js-style|exceljs)['"]`。分三桶。

| 桶 | 文件 | 调用点 | 说明 |
|---|---|---|---|
| **prod 待迁移** | **46** | **93** | 本 spec 的作业面 |
| test 豁免 | 3 | 4 | 需 mock 真实库，按路径豁免 |
| entry 单一入口 | 1 | 2 | `useExcelIO.ts` 自身 |
| 合计 | **50** | **99** | |

| 项 | 数 | 口径 |
|---|---|---|
| 按库分布（prod） | xlsx **41** / exceljs **4** / xlsx-js-style **1** | 合计 46，无文件跨库 |
| 形态分布（生产） | 读+写 **24** / 只写 **15** / 只读 **7** | |
| 已混用 `useExcelIO` 却仍裸 import | **6** | 这 6 个是封装能力不足的直接证据 |
| 走 `useExcelIO` 且零裸 import 的文件 | **33** | 不在本 spec 作业面，仅作零回归基线 |

读侧形态：`read type:'array'` 25 次/25 文件 · `sheet_to_json` 对象模式 12 次/12 文件 · `sheet_to_json({header:1})` 11 次/7 文件 · exceljs `xlsx.load` 3 次/3 文件。

写侧形态：`writeFile` 37 次/26 文件 · `writeFileXLSX` 23 次/13 文件 · `writeBuffer` 4 次/3 文件 · `!cols` 88 次/28 文件。

### 🔴 不剥注释会漏文件（实证，这条决定了扫描口径）

第一轮 python 扫描**未剥注释**，报 exceljs 3 文件；换成先 `stripComments()` 的口径后是 **4 文件**。漏掉的是 `components/formula/exportFormulaTemplate.ts`，它写的是：

```ts
const ExcelJS = await import(/* @vite-ignore */ 'exceljs')
```

注释夹在 `import(` 与字符串之间，`import\(\s*['"]` 的 `\s*` 匹配不到 ⇒ 静默漏掉。**⇒ 扫描口径必须 `stripComments()` 前置**，且该剥离函数自身要有反向自检。

同一原因让 `useExcelIO.ts` 的调用点从 3 降到 2：它文件头注释里写着「其余 18 处 `import('xlsx')` 调用不动」，不剥注释会把这句说明数成真实 import。

**兜底扫描已排除更奇特的漏网写法**：宽口径搜「提到三个库名但主正则未命中」的文件得 11 个，逐个核对**全是误报** —— 均为把 `'xlsx'` 当文件扩展名用（`accept=".xlsx"`、后缀判断、图标映射）。`require('xlsx')` 形态 **0 命中**。故主正则口径完备，无变量式/拼接式动态导入。

### 立项探针的两处误报（已修正，写在这里防下轮重复踩）

第一轮宽泛正则给出的两个「高频能力缺口」经精查**均不成立**：

- **`sheet_names` 31 文件 → 真缺口 2 文件**。27 次 `SheetNames` 用法里 **26 个文件只是 `wb.Sheets[wb.SheetNames[0]]` 取第一个**，`parseFile` 的降级逻辑（找不到指定 sheet 则取第一个）早已覆盖。真需特殊定位的只有 `ShareChangeSheet.vue` 的模糊查找 `SheetNames.find(sn => sn.includes(comp.name) && sn.includes('净资产'))`；`ExcelImportPreviewDialog.vue` 的按名精确查找 `parseFile` 已支持。
- **`!cols` 88 次/28 文件是调用形态差异，不是能力缺口**。实测形态只有两种：等宽（`headers.map(() => ({ wch: 16 }))`）与按标题长度（`Math.max(col.length * 2, 12)`）。两者都能用 `ExcelColumn.width` 表达，且 `useExcelIO.computeColumnWidth` 的 CJK 双宽感知比它们手写的更准。

### 迁移不是机械替换（关键约束的实证）

`GtConfirmationWealthList.vue` 的模板示例行首列是 `'E0-6-1'` 而非 `'示例'`，而 `parseFile` 默认 `skipExamplePrefix: '示例'` 检查的是 `rawRow[0]` —— **默认规则不会命中这一行**。若机械替换，示例行会被当成真实数据导入。示例行判定、判重键、金额清洗规则每个文件各不相同，必须逐文件核对。

### 范围边界

- **只做前端**。后端 `openpyxl` 有 **674 个 import 点**，与本 spec 无关，不得顺手改。
- **不换底层库**。是否用 hucre 等替代 SheetJS 是独立议题；本 spec 的产出恰好是「换库时只需改一个文件」的前置条件。
- **不统一产物样式**。当前三套样式并存（无样式 / 加粗灰底 / 仿宋三线表），统一涉及事务所交付物外观，属独立议题。本 spec 严格**行为等价**。

---

## Glossary

- **单一入口**：`composables/useExcelIO.ts`，唯一允许 import xlsx / xlsx-js-style / exceljs 的生产文件。
- **裸 import**：在 useExcelIO 之外直接 `from 'xlsx'` 或 `await import('xlsx')`（含 xlsx-js-style / exceljs）。
- **次级封装**：~~`components/query/queryExport.ts`（三方复用的查询导出工具）与 `utils/batchExport.ts`（多 sheet 合并导出）~~ → **只剩 `queryExport.ts`**。它是合法的领域封装，已改为内部调 useExcelIO 并保留其领域 API 与调用方。
  - 🔴 **2026-08-12 实测补正 + 2026-08-14 处置**：`utils/batchExport.ts` 的 `exportBatchToXlsx` **全库零消费方**；唯一可能的消费场景 `components/query/BatchQueryResultGroup.vue`（带「合并导出」按钮，`emit('merged-export')`）**自身也零消费方**，除 `components.d.ts` 自动声明外无任何页面 import ⇒ 完整孤儿链，「合并导出」是用户不可达功能。
  - 立项时按「收敛不删除」处置（已迁移完毕并验证等价）；**2026-08-14 经用户裁决改为直接删除** —— 孤儿链的「接线上线 vs 删除」是产品决策，用户选了删。连带删除：该组件、`b1-batchExport-multi.json` 等价快照、变异 M8、以及 `ExcelMultiSheetDef.headerStyle`（那个表头样式覆写通道是**专为它**而加的，唯一用户消失后即零消费方）。
- **行为等价**：迁移前后产物的单元格值、列宽、样式、sheet 名与顺序、文件名逐项相同；导入侧对同一输入文件解析出的行集相同。
- **形态**：调用点是读、写、还是读+写。
- **AOA**：array-of-arrays，`sheet_to_json(ws, { header: 1 })` 与 `aoa_to_sheet` 使用的二维数组结构。

---

## Requirements

### Requirement 1: 裸 import 收敛到单一入口

**User Story:** 作为维护者，我要 Excel 库只在一个文件里被 import，这样换库、打补丁、加防护都只改一处，而不是找遍 46 个文件。

#### Acceptance Criteria

1.1. WHEN 扫描 `audit-platform/frontend/src` 下全部 `.vue` 与 `.ts` 生产文件 THEN 除 `composables/useExcelIO.ts` 与显式豁免清单外 SHALL 不存在 xlsx / xlsx-js-style / exceljs 的 import。
1.2. 测试文件（`__tests__/` 目录下或 `*.spec.ts`）SHALL 豁免，因其需 mock 真实库；豁免判据用**路径**而非符号名。
1.3. 次级封装 `queryExport.ts` SHALL 改为内部调用 useExcelIO 并保留其领域 API 与调用方，不得删除后让调用方直连 useExcelIO。
  - 🔴 **2026-08-14 修正**：原文含 `batchExport.ts`，但它经实测是**零消费方孤儿链**（见上方术语段），已按用户裁决删除。本 AC 现在只约束 `queryExport.ts`（它有真实调用方 CustomQueryDialog / CustomQueryTab）。「有真实调用方的领域封装不得删」这条原则不变 —— 变的是 `batchExport.ts` 不符合「有调用方」这个前提。
1.4. 无法收敛的文件 SHALL 进显式豁免清单，每条含 `reason` 与 `evidence`；清单条目数 SHALL 有上限且只许下调。
1.5. 迁移完成后 `xlsx` / `xlsx-js-style` / `exceljs` 三者 SHALL 仍保留在 `package.json`（useExcelIO 内部使用），不得因「看起来没人用了」而移除。
1.6. WHEN 新增代码引入裸 import THEN 守卫 SHALL 打红并给出「请改用 useExcelIO」的可操作提示。

### Requirement 2: 迁移必须行为等价

**User Story:** 作为审计师，我导出的底稿在这次重构前后必须一模一样 —— 列宽、字体、sheet 名、文件名都不能变，因为这些文件要归档进审计档案。

#### Acceptance Criteria

2.1. WHEN 同一调用点在迁移前后各导出一次 THEN 两份产物的全部单元格值 SHALL 逐格相等。
2.2. 产物的列宽（`!cols`）SHALL 逐列相等；原本无列宽设置的产物迁移后 SHALL 仍无列宽设置。
2.3. 产物的单元格样式 SHALL 保持：原有样式的保持原样式，原本无样式的 SHALL NOT 因走封装而被添加三线表样式。
2.4. 产物的 sheet 名与 sheet 顺序 SHALL 逐个相等，含多 sheet 场景（如「数据 sheet + 填写说明 sheet」的两 sheet 结构）。
2.5. 下载文件名 SHALL 逐字相等。
2.6. WHEN 同一份输入 xlsx 在迁移前后各导入一次 THEN 解析出的行集 SHALL 相等（行数、每行字段、字段值与类型）。
2.7. 示例行跳过规则、判重键、金额清洗规则 SHALL 逐文件核对后显式传参，不得套用 `parseFile` 默认值。
2.8. 用户可见的成功／失败提示文案 SHALL 逐字保持。

### Requirement 3: useExcelIO 补齐三项真缺口

**User Story:** 作为维护者，我要封装真的够用 —— 现在有 6 个文件既用了封装又绕开它，说明能力有洞，不补洞就收敛不掉。

#### Acceptance Criteria

3.1. useExcelIO SHALL 提供「返回字节而非直接触发下载」的导出变体，供需要自行处理产物的调用方使用（3 个 exceljs 文件用 `writeBuffer` 走此路径）。
3.2. `parseFile` SHALL 支持以 predicate 定位 sheet（`ShareChangeSheet.vue` 需按「含公司名且含净资产」模糊匹配）。
3.3. `exportTemplate` SHALL 支持传入完整自定义的说明 sheet 内容并原样输出，SHALL NOT 叠加现有的固定通用提示与字段说明表（12 个函证文件的说明 sheet 是手写业务长文本，含「列名请勿修改」「金额口径」等条目）。
3.4. 新增 API SHALL NOT 改变既有 API 的默认行为；33 个已走 useExcelIO 且零裸 import 的文件 SHALL 零回归。
3.5. WHEN 调用方需要 `json_to_sheet` 语义（对象数组直接建表）THEN SHALL 复用既有 `exportData`，不新增 API。
  - 🔴 **2026-08-14 实测推翻**：B7 的 `ReportLineMappingDialog`（3 sheet）与 `LedgerBalanceTreeView` 是**多 sheet** 场景，`exportData` 只做单 sheet，表达不了。且不能让调用方自己把对象数组转成 AOA —— `json_to_sheet` 的表头是**所有对象键的并集**（按首次出现序），手写 `Object.keys(data[0])` 在对象键不齐时会**静默漏列**，空数组还直接抛错。故新增了 `ExcelJsonSheetDef`（L1-11，`exportMultiSheetData` 的第三种 sheet 形态）。本 AC 的意图（不为单 sheet 对象数组另开 API）仍成立，但「不新增 API」这个措辞过宽。
3.6. 补齐后的 API SHALL 覆盖清册中全部 **93** 个调用点的语义；未覆盖者 SHALL 进 R1.4 豁免清单并说明原因。
  - 立项写 96，那是**未剥注释**的第一轮扫描值。剥注释后实测 93（差异来自 `import(/* @vite-ignore */ 'exceljs')` 这类写法）。**实际结果：93 个全部覆盖，豁免清单为空。**

### Requirement 4: 单一读入口做安全加固

**User Story:** 作为平台负责人，我要读用户上传 xlsx 这条路径有防护 —— npm 上的 SheetJS 永远修不了它的原型污染漏洞，那就在我们自己的入口上拦。

#### Acceptance Criteria

4.1. WHEN 解析上传文件产出对象模式行数据 THEN `__proto__` / `constructor` / `prototype` 三个键 SHALL NOT 被写入结果对象。
4.2. 防护 SHALL 有反向自检：构造一份列头含 `__proto__` 的 xlsx，解析后 `Object.prototype` SHALL 未被污染，且该守卫在撤掉防护代码后 SHALL 打红。
4.3. 解析 SHALL 有行数上限保护，超限时截断并向调用方返回被截断的行数，而非静默丢弃或 OOM。
4.4. 加固 SHALL NOT 改变合法输入的解析结果（R2.6 的行集相等在加固后仍成立）。
4.5. 防护位置 SHALL 在 useExcelIO 内部单点，SHALL NOT 要求调用方各自防护。

### Requirement 5: 守卫、变异检验与实测

**User Story:** 作为维护者，我要这次收敛别在半年后又漂回去 —— 守卫必须真能拦住新增的裸 import，而不是写了个只查字符串的假绿测试。

#### Acceptance Criteria

5.1. SHALL 有 vitest 守卫按 **import 路径**扫描全部生产文件，断言裸 import 数为 0（豁免清单除外）。
5.2. 守卫 SHALL 通过变异检验：在任一生产文件注入一处裸 import，守卫 SHALL 打红；且打红的 SHALL 正是预期那条断言（四态判定 RED / GREEN / ANCHOR-MISS / WRONG-TEST，不看退出码）。
5.3. 守卫 SHALL NOT 用「源码里是否出现某字符串」作为行为判据；判「某调用点已收敛」须落到该文件不再 import 真实库**且**其导出/导入函数仍可被调用并产出正确结果。
5.4. SHALL 有行为等价守卫：对至少覆盖三个批次的代表文件，断言迁移前后产物的单元格值 / 列宽 / 样式 / sheet 名与顺序 / 文件名逐项相等（R2.1~R2.5）。
5.5. 行为等价基线 SHALL 用「迁移前抓取的真实产物快照」，SHALL NOT 用 HEAD-swap（并发会话会让 HEAD 漂移）。
5.6. 豁免清单 SHALL 配 stale 检测：清单里的文件一旦实际已无裸 import，守卫 SHALL 打红要求移出清单。
5.7. 守卫 SHALL 挂进 CI（`governance-checks.yml`），job 名不与既有重名且 `yaml.safe_load` 可解析。
5.8. SHALL 用 Playwright 实测至少 3 个循环的「导出模板 / 导出数据 / 导入数据」三态，确认产物可被 Excel 打开且内容正确；实测涉及的底稿数据 SHALL 在测后逐字节复原并独立只读核实。

### Requirement 6: 分批可中断且每批自洽

**User Story:** 作为维护者，93 个调用点不可能一次改完还能验证清楚，我要能一批一批来，每批都能独立验证、独立回滚。

#### Acceptance Criteria

6.1. 迁移 SHALL 按天然同构批次划分为 7 批共 46 文件：次级封装 2 · 函证组 12（`GtConfirmation*` 与 `alternative*`，均 3 调用点 / 多 sheet / `writeFileXLSX`）· H/I 循环 composables 8（`useH1` / `useH3` / `useH8`×3 / `useI1`×3，均 `json_to_sheet`）· consolidation 5 · exceljs 4 · 大文件 3（`TrialBalance.vue` 4484 行 / `ProcedureTrimming.vue` 3933 行 / `GtB22AControlMatrix.vue` 2668 行，各自单独成批）· 其余散件 12。
6.2. WHEN 任一批次完成 THEN 该批次涉及文件 SHALL 通过 `get_diagnostics` 零错误、相关 vitest 全绿、裸 import 计数按该批次文件数下降。
6.3. 每批次 SHALL 独立可回滚，SHALL NOT 出现「改了一半两个批次互相依赖」的中间态。
6.4. 大文件（>2000 行）SHALL 单独成批，SHALL NOT 与其他文件混批。
6.5. WHEN 某批次发现该文件语义无法用 useExcelIO 表达 THEN SHALL 停下并进 R1.4 豁免清单，SHALL NOT 为迁就封装而改变该文件的产物。
6.6. 裸 import 计数 SHALL 有单调下降的进度基线，每批次后更新；基线只许下调。

6.7. 进度基线 SHALL 以**机器可读的文件清单**（`_progress[].files` 数组）记录每个待处置文件，SHALL NOT 只写在 `note` 的自然语言描述里；处置为删除的文件 SHALL 进独立的 `_files_deleted_not_migrated` 清单而非留在 `files` 里；且 SHALL 有守卫断言「清单并集 + 已删清单 == 立项清点数」与「清单内每项均存在于磁盘且当前无裸 import」。
  - 🔴 **2026-08-14 补入，起因是一次真实漏记**：`B2-14/14` 那批 13 个 confirmation 文件只写在 `note` 里（"其余 13 个：GtConfirmationSummary · …"），`files` 是空数组。后果连锁三处：① 按 files 精确 stage 的脚本漏掉它们 ⇒ 远端仍带裸 import ⇒ CI 零裸 import 守卫必红 ② CI 的 Vite 编译扫描 `--from-baseline` 只覆盖 **33/46**，那 13 个从未被编译验证 ③「46 → 0」在权威清单里只体现 33。
  - 本 spec 此前所有守卫都在验「代码符不符合清单」，**没有一条验「清单本身完不完整」** —— 这是判据形态上的盲区，不是疏忽。
  - 守卫不得只比数量：实测曾出现「基线 46 / HEAD 46」看着自洽，做集合 diff 才发现各差一个元素（基线有 `exportFormulaTemplate.ts` 缺 `batchExport.ts`，HEAD 反之）。
