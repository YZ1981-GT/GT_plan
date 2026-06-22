# Requirements Document

## Introduction

D0 函证系列已为 9 张 sheet 分别建立专用组件 spec（D0-1 函证结果汇总 / D0-2 核实被函证单位 / D0-3 跟函过程控制 / D0-4 差异调节 / D0-4b 差异检查表 / D0-5 合同负债替代 / D0-6 应收替代 / D0-7 回函可靠性 / D0-8 舞弊风险评价）。这些表共同构成一个**函证子系统**：同一笔函证的信息分散在多张表中，通过函证索引关联。

本 spec 是**函证模块的横切协同设计**——不新增业务底稿，而是统一 9 张表之间的协同机制：① 函证主数据单一数据源（SSOT，避免 9 表各存副本漂移）② 函证生命周期状态机（统一 confirmation_status）③ 统一枚举命名空间（避免重复/冲突）④ 共享 UI 设计规范（看板/红线配色/tooltip/自动取数标识/网格美化一致）⑤ 跨表"本笔函证相关底稿"导航 ⑥ D0-1 作为枢纽的下游分发。

目标：从**实用性、使用方便、美观、模块联动** 4 个维度统一函证子系统，使审计助理与现场经理在 9 张表间获得一致、连贯、不漂移的体验。

## Glossary

- **函证 SSOT（Single Source of Truth）**：一个项目所有函证的主数据台账，主键 confirm_index，由 D0-1 承载
- **confirm_index（函证索引）**：贯穿 9 张表的全局主键，唯一标识一笔函证
- **函证主数据字段**：confirm_index / subject(科目) / entity_name(被询证单位) / book_amount(账面发函金额) / confirm_method(函证方式) / reply_method(回函方式) / reply_status(回函状态) / reply_amount(回函金额) / is_consistent(是否相符)
- **confirmation_status（函证状态）**：函证生命周期状态枚举（见需求 2）
- **confirmation_dicts**：函证模块统一枚举命名空间
- **ConfirmationKit**：函证模块共享 UI 基础组件与设计规范（看板/工具栏/状态徽章/tooltip/网格美化）
- **函证导航条**：选中某笔函证时展示其在 9 张表中状态与跳转入口的面包屑

## Requirements

### 需求 1：函证主数据单一数据源（SSOT）

**用户故事**：作为审计助理，我不想在 9 张表里反复录入同一被询证单位的名称/科目/金额，更不想它们彼此对不上。

#### 验收标准
1. THE 函证主数据 SHALL 以 confirm_index 为主键单源存储，由 D0-1 函证结果汇总表承载（SSOT）
2. THE 主数据字段（confirm_index/subject/entity_name/book_amount/confirm_method/reply_method/reply_status/reply_amount/is_consistent）SHALL 仅存一份
3. WHEN D0-2 发函前核实 THEN 系统 SHALL 写入/更新该笔函证主数据（被询证单位/科目/地址/联系人等）
4. WHEN D0-3/D0-4/D0-4b/D0-5/D0-6/D0-7/D0-8 需要被询证单位/科目/金额 THEN 系统 SHALL 通过 confirm_index 引用 D0-1 主数据（只读派生，不持久化副本）
5. WHEN 主数据更新 THEN 所有引用表 SHALL 获取最新值（不漂移）
6. WHEN 某表独立使用（主数据缺失）THEN 系统 SHALL 降级允许手工录入，不阻塞
7. THE 主数据共享 SHALL 通过既有跨底稿引用机制（cross_wp_references / address_registry wp 域）实现

### 需求 2：函证生命周期状态机

**用户故事**：作为现场经理，我希望一眼看清每笔函证走到了哪一步、卡在哪里。

#### 验收标准
1. THE 后端 `_DICTS` SHALL 定义 `confirmation_status` 枚举：未核实 / 已核实 / 已发函 / 跟函中 / 已回函 / 未回函 / 待可靠性验证 / 相符 / 有差异 / 替代程序中 / 替代完成 / 存在舞弊迹象
2. THE 状态流转 SHALL 由各表事件驱动：D0-2 核实完成→已核实；D0-1 发函→已发函；D0-3 跟函→跟函中；D0-1 回函登记→已回函/未回函；D0-7 验证→待可靠性验证/相符；D0-4 差异→有差异；D0-5/D0-6→替代程序中/替代完成；D0-8→存在舞弊迹象
3. THE confirmation_status SHALL 作为主数据字段单源存储（D0-1 维护）
4. THE D0-1 看板 SHALL 展示全项目函证的状态分布（各状态计数 + 占比）
5. WHEN 状态异常停滞（如已发函久未回函 / 有差异久未调节）THEN 系统 SHALL 在看板提示

### 需求 3：统一枚举命名空间 confirmation_dicts

**用户故事**：作为开发与维护者，我希望函证枚举集中管理，不要 9 张表各定义一套、键名冲突。

#### 验收标准
1. THE 后端 SHALL 将函证相关枚举集中于 `confirmation_dicts` 命名空间，统一注册：
   - confirmation_subject（科目）/ confirmation_method（积极式/消极式）/ confirmation_reply_method（原件/传真/电子邮件）/ confirmation_send_result（送抵/退回）/ confirmation_followup_scenario（现场即时/无法即时）/ confirmation_diff_type（时间性/记账/未达账项/其他）/ sampling_method（随机/系统/货币单元/随意）/ reply_reliability_conclusion（可靠/部分可靠/不可靠）/ confirmation_status（见需求 2）/ yes_no / yes_no_na
2. EACH 表 SHALL 复用同一枚举（不重复定义同义枚举）
3. WHEN 多表用到同一枚举（如 yes_no_na 用于 D0-3/D0-8）THEN SHALL 引用同一 dictKey
4. THE 枚举新增/修改 SHALL 单点维护，全模块生效

### 需求 4：共享 UI 设计规范（ConfirmationKit）

**用户故事**：作为审计助理，我希望 9 张函证表长得像一家人，配色和操作一致，不用每张重新适应。

#### 验收标准
1. THE 9 个组件 SHALL 复用统一基础组件：ConfirmationDashboard（看板）/ ConfirmationToolbar（工具栏）/ ConfirmationStatusBadge（状态徽章）/ tooltip 问号图标 / 自动取数视觉标识
2. THE 红线配色 SHALL 统一：绿=完成/相符/已平 ; 橙=需关注/未完成/覆盖不足/待处理 ; 红=异常/不可靠/超重要性/舞弊迹象
3. THE 金额格式 SHALL 统一：右对齐 / 千分位 / 2 位小数 / 单位"元"
4. THE 网格美化 SHALL 统一规范（沿用 GtGridSheet）：分组表头按区/科目着色（5 色轮转）/ 冻结首列或序号列 / 斑马纹 / 空值淡化
5. THE 自动取数（从 D0-1/上游带入）SHALL 用统一视觉标识（如蓝色角标/浅蓝底）区分手工录入
6. THE tooltip 提示 SHALL 统一样式（问号图标 + hover 浮层），不占数据行空间
7. THE 工具栏 SHALL 统一布局与图标（新增/删除/带入/保存/导入/导出 顺序一致）

### 需求 5：跨表"本笔函证相关底稿"导航

**用户故事**：作为审计助理，我在看一笔函证的差异时，想一键跳到它的核实记录、跟函记录、可靠性验证，而不用在 9 个 tab 里翻找。

#### 验收标准
1. WHEN 在任一函证表中选中某 confirm_index THEN 系统 SHALL 展示"本笔函证相关底稿"导航条：D0-2 核实 | D0-1 汇总 | D0-3 跟函 | D0-7 可靠性 | D0-4 差异 | D0-4b 检查 | D0-5/D0-6 替代 | D0-8 舞弊
2. THE 导航条 SHALL 按该笔函证状态点亮可用入口（无关/不存在的置灰）
3. WHEN 点击导航入口 THEN 系统 SHALL 跳转到对应表并定位到该 confirm_index 行
4. THE 跳转 SHALL 保留来源上下文（可返回）

### 需求 6：D0-1 枢纽下游分发

**用户故事**：作为审计助理，我希望从 D0-1 汇总表出发，按每笔函证的状态一键把它分发到该做的下游表，而不是去每张下游表分别"拉取"。

#### 验收标准
1. THE D0-1 SHALL 提供"分发到下游"动作：按每笔函证状态分发
   - 差异≠0 → 分发到 D0-4 差异调节
   - 未回函 → 分发到 D0-5（合同负债）/ D0-6（应收账款）（按科目）
   - 电子回函（传真/邮件）→ 分发到 D0-7 可靠性验证
2. THE 分发 SHALL 与下游表的"从 D0-1 带入"等价（双向均可，去重一致）
3. THE 分发 SHALL 批量（一次处理所有符合条件的函证）
4. WHEN 已分发 THEN D0-1 SHALL 标记该笔的下游处理状态（避免重复分发）

### 需求 7：不破坏已有 9 个 spec

#### 验收标准
1. THE 本协同 spec SHALL 不改变 9 个组件 spec 的核心组件结构（仅统一其共享层）
2. THE 各 spec 的 componentType 注册 SHALL 保持不变
3. THE 协同机制 SHALL 增量实现（SSOT/状态机/导航条 可分阶段落地，不阻塞单表先行）

### 需求 8：统一交互能力基线（编辑/右键/选区/复制/粘贴/求和）

**用户故事**：作为审计助理，我希望每张函证表的所有数据表格/子表都能像报表模块一样编辑、右键、框选、复制粘贴，体验完全一致，不因表而异。

#### 验收标准
1. THE 所有函证表格（含 master 网格、明细子表、宽表区块、检查清单）SHALL 一致具备以下交互能力基线：单元格直接编辑（按列类型 el-input/el-input-number/el-select/date-picker）/ CellContextMenu 右键菜单 / useCellSelection 选区（单击/Ctrl/Shift/拖拽框选）/ 复制（TSV+HTML 双格式）/ 粘贴（从 Excel/TSV 批量填充）/ 多选求和 / 增删行
2. THE D0-4b 的 4 个 B/C/F/G 明细子表（DetailSubTable）SHALL 同样接入 useCellSelection（选区/复制/粘贴/求和），不止右键
3. THE D0-8 检查清单 SHALL 明确支持 useCellSelection（至少复制/粘贴，便于批量贴入迹象与应对），不标"可选"
4. THE 所有表 SHALL 一致支持"导入/导出"（含 D0-8 导入自定义舞弊迹象清单），无表缺失
5. WHEN 只读 THEN 编辑/增删/粘贴/导入禁用，复制/求和/导出仍可用（一致守卫）
6. THE 键盘导航（Tab/Enter 移动单元格、Esc 取消编辑）SHALL 在所有表格一致（沿用 useCellSelection/el-table 默认）

## Non-Goals

- 不实现"函证总览驾驶舱"独立页面（按 confirm_index 聚合 9 表的全景视图）——列为 v3.0 愿景，本 spec 仅打好主数据/状态/导航地基
- 不重写 9 个组件 spec（仅抽取共享层 + 补协同条款）
- 不改 B50 风险评估 / AJE 调整分录 / 替代程序业务逻辑本身
- 不改 OnlyOffice 路径
