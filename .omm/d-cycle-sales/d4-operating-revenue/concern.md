# D4 关注点

## 1. 子表经 window event 保存，主入口必须监听

`d4:save-items` 与 `d4:writeback-trial-balance` 两个监听器缺一，大部分子表（D4-2/4/6~11/12/15/IPO/Other）
的数据就**静默不落库**（前端还会弹成功 toast）。这是 D4 体量大、子表多带来的结构性脆弱点。

## 2. TB 回写走显式发布门（2026-09-28 已核实，原「未见 TB 回写」结论作废）

~~`useD4FormData` 中没有 `trial-balance/writeback` 调用，可能是缺口。~~

**核实结论：D4 有 TB 回写，且走的是平台显式发布门，不是缺口。**

- 活路径在 **`useD4Adjudication.ts`**（非 `useD4FormData`）：二次确认（中文）→
  `POST /api/workpapers/{wpId}/audit-determination/publish-to-tb`，携带含 `D4-1` 子码的审定表
  sheet 名 + `audit_rows`，由后端算审定数、校验发布权限、发 `publish_confirmed=True` + token →
  回写 handler 幂等写 `trial_balance`。普通保存对 TB 仍是 no-op。
- `useD4FormData.ts` 里出现的 `trial-balance/writeback` 与 `publish-to-tb` 字面量**全是注释**
  （记录已移除的旧直写方法 + 其孤儿 dispatcher，spec `tb-writeback-explicit-publish-gate` Task 17 批C）。
  grep 命中这些字面量时**必须判注释/代码**，否则会误判成"仍在走旧端点"。
- 原先的猜测「损益类不需要回写」**不成立**：D4-1 审定表确实回写，科目 6001/6051。

## 3. 损益类取数口径

D4 是 6001/6051 **发生额**，不能取余额；序时账 resolver `d4_ledger_monthly_by_product`
按 `account_name`（回退 `account_code`）× 月汇总**贷方净额**。

## 4. IPO 专项 13 表的适用性

`ipo/` 下 13 个 Tab 只对 IPO / 新三板 / 重组项目适用，普通年审项目应通过程序裁剪排除，
否则审计师面对一堆不适用的空表。适用性判断目前靠人工裁剪（程序表类别筛选 + 批量裁剪）。

## 5. 分析表口径依赖录入源

`analysis/` 6 张分析表全部从 D4-2（产品 × 12 月）派生，D4-2 未从序时账取数时这些分析表一律空。
「从序时账导入」是 D4-2 的关键入口，不是可选项。
## 6. ~~D4-4 是 D4 唯一未接双向同步的有载荷表~~ → **已落地真双向（2026-09-28）**

> ✅ **本条已完成**。spec `d4-4-adjustment-summary-bidirectional-writeback` 落地：
> 契约新增 `d44-managed`（35→36 张 / 775→785 字段）、provider `phase5_d4_adjustment_sheet`
> （11 处接线）、`D4TabAdjustment.vue` 已接 `useD4SyncMode`、宿主 `isD4DedicatedSyncSheet`
> 已含 `'D4-4'`（现算 34 张）、`D4_LEGACY_OO_BLOCKED_SHEETS` 已摘除 `'D4-4'`（现算仅剩 `['D4-5']`）、
> UI 已补 `placeholder`/`remark` 两列（五层一致）。
> ⇒ **D4-4 不再是未接双向的表**；逐张清册的 `⬜` 从 2 张降到 **1 张**（仅剩 D4-13 纯叙述文本表）。
> 详见 `docs/operations/d4-bidirectional-writeback-inventory.md` 第十二轮。
>
> 下面保留原分析作为记录（其判断已被实施验证）。

### 原分析（2026-09-28 复核，已兑现）

D4-4 调整分录汇总是 36 张里**唯一**的 `⬜ single_html`（D4-13 已于此前落地 `d413-managed`，清册的
N/A 裁决已作废）。原裁决的两条理由经实测**均已不成立**：

- 「模板无行身份 UUID 列载体」→ 模板 `A1:J23`，**K~O 五列全空**可做隐藏载体（D4-12 是往模板注入
  definedName + 隐藏行才落地的，D4-4 连加行都不用）；且前端 `D4AdjustmentRow` **已有 `rowId`**、
  `removeRow(rowId)` 按身份删（D4-7 当初还要补 rowId，D4-4 这步已完成）。
- 「hub store 被 A13/借贷平衡语义占用」→ 借贷平衡是纯 `computed`、A13 是 `eventBus.emit`，
  `useAdjustmentCentralSync` 零写路径；落库的 `D4-4-rows` 就是干净的 10 字段行数组。

它其实是剩余表里**几何最简**的一张：单区动态行表、模板 10 列 ↔ 前端 10 字段 1:1、**数据区公式格 0**、
无 footer 合计行、非转置、非静态矩阵。落地 spec 见 `.kiro/specs/d4-4-adjustment-summary-bidirectional-writeback/`。

🔴 **与本条相关的历史风险（已修 + 2026-09-28 Playwright 实测确认）**：修复前 D4-4 会命中宿主的
legacy `GtOnlyOfficeSheet` 分支（能进 OO、能编辑、改动不回 store = 静默丢失）。现由
`d4Constants.ts` 的 `D4_LEGACY_OO_BLOCKED_SHEETS` 挡住 —— 实测 `结构化视图 [checked]` +
`在线编辑 [disabled]` + 提示标签，console 0 errors；同时 D4-2/D4A 的「在线编辑」仍可点（未一刀切）。
~~**该名单在 D4-4 接桥后必须移除**，否则新做的双向入口会被自己的禁入名单挡掉。~~
✅ **已移除**（2026-09-28，与「加进 dedicated」同批改 —— 两处缺一即坏：只加 dedicated 不摘名单
⇒ `renderMode` 恒 `'html'`、切换器恒 disabled；只摘名单不加 dedicated ⇒ 掉回 legacy 单向通道）。

✅ **已补齐**（2026-09-28 Task 13b）：`补充说明`(F/`placeholder`) 与 `备注`(J/`remark`) 两列已加，
UI 现 10 个业务列，顺序与模板 A~J 一致，守卫做「列数 ↔ 字段数对账」防将来加字段忘补 UI。
下面是修复前的实测记录：

🔴 ~~**D4-4 的 `placeholder`/`remark` 两字段目前 UI 不可见**~~（实测 `thead th` 只有 8 列，而模板 10 列、
`D4AdjustmentRow` 类型 10 字段、导入导出 10 列）。⇒ 这两个字段现在只能「导出模板→Excel 填→导入」，
UI 里填不了。落地双向前必须补这 2 列（spec Task 13b），否则 OO 侧改动回写进 store 却在结构化视图
看不见，表现为「改动丢了」。
⚠️ grep 陷阱：该文件 6 处 `placeholder="…"` 是 el-input **占位属性**，与同名**字段**无关。

## 7. 「N/A / 已裁决」类结论有保鲜期

D4 组里被裁「不可双向」的表，**已有三张后来被推翻**：D4-8（原「引擎不支持纯静态 sheet」→ 被
`workpaper-sync-static-cell-sheet-writeback` 的 definedName 静态区路径推翻）、D4-12（原「转置大工程」→
泛化引擎后落地）、D4-13（原「纯叙述文本表」→ 已有 `d413-managed`）。
**D4-4 是第四张，且已于 2026-09-28 兑现**（原「无行身份 UUID 列载体」与「hub store 被
A13/借贷平衡语义占用」两条理由经 openpyxl + 现读实测均不成立 ⇒ 落地真双向，见 §6）。

🔴 **本条在本轮又多了一个变体：不只「N/A 裁决」有保鲜期，spec 自身的现状描述也有**。
实施 D4-4 时踩到三处 spec 前提过期 / 与现算不符：
1. spec 说 4-tuple 硬解包在 `oo_to_html.py` L2842 —— 现算**已搬到 `store_mirror.py` L314**
   （spec 写于该重构之前，同一天）；
2. design 说接线 **8 处** —— 现算 D4-19 的真实接线点是 **11 处**，按 8 处做会漏 3 处；
3. design 的 flag 命名 `_INCLUDE_D44_SHEET` 与既有 5 个同类 flag 的 `_INCLUDE_D{n}_{名字}_SHEET`
   惯例不符。
⇒ **实施前的「现状 grep 确认」不能只确认业务判断，还要确认 spec 引用的每个代码坐标**
（文件名、符号名、处数、命名惯例）。坐标漂移不会报错，只会让你少做几处而不自知。

⇒ 引用任何「已裁决 N/A」前先重算它的理由是否仍成立，特别是理由形如「引擎/模板不支持 X」——
平台能力在演进，这类理由的保鲜期很短。同理，引用性能数字前须确认它测于哪个优化版本之后
（清册里「138s 逼近上限」就是 Wave 5 修复前的旧值，据此会误判出不存在的风险）。
