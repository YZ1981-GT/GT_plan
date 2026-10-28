# 设计：表格按 Excel 方式呈现与编辑

## 1 现状（2026-10-27 现算）

### 1.1 规模

探针按「最内层 `el-table-column` 块 + 原生 `<table>` 块内的编辑控件标签」统计（`.vue` 模板，口径：标签名精确匹配）：

| 项 | 数 |
|---|---|
| 含 el-table 的文件 / el-table 标签 | 1325 / 2244 |
| 单元格编辑控件 | 7971（el-input 4092、el-input-number 2188、el-select 1194、el-date-picker 260、el-checkbox 175、el-switch 52、el-radio-group 10） |
| 其中 `components/workpaper` | 约 97% |
| 绑定方式 | `:model-value` 4818、`v-model` 3124 |
| 控件上的事件 | `@change` 6076、`@input` 259、`@blur` 100（35 个文件，多数读 `e.target.value` 保存） |
| el-input-number 精度 | 无 1409、2 → 630、4 → 94、0 / 6 各 19、1 → 10 |
| el-date-picker | type=date 255、month 4、daterange 1；value-format 几乎都是 `YYYY-MM-DD` |
| el-select | clearable 349、filterable 190、allow-create 162、multiple 11 |
| 原生 `<table>` 里有编辑控件 | 44 个文件 398 个控件 |
| 渲染函数里显式导入编辑控件 | 约 25 个文件（`import { ElInputNumber… } from 'element-plus'`） |

计数类一律以现算为准，禁写死进判据。

### 1.2 已有零件（只列结论，细节见会话分析）

- `useCellSelection`（8 个页面在用）：按 DOM 物理序号定位，合并单元格 / 勾选列会错位；页面传入的列号是自定义映射，与高亮用的视觉列号不一致（试算表点「审定数」高亮落在别的列）。
- `useKeyboardNav`（只有 GtEditableTable 用）：无 F2、直接输入、Esc 还原、Delete、复制粘贴快捷键。
- `useLazyEdit`：只记录哪一格在编辑，无原值快照、无聚焦。
- `useCopyPaste`：粘贴解析可复用（有单测）；写入不看锁、不看类型。
- 自建「点了才出输入框」：附注编辑器、试算平衡表、合并附注、GtEditableTable、ReportConfigEditor、公式管理两处、附注公式弹窗、StructureEditor、自定义网格底稿。

### 1.3 单向绑定 el-input 打不进字（浏览器实证）

el-input 2.13.6 的 `handleInput` 发出 `update:modelValue` 后，在 `nextTick` 里把原生值改回 `modelValue`（`setNativeInputValue`）。宿主只绑 `:model-value` 不接写回时，每敲一个字立即被改回。Playwright 真浏览器实测：`:model-value="abc"` + `@change`，敲 `XYZ` 后输入框仍是 `abc`、`change` 未触发；同样写法的 el-input-number 正常（内部有 `userInput` 状态）。现算 2157 处（表格内 1487 处，523 个文件），包括大量 `@blur="(e) => save(e.target.value)"` 写法 —— 读到的永远是原值。

### 1.4 Element Plus 2.13.6 表格结构（读 `node_modules/element-plus/es/components/table/src`）

- 表体每格由 `TableTdWrapper` 组件渲染 `<td>`，内容是 `column.renderCell(data)`；展开行内容由 `ElTableBody` 直接渲染 `h('td', { class: 'el-table__expanded-cell' })`，不经过 `TableTdWrapper`。表头 / 表尾分别是 `ElTableHeader` / `ElTableFooter`。
- `<td>` 的 class 含列 id（`el-table_{n}_column_{m}`）、对齐（`is-right`）、`el-table__cell`；固定列是同一张表上的 sticky 类，无重复表。分组表头（多级 `el-table-column`）下叶子列的 id 是「父 id + `_column_{k}`」（`el-table_2_column_14_column_15`）—— 坐标正则须认多段（5.3 浏览器实测：原正则只认一段，试算平衡表「审计调整 / 重分类调整」借贷列不在坐标里，单击选不中、双击打不开；守卫 `gridGroupedColumns.spec.ts`，变异 M51）。
- 行的 dblclick / click / contextmenu 绑在 `<tr>` 上，由 `handleEvent` 再发 `cell-*` / `row-*`。
- `ElTable` 的内部实例上有 `store`（`store.states.columns.value` 为叶子列顺序）、`tableId`、`vnode.el`。

## 2 方案决策

**ADR-1 集中适配，不逐文件改模板。** 在 `vite.config.ts` 的组件解析器前加一个解析器，把模板里的 `ElInput / ElInputNumber / ElSelect / ElDatePicker / ElCheckbox / ElSwitch / ElRadioGroup` 解析到 `@/components/grid/adapters` 的同名导出（类型声明为原组件类型，vue-tsc 口径不变）；适配组件内部直接 import 原组件。表格交互用全局 mixin 挂到每个 `ElTable` 实例上（不包装 ElTable，模板 ref 仍是原实例）。
否决：codemod 改 1000 个文件（并发会话正在改其中大量文件、风险不可控）；换成电子表格组件（底稿联动全在 Vue 模板与 `@change` 里）；只改样式（交互不变）。
单测（vitest 未接解析器）仍用原组件，既有测试不受影响；适配层另写单测。

**ADR-2 单元格判定看组件父链。** 适配组件 setup 时沿 `instance.parent` 上溯：先遇到 `TableTdWrapper` 再遇到 `ElTable` ⇒ 表体单元格；先遇到 `ElTableHeader / ElTableFooter` 或弹出层内容（`ElPopperContent / ElTooltipContent / ElDialog / ElDrawer`）⇒ 不是；遇到 `GtGridCell` ⇒ 由它托管；遇到 `GtGridTable` ⇒ 原生表格单元格（挂载后再按 DOM 确认在 `<td>` 里）。判定在渲染前完成，不闪烁。

**ADR-3 内核按 DOM 坐标。** 每个表一个 `GridKernel`：列号 = `<td>` 列 id 在 `store.states.columns` 里的序号，行号 = 可见 `tr.el-table__row` 序号；合并单元格按 rowspan / colspan 建占位图，落在被覆盖位置时选中源格。选区用 `<td>` 上的 `data-gt-*` 属性 + CSS 绘制（Vue 不会改写自己未声明的属性；表体变化时由 MutationObserver 重贴）。

**ADR-4 焦点承接框。** 选中态下焦点在表格根节点内一个透明 `<textarea>`（承接框，贴在当前格上）：键盘事件归表格；直接输入的字符先进承接框，编辑器挂好后整体转交（快速连敲不丢字）；中文输入法在承接框里完成组字（组字期间承接框显示为编辑框），`compositionend` 后带着结果打开编辑器。

**ADR-5 编辑期 `change` 由适配层在提交时统一发出。** 程序写入的初值不会触发原生 `change`，故编辑期内拦截内层控件的 `change`，提交时按最终值发一次；`update:modelValue` / `input` 照旧即时转发（保持现有联动的实时性）；取消时把即时更新还原。`blur` 由真实失焦产生（提交时焦点移回承接框），读 `e.target.value` 的宿主读到最终值。

**ADR-6 显式接入两种。** `GtGridCell`：自定义显示插槽 + 默认插槽放编辑器（附注单位金额、试算平衡表）。`GtGridTable`：替换原生 `<table>`，提供表格上下文与承接框。

**ADR-7 经典方式 = 透传。** 适配组件直接渲染原控件、内核不处理事件；只保留 R9 的单向绑定修复。

## 3 模块与文件（`src/components/grid/`）

| 文件 | 职责 |
|---|---|
| `gridMode.ts` | 读取编辑方式（`displayPrefs.gridEditMode`），提供响应式判定 |
| `cellDetect.ts` | ADR-2 父链判定 |
| `cellValue.ts` | 各类编辑器的显示格式、文本 ↔ 值解析（§4） |
| `gridDom.ts` | el-table / 原生表格的坐标、占位图、矩形、滚动 |
| `GridKernel.ts` | 选区、键盘、承接框、复制粘贴、撤销、编辑状态机（§5） |
| `editorHost.ts` | 编辑器协议（§6）与 `元素 → 句柄` 登记 |
| `adapters.ts` | 7 个适配组件 |
| `GtGridCell.vue` / `GtGridTable.vue` | ADR-6 |
| `plugin.ts` | 全局 mixin、待写盘登记、全局提交入口 |
| `styles/gt-grid.css` | 选区、编辑态、显示文本、锁定格样式 |

## 4 显示格式与解析（`cellValue.ts`）

| 种类 | 显示 | 粘贴 / 清空解析 |
|---|---|---|
| 文本（el-input） | 原样；textarea 保留换行；password 显示圆点 | 原文；清空为 `''` |
| 数字（el-input-number） | 有 precision 按位数；无则按值本身小数位（≤10）；有小数或绝对值 ≥ 10000 时千分位；负数按「负数红色」偏好 | 去千分位、括号负数、百分号、全角；按 precision 舍入、min / max 夹紧；清空为 `null` |
| 下拉（el-select） | 选项名称；多选「、」连接；找不到名称显示值本身 | 先按名称再按值匹配；allow-create 接受原文；多选按 `、,;，；` 拆分；不匹配跳过 |
| 日期（el-date-picker） | 有 format 按 format，否则按 type 默认（日 / 月 / 年 / 日期时间）；区间「a 至 b」 | `YYYY-MM-DD / YYYY/MM/DD / YYYY.MM.DD / YYYYMMDD / YYYY年M月D日` 及 Excel 序列号；按 value-format 输出 |
| 勾选 / 开关 | 控件本身（直接可点） | 是/否、√/×、true/false、1/0、勾选；开关按 active-value / inactive-value |
| 单选组 | 控件本身 | 按选项名称匹配 |

复制取显示文本（与 Excel 粘贴兼容）；只读格取单元格可见文本并去掉图标字符。

## 5 状态机与键位（`GridKernel`）

状态：`idle` → `selected`（承接框聚焦）→ `entering`（直接输入进入）/ `editing`（F2、双击进入）/ `picking`（下拉、日期展开）。

| 键 | selected | entering | editing | picking |
|---|---|---|---|---|
| 方向键 | 移动（Shift 扩展、Ctrl 到边） | 提交并移动 | 光标 | 交给控件 |
| Enter / Shift+Enter | 下 / 上移 | 提交并下 / 上移 | 同左（Alt+Enter 换行） | 交给控件，选定即提交 |
| Tab / Shift+Tab | 下 / 上一个可编辑格 | 提交并移动 | 同左 | 提交并移动 |
| Esc | 交还页面 | 取消（阻止冒泡） | 取消（阻止冒泡） | 收起并取消 |
| F2 | 进入 editing | 切到 editing | 切到 entering | — |
| 字符 / 输入法 | 进入 entering（覆盖） | 输入 | 输入 | 过滤（可搜索下拉） |
| Delete / Backspace | 清空选区 / 清空并 entering | 输入 | 输入 | — |
| Ctrl+A / C / X / V / Z / Y | 全选 / 复制 / 剪切 / 粘贴 / 撤销 / 重做 | 交给控件 | 交给控件 | — |
| 空格 | 勾选类切换，其余同字符 | 输入 | 输入 | — |

编辑中的按键在表格根节点捕获阶段处理（先于 el-input-number 自身的上下键加减）；`isComposing` 时一律不处理。
鼠标：表体 `mousedown`（捕获）选中并阻止文字选择；点在按钮、链接、勾选框、标签关闭等交互元素上只选中不拦截；`dblclick`（捕获）在可编辑格上拦下并进入编辑，只读格放行。
提交时机：移到别的格、Enter / Tab / 方向键（entering）、焦点离开表格（移入弹出层 `.el-popper` 不算）、Ctrl+S、待写盘 flush、编辑器卸载。

**只读表交还 Enter / Backspace / Delete（5.3）**：整张表没有可编辑格（纯文字列、编辑器全禁用；嵌套子表里的编辑器归子表）时，这三个键内核不处理、照常冒泡给页面 —— 平台只读列表常拿它们做「返回上级 / 返回上一页」（试算表溯源返回、查账穿透 Enter / Backspace、全局返回栈 Backspace），选中单元格（焦点在承接框）后照常可用；方向键 / Ctrl+A / 复制仍由内核处理。有可编辑格的表照上表，只读格上 Backspace / Delete 轻提示、不冒泡（不误触返回）。页面自己的「在输入框里不拦截」判定统一用 `isTextEntryTarget`（`utils/shortcuts.ts`，承接框不算输入框）：现扫「键盘处理里把 textarea 当输入框」9 处，改 5 处（试算表、查账穿透、全局返回栈、Ctrl+K 全局搜索、附注表格结构撤销）；`shortcuts.ts` 本身已认承接框，`useKeyboardNav` 在内核方式下不启用，复核工作台的上下键在选中单元格时本就由内核处理，`ReportView` 那处是鼠标拖选判定 —— 4 处不改。守卫 `gridReadonlyKeys.spec.ts`（变异 M19 / M47~M50）。

## 6 编辑器协议（`editorHost.ts`）

每个单元格编辑器（适配组件 / GtGridCell）在显示根节点上标 `data-gt-cell-editor`，登记句柄：

```ts
interface CellEditorHandle {
  kind: 'text' | 'number' | 'select' | 'date' | 'toggle'
  editable(): boolean            // !disabled && !readonly
  getText(): string              // 显示文本（复制 / 统计）
  getValue(): unknown
  open(mode: 'entering' | 'editing' | 'picking', initialText?: string): Promise<void>
  commit(): void                 // 同步发事件
  cancel(): void
  setValue(v: unknown): boolean  // 程序写入：粘贴 / 清空 / 撤销
  parse(text: string): { ok: true; value: unknown } | { ok: false }
}
```

事件契约（宿主视角）：

- 即时：`update:modelValue`、`input` 照内层控件原样转发。
- 提交：值变了才发 `change(final[, old])`；随后真实失焦产生 `blur`。
- 取消：发过即时更新的，补发 `update:modelValue(原值)` / `input(原值)`；不发 `change`。
- 程序写入：`update:modelValue` → `input`（宿主监听时）→ `change` → `blur`（宿主监听时，合成事件，`target.value` 为值的文本）。
- 单向绑定（无 `onUpdate:modelValue`）：适配组件持有草稿值作为内层 `modelValue`，表格内外都如此（R9）。

## 7 兼容规则（迁移前的自激活编辑器）

页面自己控制「点了才渲染编辑器」时，新挂载的编辑器在下面任一情形直接打开（editing），不显示为文本：
1. 挂载在当前选中格里，且该格 300 ms 内有过单击 / 双击 / 按键；
2. 页面调用其 `focus()`（适配组件的 `focus` 在显示态等同打开）；
3. 带 `autofocus`。

## 8 接入清单

**显式导入（4.1，现算 24 个文件，全部改从 `@/components/grid/adapters` 导入）**：适配组件在表格外整段透传（R2.2），表格外的用法改了也只多 R9 的单向绑定修复，故不按「是否在表体内」分留改。清单由 `import { …ElInput… } from 'element-plus'` 现扫得出：CNoteCell、econtrol/FieldInput、F2CutoffSheet、F2 供应商核查清单 / 结构 / 单耗、G1 证券盘点、G7 五个（基本信息、处置单项 / 打包、同控 / 非同控初始计量、后续计量）、GtDFormConfirmation、H1 明细 / 政策检查 / 关联方、H2 明细 / 裁决、H3 转移复核、H4 裁决、H8 明细、I1 增加 / 处置检查。工作树有他人改动的跳过（现算 0）。
- 测试影响：适配层从 `element-plus/es` 取原组件，与 `'element-plus'` 解析到同一文件，`vi.mock('element-plus', 工厂)` 同样约束它 —— 工厂里缺七个组件之一的测试，模块求值时一碰导出即报「No "ElCheckbox" export」。5.2 起适配组件惰性取原组件（`raw: () => RawElX`，渲染时才取），模块求值不再碰导出：原先补给 GtDForm.integration 的三个 stub 已撤回，GtEditableTable 接入后受影响的 3 个合并工作底稿测试同样不用改；守卫 `gridAdaptersMockSafety.spec.ts`。

**原生 `<table>`（4.2，现算 40 个文件 74 张表 382 个控件；改 39 个文件）**：只改「块内（不含嵌套子表）有编辑控件」的表；`<script setup>` 显式 import GtGridTable（vitest 不走组件自动注册）。`custom/GtCustomGridSheet` 自带双击编辑，留到 5.5。
- GtGridTable 结构改为**根节点就是那张 `<table>`**（原方案外包 `div` 有两处破坏：父组件 scoped 样式落不到内层 table —— 作用域属性只给子组件根节点；`.x > table` 选择器断开）。承接框与读屏播报放在 table 第一个子元素 —— 零高 `<caption>` 里。Chrome 实测：往 table 里直接放任何子元素（含绝对 / 固定定位、空 tbody、绝对定位 caption）都会被当成一个匿名行组，separate 边框的表多出一个 border-spacing（默认 2px）；零高 caption 在 collapse / separate / 带边框三种表上都是 0。
- 定位规则用 `:where()` 零优先级：页面写的 `position: sticky`（F2 合同 / IPO 类首列）照旧；单元格只在被选中时取 `position: relative`（画选区边框用）。承接框定位扣掉根节点边框（`clientLeft / clientTop`）。
- 现算：40 个文件里 `> table` 选择器 0 处、开标签带 `ref` 0 处、单元格内绝对定位元素 0 处（GtDFormQA 的 AI 按钮在表外）。
- 实测抓到 gt-grid.css 层叠缺陷：区域外沿宽度规则（0,2,1）低于 `td[data-gt-sel]::after { border: 0 }` 简写（0,2,2），选区外框从没画出来（el-table 同样）⇒ 外沿规则带上 `td / th`；守卫 `gridStyles.spec.ts` 按优先级核对。

**el-table-v2 速览**：保持只读；`useWorkpaperBrowseMode` 阈值按实测渲染耗时调整（见 4.3）。

## 9 自建实现与手势迁移

| 位置 | 改法 |
|---|---|
| `useCellSelection` | 改为读内核选区的门面（选区、值、统计、复制）；`cellClassName` 不再画选区；`setupTableDrag` 只登记取值函数 |
| GtEditableTable / GtFormTable / GtTableExtended | 去掉自带懒编辑、键盘、粘贴、选区；内置编辑器改用适配组件；两个包装的布尔默认值改 `withDefaults` |
| 附注编辑器（`activeCellEdit` 一套） | 数值格、项目名格改 `GtGridCell`；删除激活 / 键盘 / 失焦三段 |
| 试算平衡表（`tbSumLazyEdit`） | 未审数 / 重分类格改 `GtGridCell`；方向切换改双击 + 右键菜单；行双击跳转只在只读格生效 |
| 合并附注（`lazyEdit`） | 同附注编辑器 |
| 报表权益表 / 减值表（双击弹 prompt） | 改格内编辑（`GtGridCell`），提交时写 `/reports/cell` |
| ReportConfigEditor（`row._editing`） | 名称格直接放编辑器 |
| 公式管理两处（`editingId` + 缓冲） | 公式格直接放编辑器，提交时保存、Esc 取消 |
| 附注公式弹窗（`_editing`） | 同上 |
| StructureEditor（v-html + contenteditable） | 单击选中、双击 / 输入编辑，复用内核键位常量 |
| 自定义网格底稿（原生表 + 双击编辑） | 改 `GtGridTable` + 适配组件 |

并发会话正在改的文件（附注编辑器、合并附注、附注公式弹窗、合并总览等）放到最后，动手前现查状态，只改本 spec 需要的块。

**5.5 实施结果（与上表的偏差）**：
- 公式管理弹窗：表格里的行内编辑分支自 2026-05-02 起不可达（编辑走 FormulaEditDialog 弹窗）⇒ 表格没有可接的格内编辑器，双击公式照旧开弹窗。死分支里挂着 `FormulaInput` / `FormulaParamPicker`（2026-10-21/22 加的），删分支会让两者零挂载（挂载守卫要求删组件）⇒ 不删，待拍板。「建议公式」整条链路不可达：`formulaSuggestions` 读 `r._upstream?.formula`，而 `_upstream` 是 `reportEffectiveRows.snap()` 的 JSON 字符串 ⇒ 恒空（待拍板，未修）；其预填写进死分支缓冲、弹窗不读的问题已修（FormulaEditDialog `prefill`）。
- 合并公式面板：每格提交都是模板级改动、要确认 + 推送 ⇒ 不逐格保存，攒 200ms 一批（确认一次 → 同行合并一次请求 → 有成功才推送一次），粘贴多格也只确认一次。
- 表样编辑器：后端 HTML 的 `td[contenteditable]` 不改后端，前端接入时改写为「span 编辑器 + 内核」（`grid/contentEditableCells.ts`），拆除时还原；页面原有的 document 级导航只留给经典方式。
- 自定义底稿网格：经典方式下可编辑格输入框常驻（与其他表格的经典方式一致；原先只有双击编辑这一种）。

**报表矩阵格内编辑（5.4）**：金额格统一为 `components/report/ReportMatrixCell.vue`（GtGridCell + 数字适配组件），表格组件只发 `cell-edit(行, 列键, 值[, 年度])`，保存在 `useReportContextMenu.onRvCellEdit`（逐格 PUT、同一批合并为一次重新取数）。减值表列键与导出模板 `{{imp:CODE:列键}}`、`report_excel_exporter._resolve_imp_value` 同一套。🔴 待拍板（范围外）：报表重新生成（`report_engine._generate_report`）把每行 `source_accounts` 整列改写为取数科目列表，权益表再由 `_apply_eq_matrix_to_db_row` 按底稿 / 试算表重算矩阵 ⇒ 手工改的格在下一次生成后丢失；要保留须另存「手工覆盖」并在生成后回放（后端设计改动，未做）。

## 10 集成点

- 快捷键（`utils/shortcuts.ts`）：承接框不算输入框；编辑中 Ctrl+S 先调全局提交再保存；内核在编辑中处理 Esc 并阻止冒泡（不触发 `shortcut:escape` 与弹窗的 Esc 关闭）。
- 待写盘：插件安装时在常驻 effect scope 内 `registerPendingFlusher(commitAllGrids)`。
- 离开页面：编辑器卸载即提交；`useEditMode` 的离开确认不变。

## 11 风险与回退

| 风险 | 处置 |
|---|---|
| 全局适配影响表格外控件 | 表格外透传；只多一层组件；单测覆盖透传的 props / slots / expose |
| 某张表交互异常 | 个人设置切经典方式；表格级 `data-gt-grid="off"` |
| 页面依赖每次按键的即时事件 | 即时事件照旧转发（ADR-5） |
| 大表性能 | 显示态只渲染文本；句柄按元素懒登记；实测记录耗时 |
| 输入法丢首字 | 承接框组字（ADR-4），浏览器实测中文输入 |

## 12 验证

- 单测：`cellValue`（格式 / 解析，含属性测试，`numRuns` 小）、`gridDom`（合并单元格占位图）、`GridKernel`（jsdom 下键位、承接框转交、组字、粘贴矩阵、撤销、Esc 不冒泡）、适配组件（四类宿主写法：v-model、单向 + change、单向 + blur 读 target、单向 + input；表格外透传；expose 转发）、`GtGridCell` / `GtGridTable`。
- 磁盘变异：父链判定、提交发 change、取消还原、Esc 阻止冒泡、承接框转交、锁定格跳过、粘贴解析、单向草稿，各至少一条，必须红在预期断言上。
- 回归：改动文件关联的前端测试在改前 / 改后逐条对比。
- 浏览器：R12.3 清单，三种编辑方式各走一遍，改值后刷新回读。
