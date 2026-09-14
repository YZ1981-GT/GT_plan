# Requirements — A5-1 现金流量表审计 精美 HTML 专属组件

## Introduction

A5-1（现金流量表审计）是一个多 sheet 综合性底稿（程序表+审定表+检查表混合），需要从当前 OnlyOffice xlsx 编辑模式升级为精美 HTML 专属组件，同时保留 OnlyOffice Excel 编辑模式作为备选（双模式切换）。

源模板：`A5-1 现金流量表审计.xlsx`，包含 7 个有效 sheet + GT_Custom：
- 表头（封面，客户/期间/编制人 + 底稿目录索引）— 融入编制信息头，不单独 Tab
- A5-1 现金流量审计程序（程序表，21 步骤：6 主步骤 + 15 子步骤 + 审计目标 3 条 + 程序批准签字）
- A5-1-1 列示于现金流量表的现金及现金等价物（审定表，8 行数据 + 编制说明 7 条只读）
- A5-1-3 相关报表勾稽关系核对（检查表，4 大类各 10 行项目 + 合计/报表数/差异）
- A5-1-4 现金流量核查（补充资料——取得/处置子公司，各 ~10 行，含差异/原报/测算/依据）
- A5-1-5 现金流量核查（现金和现金等价物明细，10 行：库存/银行/其他货币/央行/同业/等价物/期末余额）
- A5-1-6 其他现金流量（经营/投资/筹资 3 类收支对照，各 10 行 + 合计 + 编制说明 9 条只读）
- 会计提示（只读参考：实务问题 2 条 + 等价物范围 + 受限存款列报 + 分类对照表 18 条）

**父组件上下文：** A5-1 在 A5（CashFlowVerification.vue）内作为一个 Tab 内嵌渲染。wp_code_overrides 中 A5-1 映射为 `skip`，由父组件通过 `force_component_type=a5-1-cashflow-audit` 参数加载渲染器。

## Requirements

### Requirement 1: 专属组件注册

**User Story:** 作为前端开发者，我需要一个专属 componentType 来实现 A5-1 的多 Tab 结构化渲染，使其不与通用 audit-sheet 冲突。

#### Acceptance Criteria

1. THE 系统 SHALL 注册新 componentType `a5-1-cashflow-audit`
2. THE wp_code_overrides.json SHALL 保持 A5-1 为 `skip`（在 CashFlowVerification Tab 内嵌渲染）
3. THE CashFlowVerification.vue SHALL 在 A5-1 Tab 中渲染 GtA51CashflowAudit（替代 GtOnlyOfficeSheet）
4. THE VALID_COMPONENT_TYPES（`wp_classification_service.py`）SHALL 包含 `a5-1-cashflow-audit`
5. THE htmlRendererRegistry SHALL 注册 `a5-1-cashflow-audit` → lazy import GtA51CashflowAudit.vue
6. THE RENDERER_DISPATCH SHALL 新增 `a5-1-cashflow-audit` → `_a51_cashflow.render` 渲染策略函数

### Requirement 2: 双模式切换（结构化 HTML + OnlyOffice Excel）

**User Story:** 作为审计助理，我需要在精美 HTML 结构化视图和 Excel 原始编辑之间自由切换，结构化视图用于日常填写，Excel 模式用于复杂公式调整或自由格式编辑。

#### Acceptance Criteria

1. THE 组件 SHALL 在顶部提供 el-segmented 模式切换控件，两个选项：「结构化视图」|「Excel 编辑」
2. THE 组件 SHALL 默认选中「结构化视图」模式
3. WHEN 用户选择「Excel 编辑」, THE 组件 SHALL 隐藏结构化视图并显示 GtOnlyOfficeSheet
4. THE GtOnlyOfficeSheet SHALL 以 whole-workbook=true 模式加载（用户可在 Excel 内自由切换 sheet）
5. WHEN 组件挂载时, THE 组件 SHALL 调用 `/api/workpapers/onlyoffice/health` 检查 OnlyOffice 服务可用性
6. IF OnlyOffice 健康检查返回 `healthy=false`, THEN THE 「Excel 编辑」选项 SHALL 显示为禁用状态并附 tooltip 说明"OnlyOffice 服务不可用"
7. WHILE 模式切换进行中, THE 组件 SHALL 显示 loading 遮罩防止重复操作
8. WHEN 用户从 Excel 模式切回结构化视图, THE 组件 SHALL 重新调用 render-config API 刷新所有 Tab 数据（Excel 中的修改可能影响数据）
9. THE 组件 SHALL 在模式切换时保留当前 Tab 选中状态（切回后恢复同一 Tab）

### Requirement 3: 6 Tab 结构化渲染

**User Story:** 作为审计助理，我需要 A5-1 底稿的 7 个 sheet 以 6 个直观 Tab 呈现，避免在 Excel 中反复切换 sheet 查找。

#### Acceptance Criteria

1. THE 组件 SHALL 提供 6 个 Tab：程序表 | 现金等价物审定 | 勾稽核对 | 核查-子公司 | 核查-明细 | 其他现金流量
2. THE Tab 栏 SHALL 支持鼠标滚轮横向滚动（防止 Tab 标签溢出隐藏）
3. THE 组件 SHALL 默认显示第一个 Tab（程序表）
4. THE Tab 切换 SHALL 为前端即时切换（所有 Tab 数据一次性加载，不按 Tab 懒加载）

### Requirement 4: Tab 1 — A5-1 程序表

**User Story:** 作为审计助理，我需要逐步勾选 21 个审计程序步骤的执行情况，并查看整体进度，以便跟踪现金流量表审计的完成状态。

#### Acceptance Criteria

1. THE 程序表 SHALL 顶部显示审计目标（3 条，只读卡片，浅蓝背景）
2. THE 程序表 SHALL 渲染 21 个步骤为卡片列表（6 主步骤 + 15 子步骤，层级缩进）
3. EACH 步骤卡片 SHALL 含：序号标签 + 审计程序描述 + 是否适用(Y/N/NA) + 执行人 + 执行情况说明 + 索引号
4. THE 子步骤 SHALL 按层级缩进：level 1 左边距 24px，level 2 左边距 48px
5. THE 组件 SHALL 在步骤列表上方显示进度统计：`已填 X / 总数 21` + el-progress 进度条
6. THE Y/N/NA 按钮 SHALL 有色彩编码：Y=绿色(#67C23A) / N=红色(#F56C6C) / NA=灰色(#909399)
7. THE 底部 SHALL 显示审计程序批准签字区：经理签字(input) + 签字日期(date-picker)
8. THE 进度计算公式 SHALL 为：`已填数 = COUNT(步骤中 conclusion ∈ {Y, N, NA} 的条目)`

### Requirement 5: Tab 2 — A5-1-1 审定表（含公式）

**User Story:** 作为审计助理，我需要逐行填写现金及现金等价物的未审金额和调整金额，系统自动计算审定数和净增减额，以确保金额准确可追溯。

#### Acceptance Criteria

1. THE 审定表 SHALL 渲染为精美表格，8 行数据：
   - audit-1: {year}年12月31日货币资金
   - audit-2: 减：使用受到限制的存款
   - audit-3: 减：其他扣减项
   - audit-4: 加：持有期限不超过三个月的国债投资
   - audit-5: 加：其他加项
   - audit-6: {year}年12月31日现金及现金等价物余额（自动计算行）
   - audit-7: 减：{prev_year}年12月31日现金及现金等价物余额
   - audit-8: 现金及现金等价物净增加/(减少)额（自动计算行）
2. EACH 可编辑行（audit-1 ~ audit-5, audit-7）SHALL 含列：项目名称(只读) | 未审金额(input) | 审计调整(input) | 调整说明(input) | 审定数(自动) | 备注(input)
3. THE 审定数列 SHALL 按公式实时计算：**`审定数 = 未审金额 + 审计调整`**（parseFloat 容错，NaN → 0）
4. THE audit-6 行（现金等价物余额）SHALL 为自动计算行，公式：**`audit-6.审定数 = audit-1.审定数 − audit-2.审定数 − audit-3.审定数 + audit-4.审定数 + audit-5.审定数`**
5. THE audit-8 行（净增减额）SHALL 为自动计算行，公式：**`audit-8.审定数 = audit-6.审定数 − audit-7.审定数`**
6. THE 自动计算行（audit-6, audit-8）SHALL 背景色灰色(#F5F7FA)且所有列不可编辑
7. THE 底部 SHALL 有"审计说明" textarea（可编辑，用于记录审计结论）
8. THE 编制说明区（6 条）SHALL 以 el-collapse 折叠显示（默认折叠，点击展开，只读参考文本）

### Requirement 6: Tab 3 — A5-1-3 勾稽核对（含公式）

**User Story:** 作为审计助理，我需要将各项现金流量的计算组成明细加总后与报表数对比，快速发现勾稽差异以锁定审计调整方向。

#### Acceptance Criteria

1. THE 勾稽核对 SHALL 按 4 大类分组卡片渲染：
   - reconcile-1：销售商品、提供劳务收到的现金（10 项）
   - reconcile-2：购买商品、接受劳务支付的现金（10 项）
   - reconcile-3：支付给职工以及为职工支付的现金（3 项）
   - reconcile-4：支付的各项税金（3 项）
2. EACH 分组 SHALL 含：标题 + 项目行（项目名/金额 input/备注 input/索引号 input） + 合计行 + 报表数行 + 差异行
3. THE 合计行 SHALL 按公式实时计算：**`合计 = SUM(该分组所有项目行的金额)`**
4. THE 差异行 SHALL 按公式实时计算：**`差异 = 合计 − 报表数`**
5. THE 差异行 SHALL 在 `|差异| > 0` 时红色高亮警告（文字 #F56C6C + 背景 #FEF0F0）
6. EACH 分组 SHALL 为独立卡片，带圆角边框(border-radius: 8px)和轻阴影
7. THE 金额列 SHALL 右对齐，使用 displayPrefs.fmtAmount 千分位格式化

### Requirement 7: Tab 4 — A5-1-4 核查-子公司（含公式）

**User Story:** 作为审计助理，我需要对取得/处置子公司的现金流量进行测算复核，比较原报数与测算数的差异以验证报表准确性。

#### Acceptance Criteria

1. THE 核查 SHALL 分为两部分卡片：「一、取得子公司及其他营业单位」+「二、处置子公司及其他营业单位」
2. EACH 部分 SHALL 含 ~10 行表格，列结构：项目(只读) | 差异(自动) | 原报数(input) | 测算数(input) | 测算依据(input)
3. THE 差异列 SHALL 按公式实时计算：**`差异 = 测算数 − 原报数`**（parseFloat 容错，NaN → 0）
4. THE 差异列 SHALL 在 `|差异| > 0` 时红色标注（文字变红 #F56C6C + 加粗）
5. THE 两部分 SHALL 为独立卡片上下排列，各带标题
6. THE「支付/收到净额」行 SHALL 为自动汇总行：
   - 取得子公司：**`支付净额 = 支付现金总额 − 子公司持有现金`**
   - 处置子公司：**`收到净额 = 收到现金总额 − 子公司持有现金`**

### Requirement 8: Tab 5 — A5-1-5 核查-现金明细（含公式）

**User Story:** 作为审计助理，我需要逐项核对现金及现金等价物各组成部分的原报数与测算数，以验证现金流量表列示的现金余额准确。

#### Acceptance Criteria

1. THE 现金明细 SHALL 渲染为表格，行项目：库存现金/银行存款/其他货币资金/央行款项/同业存放/拆放同业/现金等价物(短期债券)/期末余额(自动)/受限部分
2. 列结构同 Tab 4：项目(只读) | 差异(自动) | 原报数(input) | 测算数(input) | 测算依据(input)
3. THE 差异列 SHALL 按公式实时计算：**`差异 = 测算数 − 原报数`**（与 Tab 4 相同逻辑）
4. THE 差异列 SHALL 在 `|差异| > 0` 时红色标注
5. THE「期末余额」行 SHALL 为自动汇总行，公式：**`期末余额.测算数 = SUM(库存现金 ~ 现金等价物的测算数) − 受限部分.测算数`**
6. THE 底部注释 SHALL 以小字灰色(#909399, font-size:12px)显示持有待售资产相关说明

### Requirement 9: Tab 6 — A5-1-6 其他现金流量（含公式）

**User Story:** 作为审计助理，我需要按经营/投资/筹资三类分别填写其他现金流量收支明细，系统自动汇总合计以便与报表核对。

#### Acceptance Criteria

1. THE 其他现金流量 SHALL 按 3 大类分组：经营活动 | 投资活动 | 筹资活动
2. EACH 类 SHALL 渲染为**左右对照**布局：左列="收到的其他…现金"（10 项+合计），右列="支付的其他…现金"（10 项+合计）
3. EACH 项 SHALL 含：项目名(可编辑 input，模板提供默认值) + 金额(input，正数填入)
4. THE 左侧合计 SHALL 按公式实时计算：**`收到合计 = SUM(收到项1 ~ 收到项10)`**
5. THE 右侧合计 SHALL 按公式实时计算：**`支付合计 = SUM(支付项1 ~ 支付项10)`**
6. THE 合计行 SHALL 背景色灰色(#F5F7FA)且金额列不可编辑
7. THE 金额列 SHALL 右对齐，使用 displayPrefs.fmtAmount 千分位格式化
8. THE 编制说明区（9 条）SHALL 以 el-collapse 折叠显示（默认折叠，只读参考）

### Requirement 10: 会计提示弹窗

**User Story:** 作为审计助理，我需要随时参考现金流量表相关的会计提示（等价物范围、受限存款列报、分类对照等），以便在填写过程中不遗漏关键披露。

#### Acceptance Criteria

1. THE 组件 SHALL 在顶部栏右侧提供「💡 会计提示」按钮
2. WHEN 点击 SHALL 弹出 el-drawer（右侧抽屉，宽度 480px）
3. THE 抽屉 SHALL 按 4 节渲染内容：
   - 第一节：实务问题（2 个问答式条目）
   - 第二节：现金及现金等价物范围（可/不可作为现金等价物列示的对照说明）
   - 第三节：受限存款及利息收入列报（分类对照表 18 行：项目→现金流量表列示科目）
   - 第四节：政府补助 + 固定资产进项税处理
4. THE 内容 SHALL 为只读参考（不可编辑），使用清晰排版（标题加粗 + 列表缩进 + 表格对齐）
5. THE 抽屉关闭后 SHALL 不影响主组件状态

### Requirement 11: 自动保存与数据持久化

**User Story:** 作为审计助理，我填写的所有数据需要自动保存，避免手动保存操作和数据丢失。

#### Acceptance Criteria

1. THE 组件 SHALL 通过 debounce 2s 自动保存所有 Tab 的用户填写数据
2. THE 保存 SHALL 使用 `PUT /api/workpapers/{wpId}/checklist-responses`
3. THE item_id 格式 SHALL 为 `a51-{tab}-{field_id}`（如 `a51-program-step-1.conclusion`、`a51-audit-row1.unadjusted`）
4. THE remark 字段 SHALL 存储 JSON 格式的字段值
5. THE 组件加载时 SHALL 从 render-config 的 responses 字段恢复所有已保存数据
6. IF 保存失败, THEN THE 组件 SHALL 重试最多 3 次（间隔 1s/2s/4s 指数退避）+ ElMessage.warning
7. THE 顶部栏 SHALL 显示"已保存 X秒前"状态指示（✓ 图标 + 灰色文字）
8. WHEN 组件卸载时（onBeforeUnmount）, THE 组件 SHALL flush 所有 pending 变更确保不丢数据
