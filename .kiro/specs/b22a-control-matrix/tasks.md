# Tasks — B22A 内部控制了解程序表

## 1. 注册与配置

- [x] 1.1 在 `htmlRendererRegistry.ts` 的 `HtmlComponentType` union 中新增 `'b22a-control-matrix'`
- [x] 1.2 在 `REGISTRY_LIST` 中新增注册条目：componentType=`b22a-control-matrix`, icon='🛡️', label='B22A 内部控制了解程序表', emits=['save','completed'], contextProps='standard'
- [x] 1.3 添加 lazy import: `const GtB22AControlMatrix = defineAsyncComponent(() => import('./GtB22AControlMatrix.vue'))`
- [x] 1.4 更新 `wp_code_overrides.json`：将 `"B22A"` 映射为 `"b22a-control-matrix"`，将 `"B22A-1"`、`"B22A-2"`、`"B22A-3"`、`"B22A-4"`、`"B22A-4-1"`、`"B22A-4-2"`、`"B22A-4-3"`、`"B22A-4-4-1"`、`"B22A-4-4-2"`、`"B22A-4-5"`、`"B22A-5"` 映射为 `"skip"`
- [x] 1.5 后端 `checklist_responses.py` 中 conclusion 校验增加 `B22A-` 前缀分支
  - 在现有 `elif item.item_id.startswith("B50-"):` 分支后新增 `elif item.item_id.startswith("B22A-"):` 分支
  - 白名单：`设计有效/设计无效/已实施/未实施/不适用/Y/N/NA/有效/部分有效/无效/高/中/低`
  - _Requirements: 11.1, 11.2, 11.3, 9.1, 9.5_

## 2. 组合式函数

- [x] 2.1 创建 `composables/useB22AFormData.ts` — 数据加载/debounce保存/即时保存/tab数据视图/续审加载
  - 实现 `loadAll()` 从 GET checklist-responses 加载全部 `B22A-*` 数据
  - 实现 `loadPriorYear(priorWpId)` 从上年 wp_id 加载历史 B22A-* 数据作为初始值
  - 实现 `saveImmediate(items)` 通过 PUT 批量保存
  - 实现 `saveDebouncedText(item)` debounce 2000ms 文本保存
  - 实现 tab1Data~tab5Data + summaryData 计算属性（按 item_id 前缀 B22A-T{n}- 分发）
  - 实现 `getField(itemId)` / `setFieldImmediate(itemId, data)` 辅助方法
  - 组件卸载时 `flushPendingSave()` flush 未保存数据
  - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7, 8.3_

- [x] 2.2 创建 `composables/useB22AControlMatrix.ts` — 检查项CRUD/结论评估/Element_Score自动计算/缺陷追踪/IT依赖/续审继承/业务规则警告
  - 实现 `getCheckItems(tab)` / `addCheckItem(tab, subPanel?)` / `removeCheckItem(tab, index, subPanel?)` 检查项 CRUD
  - 实现 `setConclusion(tab, index, conclusion, subPanel?)` 含即时保存 + 缺陷标记
  - 实现 `setUnderstandingMethod(tab, index, methods, subPanel?)` 了解方法多选
  - 实现 `computeElementScore(tab)` 自动计算（有效/部分有效/无效规则）
  - 实现 `overrideElementScore(tab, score, reason)` 手动覆盖 + `isScoreOverridden(tab)` 标识
  - 实现 `itDependency` / `setITDependency(level)` IT 依赖程度控制
  - 实现 `itgcConclusion` / `isITGCInvalid` ITGC 结论传递
  - 实现 `deficiencyList` 缺陷清单（自动收集设计无效/未实施项）
  - 实现 `elementStats` / `overallConclusion` / `completedElementCount` 汇总统计
  - 实现 `tabStatus(tab)` Tab 完成状态（empty/partial/complete）
  - 实现 `priorYearData` / `markNoChange(tab, index, confirmer)` 续审继承
  - 实现 `controlEnvWeakWarning` / `itControlWeakWarning` 业务规则警告
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 4.2, 4.3, 4.5, 4.6, 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 6.1, 6.2, 6.5, 8.3, 8.4, 8.5, 8.6, 13.1, 13.3, 13.4_

- [x] 2.3 创建 `composables/useB22AReview.ts` — 现场经理复核签字/只读状态/Amendment机制
  - 实现 `isReviewed` / `isReadonly` / `canReview` 计算属性
  - 实现 `pendingItems` 计算属性（待完成事项清单）
  - 实现 `reviewInfo` 计算属性（复核人/日期）
  - 实现 `doReview()` 签字保存方法（含前置条件校验）
  - 实现 `startAmendment(reason)` 修改机制（重置复核 + 记录修改原因）
  - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.6_

## 3. Vue 组件实现

- [x] 3.1 创建 `GtB22AControlMatrix.vue` 骨架 — script setup + props/emits 定义
  - Props: wpId, projectId, wpCode, year, readonly
  - Emits: save, completed
  - 引入三个 composables 并初始化
  - _Requirements: 11.4, 11.5_

- [x] 3.2 实现 6-tab 容器 — 5 COSO 要素 + 汇总 Tab + 默认激活 Tab_1 + tab 完成状态指示器
  - Tab_1"控制环境"、Tab_2"风险评估过程"、Tab_3"信息系统与沟通"、Tab_4"控制活动"、Tab_5"监督"、Summary_Tab"控制矩阵汇总"
  - 各 tab 页签显示 TabStatus 指示（empty/partial/complete）
  - tab 栏右侧显示整体完成进度（已完成要素数/5）
  - _Requirements: 1.1, 1.2, 1.4, 1.5, 1.6_

- [x] 3.3 实现 Tab 1~5 通用检查项表格 — 结构化行（序号/控制要点/描述/了解方法多选/结论下拉/参考引用）+ 新增/删除行
  - 检查项表格渲染：序号自动分配、控制要点/描述文本编辑、了解方法多选（询问/观察/检查文件/穿行测试）、Conclusion 下拉（设计有效/设计无效/已实施/未实施/不适用）、参考依据文本
  - 新增行按钮 + 删除行确认（预置检查项不可删除）
  - Conclusion 为"设计无效"/"未实施"时行显示红色警告标识（Control_Deficiency）
  - 底部"审计说明"文本区 + "要素整体结论"下拉（有效/部分有效/无效）
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7_

- [x] 3.4 实现 Tab 4 IT 控制子区 — 手风琴 6 面板 + IT_Dependency 选择器 + ITGC 警告
  - IT_Dependency 下拉（高/中/低）在子区顶部
  - 6 子面板手风琴：IT环境了解、ITGC、IT应用控制、变更管理、访问安全、职责分离
  - 各子面板使用与主检查项表相同行结构
  - IT_Dependency="高"时全展开+必填标记；"中"时展开+可选标注；"低"时收起+"可简化执行"提示
  - ITGC 结论为"无效"时 IT 应用控制子面板顶部显示警告条
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7_

- [x] 3.5 实现 Summary Tab — 交叉汇总矩阵 + 自动聚合 Element_Score + 颜色编码 + 统计
  - 交叉汇总表：行=检查维度、列=5 COSO 要素，单元格=该要素评价
  - 颜色编码：有效=绿色、部分有效=黄色、无效=红色、不适用=灰色
  - 各要素统计信息（有效项数/无效项数/未实施项数/总检查项数）
  - 底部"企业层面控制整体结论"下拉 + 说明文本区
  - 任一要素 Element_Score="无效"时显示醒目警告
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7_

- [x] 3.6 实现 Summary Tab 缺陷清单区域 — 控制缺陷汇总 + ref_chip 引用
  - 自动收集全部 Conclusion 为"设计无效"/"未实施"的检查项
  - 显示：来源要素 + 控制要点 + 缺陷类型
  - 支持从缺陷条目生成 ref_chip 供 B22B 关联
  - _Requirements: 6.1, 6.2, 6.4_

- [x] 3.7 实现 Element_Score 自动计算 + 手动覆盖对话框
  - 自动计算规则：全有效→"有效"；缺陷≤20%→"部分有效"；>20%→"无效"
  - 手动覆盖需填写调整理由（无理由拒绝）
  - 覆盖后显示"已手动调整"标识
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6_

- [x] 3.8 实现现场经理复核区 — 签字按钮 + 待完成事项清单 + 状态横幅
  - Summary_Tab 底部"现场经理复核"签字区域
  - 前置条件不满足时禁用按钮 + 显示 pendingItems
  - 签字完成后全组件只读 + emit completed
  - 顶部"已复核"绿色横幅（复核人/日期）
  - _Requirements: 10.1, 10.2, 10.3, 10.4_

- [x] 3.9 实现只读模式 + Amendment 机制
  - readonly prop 或已复核 → 全字段禁用
  - Amendment：填写修改原因 → 重置复核 → 重新编辑 → 重新复核
  - 修改原因为空/纯空白时拒绝提交
  - _Requirements: 10.5, 10.6_

- [x] 3.10 实现 EventBus 跨底稿联动
  - 整体结论或 Element_Score 变更时发布 `control:conclusion-changed` 事件（含 elementScores + itDependency + itgcConclusion + overallConclusion）
  - IT_Dependency 或 ITGC 结论变更时发布 `control:it-conclusion-changed` 事件
  - 存在控制缺陷变更时发布 `control:deficiency-changed` 事件（供 B22B 接收）
  - Tab_1 控制环境结论="无效"时触发控制环境薄弱事件
  - 支持从检查项生成 ref_chip 供 B23/B50 关联
  - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5_

- [x] 3.11 实现续审继承 UI — 上年数据加载按钮 + "本年无变化"确认 + 上年结论灰色提示
  - 续审项目识别（项目元数据判断审计类型）
  - 加载上年 checklist_responses 按 item_id 匹配填充空白项
  - 各检查项行标注"上年结论"灰色提示
  - "本年无变化"快速确认按钮（记录确认人 + 确认日期）
  - 首年审计要求全部检查项逐项完成
  - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6_

- [x] 3.12 实现控制环境薄弱警告横幅 + IT 控制薄弱警告
  - Summary_Tab 顶部红色横幅："控制环境薄弱——建议提高整体风险评估"（含跳转 B50 链接）
  - Tab_1 score="无效"/"部分有效" + 管理层诚信/治理层独立性检查项"设计无效"时触发
  - IT_Dependency="高" + ITGC 结论="无效"时 Tab_4 和 Summary_Tab 显示 IT 控制薄弱警告
  - 条件恢复后自动消失
  - _Requirements: 13.1, 13.2, 13.3, 13.4_

- [x] 3.13 实现响应式布局 — ≥1024px 完整显示 / 768~1024px 水平滚动
  - _Requirements: 12.1, 12.2_

## 4. 打印样式

- [x] 4.1 添加 `@media print` 样式 — Summary_Tab 汇总矩阵 A4 横版 + 颜色保留 + 隐藏交互控件
  - 隐藏按钮/输入控件，仅保留检查项数据+结论+颜色编码
  - A4 横版布局，`-webkit-print-color-adjust: exact`
  - 打印中保持有效性评价的颜色区分（绿/黄/红）
  - _Requirements: 12.3, 12.4, 12.5_

## 5. Property-Based Tests（fast-check）

- [x] 5.1 Property 1: 汇总矩阵同步不变式
  - **Property 1: Summary_Tab 统计数据 = Tab_1~5 检查项 Conclusion 实际分布计数**
  - 生成随机 5 tab × 随机检查项数量 × 随机 Conclusion → 验证 elementStats 计算与手动计数一致
  - **Validates: Requirements 4.2, 4.6, 5.1**

- [x] 5.2 Property 2: Element_Score 自动计算一致性
  - **Property 2: computeAutoScore 结果满足 20% 阈值规则**
  - 生成随机 N 个检查项 × 随机 Conclusion → 验证：全有效→"有效"；缺陷≤20%→"部分有效"；>20%→"无效"
  - **Validates: Requirements 5.2, 5.3, 5.4**

- [x] 5.3 Property 3: 控制缺陷清单同步不变式
  - **Property 3: deficiencyList = 所有 Conclusion 为"设计无效"/"未实施"的检查项集合**
  - 生成随机检查项集合 × 随机 Conclusion 变更序列 → 验证清单一致性
  - **Validates: Requirements 6.1, 6.5, 2.7**

- [x] 5.4 Property 4: IT 依赖程度作用域约束
  - **Property 4: IT_Dependency 切换 → 子面板展开/必填状态正确，已填数据不变**
  - 生成随机 ITDependency 值 × 随机 ITGC 结论 × 随机已填数据 → 验证 UI 状态 + 数据完整性
  - **Validates: Requirements 3.3, 3.4, 3.5**

- [x] 5.5 Property 5: ITGC 结论传递约束
  - **Property 5: ITGC 结论"无效"→ IT 应用控制显示警告；单向传递不逆向**
  - 生成随机 ITGC 结论 × 随机 IT 应用控制结论 → 验证警告条件和单向性
  - **Validates: Requirements 3.7, 7.3**

- [x] 5.6 Property 6: 复核前置条件完备性
  - **Property 6: canReview=true ⟺ 全部检查项有 Conclusion ∧ 整体结论已选择**
  - 生成随机 5 tab 检查项状态 × 随机整体结论 → 验证 canReview 计算
  - **Validates: Requirements 10.2**

- [x] 5.7 Property 7: 复核后只读不变式
  - **Property 7: review conclusion='Y' 或 readonly=true → isReadonly=true，写入操作被阻止**
  - 生成随机复核状态 × 随机 readonly prop → 验证 isReadonly + 写入拒绝
  - **Validates: Requirements 10.3, 10.4, 10.6**

- [x] 5.8 Property 8: item_id 命名唯一性
  - **Property 8: generateItemId(tab, subPanel, index, field) 唯一，相同输入相同输出**
  - 生成随机 tab × 随机 subPanel × 随机 index × 随机 field 组合 → 验证唯一性和确定性
  - **Validates: Requirements 9.7**

- [x] 5.9 Property 9: 颜色编码双射
  - **Property 9: SCORE_COLOR_MAP 满足双射（有效→绿/部分有效→黄/无效→红/不适用→灰）**
  - 全量枚举（仅 4 值，exhaustive）→ 验证唯一映射
  - **Validates: Requirements 4.3**

- [x] 5.10 Property 10: Tab 切换数据保持不变式
  - **Property 10: switchTab 操作不改变 tabXData 状态**
  - 生成随机编辑内容 → 随机 switchTab 序列 → 深度比较切换前后各 tab 数据
  - **Validates: Requirements 1.3**

- [x] 5.11 Property 11: 续审数据继承完整性
  - **Property 11: 加载上年数据仅填充空白项，不覆盖已有编辑；priorYearConclusion 正确填充**
  - 生成随机上年数据 × 随机当前数据（部分有值部分为空）→ 验证仅空项被填充
  - **Validates: Requirements 8.3, 8.4**

- [x] 5.12 Property 12: Tab/要素完成状态准确性
  - **Property 12: tabStatus + elementStats + completedElementCount 计算准确**
  - 生成随机检查项分布 → 手动计数 vs 函数输出 → 验证一致
  - **Validates: Requirements 1.4, 1.6, 4.6**

- [x] 5.13 Property 13: 业务规则警告条件正确性
  - **Property 13: controlEnvWeakWarning 和 itControlWeakWarning 的布尔值满足条件规则**
  - 生成随机 Tab_1 score × 随机关键检查项结论 × 随机 IT_Dependency × 随机 ITGC 结论 → 验证警告布尔值
  - **Validates: Requirements 13.1, 13.3, 13.4, 4.5**

## 6. Unit Tests（vitest）

- [x] 6.1 注册契约测试 — 验证 registry 包含 `b22a-control-matrix`，wp_code_overrides 映射正确（B22A→b22a-control-matrix, B22A-1~5 + B22A-4-x→skip）
  - _Requirements: 11.1, 11.2, 11.3_

- [x] 6.2 组件行为测试 — 6 tab 渲染 + 默认激活 Tab_1 + tab 状态指示器 + 完成进度
  - _Requirements: 1.1, 1.2, 1.4, 1.6_

- [x] 6.3 检查项 CRUD 测试 — 新增/删除/预置不可删 + 了解方法多选 + Conclusion 下拉
  - _Requirements: 2.1, 2.4, 2.5_

- [x] 6.4 IT 子区交互测试 — 手风琴展开/收起 + IT_Dependency 变更后子面板状态变化 + ITGC 警告条
  - _Requirements: 3.1, 3.3, 3.4, 3.7_

- [x] 6.5 保存行为测试 — debounce 2s 文本保存 + Conclusion/Element_Score 变更立即保存 + emit save
  - _Requirements: 9.2, 9.3_

- [x] 6.6 只读模式测试 — readonly prop / 已复核 → 全交互禁用 + 横幅渲染
  - _Requirements: 10.3, 10.4, 10.5_

- [x] 6.7 Amendment 流程测试 — 启动修改 → 填写原因 → 重置复核 → 重新编辑 → 重新复核
  - _Requirements: 10.6_

- [x] 6.8 续审模式测试 — "本年无变化"按钮 + 上年结论灰色提示 + 仅填充空白项
  - _Requirements: 8.3, 8.4, 8.5, 8.6_

- [x] 6.9 控制环境薄弱横幅测试 — 触发条件渲染 + 恢复后消失 + B50 跳转链接
  - _Requirements: 13.1, 13.2, 13.3_

- [x] 6.10 手动覆盖 Element_Score 测试 — 需理由校验 + "已手动调整"标识 + 覆盖不影响自动计算
  - _Requirements: 5.5, 5.6_

## 7. 后端 PBT（hypothesis）

- [x] 7.1 Property 8: 数据持久化往返一致性 — 生成随机 B22A- item_id + 合法 conclusion + 随机 remark → PUT → GET → 验证一致性
  - **Property 8 (Design): Round-trip consistency**
  - **Validates: Requirements 9.1, 9.5, 9.6**

- [x] 7.2 Conclusion 白名单校验 — 生成随机 B22A- item_id + 随机 conclusion 值 → 验证合法值 200、非法值 422
  - **Validates: Requirements 9.1（后端校验分支）**
