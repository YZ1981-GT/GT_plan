# 表格组件迁移能力对账

> 本文档是 P1-1 任务的产出物，记录各试点页面当前 `el-table` 使用的表格能力，
> 以及迁移到 `GtTableExtended` / `GtFormTable` 的前置条件和风险评估。

## 1. TrialBalance.vue（试算表）

### 1.1 当前表格能力清单

| # | 能力 | 实现方式 | 涉及表格 |
|---|------|---------|---------|
| 1 | **双表头（多级列头）** | `el-table-column` 嵌套：`审计调整 > 借方/贷方`、`重分类调整 > 借方/贷方` | 试算平衡表 |
| 2 | **合计行** | 手动注入 `_isSubtotal` / `_isTotal` 行到 tableData，通过 `row-class-name` 加粗 | 科目明细表 |
| 3 | **右键菜单** | `@cell-contextmenu` → 自定义 ContextMenu 组件（评论/溯源/穿透/锁定） | 全部表格 |
| 4 | **行内编辑列** | 试算平衡表的「未审数」列使用 `el-input-number` 条件渲染；重分类借/贷列同样 | 试算平衡表 |
| 5 | **条件格式/行样式** | `row-class-name` 回调：stale 行黄底、锁定行灰底、小计行加粗 | 全部表格 |
| 6 | **固定列** | 科目明细表 `科目编码` 列无 fixed，试算平衡表无 fixed | — |
| 7 | **列可拖拽调整宽度** | 未使用（`resizable` 未显式设置） | — |
| 8 | **虚拟滚动** | 未使用（`:max-height` 限高 + 分页） | — |
| 9 | **横向滚动** | 试算平衡表列数多，天然横向滚动 | 试算平衡表 |
| 10 | **调整分录弹窗表格** | 独立 `el-table`（无编辑，纯展示） | 弹窗 |
| 11 | **排序** | 未使用客户端排序（数据预排序） | — |
| 12 | **CommentTooltip** | 在金额列内嵌 `CommentTooltip` 包裹 `GtAmountCell` | 科目明细表 |
| 13 | **LinkageBadge** | 联动列展示关联调整分录数量 | 科目明细表 |

### 1.2 迁移到 GtTableExtended / GtFormTable 的前置条件

| 前置项 | 当前状态 | 说明 |
|--------|---------|------|
| GtTableExtended 支持多级列头 | ❌ 需增强 | 试算平衡表的「审计调整 > 借方/贷方」需要嵌套 column 定义 |
| GtFormTable 支持条件编辑列 | ❌ 需增强 | 仅特定行可编辑（`tbSumUnadjEditable` / `formula_detached`） |
| GtTableExtended 支持右键菜单 | ⚠️ 需确认 | 需要 slot 或事件透传 `@cell-contextmenu` |
| GtTableExtended 支持 `row-class-name` | ⚠️ 需确认 | 条件行样式是核心功能 |
| GtTableExtended 支持 CommentTooltip slot | ✅ 已有 slot | 列 slot 允许自定义内容 |
| 迁移不破坏「复制选中区域」功能 | ⚠️ 需验证 | `useCellSelection` 绑定在 el-table ref 上 |

### 1.3 迁移计划（P1-1.4）

**阶段一：科目明细表迁移**
- 目标组件：`GtTableExtended`（纯展示 + 右键 + 条件格式）
- 前置：确认 GtTableExtended 支持 `row-class-name`、`@cell-contextmenu`、列 slot
- 风险：`useCellSelection` 依赖 el-table DOM 结构，需适配

**阶段二：试算平衡表迁移**
- 目标组件：`GtFormTable`（多级列头 + 行内编辑 + 条件格式）
- 前置：GtFormTable 必须支持多级列头（嵌套 column 定义）
- 风险：中等——多级列头是核心需求，需先在 GtFormTable 中实现

**阶段三：弹窗表格迁移**
- 目标组件：`GtTableExtended`（简单展示）
- 风险：低

---

## 2. ReportView.vue（财务报表）

### 2.1 当前表格能力清单

| # | 能力 | 实现方式 | 涉及表格 |
|---|------|---------|---------|
| 1 | **动态列** | 根据 `reportMode`（已审/未审/对比）切换不同列定义 | 主表 + 对比表 |
| 2 | **合并单元格** | `span-method` 回调实现权益变动表行列合并 | 权益变动表 |
| 3 | **横向滚动** | 对比视图 7+ 列，天然横向滚动；`:max-height="600"` | 对比表 |
| 4 | **固定列** | 普通模式「项目」列 `fixed` | 主表 |
| 5 | **排序** | `:sortable` + `:sort-method`（本期/上期金额列） | 主表 |
| 6 | **行缩进** | `indent_level` 计算 `paddingLeft` 实现树形缩进 | 全部表格 |
| 7 | **行样式** | `row-class-name` 区分 header/total/data 行 | 全部表格 |
| 8 | **右键菜单** | `@cell-contextmenu` → 穿透/溯源/复制 | 全部表格 |
| 9 | **双击编辑** | `@cell-dblclick` → 行内编辑金额（条件允许时） | 主表 |
| 10 | **跨表核对表** | 独立 `el-table` 展示 7 条等式核对结果 | 跨表核对 |
| 11 | **GtAmountCell** | 对比视图已接入，主表部分列尚未接入 | 对比表 |
| 12 | **列宽可调整** | 全部列 `:resizable="true"` | 全部表格 |
| 13 | **显示偏好字号** | `:style="{ fontSize: displayPrefs.fontConfig.tableFont }"` | 全部表格 |

### 2.2 迁移前置条件

| 前置项 | 当前状态 | 说明 |
|--------|---------|------|
| GtTableExtended 支持 `span-method` | ❌ 需增强 | 权益变动表的合并单元格是强需求 |
| GtTableExtended 支持 `fixed` 列 | ⚠️ 需确认 | 普通模式「项目」列固定左侧 |
| GtTableExtended 支持客户端排序 | ⚠️ 需确认 | 需透传 `sortable` + `sort-method` |
| GtTableExtended 支持动态列切换 | ✅ 响应式 | 列定义可根据 mode 动态生成 |
| 不破坏穿透/溯源交互 | ⚠️ 需验证 | 右键菜单 + 行名点击穿透依赖 DOM 事件 |
| 显示偏好字号注入 | ✅ style 绑定 | 通过 prop 或 style 注入 |

### 2.3 迁移计划（P1-1.5）

**阶段一：跨表核对表迁移**
- 目标：`GtTableExtended`（纯展示、无编辑、无合并）
- 风险：极低

**阶段二：普通模式主表迁移**
- 目标：`GtTableExtended`（fixed 列 + 排序 + 右键 + 行样式 + 行缩进）
- 前置：确认 GtTableExtended 支持 `fixed`、`sortable`、`row-class-name`
- 风险：中等——缩进渲染 + 穿透点击逻辑需保持

**阶段三：对比视图迁移**
- 目标：`GtTableExtended`
- 前置：同阶段二
- 风险：低（对比视图结构更统一）

**阶段四：权益变动表迁移**
- 目标：`GtTableExtended` + span-method 支持
- 前置：GtTableExtended 必须实现 span-method 透传
- 风险：高——合并单元格逻辑复杂，建议最后迁移

---

## 3. DisclosureEditor.vue（附注编辑器）

### 3.1 当前表格能力清单

| # | 能力 | 实现方式 | 涉及表格 |
|---|------|---------|---------|
| 1 | **动态行列** | headers/rows 从后端返回，列数不固定 | 附注表格 |
| 2 | **合并单元格** | `span-method` 回调（附注表格支持行/列合并） | 附注表格 |
| 3 | **公式计算** | 单元格支持公式（`=SUM(...)`），前端渲染计算结果 | 附注表格 |
| 4 | **行内编辑** | 全部数据单元格可编辑（`el-input` 条件渲染） | 附注表格 |
| 5 | **右键菜单** | `@cell-contextmenu` → 插入行/列、删除、公式、格式 | 附注表格 |
| 6 | **单元格点击** | `@cell-click` → 选中单元格（公式栏联动） | 附注表格 |
| 7 | **动态列宽** | 第一列 160px，其余 120px | 附注表格 |
| 8 | **显示偏好字号** | `:style="{ fontSize: displayPrefs.fontConfig.tableFont }"` | 附注表格 |
| 9 | **条件格式** | `cell-class-name` 标记编辑中/公式/错误单元格 | 附注表格 |
| 10 | **Tab 切换多表格** | `el-tabs` 切换不同附注表，每表独立 headers/rows | 附注表格 |

### 3.2 迁移前置条件

| 前置项 | 当前状态 | 说明 |
|--------|---------|------|
| GtFormTable 支持动态列数 | ❌ 需增强 | 列定义从后端数据动态生成，列数不固定 |
| GtFormTable 支持 `span-method` | ❌ 需增强 | 附注表格有复杂合并逻辑 |
| GtFormTable 支持公式单元格 | ❌ 需新建 | 公式计算是附注编辑器的核心特性 |
| GtFormTable 支持 `cell-class-name` | ⚠️ 需确认 | 单元格级样式定制 |
| GtFormTable 支持插入/删除行列 | ❌ 需增强 | 右键菜单操作需 API 支持 |
| 不破坏公式栏联动 | ⚠️ 需验证 | cell-click → 公式栏显示/编辑 |

### 3.3 迁移计划（P1-1.6）

**结论：DisclosureEditor 是迁移复杂度最高的页面。**

附注编辑器本质是一个"简易电子表格"——支持动态行列、合并、公式、格式。
这与 `GtFormTable`（固定列定义 + 行内编辑）的设计范式差异较大。

**建议方案**：
1. **短期**：保持 `el-table` + 豁免注释 `<!-- allow-el-table: 附注编辑器需动态行列+合并+公式，GtFormTable 尚不支持 -->`
2. **中期**：评估是否将附注表格迁移到 Univer（已用于表格底稿），共享底层
3. **长期**：如坚持迁移到 GtFormTable，需先实现：
   - 动态列定义 API
   - span-method 支持
   - 公式引擎集成
   - 插入/删除行列 API

**风险评估**：高。强行迁移可能引入回归，且投入产出比不高。建议 P2 阶段再议。

---

## 4. GtTableExtended / GtFormTable 能力缺口汇总

| 缺口能力 | 需求来源 | 优先级 | 实现建议 |
|----------|---------|--------|---------|
| 多级列头（嵌套 column） | TrialBalance 试算平衡表 | P1 | column 定义支持 children 数组 |
| span-method（合并单元格） | ReportView 权益变动表、DisclosureEditor | P1 | 透传 el-table 的 span-method prop |
| row-class-name（行样式） | TrialBalance、ReportView | P1 | 透传到底层 el-table |
| cell-class-name（单元格样式） | DisclosureEditor | P2 | 透传到底层 el-table |
| @cell-contextmenu（右键） | 全部页面 | P1 | 事件透传或 slot |
| @cell-dblclick（双击编辑） | ReportView | P1 | 事件透传 |
| fixed 列 | ReportView | P1 | column 定义支持 fixed 属性 |
| sortable + sort-method | ReportView | P1 | column 定义支持排序配置 |
| 条件编辑（部分行可编辑） | TrialBalance | P2 | editable 回调函数 |
| 动态列数（运行时变化） | DisclosureEditor | P2 | 列定义响应式数组 |
| 公式单元格 | DisclosureEditor | P2 | 需集成 formula_engine |

---

## 5. 迁移风险与缓释措施

| 风险 | 影响 | 缓释 |
|------|------|------|
| useCellSelection 依赖 el-table DOM | 复制选中区域功能失效 | 迁移时先验证 cell-selection 兼容性 |
| 多级列头渲染不一致 | 试算平衡表错位 | 先在独立 demo 验证再迁移 |
| span-method 计算逻辑复杂 | 权益变动表合并错乱 | 保留旧实现作 fallback |
| 公式计算与表格渲染耦合 | 附注编辑器功能回归 | 短期不迁移，加豁免注释 |
| 右键菜单事件链路变化 | 穿透/溯源功能失效 | 逐页面验证事件冒泡 |

---

## 6. 执行建议

1. **先增强 GtTableExtended**：补齐 row-class-name、@cell-contextmenu、fixed、sortable、span-method 透传
2. **先迁移简单表格**：弹窗内展示表、跨表核对表（无编辑、无合并）
3. **再迁移科目明细表**：中等复杂度，验证右键 + 条件格式 + CommentTooltip
4. **试算平衡表最后**：需先实现多级列头支持
5. **附注编辑器暂缓**：加豁免注释，P2 阶段评估 Univer 方案
