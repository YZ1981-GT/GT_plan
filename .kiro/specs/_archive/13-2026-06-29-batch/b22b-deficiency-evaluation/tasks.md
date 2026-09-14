# Tasks — B22B 内部控制缺陷评价表

## 1. 注册与配置

- [x] 1.1 在 `htmlRendererRegistry.ts` 的 `HtmlComponentType` union 中新增 `'b22b-deficiency-evaluation'`
- [x] 1.2 在 `REGISTRY_LIST` 中新增注册条目：componentType=`b22b-deficiency-evaluation`, icon='⚠️', label='B22B 内部控制缺陷评价表', emits=['save','completed'], contextProps='standard'
- [x] 1.3 添加 lazy import: `const GtB22BDeficiencyEvaluation = defineAsyncComponent(() => import('./GtB22BDeficiencyEvaluation.vue'))`
- [x] 1.4 更新 `wp_code_overrides.json`：将 `"B22B"` 映射为 `"b22b-deficiency-evaluation"`
- [x] 1.5 后端 `checklist_responses.py` 中 conclusion 校验增加 `B22B-` 前缀分支
  - 在现有 `elif item.item_id.startswith("B22A-"):` 分支后新增 `elif item.item_id.startswith("B22B-"):` 分支
  - 白名单：`重大缺陷/重要缺陷/一般缺陷/设计缺陷/运行缺陷/Y/N/存在重大缺陷/存在重要缺陷/仅存在一般缺陷/未发现控制缺陷`
  - _Requirements: 10.1, 10.2, 10.3, 10.4, 9.1, 9.2_

## 2. 组合式函数

- [x] 2.1 创建 `composables/useB22BFormData.ts` — 数据加载/debounce保存/即时保存/B15重要性水平读取
  - 实现 `loadAll()` 从 GET checklist-responses 加载全部 `B22B-*` 数据
  - 实现 `loadMaterialityLevel()` 从 B15 checklist_responses 读取 `B15-materiality-level` 重要性水平金额
  - 实现 `saveImmediate(items)` 通过 PUT 批量保存
  - 实现 `saveDebouncedText(item)` debounce 2000ms 文本保存
  - 实现 `flushPendingSave()` 组件卸载时 flush 未保存数据
  - 实现 `getField(itemId)` / `setFieldImmediate(itemId, data)` 辅助方法
  - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 11.1, 11.4_

- [x] 2.2 创建 `composables/useB22BDeficiency.ts` — 缺陷条目同步/评价逻辑/严重程度建议/整体结论/EventBus发布
  - 实现 `syncFromEvent(payload)` 监听 `control:deficiency-changed` 事件同步缺陷条目
  - 实现 `loadFromB22A(b22aResponses)` 初始化时从 B22A checklist_responses 加载现有缺陷
  - 实现 `setCategory(index, category)` / `setAffectedAccounts(index, accounts)` / `setPotentialMisstatement(index, amount)` 评价维度设置
  - 实现 `setCompensatingControl(index, hasControl, description)` / `setCorrectiveAction(index, hasAction, description)` 补偿性控制/纠正措施
  - 实现 `setSeverity(index, severity)` / `setSeverityOverride(index, severity, reason)` 严重程度评定+手动覆盖
  - 实现 `suggestSeverity(index)` 自动建议算法（M>T且无补偿/纠正→重大；M>T有补偿或纠正→重要；M≤T→一般）
  - 实现 `compareMateriality(amount)` 重要性水平对比（exceeds/difference/color）
  - 实现 `overallConclusion` / `severityStats` / `allEvaluated` / `showAuditImpactWarning` 计算属性
  - 实现 `publishSeverityEvent()` EventBus 发布 `deficiency:severity-evaluated` 事件
  - 实现 `deficiencyItems` / `eliminatedItems` 响应式列表
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.6, 2.1, 2.2, 2.3, 2.4, 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 6.1, 6.2, 6.3, 6.4, 6.5, 11.2, 11.3_

- [x] 2.3 创建 `composables/useB22BReview.ts` — 现场经理复核签字/只读状态/Amendment机制
  - 实现 `isReviewed` / `isReadonly` / `canReview` 计算属性
  - 实现 `pendingItems` 计算属性（未完成严重程度评定的缺陷清单）
  - 实现 `reviewInfo` 计算属性（复核人/日期）
  - 实现 `doReview()` 签字保存方法（前置条件：allEvaluated=true）
  - 实现 `startAmendment(reason)` 修改机制（重置复核状态 + 记录修改原因）
  - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6_

## 3. Vue 组件实现

- [x] 3.1 创建 `GtB22BDeficiencyEvaluation.vue` 骨架 — script setup + props/emits 定义
  - Props: wpId, projectId, wpCode, year, readonly
  - Emits: save, completed
  - 引入三个 composables 并初始化
  - onMounted 中 loadAll + loadMaterialityLevel + loadFromB22A + 注册 EventBus 监听
  - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5_

- [x] 3.2 实现缺陷列表区域 — 缺陷条目表格 + 来源标注只读显示 + 缺陷分类下拉
  - 每条缺陷显示来源信息：Tab编号 + 要素名称 + 控制要点 + 缺陷类型（只读灰色文本）
  - 缺陷分类下拉：设计缺陷/运行缺陷（默认映射自动填充）
  - 已消除缺陷移入折叠"历史区"
  - _Requirements: 1.5, 2.1, 2.2, 2.3, 2.4_

- [x] 3.3 实现多维度评价区域 — 4 维度表单（报表项目多选/潜在错报金额/补偿性控制/纠正措施）
  - "可能影响的报表项目范围"多选（资产/负债/所有者权益/收入/费用）
  - "潜在错报金额"数值输入（单位：元）+ 重要性水平实时对比结果（超过=红/未超过=绿）
  - "补偿性控制"是/否选择 + 描述文本区
  - "纠正措施"是/否选择 + 描述文本区
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6_

- [x] 3.4 实现严重程度评定区域 — 系统建议 + 下拉选择 + 手动覆盖机制
  - 系统自动建议严重程度（suggestSeverity 结果显示为参考提示）
  - 严重程度下拉：重大缺陷/重要缺陷/一般缺陷
  - 手动覆盖建议时弹出"调整理由"输入（无理由拒绝覆盖）
  - 覆盖后显示"已手动调整"标识
  - _Requirements: 3.7, 4.1, 4.2, 4.3, 4.4, 4.5, 4.6_

- [x] 3.5 实现整体评价结论区域 — 汇总结论 + 数量统计 + 评价说明 + 审计影响提示
  - 底部汇总区显示整体评价结论（自动计算 = 最高严重程度）
  - 各严重程度数量统计（重大N项/重要N项/一般N项）
  - "整体评价说明"文本区域
  - 存在重大/重要缺陷时显示醒目提示："影响审计报告意见类型，需与业务合伙人沟通"
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 6.5_

- [x] 3.6 实现重要性水平对比功能 — B15数据读取 + 手动输入 fallback + 实时对比
  - 从 B15 读取重要性水平成功时自动填充
  - 读取失败时显示提示"请先完成 B15 重要性水平确定" + 允许手动输入
  - 潜在错报金额变更后实时更新对比结果（颜色 + 差额）
  - _Requirements: 11.1, 11.2, 11.3, 11.4_

- [x] 3.7 实现现场经理复核区 — 签字按钮 + 待完成事项清单 + 状态横幅
  - 底部"现场经理复核"签字区域
  - 前置条件不满足时禁用按钮 + 显示 pendingItems（未评定严重程度的缺陷列表）
  - 签字完成后全组件只读 + emit completed
  - 顶部"已复核"绿色横幅（复核人/日期）
  - _Requirements: 8.1, 8.2, 8.3, 8.4_

- [x] 3.8 实现只读模式 + Amendment 机制
  - readonly prop 或已复核 → 全字段禁用
  - Amendment：填写修改原因 → 重置复核 → 重新编辑 → 重新复核
  - 修改原因为空/纯空白时拒绝提交
  - _Requirements: 8.5, 8.6_

- [x] 3.9 实现 EventBus 跨底稿联动
  - 监听 `control:deficiency-changed` 事件（来自 B22A）→ syncFromEvent 同步缺陷
  - 严重程度评定/变更时发布 `deficiency:severity-evaluated` 事件（含载荷：severities + overallConclusion + materialCount + significantCount + impactsAuditOpinion + requiresExtendedProcedures）
  - 组件卸载时注销 EventBus 监听
  - _Requirements: 1.1, 6.1, 6.2, 6.3, 6.4_

## 4. 打印样式

- [x] 4.1 添加 `@media print` 样式 — 缺陷评价表 A4 横版 + 颜色保留 + 隐藏交互控件
  - 隐藏按钮/输入控件，保留缺陷评价数据+严重程度+结论+颜色编码
  - A4 横版布局，`-webkit-print-color-adjust: exact`
  - 严重程度颜色保留（重大=红/重要=黄/一般=绿）
  - _Requirements: 9.4（标准 contextProps 隐含打印支持）_

## 5. Property-Based Tests（fast-check）

- [x] 5.1 Property 1: 缺陷来源同步不变式
  - **Property 1: 事件序列 → 缺陷列表最终状态正确**
  - 生成随机 DeficiencyItem[] × 随机 added/removed 事件序列 → 验证：added 条目存在于列表，removed 条目移入已消除区，最终列表与 B22A 当前缺陷集一致
  - **Validates: Requirements 1.1, 1.2, 1.3, 1.4, 1.6**

- [x] 5.2 Property 2: 缺陷分类默认映射一致性
  - **Property 2: deficiencyType → 默认 category 双射**
  - 生成随机 DeficiencyItem × deficiencyType ∈ {设计无效, 未实施} → 验证："设计无效"→"设计缺陷"，"未实施"→"运行缺陷"
  - **Validates: Requirements 2.2, 2.3**

- [x] 5.3 Property 3: 严重程度建议逻辑一致性
  - **Property 3: suggestSeverity(M, T, C, A) 满足三分支规则**
  - 生成随机 (amount>0, materiality>0, compensating∈{T,F}, corrective∈{T,F}) → 验证：M>T∧C=F∧A=F→重大；M>T∧(C=T∨A=T)→重要；M≤T→一般；M=null或T=null→null
  - **Validates: Requirements 4.1, 4.2, 4.3, 4.4**

- [x] 5.4 Property 4: 整体评价结论汇总不变式
  - **Property 4: computeOverallConclusion 满足 max-severity 规则**
  - 生成随机 SeverityLevel[] (0~20条，含 eliminated 标记) → 验证：存在重大→"存在重大缺陷"；无重大有重要→"存在重要缺陷"；全一般→"仅存在一般缺陷"；空/全null→"未发现控制缺陷"
  - **Validates: Requirements 5.1, 5.2, 5.3, 5.4, 5.5**

- [x] 5.5 Property 5: EventBus 事件发射正确性
  - **Property 5: 载荷中 impactsAuditOpinion / requiresExtendedProcedures 标志正确**
  - 生成随机缺陷集合 × 随机严重程度分布 → 验证：impactsAuditOpinion=true ⟺ 整体结论="存在重大缺陷"；requiresExtendedProcedures=true ⟺ 整体结论∈{存在重大缺陷,存在重要缺陷}；materialCount/significantCount = 实际计数
  - **Validates: Requirements 6.1, 6.2, 6.3, 6.4**

- [x] 5.6 Property 6: 复核前置条件完备性
  - **Property 6: canReview=true ⟺ 全部非已消除缺陷 severity 非 null**
  - 生成随机缺陷条目（severity 部分为 null、部分已消除）→ 验证 canReview 计算
  - **Validates: Requirements 8.2**

- [x] 5.7 Property 7: 复核后只读不变式
  - **Property 7: review conclusion='Y' 或 readonly=true → isReadonly=true**
  - 生成随机复核状态 × 随机 readonly prop → 验证 isReadonly 逻辑
  - **Validates: Requirements 8.3, 8.5, 8.6**

- [x] 5.8 Property 8: 数据持久化往返一致性
  - **Property 8: B22B- item_id + 合法 conclusion + 随机 remark → PUT → GET → 一致**
  - 生成随机 B22B- item_id（合法格式）+ 白名单 conclusion + 随机 remark → 验证 round-trip
  - **Validates: Requirements 7.1, 7.5, 7.6**

- [x] 5.9 Property 9: item_id 命名唯一性
  - **Property 9: generateItemId(idx, field) 唯一且确定**
  - 生成随机 idx(1~50) × 随机 field ∈ {category,accounts,amount,compensating,corrective,severity,override,source,eliminated} → 验证不同(idx,field)唯一，相同(idx,field)相同输出
  - **Validates: Requirements 7.7**

- [x] 5.10 Property 10: 重要性水平对比确定性
  - **Property 10: (amount, materiality) → exceeds/color 确定性**
  - 生成随机正数对 → 验证：exceeds=true ⟺ amount>materiality；color='red' ⟺ exceeds=true
  - **Validates: Requirements 3.4, 11.2, 11.3**

- [x] 5.11 Property 11: 缺陷数量统计准确性
  - **Property 11: severityStats 各字段 = 手动计数**
  - 生成随机缺陷集合(含 eliminated/severity 分布) → 手动计数 vs severityStats → 验证 material/significant/general/total 一致
  - **Validates: Requirements 5.6**

- [x] 5.12 Property 12: 后端白名单校验正确性
  - **Property 12: B22B- item_id + 合法 conclusion → 200；非法 conclusion → 422**
  - 生成随机 B22B- item_id + 随机 conclusion（合法/非法混合）→ 验证 HTTP 状态码
  - **Validates: Requirements 10.1, 10.2, 10.3, 10.4**

## 6. Unit Tests（vitest）

- [x] 6.1 注册契约测试 — 验证 registry 包含 `b22b-deficiency-evaluation`，wp_code_overrides 映射正确（B22B→b22b-deficiency-evaluation）
  - _Requirements: 9.1, 9.2_

- [x] 6.2 缺陷列表渲染测试 — 缺陷条目表格 + 来源标注只读 + 已消除历史区折叠
  - _Requirements: 1.2, 1.5, 1.6_

- [x] 6.3 缺陷分类交互测试 — 下拉选择 + 默认映射预填 + 手动修改
  - _Requirements: 2.1, 2.2, 2.3, 2.4_

- [x] 6.4 多维度评价表单测试 — 报表项目多选 + 金额输入 + 补偿性控制切换 + 纠正措施切换
  - _Requirements: 3.1, 3.2, 3.3, 3.5, 3.6_

- [x] 6.5 重要性水平对比测试 — 超过/未超过颜色显示 + B15不可用时手动输入
  - _Requirements: 3.4, 11.1, 11.2, 11.3, 11.4_

- [x] 6.6 严重程度评定测试 — 系统建议显示 + 下拉选择 + 手动覆盖需理由 + "已手动调整"标识
  - _Requirements: 3.7, 4.1, 4.5, 4.6_

- [x] 6.7 保存行为测试 — debounce 2s 文本保存（fake timers）+ 选择字段立即保存 + emit save
  - _Requirements: 7.2, 7.3_

- [x] 6.8 整体结论汇总测试 — 结论自动计算 + 数量统计渲染 + 审计影响提示条件
  - _Requirements: 5.1, 5.6, 5.7, 6.5_

- [x] 6.9 只读模式测试 — readonly prop / 已复核 → 全交互禁用 + 横幅渲染
  - _Requirements: 8.3, 8.4, 8.5_

- [x] 6.10 复核签字测试 — 前置条件校验 + 签字操作 + emit completed
  - _Requirements: 8.1, 8.2_

- [x] 6.11 Amendment 流程测试 — 启动修改 → 填写原因（空值校验）→ 重置复核 → 重新编辑
  - _Requirements: 8.6_

- [x] 6.12 EventBus 联动测试 — 监听 control:deficiency-changed 同步 + 发布 deficiency:severity-evaluated 载荷正确
  - _Requirements: 1.1, 6.1, 6.2, 6.3, 6.4_

## 7. 后端 PBT（hypothesis）

- [x] 7.1 Property 8: 数据持久化往返一致性 — 生成随机 B22B- item_id + 合法 conclusion + 随机 remark → PUT → GET → 验证一致性
  - **Property 8 (Design): Round-trip consistency**
  - **Validates: Requirements 7.1, 7.5, 7.6**

- [x] 7.2 Property 12: Conclusion 白名单校验 — 生成随机 B22B- item_id + 随机 conclusion 值 → 验证合法值 200、非法值 422
  - **Validates: Requirements 10.1, 10.2, 10.3, 10.4**

## 8. Checkpoint

- [x] 8.1 确保所有测试通过，如有疑问询问用户
  - 运行 vitest（单元测试 + property tests）
  - 运行 hypothesis（后端 PBT）
  - 验证 TypeScript 编译无错误
  - 验证 componentType 契约测试通过
