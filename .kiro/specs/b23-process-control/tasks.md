# Tasks — B23 业务流程与控制了解表

## 1. 注册与配置

- [x] 1.1 在 `htmlRendererRegistry.ts` 的 `HtmlComponentType` union 中新增 `'b23-process-control'`
- [x] 1.2 在 `REGISTRY_LIST` 中新增注册条目：componentType=`b23-process-control`, icon='🔄', label='B23 业务流程与控制了解表', emits=['save','completed'], contextProps='standard'
- [x] 1.3 添加 lazy import: `const GtB23ProcessControl = defineAsyncComponent(() => import('./GtB23ProcessControl.vue'))`
- [x] 1.4 更新 `wp_code_overrides.json`：将 `"B23"` 映射为 `"b23-process-control"`，将 `"B23-1"`~`"B23-8"` 映射为 `"skip"`
- [x] 1.5 后端 `checklist_responses.py` 中 conclusion 校验增加 `B23-` 前缀分支
  - 在现有 `elif item.item_id.startswith("B22B-"):` 分支后新增 `elif item.item_id.startswith("B23-"):` 分支
  - 白名单：`设计有效且已实施/设计有效但未有效实施/设计无效/不适用/控制有效运行/控制未有效运行/未执行穿行/每笔/每日/每周/每月/每季/每年/不定期/Y/N`
  - _Requirements: 10.1, 10.2, 10.3, 10.4, 11.1, 11.2, 11.4_

## 2. 组合式函数

- [x] 2.1 创建 `composables/useB23FormData.ts` — 数据加载/debounce保存/即时保存/流程数据视图
  - 实现 `loadAll()` 从 GET checklist-responses 加载全部 `B23-*` 数据到 `allResponses` Map
  - 实现 `saveImmediate(items)` 通过 PUT 批量保存（Process_Conclusion/穿行结论/适用性开关触发）
  - 实现 `saveDebouncedText(item)` debounce 2000ms 文本保存（控制目标/描述/备注/穿行记录字段）
  - 实现 `flushPendingSave()` 组件卸载时 flush 未保存数据
  - 实现 `processData(processNum)` 按流程编号过滤数据视图
  - 实现 `getField(itemId)` / `setFieldImmediate(itemId, data)` 辅助方法
  - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7_

- [x] 2.2 创建 `composables/useB23ProcessControl.ts` — 流程卡片/控制点CRUD/穿行测试/结论建议/适用性/EventBus
  - 实现 `processes` 计算属性（8 张流程卡片 ProcessCard[]）
  - 实现 `expandedProcesses` / `toggleProcess` / `expandAll` / `collapseAll` 展开收起管理
  - 实现 `setApplicability(num, applicable)` 适用性切换（不适用→结论自动设"不适用"；恢复适用→清除结论）
  - 实现 `getControlPoints(num)` / `addControlPoint(num)` / `removeControlPoint(num, index)` / `setControlPointField(...)` 控制点 CRUD
  - 实现 `getWalkthroughRecords(num, ctrlIndex)` / `addWalkthroughSample(num, ctrlIndex)` / `setWalkthroughField(...)` 穿行测试记录管理
  - 实现 `isWalkthroughComplete(num)` / `walkthroughSummary(num)` 穿行完成判定和摘要
  - 实现 `suggestConclusion(num)` 自动建议算法（30% 阈值规则）
  - 实现 `setConclusion(num, conclusion, overrideReason?)` / `isConclusionOverridden(num)` / `getOverrideReason(num)` 结论设置+覆盖
  - 实现 `dashboardStats` 计算属性（completionDistribution + effectivenessDistribution + pendingWalkthroughCount）
  - 实现 `entityLevelContext` / `onControlConclusionChanged(payload)` B22A 上下文接收
  - 实现 `linkageInfo` 计算属性（流程→B50影响 + D~N循环映射）
  - 实现 `publishProcessConcluded(num, old, new)` / `publishWalkthroughCompleted(num)` EventBus 发布
  - _Requirements: 1.1~1.7, 2.1~2.6, 3.1~3.7, 4.1~4.6, 5.1~5.7, 6.1~6.6, 7.1~7.6, 12.1~12.5_

- [x] 2.3 创建 `composables/useB23Review.ts` — 现场经理复核签字/只读状态/Amendment机制
  - 实现 `isReviewed` / `isReadonly` / `canReview` 计算属性
  - 实现 `pendingItems` 计算属性（未完成评估的适用流程 + 缺穿行结论的控制点）
  - 实现 `reviewInfo` 计算属性（复核人/日期）
  - 实现 `doReview()` 签字保存方法（前置条件：所有适用流程 Process_Conclusion 非空 + 穿行完成）
  - 实现 `startAmendment(reason)` 修改机制（重置复核状态 + 记录修改原因 + 解锁编辑）
  - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6_

## 3. Vue 组件实现

- [x] 3.1 创建 `GtB23ProcessControl.vue` 骨架 — script setup + props/emits + composables 初始化
  - Props: wpId, projectId, wpCode, year, readonly
  - Emits: save, completed
  - 引入三个 composables 并初始化
  - onMounted 中 loadAll + 注册 EventBus 监听 `control:conclusion-changed`
  - onBeforeUnmount 中 flushPendingSave + 注销 EventBus 监听
  - _Requirements: 10.1, 10.4, 10.5, 10.6_

- [x] 3.2 实现 Status_Dashboard 状态仪表盘 — 完成度分布/有效性分布/待穿行数量
  - 顶部汇总面板渲染 completionDistribution（已完成/进行中/未开始/不适用计数）
  - 有效性分布渲染 effectivenessDistribution（有效/部分有效/无效/不适用）+ 颜色编码
  - 待穿行测试数量显示 pendingWalkthroughCount
  - 数据实时响应各 Process_Card 内变更
  - _Requirements: 1.1, 1.7, 12.3_

- [x] 3.3 实现 Process_Card 流程卡片骨架 — 8 卡片渲染 + 展开/收起 + 标题栏信息
  - 渲染 8 张 Process_Card（P1~P8：采购与付款/销售与收款/资金管理/生产与存货/薪酬与人力/固定资产/投资/其他）
  - 标题栏显示：流程名称 + Process_Conclusion 状态标签（颜色编码）+ 控制点完成比例(N/M) + 穿行完成状态图标
  - 左侧色带 4px 宽，颜色随 Process_Conclusion 变化
  - 支持单卡片展开/收起 + 全部展开/全部收起快捷按钮
  - 适用性开关（适用/不适用）在标题栏右侧
  - 不适用时灰色样式 + 自动折叠 + "不适用"标签
  - _Requirements: 1.2, 1.3, 1.4, 1.5, 1.6, 2.1, 2.2, 2.3, 2.5, 2.6, 12.4_

- [x] 3.4 实现控制点表格 — 结构化表格 + CRUD + 下拉字段
  - 每行：序号/控制目标(文本)/控制活动描述(文本)/Control_Frequency(下拉：每笔~不定期)/执行人/部门(文本)/Understanding_Method(多选：询问/观察/检查文件/穿行测试/重新执行)/穿行测试结论(下拉)/备注/索引(文本)
  - 新增控制点行（自动序号分配）
  - 删除控制点行（预置控制点需确认弹窗后方可删除）
  - 穿行测试结论为"控制未有效运行"时该行红色警告标识
  - 单流程最多 20 个控制点，达上限"新增"按钮禁用
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7_

- [x] 3.5 实现穿行测试记录区域 — 可展开详细记录 + 多笔样本 + 摘要
  - 控制点表格下方可展开"穿行测试详细记录"区域
  - 当控制点 Understanding_Method 包含"穿行测试"时自动创建测试记录条目
  - 每笔记录字段：样本选取（凭证编号/交易日期/金额）/测试路径描述/发现与结论/证据引用
  - 支持同一控制点多笔样本（最多 5 笔，达上限"新增"按钮禁用）
  - 折叠状态下显示摘要：已测试控制点数/总控制点数 + 穿行完成率
  - 全部穿行完成时标题栏显示"穿行已完成"绿色徽标
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6_

- [x] 3.6 实现 Process_Conclusion 结论区域 — 自动建议 + 手动选择 + 覆盖机制
  - 每张 Process_Card 底部 Process_Conclusion 选择区域（设计有效且已实施/设计有效但未有效实施/设计无效/不适用）
  - 系统自动建议显示为参考提示（suggestConclusion 结果 + 30% 阈值规则说明）
  - 手动覆盖自动建议时弹出"调整理由"输入（无理由拒绝覆盖）
  - 覆盖后显示"已手动调整"标识和覆盖理由
  - 结论变更时立即保存 + 触发 publishProcessConcluded
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7_

- [x] 3.7 实现 Entity_Level_Context 面板 — B22A 实体层面只读参考
  - Status_Dashboard 区域提供 Entity_Level_Context 只读参考面板
  - 显示 B22A 五要素各自的 Element_Score（有效/部分有效/无效）+ 整体结论 + 颜色编码
  - 通过 EventBus `control:conclusion-changed` 实时更新面板内容
  - 控制环境（要素1）结论为"无效"时显示醒目警告
  - B22A 未完成时显示灰色提示"B22A 未完成，实体层面结论待定"
  - 提供 ref_chip 跳转链接到 B22A 底稿
  - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6_

- [x] 3.8 实现 Linkage_Panel 联动面板 — B50影响 + D~N循环映射 + ref_chip
  - 显示各流程结论对应的 B50 控制风险影响提示（CONCLUSION_TO_B50_IMPACT 映射）
  - 显示各流程对应的 D~N 循环程序表映射关系（P1→DA/P2→EA/...）+ ref_chip 跳转
  - 显示 B22A 关联状态（已完成/未完成/摘要）
  - Process_Conclusion 为"设计无效"时高亮该流程关联行 + "需扩大实质性程序"提示 + needsExtendedProcedures=true
  - _Requirements: 7.3, 7.4, 7.5, 7.6_

- [x] 3.9 实现现场经理复核区 — 签字按钮 + 待完成事项清单 + 状态横幅
  - Status_Dashboard 下方"现场经理复核"签字区域
  - 前置条件不满足时禁用按钮 + 显示 pendingItems（未完成 Process_Conclusion 的流程 + 缺穿行结论的控制点）
  - 签字完成后全组件只读 + emit completed
  - 顶部"已复核"绿色横幅（复核人/日期信息）
  - _Requirements: 9.1, 9.2, 9.3, 9.4_

- [x] 3.10 实现只读模式 + Amendment 机制
  - readonly prop 或已复核 → 全字段禁用（文本/下拉/开关/按钮）
  - Amendment：填写修改原因 → 重置复核 → 解锁编辑 → 重新复核流程
  - 修改原因为空/纯空白时拒绝提交，显示校验错误
  - _Requirements: 9.5, 9.6_

- [x] 3.11 实现 EventBus 跨底稿联动
  - 监听 `control:conclusion-changed` 事件（来自 B22A）→ onControlConclusionChanged 更新 entityLevelContext
  - Process_Conclusion 变更时发布 `process:control-concluded` 事件（含 processNum/processName/oldConclusion/newConclusion）
  - 某流程全部穿行测试完成时发布 `process:walkthrough-completed` 事件（含 processNum/controlPointCount/effectiveRate）
  - 组件卸载时注销 EventBus 监听
  - _Requirements: 7.1, 7.2, 6.3_

- [x] 3.12 实现响应式布局
  - ≥1024px 完整显示 Status_Dashboard + Process_Card 内容
  - 768px~1024px 控制点表格水平滚动，不截断内容
  - 中文标签，所有 UI 文字与审计准则术语一致
  - _Requirements: 13.1, 13.2, 1.6_

- [x] 3.13 实现导入导出功能 — 导出模板/导出数据/导入（三级）
  - 工具栏"导出模板"按钮 → 生成 8 Sheet 空白 Excel（含列标题）
  - 工具栏"导出数据"按钮 → 导出全部已填数据 Excel（结构=模板+内容）
  - 工具栏"导入"按钮 → 解析 Excel → 校验结构 → 冲突弹窗（覆盖/跳过）→ 写入
  - 格式不符时错误提示拒绝导入
  - 复用 ExcelJS（不引入新依赖）
  - _Requirements: 14.1, 14.2, 14.3, 14.4, 14.5, 14.6_

- [x] 3.14 实现关联流程图 — B22A→B23→B50→D~N 审计链路可视化
  - Status_Dashboard 和 Linkage_Panel 之间渲染流程图区域
  - SVG/CSS 实现左→右水平流转节点+连线（不引入 D3/ECharts）
  - 节点显示底稿编号+名称+状态色（已完成绿/进行中蓝/未开始灰）
  - B23→各D~N 连线按适用流程动态渲染（不适用流程无连线）
  - 点击节点通过 ref_chip 跳转到对应底稿
  - 可折叠/展开（默认展开），折叠时显示一行摘要
  - _Requirements: 15.1, 15.2, 15.3, 15.4, 15.5, 15.6_

- [x] 3.15 实现 C~N 循环程序表关联区域 — 各流程 Process_Card 底部
  - 每张适用流程卡片底部"关联程序表"区域，列出对应 D~N 程序表（wp_code+名称+完成状态）
  - P1→DA / P2→EA / P3→FA / P4→GA / P5→HA / P6→IA / P7→JA / P8→KA 映射
  - "设计无效"/"设计有效但未有效实施"时显示"控制不可依赖——建议扩大实质性程序范围和样本量"
  - "设计有效且已实施"时显示"控制可依赖——可适当缩小实质性程序范围"
  - 提供 ref_chip 跳转到对应 D~N 程序表底稿
  - _Requirements: 16.1, 16.2, 16.3, 16.4, 16.5_

## 4. 打印样式

- [x] 4.1 添加 `@media print` 样式 — 流程控制了解表 A4 纵版 + 颜色保留 + 隐藏交互控件
  - 隐藏交互控件（展开/收起按钮、适用性开关、新增/删除按钮）
  - 自动展开所有适用流程卡片内容
  - 保留颜色编码区分（`-webkit-print-color-adjust: exact`）
  - 控制点表格和结论区域适配 A4 纵版
  - _Requirements: 13.3, 13.4, 13.5, 12.5_

## 5. Checkpoint

- [x] 5.1 确保所有组件代码编译无错误，TypeScript 类型检查通过
  - 确保所有测试通过，如有疑问询问用户

## 6. Property-Based Tests（fast-check）

- [x]* 6.1 Property 1: 状态仪表盘同步不变式
  - **Property 1: 流程状态分布 → dashboardStats 计数一致**
  - 生成随机 8 流程 × 随机适用性 × 随机控制点状态 × 随机 Process_Conclusion → 验证：completionDistribution 各分类计数之和=8；effectivenessDistribution 各分类=实际结论分布；pendingWalkthroughCount=适用流程中需穿行但结论为空的控制点数
  - **Validates: Requirements 1.1, 1.7, 2.4**

- [x]* 6.2 Property 2: Process_Conclusion 自动建议一致性
  - **Property 2: 控制点穿行结论分布 → suggestProcessConclusion 满足 30% 阈值规则**
  - 生成随机 N 个控制点(1~20) × 随机 WalkthroughConclusion 值 → 验证：全有效→"设计有效且已实施"；无效占比≤30%→"设计有效但未有效实施"；>30%→"设计无效"；无已评估→null
  - **Validates: Requirements 5.2, 5.3, 5.4, 5.5**

- [x]* 6.3 Property 3: 流程适用性约束
  - **Property 3: 适用性 toggle 序列 → conclusion 最终状态一致**
  - 生成随机流程编号 × 随机 toggle 序列(1~10次) → 验证：最终不适用→conclusion="不适用"；最终适用→conclusion=null；已有控制点数据不被删除
  - **Validates: Requirements 2.2, 2.3, 2.5**

- [x]* 6.4 Property 4: 穿行测试与了解方法联动
  - **Property 4: Understanding_Method 变更 → 穿行记录存在性 + 摘要正确**
  - 生成随机控制点集合 × 随机 methods 组合 → 验证：methods 含"穿行测试"时存在记录条目；testedCount=有结论的控制点数；totalCount=需穿行的控制点数；全完成时 isWalkthroughComplete=true
  - **Validates: Requirements 4.3, 4.5, 4.6**

- [x]* 6.5 Property 5: 复核前置条件与只读不变式
  - **Property 5: 流程状态组合 → canReview + isReadonly 正确**
  - 生成随机 8 流程完成度 × 随机 review 状态 × 随机 readonly prop → 验证：canReview=true ⟺ 全适用流程有结论+穿行完成；isReadonly=true ⟺ reviewed=Y 或 externalReadonly=true
  - **Validates: Requirements 9.2, 9.3, 9.5**

- [x]* 6.6 Property 6: 数据持久化往返一致性
  - **Property 6: B23- item_id + 合法 conclusion + 随机 remark → PUT → GET → 一致**
  - 生成随机 B23- item_id（合法格式）+ 白名单 conclusion + 随机 remark → 验证 round-trip 一致
  - **Validates: Requirements 8.1, 8.6**

- [x]* 6.7 Property 7: item_id 命名唯一性
  - **Property 7: generateItemId(processNum, ctrlIndex, sampleIndex, field) 唯一且确定**
  - 生成随机 processNum(1~8) × ctrlIndex(1~20) × sampleIndex(1~5) × 随机 field → 验证：不同组合唯一，相同组合相同输出
  - **Validates: Requirements 8.7**

- [x]* 6.8 Property 8: EventBus 事件发射正确性
  - **Property 8: 结论变更 → process:control-concluded 事件触发条件正确**
  - 生成随机流程 × 随机新旧 conclusion × 随机穿行完成状态 → 验证：新旧不同时发射 process:control-concluded；全穿行完成时发射 process:walkthrough-completed；新旧相同时不发射
  - **Validates: Requirements 7.1, 7.2**

- [x]* 6.9 Property 9: 颜色编码双射
  - **Property 9: ProcessConclusion → 颜色映射无重复/无遗漏**
  - 全量枚举 5 值（4 结论 + 待测试）→ 验证：每个结论对应唯一颜色；无同色不同结论；覆盖全部 ProcessConclusion 值
  - **Validates: Requirements 12.1, 12.2, 12.4**

- [x]* 6.10 Property 10: Entity_Level_Context 只读不变式
  - **Property 10: B22A 事件载荷 → entityLevelContext 状态正确**
  - 生成随机 ControlConclusionPayload → 验证：面板数据只读；completed=false 时显示"未完成"；elementScores[1]='无效'时触发警告条件
  - **Validates: Requirements 6.2, 6.3, 6.4, 6.6**

- [x]* 6.11 Property 11: 后端白名单校验正确性
  - **Property 11: B23- item_id + 随机 conclusion → 白名单内 200 / 白名单外 422**
  - 生成随机 B23- item_id + 随机 conclusion（合法/非法混合）→ 验证 HTTP 状态码
  - **Validates: Requirements 11.1, 11.2, 11.4**

- [x]* 6.12 Property 12: 联动面板结论映射
  - **Property 12: ProcessConclusion → B50 影响映射 + needsExtendedProcedures 标志**
  - 全量枚举 ProcessConclusion × 验证 CONCLUSION_TO_B50_IMPACT 映射正确 + "设计无效"时 needsExtendedProcedures=true
  - **Validates: Requirements 7.3, 7.6**

## 7. Unit Tests（vitest）

- [x]* 7.1 注册契约测试 — 验证 registry 包含 `b23-process-control`，wp_code_overrides 映射正确（B23→b23-process-control, B23-1~8→skip）
  - _Requirements: 10.1, 10.2, 10.3_

- [x]* 7.2 流程卡片渲染测试 — 8 卡片渲染 + 默认全部适用 + 标题栏信息（名称/结论标签/完成比例）
  - _Requirements: 1.2, 1.4, 2.6_

- [x]* 7.3 展开收起交互测试 — 单卡片 toggle + 全部展开/收起
  - _Requirements: 1.3, 1.5_

- [x]* 7.4 适用性开关测试 — 切换不适用→灰色样式+结论自动设"不适用" / 恢复适用→清除结论
  - _Requirements: 2.1, 2.2, 2.3, 2.5_

- [x]* 7.5 控制点 CRUD 测试 — 新增（自动序号）/删除（预置确认弹窗）/字段编辑
  - _Requirements: 3.5, 3.6_

- [x]* 7.6 了解方法多选交互测试 — Understanding_Method 多选 + 穿行测试区域自动创建
  - _Requirements: 3.2, 4.3_

- [x]* 7.7 控制频率下拉测试 — 7 个选项渲染 + 选择即时保存
  - _Requirements: 3.3_

- [x]* 7.8 穿行测试结论下拉测试 — "控制未有效运行"红色标识 + 即时保存
  - _Requirements: 3.4, 3.7_

- [x]* 7.9 穿行测试记录区域测试 — 自动创建条目 + 多笔样本 + 摘要信息 + 上限5笔
  - _Requirements: 4.1, 4.2, 4.4, 4.5_

- [x]* 7.10 Process_Conclusion 自动建议测试 — 建议显示 + 手动覆盖需理由 + "已手动调整"标识
  - _Requirements: 5.1, 5.6, 5.7_

- [x]* 7.11 Status_Dashboard 统计渲染测试 — 完成度/有效性/待穿行数量实时更新
  - _Requirements: 1.1, 1.7_

- [x]* 7.12 Entity_Level_Context 面板测试 — 只读渲染 + B22A未完成提示 + 控制环境无效警告
  - _Requirements: 6.1, 6.2, 6.4, 6.6_

- [x]* 7.13 Linkage_Panel 映射测试 — B50影响提示 + D~N循环映射 + ref_chip + "需扩大实质性程序"高亮
  - _Requirements: 7.3, 7.4, 7.6_

- [x]* 7.14 保存行为测试 — debounce 2s 文本保存（fake timers）+ 选择字段立即保存 + emit save
  - _Requirements: 8.2, 8.3_

- [x]* 7.15 只读模式测试 — readonly prop / 已复核 → 全交互禁用 + 横幅渲染
  - _Requirements: 9.3, 9.4, 9.5_

- [x]* 7.16 复核签字测试 — 前置条件校验 + 签字操作 + emit completed
  - _Requirements: 9.1, 9.2_

- [x]* 7.17 Amendment 流程测试 — 启动修改→填写原因（空值校验）→重置复核→重新编辑
  - _Requirements: 9.6_

- [x]* 7.18 EventBus 联动测试 — 监听 control:conclusion-changed 同步 + 发布 process:control-concluded / process:walkthrough-completed 载荷正确
  - _Requirements: 7.1, 7.2, 6.3_

- [x]* 7.19 打印样式类存在性测试 — @media print 样式存在 + 交互控件隐藏
  - _Requirements: 13.3, 13.4, 12.5_

## 8. 后端 PBT（hypothesis）

- [x]* 8.1 Property 6: 数据持久化往返一致性 — 生成随机 B23- item_id + 合法 conclusion + 随机 remark → PUT → GET → 验证一致性
  - **Property 6 (Design): Round-trip consistency**
  - **Validates: Requirements 8.1, 8.5, 8.6**

- [x]* 8.2 Property 11: Conclusion 白名单校验 — 生成随机 B23- item_id + 随机 conclusion 值 → 验证合法值 200、非法值 422
  - **Validates: Requirements 11.1, 11.2, 11.4**

## 9. Final Checkpoint

- [x] 9.1 确保所有测试通过，如有疑问询问用户
  - 运行 vitest（单元测试 + property tests）
  - 运行 hypothesis（后端 PBT）
  - 验证 TypeScript 编译无错误
  - 验证 componentType 契约测试通过
