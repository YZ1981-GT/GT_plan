# Tasks — C 类控制测试专属组件

## 1. 注册与配置

- [x] 1.1 在 `htmlRendererRegistry.ts` 的 `HtmlComponentType` union 中新增 `'c-control-test'`
- [ ] 1.2 在 `REGISTRY_LIST` 中新增注册条目：componentType=`c-control-test`, icon='🧪', label='C 控制测试', emits=['save','completed'], contextProps='standard'
- [ ] 1.3 添加 lazy import: `const GtCControlTest = defineAsyncComponent(() => import('./GtCControlTest.vue'))`
- [ ] 1.4 更新 `wp_code_overrides.json`：将 `C2`~`C15` 共 14 条映射为 `c-control-test`
- [ ] 1.5 后端 `checklist_responses.py` 中 conclusion 校验增加 `C{n}-` 前缀分支（n=2~15）
  - 白名单：`控制有效运行/控制存在偏差但可接受/控制无效/有效/偏差/不适用/全部有效/部分偏差/控制失效/询问/观察/检查/重新执行/Y/N`
  - _Requirements: 1.1, 1.2, 14.1, 14.2, 14.3, 14.4_

## 2. 组合式函数

- [ ] 2.1 创建 `composables/useCControlTestData.ts` — 数据加载/debounce保存/即时保存
  - 实现 `loadAll()` 从 GET checklist-responses 加载全部 `C{n}-*` 数据到 `allResponses` Map
  - 实现 `saveImmediate(items)` 通过 PUT 批量保存（Test_Method/Sample_Result/结论触发）
  - 实现 `saveDebouncedText(item)` debounce 2000ms 文本保存（偏差描述/凭证号/金额等字段）
  - 实现 `flushPendingSave()` 组件卸载时 flush 未保存数据
  - 实现 `getField(itemId)` / `setFieldImmediate(itemId, data)` 辅助方法
  - _Requirements: 12.1, 12.2, 12.3, 12.4, 12.5, 12.6, 12.7_

- [ ] 2.2 创建 `composables/useCControlTest.ts` — 控制点卡片/样本CRUD/偏差计算/结论建议/EventBus/复核
  - 实现 `controlPoints` 计算属性（ControlPointTest[] 卡片数据）
  - 实现 `expandedCards` / `toggleCard` / `expandAll` / `collapseAll` 展开收起管理
  - 实现 `addControlPoint()` / `removeControlPoint(index)` 控制点 CRUD
  - 实现 `setTestMethods(ctrlIndex, methods)` 测试方法多选设置
  - 实现 `getSamples(ctrlIndex)` / `addSample(ctrlIndex, sample)` / `removeSample(ctrlIndex, sampleIndex)` / `addBatchSamples(ctrlIndex, batch)` 样本管理
  - 实现 `setSampleResult(ctrlIndex, sampleIndex, result)` / `setDeviationDescription(ctrlIndex, sampleIndex, desc)` 样本结果录入
  - 实现 `getDeviationStats(ctrlIndex)` 偏差率自动计算（公式：偏差数 ÷ (总样本-不适用)）
  - 实现 `suggestPointConclusion(ctrlIndex)` 控制点结论自动建议（0%/≤容忍率/>容忍率 三档）
  - 实现 `setPointConclusion(ctrlIndex, conclusion, overrideReason?)` 手动覆盖结论
  - 实现 `tolerableDeviationRate` / `setTolerableRate(rate)` 可容忍偏差率管理
  - 实现 `suggestCycleConclusion` / `setCycleConclusion(conclusion, overrideReason?)` 循环结论汇总
  - 实现 `b23ControlPoints` / `loadB23Reference()` B23 控制点引用加载
  - 实现 `isReviewed` / `isReadonly` / `canReview` / `pendingItems` 复核状态
  - 实现 `doReview()` / `startAmendment(reason)` 复核操作
  - 实现 `publishTestConcluded(old, new)` EventBus 发布 `control:test-concluded`
  - 实现 `linkageInfo` / `cycleName` / `targetProcedureCycle` 联动信息
  - _Requirements: 2.1~2.6, 3.1~3.4, 4.1~4.6, 5.1~5.5, 6.1~6.5, 7.1~7.7, 8.1~8.7, 9.1~9.5, 10.1~10.4, 13.1~13.6_

- [ ] 2.3 单元验证：2 composables 导出正确，TypeScript 类型无错误
  - _Requirements: 所有_

## 3. Vue 组件实现

- [ ] 3.1 创建 `GtCControlTest.vue` 骨架 — script setup + props/emits + composables 初始化
  - Props: wpId, projectId, wpCode, year, readonly
  - Emits: save, completed
  - 从 wpCode 提取 cycleNum（parseInt(wpCode.replace('C',''))）
  - 引入 2 个 composables 并初始化
  - onMounted 中 loadAll + loadB23Reference
  - onBeforeUnmount 中 flushPendingSave
  - _Requirements: 1.3, 1.4, 1.6_

- [ ] 3.2 实现 B23 引用面板 — 控制点清单 + 手动新增 + ref_chip 跳转
  - 顶部 B23_Reference 面板显示当前循环控制点清单（编号+目标）
  - B23 未录入时显示提示 + 允许手动添加
  - 手动新增控制点分配递增编号
  - ref_chip 跳转到 B23 对应流程
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6_

- [ ] 3.3 实现控制点测试卡片 — 可折叠卡片 + 标题栏信息 + 展开/收起
  - 每个控制点一张卡片（左侧色带=结论颜色）
  - 标题栏：控制编号 + 目标摘要 + 结论标签 + 偏差率 + 展开图标
  - 支持全部展开/收起快捷按钮
  - 单循环最多 30 个控制点
  - _Requirements: 2.4, 7.1_

- [ ] 3.4 实现测试方法多选区域 — 4 选项多选 + "重新执行"提示
  - 卡片内 Test_Method 多选：询问/观察/检查/重新执行
  - 至少选 1 个后可进入样本录入
  - "重新执行"选中时显示提示文本
  - 选择即时保存
  - _Requirements: 3.1, 3.2, 3.3, 3.4_

- [ ] 3.5 实现样本管理区域 — 逐条添加/删除/批量添加 + 样本量统计
  - 样本列表（凭证编号/日期/金额 三列）
  - 添加/删除单条样本
  - 批量添加（起止凭证号快捷生成）
  - 顶部"样本量: N 笔"统计
  - 空时显示"请添加测试样本"占位
  - 单控制点最多 50 笔样本
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6_

- [ ] 3.6 实现逐笔样本结果录入 — 结果选择 + 偏差描述 + 红色高亮
  - 每条样本右侧 Sample_Result 选择：有效/偏差/不适用
  - "偏差"时展开偏差描述文本框
  - 偏差样本红色背景高亮
  - Sample_Result 即时保存，偏差描述 debounce 2s
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_

- [ ] 3.7 实现偏差统计区域 — 偏差数/有效样本/偏差率 + 超限警告
  - 卡片内实时显示：偏差数 / 有效样本数 = 偏差率%
  - 超过可容忍率时红色高亮 + "超出可容忍偏差率"警告
  - 全部不适用时显示"无有效样本，无法计算偏差率"
  - 页面顶部可容忍偏差率设置（默认 10%，范围 0%~50%）
  - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_

- [ ] 3.8 实现控制点结论区域 — 自动建议 + 手动选择 + 覆盖机制
  - 卡片底部 Control_Point_Conclusion 选择（控制有效运行/存在偏差但可接受/控制无效）
  - 自动建议显示为参考提示（基于偏差率 vs 可容忍率）
  - 手动覆盖时弹出"调整理由"输入（无理由拒绝覆盖）
  - 覆盖后显示"已手动调整"标识+理由
  - 结论变更即时保存
  - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7_

- [ ] 3.9 实现循环级整体结论区域 — 汇总 + 自动建议 + 手动覆盖
  - 所有卡片下方 Cycle_Conclusion 汇总区域
  - 自动建议（全有效/部分偏差/控制失效）
  - 手动覆盖需理由
  - 结论变更即时保存 + 触发 publishTestConcluded
  - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7_

- [ ] 3.10 实现联动面板 — ref_chip 跳转 B23/B50/D~N + 影响提示
  - Linkage_Panel 显示 B23/B50/D~N 关联链接（ref_chip）
  - 各链接显示当前状态
  - "控制失效"时高亮 D~N 关联 + "需扩大实质性程序范围"提示
  - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5_

- [ ] 3.11 实现 EventBus 发布
  - Cycle_Conclusion 变更且新旧不同时发布 `control:test-concluded`
  - 载荷含 wpCode/cycleName/conclusion/deviationSummary
  - 组件卸载时注销监听
  - _Requirements: 10.1, 10.2, 10.3, 10.4_

- [ ] 3.12 实现证据管理 Tab — Cx-2 嵌入渲染
  - 主区域 + 证据明细 Tab 切换
  - Evidence_Tab 使用 GtWpRenderer 懒加载渲染 Cx-2
  - Cx-2 不存在时占位提示
  - 默认显示主测试区域
  - _Requirements: 11.1, 11.2, 11.3, 11.4_

- [ ] 3.13 实现复核签字区域 — 签字按钮 + 前置校验 + 只读锁定
  - Cycle_Conclusion 下方"现场经理复核"区域
  - 前置条件不满足时禁用 + 显示 pendingItems
  - 签字后全组件只读 + emit completed
  - 顶部"已复核"绿色横幅
  - readonly prop 或已复核 → 全禁用
  - Amendment：填写原因→解锁→重新复核
  - _Requirements: 13.1, 13.2, 13.3, 13.4, 13.5, 13.6_

- [ ] 3.14 实现打印样式 — @media print 适配
  - 隐藏交互控件（展开/收起、添加/删除按钮）
  - 自动展开所有卡片
  - 保留颜色编码（`-webkit-print-color-adjust: exact`）
  - A4 纵版适配
  - _Requirements: 打印需求_

## 4. Checkpoint

- [ ] 4.1 确保所有组件代码编译无错误，TypeScript 类型检查通过

- [ ] 4.2 确保 `VALID_COMPONENT_TYPES`（wp_classification_service.py）包含 `c-control-test`

## 5. Property-Based Tests（fast-check）

- [ ]* 5.1 Property 1: 偏差率计算不变式
  - 生成随机 N 条样本(0~50) × 随机 SampleResult → 验证：deviationRate = 偏差数 ÷ (总样本-不适用样本)；分母=0 时返回 null
  - **Validates: Requirements 6.1, 6.2, 6.4**

- [ ]* 5.2 Property 2: 控制点结论建议一致性
  - 生成随机 deviationRate(0~1,含null) × 随机 tolerableRate(0.01~0.5) → 验证：0→有效；≤容忍→可接受；>容忍→无效；null→null
  - **Validates: Requirements 7.2, 7.3, 7.4, 7.5**

- [ ]* 5.3 Property 3: 循环结论汇总一致性
  - 生成随机 N 个控制点结论(0~30) → 验证：全有效→全部有效；有偏差无无效→部分偏差；有无效→控制失效；全null→null
  - **Validates: Requirements 8.2, 8.3, 8.4, 8.5**

- [ ]* 5.4 Property 4: EventBus 事件发射正确性
  - 生成随机新旧 CycleConclusion → 验证：不同时发射、相同时不发射、载荷字段正确
  - **Validates: Requirements 10.1, 10.2, 10.3**

- [ ]* 5.5 Property 5: item_id 唯一性
  - 生成随机 cycleNum(2~15) × ctrlIndex(1~30) × sampleIndex(1~50) × field → 验证无碰撞+确定性
  - **Validates: Requirements 12.7**

- [ ]* 5.6 Property 6: 数据往返一致性
  - 生成随机 C{n}- item_id + 合法 conclusion + 随机 remark → PUT → GET → 验证一致
  - **Validates: Requirements 12.1, 12.5, 12.6**

- [ ]* 5.7 Property 7: 复核前置条件
  - 生成随机控制点完成度(0~30个,每个有/无结论) × 有/无 cycleConclusion → 验证 canReview 正确
  - **Validates: Requirements 13.2**

- [ ]* 5.8 Property 8: 白名单校验
  - 生成随机 C{n}- item_id + 随机 conclusion（合法/非法混合）→ 验证 200/422
  - **Validates: Requirements 14.1, 14.2, 14.3, 14.4**

## 6. Unit Tests（vitest）

- [ ]* 6.1 注册契约测试 — 验证 registry 包含 `c-control-test`，wp_code_overrides C2~C15 映射正确
  - _Requirements: 1.1, 1.2_

- [ ]* 6.2 wpCode 解析测试 — C2→2, C10→10, C15→15 循环编号提取正确
  - _Requirements: 1.6_

- [ ]* 6.3 B23 引用面板测试 — 控制点清单渲染 + B23未录入提示 + 手动添加 + ref_chip
  - _Requirements: 2.1, 2.2, 2.3, 2.5_

- [ ]* 6.4 控制点卡片渲染测试 — 卡片渲染 + 展开/收起 + 标题栏信息 + 色带
  - _Requirements: 2.4, 7.1_

- [ ]* 6.5 测试方法多选测试 — 4 选项多选 + 至少选 1 + "重新执行"提示 + 即时保存
  - _Requirements: 3.1, 3.2, 3.3, 3.4_

- [ ]* 6.6 样本管理测试 — 添加/删除/批量添加 + 样本量统计 + 空态占位 + 上限50
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6_

- [ ]* 6.7 样本结果录入测试 — 结果选择 + 偏差描述展开 + 红色高亮 + 保存行为
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_

- [ ]* 6.8 偏差率计算测试 — 实时计算 + 超限警告 + 全不适用提示 + 可容忍率设置
  - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_

- [ ]* 6.9 控制点结论测试 — 自动建议 + 手动覆盖需理由 + "已手动调整"标识
  - _Requirements: 7.1, 7.2, 7.6, 7.7_

- [ ]* 6.10 循环结论测试 — 汇总逻辑 + 手动覆盖 + 即时保存
  - _Requirements: 8.1, 8.2, 8.6, 8.7_

- [ ]* 6.11 联动面板测试 — ref_chip 跳转 + "控制失效"时高亮提示
  - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5_

- [ ]* 6.12 EventBus 发布测试 — 结论变更发射 + 载荷正确 + 相同不发射
  - _Requirements: 10.1, 10.2, 10.3_

- [ ]* 6.13 Evidence_Tab 测试 — Tab 切换 + Cx-2 懒加载 + 不存在时占位
  - _Requirements: 11.1, 11.2, 11.3, 11.4_

- [ ]* 6.14 保存行为测试 — debounce 2s(fake timers) + 即时保存 + emit save
  - _Requirements: 12.2, 12.3_

- [ ]* 6.15 复核签字测试 — 前置条件校验 + 签字 + emit completed + 只读
  - _Requirements: 13.1, 13.2, 13.3, 13.4_

- [ ]* 6.16 Amendment 测试 — 启动修改→原因校验→解锁→重新复核
  - _Requirements: 13.6_

- [ ]* 6.17 readonly 模式测试 — prop/已复核 → 全禁用
  - _Requirements: 13.5_

- [ ]* 6.18 打印样式测试 — @media print 样式存在 + 交互控件隐藏
  - _Requirements: 打印需求_

## 7. 后端 PBT（hypothesis）

- [ ]* 7.1 Property 5: 数据往返一致性 — C{n}- item_id + 合法 conclusion + 随机 remark → PUT → GET → 一致
  - **Validates: Requirements 12.1, 12.5, 12.6**

- [ ]* 7.2 Property 8: 白名单校验 — C{n}- item_id + 随机 conclusion → 合法 200 / 非法 422
  - **Validates: Requirements 14.1, 14.2, 14.3, 14.4**

## 8. Final Checkpoint

- [x] 8.1 确保所有测试通过，如有疑问询问用户
  - 运行 vitest（单元测试 + property tests）
  - 运行 hypothesis（后端 PBT）
  - 验证 TypeScript 编译无错误
  - 验证 componentType 契约测试通过
