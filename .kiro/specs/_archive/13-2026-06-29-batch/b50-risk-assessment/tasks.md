# Tasks — B50 重大错报风险评估汇总

## 1. 注册与配置

- [x] 1.1 在 `htmlRendererRegistry.ts` 的 `HtmlComponentType` union 中新增 `'b50-risk-assessment'`
- [x] 1.2 在 `REGISTRY_LIST` 中新增注册条目：componentType=`b50-risk-assessment`, icon='🎯', label='B50 重大错报风险评估', emits=['save','completed'], contextProps='standard'
- [x] 1.3 添加 lazy import: `const GtB50RiskAssessment = defineAsyncComponent(() => import('./GtB50RiskAssessment.vue'))`
- [x] 1.4 更新 `wp_code_overrides.json`：将 `"B50"` 映射为 `"b50-risk-assessment"`，将 `"B50-1"`、`"B50-2"`、`"B50-3"`、`"B50-4"` 映射为 `"skip"`
- [x] 1.5 后端 `checklist_responses.py` 中 conclusion 校验增加 `B50-` 前缀分支（允许 H/M/L/Y/N/NA + source/category 枚举值）
  - 在现有 `elif item.item_id.startswith("A1-11-"):` 分支后新增 `elif item.item_id.startswith("B50-"):` 分支
  - 白名单：`H/M/L/Y/N/NA/B22A/B23/industry/discussion/prior_audit/management_interview/other/control_env/management_integrity/economic_env/industry_factor`
  - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.6_

## 2. 组合式函数

- [x] 2.1 创建 `composables/useB50FormData.ts` — 数据加载/debounce保存/即时保存/tab数据视图
  - 实现 `loadAll()` 从 GET checklist-responses 加载全部 `B50-*` 数据
  - 实现 `saveImmediate(items)` 通过 PUT 批量保存
  - 实现 `saveDebouncedText(item)` debounce 2000ms 文本保存
  - 实现 tab1Data/tab2Data/tab3Data/tab4Data 计算属性（按 item_id 前缀分发）
  - 组件卸载时 flush 未保存数据
  - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7_

- [x] 2.2 创建 `composables/useB50RiskMatrix.ts` — 矩阵状态/单元格操作/CAS规则/颜色映射/统计/筛选
  - 实现 accounts 响应式数组 + addAccount/removeAccount 方法
  - 实现 setCellRisk(account, assertion, layer, level) 含 CAS 校验
  - 实现 toggleSpecialRisk(account, assertion) 含管理层凌驾保护
  - 实现 matrixStats 计算属性（高/中/低/null 计数）
  - 实现 incompleteAccounts 计算属性（未完成评估的科目）
  - 实现 specialRiskCells 计算属性（含系统强制条目）
  - 实现 colorMap 计算属性（RISK_COLOR_MAP 双射映射）
  - 实现 isFraudPresumptionActive / requestFraudRebuttal 舞弊推定逻辑
  - 实现 filterLevel / filteredCells 筛选逻辑
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8, 6.1, 6.2, 6.4, 6.6, 11.2, 11.5_

- [x] 2.3 创建 `composables/useB50Approval.ts` — 合伙人审批/只读状态/Amendment机制
  - 实现 isApproved / isReadonly / canApprove 计算属性
  - 实现 pendingItems 计算属性（待完成事项清单）
  - 实现 approvalInfo 计算属性（签字人/日期）
  - 实现 doApproval() 签字保存方法
  - 实现 startAmendment(reason) 修改机制
  - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6_

## 3. Vue 组件实现

- [x] 3.1 创建 `GtB50RiskAssessment.vue` 骨架 — script setup + props/emits 定义
  - Props: wpId, projectId, wpCode, year, readonly
  - Emits: save, completed
  - 引入三个 composables 并初始化
  - _Requirements: 10.4, 10.5_

- [x] 3.2 实现 Tab 容器 — 4 个 tab 页签 + 默认激活 Tab_3 + tab 完成状态指示器
  - Tab_1"风险因素识别"、Tab_2"报表层面重大错报风险"、Tab_3"认定层面风险矩阵"、Tab_4"特别风险汇总"
  - 各 tab 页签显示 TabStatus 指示（empty/partial/complete）
  - tab 栏右侧显示整体完成进度
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6_

- [x] 3.3 实现 Tab 1: 风险因素识别 — 表格 + 新增/删除行 + 来源下拉 + ref_chip
  - 风险因素录入表格（描述/来源类型/影响科目认定/初步风险/已转入矩阵）
  - 来源类型下拉（B22A/B23/行业分析/项目组讨论/前期审计/管理层访谈/其他）
  - 新增行自动分配序号 + 删除行需确认
  - 来源为 B22A/B23 时显示 ref_chip 关联底稿
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6_

- [x] 3.4 实现 Tab 2: 报表层面重大错报风险 — 表格 + 风险等级下拉 + 颜色编码 + 统计
  - 报表层面风险录入表格（描述/类别/等级/应对措施）
  - 风险等级下拉 H/M/L 含颜色显示
  - 底部汇总统计（高 N 项/中 N 项/低 N 项）
  - 存在高风险时旁显醒目提示
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

- [x] 3.5 实现 Tab 3: 认定层面风险矩阵 — CSS Grid 交叉表 + 单元格 Popover 编辑 + 颜色编码 + 统计面板
  - CSS Grid 渲染行=科目、列=6认定
  - 单元格显示三层风险信息 + Combined_Risk 颜色背景
  - 点击单元格弹出 Popover 编辑面板（设置 IR/CR/RMM）
  - 特别风险单元格⚠️图标 + 红色边框
  - 动态添加/删除科目行
  - 顶部统计（科目总数 + 各等级计数）
  - 未完成科目行"未完成"警告标识
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8_

- [x] 3.6 实现 Tab 3: 风险矩阵固定表头 + 筛选 + 统计面板
  - 行表头（科目名）冻结 + 列表头（认定名）冻结，内容区可滚动
  - 按 Combined_Risk 等级筛选显示
  - 单元格悬停 tooltip（三层风险 + 备注）
  - 右侧风险分布统计面板（按科目/按认定汇总）
  - _Requirements: 11.1, 11.2, 11.3, 11.5_

- [x] 3.7 实现 Tab 4: 特别风险汇总 — 自动汇总 + 应对字段 + 底稿引用 + CAS标签 + 校验警告
  - 自动汇总 Tab_3 中 Special_Risk 单元格生成清单
  - 每项显示：关联科目/认定/描述/应对程序/底稿引用
  - 收入确认舞弊推定条目标注"CAS推定"标签
  - 管理层凌驾条目标注"强制特别风险"标签
  - 缺少应对程序时显示"待补充应对"警告
  - 支持手动添加 ref_chip 底稿引用
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6_

- [x] 3.8 实现 CAS 强制 UI — 舞弊推定反驳弹窗 + 管理层凌驾锁定行
  - 收入确认科目预置 + 固有风险默认"高"
  - 降级操作触发反驳确认弹窗（填写理由 + 合伙人签字）
  - 管理层凌驾控制固定行不可删除/不可降级
  - 特别风险应对程序 soft validation（不得仅含分析程序）
  - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6_

- [x] 3.9 实现合伙人审批区 — 签字按钮 + 待完成事项清单 + 状态横幅
  - 界面底部"合伙人审批"签字区域
  - 前置条件不满足时禁用按钮 + 显示 pendingItems
  - 签字完成后全组件只读 + emit completed
  - 顶部"已审批"绿色横幅（审批人/日期）
  - _Requirements: 9.1, 9.2, 9.3, 9.4_

- [x] 3.10 实现只读模式 + Amendment 机制
  - readonly prop 或已审批 → 全字段禁用
  - 已审批横幅显示
  - Amendment：填写修改原因 → 重置审批 → 重新编辑 → 重新审批
  - _Requirements: 9.5, 9.6_

- [x] 3.11 实现 EventBus 跨底稿联动
  - Combined_Risk 变更时发布 `risk:combined-changed` 事件
  - 特别风险变更时发布 `risk:special-risk-changed` 事件
  - Tab_2 报表层面风险变更时发布 B60 同步事件
  - Tab_1 显示 B22A/B23 控制结论摘要（只读引用）
  - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5_

- [x] 3.12 实现响应式布局 — ≥1024px 完整显示 / 768~1024px 水平滚动
  - _Requirements: 12.1, 12.2_

## 4. 打印样式

- [x] 4.1 添加 `@media print` 样式 — Tab_3 矩阵 A4 横版 + 颜色保留 + 隐藏交互控件
  - 隐藏按钮/输入控件，仅保留矩阵数据+颜色+统计
  - A4 横版布局，`-webkit-print-color-adjust: exact`
  - _Requirements: 12.3, 12.4, 12.5_

## 5. Property-Based Tests（fast-check）

- [x] 5.1 Property 1: 特别风险 Tab_4 同步不变式
  - **Property 1: Tab_4 条目集合 = Tab_3 Special_Risk 并集 + 管理层凌驾**
  - 生成随机矩阵（N 科目 × 6 认定 × 随机 specialRisk 标记）→ 验证 computeSpecialRiskEntries 结果
  - **Validates: Requirements 5.1, 5.3, 5.4, 6.4**

- [x] 5.2 Property 2: 收入确认舞弊推定不变式
  - **Property 2: 收入确认 IR 必须为 H，除非有效反驳（理由非空 + 合伙人签字）**
  - 生成随机认定 × 随机降级目标 × 随机反驳状态 → 验证 setCellRisk 拒绝/接受
  - **Validates: Requirements 6.1, 6.2, 6.3**

- [x] 5.3 Property 3: 管理层凌驾控制不可变式
  - **Property 3: 管理层凌驾不可删除/不可降级/始终在 specialRiskCells 中**
  - 生成随机操作序列（delete/toggle/setRisk）→ 验证条目始终存在
  - **Validates: Requirements 6.4**

- [x] 5.4 Property 4: 风险矩阵颜色编码双射
  - **Property 4: RISK_COLOR_MAP 满足双射（H→红/M→黄/L→绿，不同级不同色）**
  - 全量枚举（仅 3 值，exhaustive）→ 验证唯一映射
  - **Validates: Requirements 4.4, 3.2**

- [x] 5.5 Property 5: 审批前置条件完备性
  - **Property 5: canApprove=true ⟺ incompleteAccounts=0 ∧ 全部特别风险有应对**
  - 生成随机矩阵状态 × 随机应对填写状态 → 验证 canApprove 计算
  - **Validates: Requirements 9.2, 4.8, 5.5, 6.6**

- [x] 5.6 Property 6: 审批后只读不变式
  - **Property 6: approval conclusion='Y' 或 readonly=true → isReadonly=true，写入操作被阻止**
  - 生成随机审批状态 × 随机 readonly prop → 验证 isReadonly + 写入拒绝
  - **Validates: Requirements 9.3, 9.4, 9.5, 9.6**

- [x] 5.7 Property 8: item_id 命名唯一性
  - **Property 8: generateItemId(tab, row, field) 唯一，相同输入相同输出**
  - 生成随机 tab × 随机行标识 × 随机字段类型组合 → 验证唯一性
  - **Validates: Requirements 8.7**

- [x] 5.8 Property 9: 特别风险应对程序约束
  - **Property 9: validateResponseProcedure 仅当只含分析程序关键词无细节测试关键词时返回 false**
  - 生成随机文本（含/不含细节测试 × 含/不含分析程序）→ 验证结果
  - **Validates: Requirements 6.5**

- [x] 5.9 Property 10: Tab 切换数据保持不变式
  - **Property 10: switchTab 操作不改变 tabXData 状态**
  - 生成随机编辑 → 随机 switchTab 序列 → 深度比较切换前后
  - **Validates: Requirements 1.3**

- [x] 5.10 Property 11: 风险统计准确性
  - **Property 11: matrixStats 计数 = 手动遍历计数，且 H+M+L+null = totalAccounts×6**
  - 生成随机矩阵 → 手动计数 vs matrixStats → 验证一致
  - **Validates: Requirements 4.7, 3.4, 11.5**

- [x] 5.11 Property 12: EventBus 风险变更事件发射
  - **Property 12: setCellRisk(combined, newLevel≠oldLevel) → 发布事件；未变更 → 不发射**
  - 生成随机单元格 × 随机新旧等级 → 验证事件发射行为
  - **Validates: Requirements 7.1, 7.3, 7.4**

- [x] 5.12 Property 13: 风险等级筛选正确性
  - **Property 13: filteredCells 仅含 combinedRisk===filterLevel；null 时返回全部**
  - 生成随机矩阵 × 随机 filterLevel → 验证筛选结果
  - **Validates: Requirements 11.2**

## 6. Unit Tests（vitest）

- [x] 6.1 注册契约测试 — 验证 registry 包含 `b50-risk-assessment`，wp_code_overrides 映射正确（B50→b50-risk-assessment, B50-1~4→skip）
  - _Requirements: 10.1, 10.2, 10.3_

- [x] 6.2 组件行为测试 — 4 tab 渲染 + 默认激活 Tab_3 + tab 状态指示器
  - _Requirements: 1.1, 1.2, 1.4_

- [x] 6.3 CAS 预置科目测试 — 收入确认 + 管理层凌驾存在性、不可删除、默认高风险
  - _Requirements: 6.1, 6.4_

- [x] 6.4 保存行为测试 — debounce 2s 文本保存 + 风险等级变更立即保存 + emit save
  - _Requirements: 8.2, 8.3_

- [x] 6.5 只读模式测试 — readonly prop / 已审批 → 全交互禁用 + 横幅渲染
  - _Requirements: 9.3, 9.4, 9.5_

- [x] 6.6 Amendment 流程测试 — 启动修改 → 填写原因 → 重置审批 → 重新编辑 → 重新审批
  - _Requirements: 9.6_

## 7. 后端 PBT（hypothesis）

- [x] 7.1 Property 7: 数据持久化往返一致性 — 生成随机 B50- item_id + 合法 conclusion + 随机 remark → PUT → GET → 验证一致性
  - **Property 7: Round-trip consistency**
  - **Validates: Requirements 8.1, 8.5, 8.6**

- [x] 7.2 Conclusion 白名单校验 — 生成随机 B50- item_id + 随机 conclusion 值 → 验证合法值 200、非法值 422
  - **Validates: Requirements 8.1（后端校验分支）**
