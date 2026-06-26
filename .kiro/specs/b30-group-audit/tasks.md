# Tasks — B30 集团审计范围确定底稿

## 1. 注册与配置

- [x] 1.1 在 `htmlRendererRegistry.ts` 的 `HtmlComponentType` union 中新增 `'b30-group-audit'`
- [x] 1.2 在 `REGISTRY_LIST` 中新增注册条目：componentType=`b30-group-audit`, icon='🏢', label='B30 集团审计范围确定', emits=['save','completed'], contextProps='standard'
- [x] 1.3 添加 lazy import: `const GtB30GroupAudit = defineAsyncComponent(() => import('./GtB30GroupAudit.vue'))`
- [x] 1.4 更新 `wp_code_overrides.json`：将 `"B30"` 映射为 `"b30-group-audit"`，将 `"B30-1"`~`"B30-5"` 映射为 `"skip"`
- [x] 1.5 后端 `checklist_responses.py` 中 conclusion 校验增加 `B30-` 前缀分支
  - 在现有 `elif item.item_id.startswith("B23-"):` 分支后新增 `elif item.item_id.startswith("B30-"):` 分支
  - 白名单：`重要组成部分/非重要组成部分/不重要组成部分/全面审计/特定项目审计/分析性程序/不执行程序/子公司/分公司/合营企业/联营企业/分部/已确认/未确认/不适用/充分/需补充/不充分/Y/N`
  - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5, 11.6, 12.1, 12.2, 12.3, 12.4_

## 2. 组合式函数

- [x] 2.1 创建 `composables/useB30FormData.ts` — 数据加载/debounce保存/即时保存
  - 实现 `loadAll()` 从 GET checklist-responses 加载全部 `B30-*` 数据到 `allResponses` Map
  - 实现 `saveImmediate(items)` 通过 PUT 批量保存（Classification/Scope_Type/Independence/Competence/签字触发）
  - 实现 `saveDebouncedText(item)` debounce 2000ms 文本保存（名称/持股比例/财务数据/备注/审计师姓名/特定项目说明字段）
  - 实现 `flushPendingSave()` 组件卸载时 flush 未保存数据
  - 实现 `getField(itemId)` / `setFieldImmediate(itemId, data)` 辅助方法
  - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7_

- [x] 2.2 创建 `composables/useB30GroupAudit.ts` — 集团结构树/组成部分表格/分类/范围/重要性分配/覆盖率/审计师/EventBus
  - 实现 `treeData` / `treeNodeCount` / `treeMaxDepth` 响应式数据
  - 实现 `addComponent(parentId, entity)` / `removeComponent(componentId)` / `moveComponent(componentId, newParentId)` / `updateComponent(componentId, field, value)` 树节点 CRUD
  - 实现 `components` 计算属性（ComponentEntity[] 扁平列表）+ `groupTotals`（集团合计）+ `filteredComponents(filter)` 筛选视图
  - 实现 `suggestClassification(entity)` 分类自动建议（15%/5% 双阈值）+ `setClassification(...)` + `getClassification(...)`
  - 实现 `groupMateriality` / `suggestAllocatedMateriality(entity)` / `validateMaterialityBounds(allocated)` / `setAllocatedMateriality(...)` 重要性分配
  - 实现 `suggestScopeType(classification)` / `setScopeType(...)` / `getScopeType(...)` / `allScopeDetermined` 审计范围确定
  - 实现 `setAuditorInfo(...)` / `getAuditorInfo(...)` / `clearAuditorInfo(...)` 组成部分审计师管理
  - 实现 `coverageMatrix` / `coverageTotals` / `coverageWarnings` 覆盖率热力图计算（加权算法：全面=1.0/特定=0.5/分析=0.25/不执行=0.0）
  - 实现 `dashboardStats` 计算属性（ScopeDashboardStats：分类分布/范围分布/覆盖率/待确认事项）
  - 实现 `linkageInfo` 计算属性 + `publishScopeDetermined()` / `onMaterialityDetermined(payload)` EventBus 联动
  - _Requirements: 1.1~1.8, 2.1~2.8, 3.1~3.9, 4.1~4.7, 5.1~5.7, 6.1~6.8, 7.1~7.6, 8.1~8.6_

- [x] 2.3 创建 `composables/useB30Review.ts` — 现场经理复核签字/只读状态/Amendment机制
  - 实现 `isReviewed` / `isReadonly` / `canReview` 计算属性
  - 实现 `pendingItems` 计算属性（Classification为空 + Scope_Type为空 + 重要组成部分Independence未确认）
  - 实现 `reviewInfo` 计算属性（复核人/日期）
  - 实现 `doReview()` 签字保存方法（前置条件：所有组成部分 Classification 非空 + Scope_Type 非空 + 重要组成部分独立性已确认）
  - 实现 `startAmendment(reason)` 修改机制（重置复核状态 + 记录修改原因 + 解锁编辑）
  - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.6_

## 3. Vue 组件实现

- [x] 3.1 创建 `GtB30GroupAudit.vue` 骨架 — script setup + props/emits + composables 初始化
  - Props: wpId, projectId, wpCode, year, readonly
  - Emits: save, completed
  - 引入三个 composables 并初始化
  - onMounted 中 loadAll + 注册 EventBus 监听 `materiality:determined`
  - onBeforeUnmount 中 flushPendingSave + 注销 EventBus 监听
  - _Requirements: 11.1, 11.4, 11.5, 11.6_

- [x] 3.2 实现 Scope_Dashboard 范围仪表盘 — 分类分布/范围分布/覆盖率进度条/待确认事项
  - 顶部汇总面板渲染 classificationDistribution（重要N/非重要N/不重要N/未分类N）+ 颜色编码
  - 范围分布渲染 scopeDistribution（全面N/特定N/分析N/不执行N/未确定N）+ 颜色编码
  - 三个覆盖率进度条（总资产/营收/利润）：≥80%绿色 / 60%~80%黄色 / <60%红色
  - 待确认事项计数（未分类 + 未确定范围 + 独立性未确认）
  - Group_Materiality 金额显示 + 已分配重要性组成部分数量
  - 树节点总数 + 层级深度
  - 数据实时响应 dashboardStats 变更
  - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 13.3_

- [x] 3.3 实现 Group_Structure_Tree 集团结构树 — el-tree + 节点CRUD + 拖拽 + 色带
  - el-tree 渲染 treeData，支持展开/折叠（默认全部展开）
  - 节点添加：弹窗输入名称/类型/持股比例 → addComponent
  - 节点删除：叶子节点直接删除，有子节点提示"请先删除或移动子节点"
  - 拖拽调整层级：el-tree draggable + moveComponent（最多5层嵌套约束）
  - 每个节点左侧 4px 色带标识 Classification 颜色（重要=红#ff4d4f/非重要=黄#faad14/不重要=灰#bfbfbf）
  - 节点标题旁显示 Scope_Type 简写标签（全面/特定/分析/无）
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 13.4_

- [x] 3.4 实现组成部分明细表格 — 结构化表格 + 双向同步 + 占比计算 + 分类建议
  - 表格列：序号/名称/类型/持股比例/总资产/营收/利润/总资产占比/营收占比/利润占比/Classification(下拉)/备注
  - 与 Group_Structure_Tree 双向同步（增删改实时联动）
  - 自动计算三个占比（占集团合计百分比）+ 底部集团合计行
  - 分类自动建议显示（>15%→重要/>5%→非重要/≤5%→不重要）
  - 手动覆盖分类时弹出"调整理由"输入（无理由拒绝覆盖）+ "已手动调整"标识
  - Financial_Data 变更时重新计算占比 + 更新分类建议
  - 筛选功能（全部/仅重要/仅非重要/仅不重要）
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8_

- [x] 3.5 实现重要性分配区域 — B15联动 + 自动建议 + 约束校验 + 警告
  - 顶部显示 Group_Materiality 金额（从 B15 获取）
  - 仅"重要组成部分"显示 Allocated_Materiality 输入字段
  - 自动建议公式：max(占比) × Group_Materiality × 0.75，clamp 到 [15%, 85%]
  - 超出 15%~85% 区间时字段旁黄色警告提示
  - 允许手动调整金额（调整后保存覆盖值）
  - B15 未完成时灰色提示"B15 未完成，集团重要性待定" + 禁用自动建议
  - 非重要/不重要组成部分显示"不分配"标注
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9_

- [x] 3.6 实现审计范围确定区域 — Scope_Type下拉 + 自动建议 + 警告 + 特定项目说明
  - 每个组成部分 Scope_Type 下拉：全面审计/特定项目审计/分析性程序/不执行程序
  - 自动建议：重要→全面/非重要→特定/不重要→不执行
  - 手动覆盖自动建议时弹出"调整理由"输入
  - 重要组成部分 Scope_Type ≠ 全面审计时橙色警告
  - Scope_Type=特定项目审计时展示"特定项目说明"文本区
  - Scope_Type 变更时重新计算覆盖率 + 更新热力图
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7_

- [x] 3.7 实现组成部分审计师管理区域 — 审计师信息 + 独立性/胜任能力确认 + 警告
  - Scope_Type 非"不执行程序"的组成部分显示审计师管理区域
  - 字段：审计师姓名/事务所名称 + Independence(下拉) + Competence(下拉) + 备注
  - Independence="未确认"时红色警告标识
  - Competence="不充分"时红色警告 + "需采取额外措施或变更组成部分审计师"提示
  - Scope_Type 变更为"不执行程序"时清空审计师信息 + 标注"无需指派"
  - 支持同一审计师姓名/事务所复用选择
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7_

- [x] 3.8 实现覆盖率热力图 — 矩阵渲染 + 加权计算 + 颜色分级 + 警告 + tooltip
  - 矩阵：行=各组成部分，列=总资产/营收/利润，单元格=加权覆盖贡献百分比
  - 颜色分级：≥15%深绿 / 5%~15%浅绿 / <5%浅灰 / 0%白色
  - 底部合计行：三个指标的加权覆盖率百分比
  - 任一指标覆盖率 <60% 时红色警告"覆盖率不足，建议扩大审计范围"
  - 鼠标悬停 tooltip：组成部分名称 + 指标金额 + 占比 + 范围类型 + 加权后贡献
  - Scope_Type 或 Financial_Data 变更时实时重算
  - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 6.8_

- [x] 3.9 实现联动面板 — B15状态 + B50状态 + ref_chip跳转 + 审计链路摘要
  - 显示 B15 关联状态（已完成/未完成 + Group_Materiality 金额）
  - 显示 B50 关联状态（已接收 scope-determined 事件/未接收）
  - 提供 ref_chip 跳转链接到 B15 底稿和 B50 底稿
  - B15 重要性变更时自动重算 Allocated_Materiality 建议并提示用户确认
  - 显示审计链路摘要：B15(重要性)→B30(范围)→B50(风险)
  - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6_

- [x] 3.10 实现现场经理复核区 — 签字按钮 + 待完成事项清单 + 状态横幅
  - Scope_Dashboard 下方"现场经理复核"签字区域
  - 前置条件不满足时禁用按钮 + 显示 pendingItems（Classification为空 + Scope_Type为空 + 重要组成部分独立性未确认）
  - 签字完成后全组件只读 + emit completed
  - 顶部"已复核"绿色横幅（复核人/日期信息）
  - _Requirements: 10.1, 10.2, 10.3, 10.4_

- [x] 3.11 实现只读模式 + Amendment 机制
  - readonly prop 或已复核 → 全字段禁用（文本/下拉/树拖拽/添加删除按钮）
  - Amendment：填写修改原因 → 重置复核 → 解锁编辑 → 重新复核流程
  - 修改原因为空/纯空白时拒绝提交，显示校验错误
  - _Requirements: 10.5, 10.6_

- [x] 3.12 实现 EventBus 跨底稿联动
  - 监听 `materiality:determined` 事件（来自 B15）→ onMaterialityDetermined 更新 groupMateriality + 重算建议
  - 全部组成部分 Scope_Type 确定后发布 `group:scope-determined` 事件（含重要组成部分列表 + 各组成部分范围 + 整体覆盖率）
  - 组件卸载时注销 EventBus 监听
  - _Requirements: 8.1, 8.2, 8.5_

- [x] 3.13 实现响应式布局
  - ≥1024px 完整显示 Scope_Dashboard + Group_Structure_Tree + 组成部分表格
  - 768px~1024px 表格水平滚动，不截断内容
  - 中文标签，所有 UI 文字与审计准则术语一致
  - _Requirements: 14.1, 14.2_

- [x] 3.14 实现导入导出功能 — 导出模板/导出数据/导入（三级）
  - 工具栏"导出模板"按钮 → 生成 2 Sheet 空白 Excel（Sheet1=集团结构：名称/类型/持股比例/父节点名称；Sheet2=组成部分明细：名称/总资产/营收/利润/分类/范围/审计师/独立性/胜任能力）
  - 工具栏"导出数据"按钮 → 导出全部已填数据 Excel（结构=模板+内容+分类+范围+重要性分配+覆盖率）
  - 工具栏"导入"按钮 → 解析 Excel → 校验结构 → 冲突弹窗（覆盖/跳过）→ 写入
  - 格式不符时错误提示拒绝导入（不写入任何数据）
  - 复用 ExcelJS（不引入新依赖）
  - _Requirements: 15.1, 15.2, 15.3, 15.4, 15.5, 15.6_

- [x] 3.15 实现颜色编码与视觉设计
  - Classification 颜色编码：重要=#ff4d4f / 非重要=#faad14 / 不重要=#bfbfbf
  - Scope_Type 颜色编码：全面=#52c41a / 特定=#95de64 / 分析=#1890ff / 不执行=#d9d9d9
  - Scope_Dashboard 使用 Classification 颜色编码渲染分布统计
  - 树节点左侧 4px 色带标识 Classification 颜色
  - _Requirements: 13.1, 13.2, 13.3, 13.4, 13.5_

## 4. 打印样式

- [x] 4.1 添加 `@media print` 样式 — A4横版热力图/A4纵版表格 + 颜色保留 + 隐藏交互控件
  - 隐藏交互控件（拖拽手柄、添加/删除按钮、筛选器、导入导出按钮）
  - 自动展开集团结构树全部节点
  - Coverage_Heatmap 适配 A4 横版，保留背景色（`-webkit-print-color-adjust: exact`）
  - 组成部分表格适配 A4 纵版
  - 保留颜色编码区分（Classification 色带 + Scope_Type 标签色）
  - _Requirements: 14.3, 14.4, 14.5, 6.8_

## 5. Checkpoint

- [x] 5.1 确保所有组件代码编译无错误，TypeScript 类型检查通过
  - 确保所有测试通过，如有疑问询问用户

## 6. Property-Based Tests（fast-check）

- [ ]* 6.1 Property 1: 仪表盘同步不变式
  - **Property 1: 组成部分集合 → dashboardStats 统计一致**
  - 生成随机 N 个组成部分(1~50) × 随机 Classification × 随机 Scope_Type × 随机 Independence → 验证：classificationDistribution 各分类计数之和=组成部分总数；scopeDistribution 各范围计数之和=组成部分总数；pendingDetails 各项=实际满足条件的数量
  - **Validates: Requirements 7.1, 7.2, 7.3, 7.4**

- [ ]* 6.2 Property 2: 覆盖率计算一致性
  - **Property 2: Financial_Data + Scope_Type → Coverage_Rate 加权公式正确**
  - 生成随机 N 个组成部分(1~50) × 随机金额(0~1e9) × 随机 ScopeType → 验证：每个贡献 = 占比 × 权重(1.0/0.5/0.25/0.0)；总覆盖率 = Σ贡献，clamp [0,1]；<60% 时产生警告
  - **Validates: Requirements 6.3, 6.4, 6.5, 6.6**

- [ ]* 6.3 Property 3: 分类自动建议一致性
  - **Property 3: 三个占比值 → suggestClassification 满足 15%/5% 阈值规则**
  - 生成随机 3 个比例(0~1) → 验证：max>15%→"重要组成部分"；max>5%且≤15%→"非重要组成部分"；max≤5%→"不重要组成部分"
  - **Validates: Requirements 2.4, 2.5, 2.6**

- [ ]* 6.4 Property 4: 重要性分配约束
  - **Property 4: 占比 + Group_Materiality → Allocated_Materiality 在 [15%, 85%] 区间**
  - 生成随机占比(0~1) × 随机 GM(1e5~1e9) → 验证：建议值 = max(占比) × GM × 0.75，clamp [GM×15%, GM×85%]；校验函数：超上限→警告 / 低下限→警告 / 区间内→无警告
  - **Validates: Requirements 3.3, 3.4, 3.5, 3.6**

- [ ]* 6.5 Property 5: 树表双向同步不变式
  - **Property 5: 节点操作序列 → 树节点数 == 表格行数 + 名称一致**
  - 生成随机操作序列(add/remove/rename, 1~20步) → 验证：treeNodeCount == components.length；各节点名称与对应表格行一致
  - **Validates: Requirements 1.5, 2.2**

- [ ]* 6.6 Property 6: 复核前置条件完备性
  - **Property 6: 组成部分状态组合 → canReview 正确**
  - 生成随机 N 个组成部分 × 随机 Classification(含null) × 随机 Scope_Type(含null) × 随机 Independence → 验证：canReview=true ⟺ (全部Classification非空 ∧ 全部Scope_Type非空 ∧ 重要组成部分Independence为"已确认"或"不适用")
  - **Validates: Requirements 10.2**

- [ ]* 6.7 Property 7: 复核后只读不变式
  - **Property 7: ReviewState + readonly prop → isReadonly 正确**
  - 生成随机 ReviewState(reviewed/not) × 随机 externalReadonly(true/false) → 验证：isReadonly = reviewed || externalReadonly；Amendment 解锁后 isReadonly=false
  - **Validates: Requirements 10.3, 10.5, 10.6**

- [ ]* 6.8 Property 8: 数据持久化往返一致性
  - **Property 8: B30- item_id + 合法值 → round-trip 一致**
  - 生成随机组成部分编号(1~50) × 随机字段(18种) × 随机合法值 → 序列化 → 反序列化 → 验证字段值一致
  - **Validates: Requirements 9.1, 9.5, 9.6**

- [ ]* 6.9 Property 9: item_id 命名唯一性
  - **Property 9: generateB30ItemId 唯一且确定**
  - 生成随机 compIndex(1~50) × 随机 field(18种) → 验证：不同组合唯一，相同组合相同输出（幂等）
  - **Validates: Requirements 9.7**

- [ ]* 6.10 Property 10: EventBus 事件发射正确性
  - **Property 10: 组成部分 Scope_Type 状态 → 事件发射条件**
  - 生成随机 N 个组成部分 × 随机 Scope_Type(含null) → 验证：全部非空时触发 group:scope-determined；存在null时不触发；载荷中 significantComponents = Classification="重要组成部分"的集合
  - **Validates: Requirements 8.1**

- [ ]* 6.11 Property 11: 颜色编码单射
  - **Property 11: Classification/ScopeType → 颜色映射无重复无交叉**
  - 全量枚举 Classification(3值) + ScopeType(4值) → 验证：每个值对应唯一颜色；Classification颜色集与ScopeType颜色集不交叉
  - **Validates: Requirements 13.1, 13.2, 13.4**

- [ ]* 6.12 Property 12: 后端白名单校验正确性
  - **Property 12: B30- item_id + 随机 conclusion → 白名单内200/外422**
  - 生成随机 B30- item_id + 随机 conclusion（合法/非法混合）→ 验证 HTTP 状态码正确
  - **Validates: Requirements 12.1, 12.2, 12.4**

- [ ]* 6.13 Property 13: Scope_Type 自动建议与分类关联
  - **Property 13: Classification → suggestScopeType 确定性映射 + 警告条件**
  - 生成随机 Classification × 随机实际 Scope_Type → 验证：重要→全面/非重要→特定/不重要→不执行；重要且实际≠全面时产生警告
  - **Validates: Requirements 4.2, 4.4**

- [ ]* 6.14 Property 14: 导入导出数据一致性
  - **Property 14: 组成部分数据集 → 导出 → 导入 → 字段值一致**
  - 生成随机组成部分数据集(1~20) → 模拟导出数据结构 → 模拟导入解析 → 验证所有字段值与原始一致
  - **Validates: Requirements 15.1, 15.2, 15.3**

## 7. Unit Tests（vitest）

- [ ]* 7.1 注册契约测试 — 验证 registry 包含 `b30-group-audit`，wp_code_overrides 映射正确（B30→b30-group-audit, B30-1~5→skip）
  - _Requirements: 11.1, 11.2, 11.3_

- [ ]* 7.2 集团结构树渲染测试 — el-tree 渲染 + 节点CRUD + 色带颜色 + Scope_Type标签
  - _Requirements: 1.1, 1.2, 1.6, 1.8_

- [ ]* 7.3 树节点拖拽与层级约束测试 — 拖拽调整层级 + 5层嵌套上限 + 有子节点不可删除
  - _Requirements: 1.3, 1.4_

- [ ]* 7.4 组成部分表格渲染测试 — 默认列 + 合计行 + 双向同步（树增删→表格联动）
  - _Requirements: 2.1, 2.2, 2.8_

- [ ]* 7.5 占比计算与分类建议测试 — 自动计算占比 + >15%→重要 + 手动覆盖需理由
  - _Requirements: 2.3, 2.4, 2.5_

- [ ]* 7.6 筛选功能测试 — 全部/仅重要/仅非重要/仅不重要 切换正确
  - _Requirements: 2.7_

- [ ]* 7.7 重要性分配区域测试 — B15已完成/未完成两种状态 + 自动建议 + 警告显示
  - _Requirements: 3.1, 3.2, 3.3, 3.8_

- [ ]* 7.8 重要性约束警告测试 — 超上限/低下限黄色警告 + 非重要/不重要"不分配"标注
  - _Requirements: 3.4, 3.5, 3.6, 3.9_

- [ ]* 7.9 Scope_Type 下拉与建议测试 — 自动建议显示 + 手动覆盖需理由 + 橙色警告
  - _Requirements: 4.1, 4.2, 4.3, 4.4_

- [ ]* 7.10 特定项目说明测试 — Scope_Type=特定项目审计时展示文本区
  - _Requirements: 4.5_

- [ ]* 7.11 审计师管理区域测试 — Scope_Type≠不执行时显示 + 独立性/胜任能力警告 + 清空逻辑
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.6_

- [ ]* 7.12 覆盖率热力图渲染测试 — 颜色分级 + 合计行 + tooltip + <60%红色警告
  - _Requirements: 6.1, 6.2, 6.3, 6.6, 6.7_

- [ ]* 7.13 Scope_Dashboard 统计渲染测试 — 分类分布/范围分布/覆盖率进度条/待确认事项
  - _Requirements: 7.1, 7.2, 7.3_

- [ ]* 7.14 联动面板测试 — B15状态 + B50状态 + ref_chip + 审计链路摘要
  - _Requirements: 8.3, 8.4, 8.6_

- [ ]* 7.15 保存行为测试 — debounce 2s 文本保存（fake timers）+ 选择字段立即保存 + emit save
  - _Requirements: 9.2, 9.3_

- [ ]* 7.16 只读模式测试 — readonly prop / 已复核 → 全交互禁用 + 横幅渲染
  - _Requirements: 10.3, 10.4, 10.5_

- [ ]* 7.17 复核签字测试 — 前置条件校验 + 签字操作 + emit completed
  - _Requirements: 10.1, 10.2_

- [ ]* 7.18 Amendment 流程测试 — 启动修改→填写原因（空值校验）→重置复核→重新编辑
  - _Requirements: 10.6_

- [ ]* 7.19 EventBus 联动测试 — 监听 materiality:determined 同步 + 发布 group:scope-determined 载荷正确
  - _Requirements: 8.1, 8.2, 8.5_

- [ ]* 7.20 导入导出测试 — 模板导出/数据导出/导入(冲突覆盖+跳过+格式校验)
  - _Requirements: 15.1, 15.2, 15.3, 15.4, 15.5_

- [ ]* 7.21 打印样式类存在性测试 — @media print 样式存在 + 交互控件隐藏
  - _Requirements: 14.3, 14.4, 14.5_

## 8. 后端 PBT（hypothesis）

- [ ]* 8.1 Property 8: 数据持久化往返一致性 — 生成随机 B30- item_id + 合法 conclusion + 随机 remark → PUT → GET → 验证一致性
  - **Property 8 (Design): Round-trip consistency**
  - **Validates: Requirements 9.1, 9.5, 9.6**

- [ ]* 8.2 Property 12: Conclusion 白名单校验 — 生成随机 B30- item_id + 随机 conclusion 值 → 验证合法值 200、非法值 422
  - **Validates: Requirements 12.1, 12.2, 12.4**

## 9. Final Checkpoint

- [x] 9.1 确保所有测试通过，如有疑问询问用户
  - 运行 vitest（单元测试 + property tests）
  - 运行 hypothesis（后端 PBT）
  - 验证 TypeScript 编译无错误
  - 验证 componentType 契约测试通过
