# 显示偏好开发指南

> **spec**: `platform-global-display-settings-closure` 任务 12A（阶段 A 屏幕显示文档）。
> 导入单位归一见 [`docs/reference/ledger-import-unit-normalization.md`](../reference/ledger-import-unit-normalization.md)（任务 12B）。
> 正式导出单位策略见 [`docs/reference/formal-export-unit-policy.md`](../reference/formal-export-unit-policy.md)（任务 12C）。

---

## 1. 三层优先级与平台默认

屏幕金额单位按以下优先级决定，**平台默认为元（`yuan`）**：

```
用户覆盖 (amount_unit_override) → 当前项目 amount_unit → 平台默认 yuan
```

- `amount_unit_override = null` 表示"跟随项目"。
- 项目上下文缺失或加载失败时降级为 `yuan`。
- 其他显示项（字号、密度、小数位等）按"账号值 → 平台默认"。
- **个人偏好不进入正式导出**：Excel/Word/PDF 由项目或模板 `ExportUnitPolicy` 决定单位，永不读取 `displayPrefs` store。

> ⚠️ `UserSettingsExtension.vue` 的 `gt-default-standard` 与 `gt-default-audit-type` 两项不在本 spec 范围，不跨设备同步。

---

## 2. 账号偏好 API

### 2.1 端点

| 方法 | 路径 | 鉴权 | 说明 |
|------|------|------|------|
| GET | `/api/users/me/display-preferences` | 仅当前登录用户 | 无记录返回完整默认 |
| PATCH | `/api/users/me/display-preferences` | 仅当前登录用户 | 增量更新，`base_revision` 必填 |

路径/请求中没有 `userId`；始终以 `get_current_user` 查询。

### 2.2 默认响应（无记录时）

```json
{
  "amount_unit_override": null,
  "font_size": "sm",
  "show_zero": false,
  "decimals": 2,
  "negative_red": true,
  "highlight_threshold": 0.2,
  "density": "default",
  "grid_edit_mode": "excel",
  "fixed_columns": {},
  "revision": 0,
  "updated_at": null
}
```

### 2.3 线协议约束

- `font_size`：`xs | sm | md | lg`（像素映射 11/12/13/14 只在前端常量）。
- `decimals`：0–6 整数。
- `highlight_threshold`：0–1 的 Decimal。
- `density`：`compact | default | comfortable`。
- `grid_edit_mode`：`excel | click | classic`。
- `fixed_columns`：对象，每个 pageKey 的值为 `{columns: string[]}`；响应额外带 `saved_at`（UTC ISO）。最多 100 个 pageKey，每键/列键 1–100 字符，每页最多 20 列，规范 JSON ≤ 64 KiB。PATCH 请求中带 `saved_at` 返回 422。
- PATCH 使用 `extra='forbid'`；显式 `null` = 清除（如 `amount_unit_override: null` 表示跟随项目），字段不出现 = 不修改。
- 并发首写返回 409 `DISPLAY_PREFS_REVISION_CONFLICT`，带 `current` 可恢复。

---

## 3. 前端缓存与 per-item mutation epoch

### 3.1 缓存键与 TTL

- 唯一缓存键：`gt_display_prefs:v3:${userId}`。
- **旧键 `gt_display_prefs` 已退役**：只删除不迁移，不读取、不上传。
- TTL 固定 **30 天**；过期缓存连同待提交补丁均不应用。
- 载荷：`{prefs, revision, pendingScalars, pendingFixedOps, cachedAt}`。
- JSON/枚举/范围/大小逐字段校验；`getItem/setItem/removeItem` 均捕获 `SecurityError`/`QuotaExceededError`，不阻塞登录。

### 3.2 per-item mutation epoch 与并发协议

store 维护全局递增 `nextMutationEpoch`，分开保存：

- `dirtyScalarEpochs: Map<key, {epoch, value}>` — 标量字段。
- `dirtyFixedOps: Map<pageKey, {epoch, kind: 'upsert'|'delete', value?}>` — 固定列操作，删除是带 epoch 的 tombstone。

**发送流程**：

1. setter 先递增 epoch、写本机值、300ms 防抖调度 flush。
2. 发送时冻结 `ownerUserId / requestGeneration / baseRevision`、完整 wire payload 与逐项 `{key, epoch}`。
3. 同账号同一时刻只允许一个 PATCH in flight，新编辑更新 map 并等待下一代。
4. 成功响应以服务端结果为新 base，**只清 epoch == sentEpoch 的项**；epoch 已前移的项覆盖响应值并触发下一次 flush。
5. 409 以 `current` 为基底，只重放 epoch 仍等于发送快照的操作，最多一次重试；第二次 409 不清任何 epoch，保留"待同步"。

**账号切换**：递增 `requestGeneration`、取消 `AbortController`/timer、清空全部 epoch/op/pending/内存默认，再读新账号缓存。晚到结果按 `userId + generation` 双检查丢弃。

### 3.3 fixed columns CAS 与 100 键淘汰

- `fixed_columns` 请求粒度为 `pageKey`：不同 pageKey 的设备修改可并存，同一 pageKey 冲突按本机最后修改重放。
- 键数将超过 100 时，按 `saved_at` 从旧到新选未挂载且不在本次发送的键，记 delete 墓碑（走同一 epoch）并提示"已清除最久未修改的 N 张表的固定列设置"。
- 可淘汰键不够时本次不保存并提示"固定列设置已达 100 张表的上限"。

---

## 4. 项目默认金额单位

- `projects.amount_unit`：合法值 `yuan | qian | wan`，既有项目默认 `yuan`。
- `GET /api/projects/{project_id}/config`：需项目只读权限。
- `PUT /api/projects/{project_id}/config`：需 `project:edit` 权限，严格枚举校验。
- 前端 `projectStore.projectAmountUnit`：换项目同步清 `null`，只有 `contextSeq` 匹配的响应才赋值；缺失/非法/失败降级 `yuan`。
- **修改后**：选择"跟随项目"（`amount_unit_override = null`）的用户立即看到新单位。显式个人覆盖不被改写。其他用户在下次加载项目上下文时生效。

---

## 5. 设置路由

| 路由 | 权限 | 内容 |
|------|------|------|
| `/settings` | `admin` only | 管理页，含系统配置、显示偏好 Tab |
| `/display-settings` | 仅已登录 | 只挂载 `DisplayPreferencesPanel`，普通用户入口 |

- Aa popover 使用 panel 的 `compact` 模式，提供"打开完整显示设置"链接。
- 顶部设置图标：admin → `/settings`，普通用户 → `/display-settings`。
- **不挂载、不修改 `UserSettingsExtension`**。

---

## 6. 字体与 CSS

### 6.1 字体族

| 用途 | CSS 变量 | 回退链 |
|------|---------|--------|
| 品牌正文 | 继承 `gt-tokens.css` | GT Walsheim → FZYueHei → 微软雅黑 → 苹方 → Helvetica Neue → Arial → `system-ui, sans-serif` |
| 数字 | `--gt-font-numeric` | `'Arial Narrow', Arial, sans-serif` + `font-variant-numeric: tabular-nums` |
| 等宽/代码 | `--gt-font-mono` | `Consolas, 'Cascadia Mono', monospace` |

- 仓库无随包字体文件（woff/ttf/otf）或 `@font-face`，依赖系统回退。
- 正式附注/审计报告/模板导出字体由文档语义决定，不消费屏幕变量。

### 6.2 四档字号

| 线值 | 中文名 | 像素 |
|------|--------|------|
| `xs` | 紧凑 | 11px |
| `sm` | 标准 | 12px |
| `md` | 舒适 | 13px |
| `lg` | 大字 | 14px |

- `useDisplayPreferencesRuntime` 在 `document.documentElement` 写 `--gt-display-font-size`、`--gt-table-row-height`、`--gt-table-cell-padding-x/y`、`--wp-font-size` 与 `data-gt-font-size/data-gt-density`。默认 `sm = 12px`。
- `global.css`：`--el-font-size-base: var(--gt-display-font-size)`。
- `gt-table.css` / `gt-polish.css`：表头/正文/`.cell`/表内输入统一读动态字号与密度 padding。**旧 `gt-polish.css` 固定 12px `!important` 已删除**。
- `DefaultLayout.vue` 初始化 runtime 与 `useGlobalTableLayout()`；切字号后所有已挂载 `el-table` 执行重排。
- `GtWpRenderer.vue` 最外层容器绑定 `runtime.fontStyle`。

### 6.3 三档密度

| 值 | 中文名 | 行高 | 内边距 | `el-table` size |
|---|--------|------|--------|----------------|
| `compact` | 紧凑 | 32px | 4px 8px | `small` |
| `default` | 标准 | 40px | 8px 12px | `default` |
| `comfortable` | 宽松 | 48px | 12px 16px | `large` |

`useTableDensityMetrics` 供 `el-table-v2` 绑定行高，字号/密度变化后重新挂载。

---

## 7. 固定列矩阵

有效集合 = `mandatory ∪ (saved ∩ allowed)`，用户只允许左侧固定。

### 7.1 持久化键（带表或模式身份）

| 页面 | 持久化键 | allowed 稳定 key | mandatory |
|------|---------|-----------------|-----------|
| TrialBalance 明细主表 | `trial-balance` | `standard_account_code, account_name, direction, unadjusted_amount, rje_adjustment, aje_adjustment, wp_adjustment, audited_amount, wp_status` | `standard_account_code, account_name` |
| ReportView 普通 | `report-view:normal` | `row_code, row_name, note, current_period_amount, prior_period_amount` | `row_code, row_name` |
| ReportView 比较 | `report-view:compare` | 普通 + `unadjusted_amount, adjustment, audited_amount, variance, variance_rate` | `row_code, row_name` |
| ReportView 权益/减值 | 不提供用户固定列 | — | 保留现有 fixed |
| DisclosureEditor | `disclosure-editor:<table_id>`（仅 `measure_status=matched`） | `label` 与该表未分组的顶层 `column_id` | `label` |
| HTML 底稿 (render schema) | `workpaper:<componentType>:<schema wp_code>/<sheet 名>/<表 id>`（sheet 直接带 `columns` 时表 id 写 `_`） | 该表的顶层 `field` | `fixed_required=true` 的顶层列 |
| HTML 底稿 (GtEditableTable) | `workpaper:<componentType>:<displayKey>`（`displayKey` 是可选 prop；不传则不提供） | 该表 GtColumn `prop` | 同上 |
| D1TabDisclosure | 不提供用户固定列 | — | 保留"票据种类"现有 `fixed` |
| 合并试算 | `consolidation:consol_tb` | 各表顶层列 | — |
| 合并报表 | `consolidation:consol_report` | `row_code, row_name, current, prior` | `row_code, row_name` |
| 合并附注 | `consolidation:consol_note:<table_id>` | `label, column_id` | `label` |
| 合并工作底稿 | `consolidation:worksheets:<activeSheet>`（如 `info`, `cost`） | 各子表顶层列 | 由 schema 明示 |

- 键超过 100 字符或无键（unmatched 附注、未传 `displayKey`）时设置入口禁用并提示"本表没有稳定标识，不能保存固定列"。
- **只有顶层列可固定**，分组列不开放。
- stale 只在同一键内计算。切到另一张表是另一个键，无 stale 提示。

---

## 8. 七类度量与逐 kind 显示规则

### 8.1 度量枚举

后端 `DisplayMeasureKind`、前端 `types/displayMeasure.ts` 逐值对拍：

| kind | 说明 |
|------|------|
| `amount` | 金额（唯一可缩放的 kind） |
| `quantity` | 数量 |
| `count` | 笔数/个数 |
| `ratio` | 比率，**必须同时携带 `ratio_scale`** |
| `exchange_rate` | 汇率 |
| `unit_price` | 单价 |
| `text` | 文本，不做数值格式化 |

`RatioScale` 固定为 `fraction | percent_points`。
- `kind = ratio` 时 `ratio_scale` 必填；其他 kind 禁止携带 → `DISPLAY_MEASURE_CONTRACT_INVALID`。

### 8.2 逐 kind 显示规则

| kind | 除数 | 小数位 | 千分位 | 零值 (`show_zero`) | 负数红色 (`negative_red`) | 高亮阈值 |
|------|------|--------|--------|-------------------|--------------------------|---------|
| `amount` | effective 金额单位 | 账号 `decimals` | ✓ | 生效 | 生效 | 生效 |
| `ratio` | 1；`fraction` 先 ×100 | **固定 2 位**，加 `%` | ✓ | 生效 | 生效 | 不生效 |
| `count` | 1 | **0 位**（原值带小数按 quantity 规则并记开发告警） | ✓ | 生效 | 生效 | 不生效 |
| `quantity` / `exchange_rate` / `unit_price` | 1 | 原值有效小数位（Decimal 去尾零，最多 6 位，超 6 位 `ROUND_HALF_UP`） | ✓ | 生效 | 生效 | 不生效 |
| `text` | — | 原样输出 | — | — | — | — |
| 未登记（null/unknown） | 1 | 账号 `decimals` | ✓ | 生效 | 生效 | 不生效 |

- `fraction` 0.2 与 `percent_points` 20 都显示 `20.00%`。
- 切到万元后：数量 10000 → `10,000`，汇率 7.2 → `7.2`，单价 10000 → `10,000`。
- 所有数值格用 `--gt-font-numeric` + `tabular-nums`，`data-gt-value` 恒为原始元值。
- `GtAmountCell` 只处理 `amount`；`GtMeasureCell` / `formatMeasure` 按上表处理所有 kind。

---

## 9. Render schema 核心清单与非核心 unknown

### 9.1 核心清单

核心清单位于 `backend/data/display_measure/render_schema_core.json`，只收 `reached_by` 非空的 schema 文件。`reached_by` 由 `render_schema_measure_audit.py` 离线算出：遍历内置科目工作包注册表，对每个 `primary_wp_code` 用 `resolve_package_sheets`（`db=None`，不连库）+ `classify_render_sheets`（纯函数）+ `_resolve_schema_path` 确定路由可达的 schema 文件与 componentType。

**离线算不到的两类路由**（不能成为核心项，`--check` 无法重算）：

1. **项目或事务所自定义工作包**：注册信息存在数据库中，离线工具只读内置注册表。
2. **无内置工作包、sheet 清单来自数据库分类结果的底稿**：`resolve_package_sheets(None, wp_code, ...)` 无结果，sheet 由运行时数据库决定。

当前三份 `C-*-disclosure.yaml`（`C-D1-disclosure.yaml`、`C-D2-disclosure.yaml`、`C-L-disclosure.yaml`）的 componentType 均为 `c-note-table`，经 D1/D2 工作包路由后 sheet 的 componentType 分别为 `d1-notes-receivable`、`d2-accounts-receivable`，**与 `c-note-table` 不等**，因此 reached_by 为空。核心清单初始为 `"entries": []`。

### 9.2 非核心 unknown 基线

由 `render_schema_measure_audit.py` 现算。计数单位为（schema 文件, sheet, 表 id, 列 field）。`--check` 与已提交基线 `render_schema_unknown_baseline.json` 比较，**只许减少不许增加**。

> 真实数量待任务 6A 完成后补入。

### 9.3 核心 unknown 处理

- 核心文件中出现 unknown/invalid 列：`--check` 失败。
- 运行时：`wp_render_schema_service` 抛 `DISPLAY_MEASURE_CONTRACT_INVALID`，render-config 对该 sheet 返回 `measure_contract_error`，GtWpRenderer 显示"本底稿列语义配置有误，请联系管理员"，不渲染该 sheet。

### 9.4 非核心 unknown 处理

非核心 schema 中一张表只要含一个 unknown/invalid 数值列，整张表的数值列走"未登记"分支：除数恒 1、不加 `%`，表头旁显示"本表列语义未登记，数值按原值显示，未随金额单位换算"。不按列部分换算、不拒绝渲染。

---

## 10. D1TabDisclosure 显示统一

`d1/D1TabDisclosure.vue` 是 D1 底稿「附注上市/附注国企」页签（listed/soe 同一文件）。

### 10.1 金额格

- 全部 `v-html="fmtAmt(...)"` 改为 `<GtAmountCell :value="...">`。
- 零值与负数改按账号的 `show_zero`、`negative_red` 统一显示（不再是固定的"—"与括号）。

### 10.2 比例格

- 全部 `fmtPct(...)` 改为 `<GtMeasureCell kind="ratio" ratio-scale="fraction" :value="...">`。
- 取 `fraction` 的依据：现有 `fmtPct` 对原值乘 100。

### 10.3 输入控件

- `WpAmountInput` 等不变，读写原始元值。

### 10.4 保留的 12px 说明文字

以下四类 CSS 类上的 12px 是说明文字，不是数据格，**保留不改**：

| 类名 | 说明 |
|------|------|
| `.excel-tip` | Excel 操作提示 |
| `.excel-hint` | 单元格操作说明 |
| `.detail-band` | 明细展开区说明 |
| `.portfolio-methodology` | 组合方法说明 |

表格 th/td 与表内输入的字号读 `--wp-font-size`，四档跟随账号偏好。

### 10.5 固定列

- **不提供用户固定列**。保留"票据种类"列现有 `fixed`。
- 金额列在 `MAIN_TABLE_GROUPS` 分组表头下，按设计不能单独固定。

---

## 11. 附注 matched/unmatched/invalid 分布

附注列级 measure status 由 `note_table_measure_catalog.json`（标题行库 + 逐表 override 生成，`--check` 守护）决定。

### 11.1 判定逻辑

- **matched**：表的 `table_id` 在该版 catalog 中存在且列结构对应。
- **unmatched**：表在 catalog 中无对应条目。
- **invalid**：catalog 中的该表定义自相矛盾（如 ratio 缺 scale）。

单体附注以 `section_id` + 新注入的 `table_id` 定位；合并附注以项目合并模板版本中按 `section_id` 查到的模板条目 `id` 作为 `table_id`。

### 11.2 只读探针现算分布

> 真实 matched/unmatched/invalid 分布数据待任务 6A 的只读探针完成后补入。
> 探针按"标准 × 项目 × 表"输出，结果写入工作流目录。不按结果放宽匹配规则。

### 11.3 屏幕行为

- `matched` 表：按 kind 换算。
- `unmatched` / `invalid` 表：走"未登记"分支（§8.2 末行），数值按 Decimal 解析后以元口径格式化，不可解析的原样输出。
- GtCNoteTable 的 `monetary_unit` 字段：标签显示"附注披露金额单位（正式输出用）"，另在卡片表头旁显示只读的"屏幕显示单位：X"。

---

## 12. 数据集单位三态

后端 `dataset_unit_contract` 把 `source_summary` 归为三类：

| 状态 | 含义 | 屏幕显示 |
|------|------|---------|
| `normalized_v1` | 已确认归一，存储单位为元 | 显示来源单位、因子与"存储单位：元" |
| `legacy_declared` | 旧 `source_summary` 有顶层 `amount_unit` 声明 | "历史声明：X，存储口径未验证" |
| `legacy_unknown` | 无任何单位证据 | "未知" |

- 唯一 presenter `datasetUnitPresentation.ts` 供 LedgerPenetration 与 TrialBalance 使用。
- 阶段 A 分类器只产出两类 legacy；`normalized_v1` 分支由阶段 B 任务 8 接入严格合同解析后才产出。
- 任何状态都不修改 `displayPrefs`。
- 已删除 LedgerPenetration load 时的 `displayUnit='yuan'` 重置。

---

## 13. 正式导出边界

**核心原则**：个人偏好不进入正式导出。

| 场景 | 行为 |
|------|------|
| 正式 Excel/Word/PDF | 由 `ExportUnitPolicy`（项目/模板）决定，不读 `displayPrefs` |
| data_exchange 导出（合并本地数据） | 输出原始元值 + `_GT_EXPORT_META` + 说明 sheet，不按 displayPrefs 缩放 |
| 模板导出 | 只有表头，无业务行 |
| PDF 导出面板 | 已删除"报表语言"选择器，本 spec 不做双语 PDF |

详细导出策略见 [`docs/reference/formal-export-unit-policy.md`](../reference/formal-export-unit-policy.md)（任务 12C）。
导入归一策略见 [`docs/reference/ledger-import-unit-normalization.md`](../reference/ledger-import-unit-normalization.md)（任务 12B）。

---

## 14. 组件与 API 速查

### 14.1 组件

| 组件 | 用途 | 备注 |
|------|------|------|
| `GtAmountCell` | 金额格显示（只处理 `amount`） | 继承字号，保留 numeric family + `data-gt-value`；已删除 `unit` prop |
| `GtMeasureCell` | 非金额度量显示 | 按 kind 规则输出 |
| `GtTableDisplaySettings` | 固定列设置面板 | props: `{pageKey, columns, mandatoryKeys?, disabled?}` |
| `DisplayPreferencesPanel` | 偏好设置面板 | props: `{compact?, showSyncState?}`；不接 userId |

### 14.2 Composables

| 名称 | 用途 |
|------|------|
| `useDisplayPreferencesRuntime` | 根 CSS 变量写入与 data 属性 |
| `useGlobalTableLayout` | 监听字号/密度变化后 `el-table` 重排 |
| `usePreferredFixedColumns` | `mandatory ∪ saved∩allowed`、stale 计算、`save(keys)` |
| `useTableDensityMetrics` | el-table-v2 行高绑定与密度变化重挂载 |

### 14.3 工具函数

| 函数 | 位置 | 说明 |
|------|------|------|
| `displayAmount` | `utils/displayAmount.ts` | Decimal 金额格式化（唯一实现） |
| `formatMeasure` | `utils/displayAmount.ts` | 按 kind 规则格式化 |

### 14.4 Store

`useDisplayPrefsStore`（`stores/displayPrefs.ts`）：

- `amountUnit`：effective 金额单位（只读 computed）。
- `setUnit(unit)`：写 override。
- `followProjectUnit()`：写 `amount_unit_override: null`。
- `revision`：CAS 版本号。
- `loadState` / `syncState`：加载与同步状态。

---

## 15. 不推荐的旧用法

以下写法**不再推荐**，新代码禁止使用：

```vue
<!-- ❌ 默认万元 — 平台默认是元 -->
<span>单位：万元</span>

<!-- ❌ 直接 v-model effective 值 -->
<el-select v-model="displayPrefs.amountUnit">

<!-- ❌ 旧 localStorage key（已退役） -->
localStorage.getItem('gt_display_prefs')

<!-- ❌ 个人单位控制导出 -->
import { useDisplayPrefsStore } from '@/stores/displayPrefs'
const prefs = useDisplayPrefsStore()
exportWithUnit(prefs.amountUnit)  // 正式导出禁止读取个人偏好

<!-- ❌ 旧 fmt() API -->
displayPrefs.fmt(row.amount)  // 改用 GtAmountCell 组件
```

### 推荐写法

```vue
<script setup lang="ts">
import { GtAmountCell, GtMeasureCell } from '@/components/common'
import { usePreferredFixedColumns } from '@/composables/usePreferredFixedColumns'
</script>

<template>
  <!-- 金额 -->
  <GtAmountCell :value="row.audited_amount" />

  <!-- 比例（fraction 原值 0.2 → 显示 20.00%） -->
  <GtMeasureCell kind="ratio" ratio-scale="fraction" :value="row.rate" />

  <!-- 数量 — 不缩放 -->
  <GtMeasureCell kind="quantity" :value="row.qty" />
</template>
```

---

## 16. 后续批次

| 任务 | 范围 | 状态 |
|------|------|------|
| 6A | 修复核心 violations、接入七类 measure kind 与逐核心页面固定列、只读探针现算 matched 分布 | 待实施；完成后补入 §9.2 真实 unknown 数量与 §11.2 真实 matched 分布 |
| 12B | 账套导入单位开发文档 | 待实施 |
| 11C | 正式导出出口闭集接入唯一守卫 | 待实施 |
| 12C | 正式导出单位开发文档 | 待实施 |

### 文档守卫核对项

本文档的守卫（待实施或已存在时运行）应核对：

1. 屏幕 API 端点路径/方法与 `user_display_preferences.py` router 一致。
2. `AmountUnit` 枚举值 (`yuan|qian|wan`) 与后端 `DisplayMeasureKind` 七类枚举值与代码一致。
3. 缓存键 `gt_display_prefs:v3:${userId}` 在 `displayPrefs.ts` 中匹配。
4. 核心页面矩阵（§7.1）的 pageKey 在各页面组件中存在对应接线。
5. ledger 动态数据集三态分类函数 `dataset_unit_contract` 产出的三个状态值与本文一致。
6. render schema unknown 基线数量与 `render_schema_unknown_baseline.json` 一致。
7. 后续批次列表如实反映未完成项。
