# Implementation Plan: A13 错报评价自动聚合

## Overview

将 A13 错报评价从手动汇总升级为事件驱动的实时聚合系统。后端新增 Aggregation_Resolver + EventBus handler + 沟通函端点，前端增强 MisstatementSummaryView（三色预警 + 上年追踪 + ref_chip + SSE 自动刷新）。Python 后端 + Vue/TypeScript 前端。

## Tasks

- [x] 1. 数据库迁移：扩展 unadjusted_misstatements 表
  - [x] 1.1 创建 V092 迁移脚本
    - 创建 `backend/migrations/V092__a13_misstatement_aggregation.sql`
    - 新增 `prior_year_status VARCHAR(20) DEFAULT 'new' CHECK (prior_year_status IN ('new', 'continuing', 'reversed'))`
    - 新增 `source_wp_code VARCHAR(20)`
    - 添加列注释
    - _Requirements: 4.1, 6.1_

  - [x]* 1.2 编写迁移验证测试
    - 验证新列存在、默认值正确、CHECK 约束生效
    - _Requirements: 4.1_

- [x] 2. 后端核心：Aggregation_Resolver 聚合计算
  - [x] 2.1 实现 `_misstatement_aggregation.py` auto_resolver
    - 创建 `backend/app/services/auto_data_resolvers/_misstatement_aggregation.py`
    - 注册 `@auto_resolver("a13_misstatement_summary")`
    - 查询 UnadjustedMisstatement 表 (project_id + year 过滤)
    - 计算: total_count, total_amount (排除 reversed)
    - 计算: by_type 分组 (factual/judgmental/projected，各 count + amount)
    - 计算: fraud_count (来自 A13-4 标记)
    - 计算: net_effect
    - 计算: prior_year (continuing_amount, reversed_amount)
    - 计算: current_year (new_amount)
    - 计算: cumulative_total = continuing_amount + new_amount
    - _Requirements: 1.5, 4.4, 4.5_

  - [x] 2.2 实现重要性水平查询与状态分类
    - 从 B15 Materiality Service 查询 PM/TE/SAT
    - 实现 `classify_materiality_status(cumulative, pm, te, sat)` 纯函数
    - 状态: green (< SAT), yellow (SAT ≤ x < PM), red (≥ PM)
    - PM 为 null/0 时返回 "undetermined"
    - fraud_count > 0 时设置 fraud_flag = True
    - 计算 ratio = cumulative / pm
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.7_

  - [x] 2.3 实现聚合结果持久化
    - 将计算结果写入 A13 底稿 `parsed_data.html_data['summary']`
    - 格式遵循 design 中的 `a13-summary-v1` JSON schema
    - 写入失败时 retry 1 次，最终失败 log.error
    - _Requirements: 1.6, 1.8_

  - [x]* 2.4 Property 1: 聚合计算正确性属性测试
    - **Property 1: Aggregation computation correctness**
    - 随机生成 misstatement 列表 (type, amount, prior_year_status)
    - 验证 total_count/total_amount 排除 reversed
    - 验证 by_type 分组正确
    - 验证 cumulative_total == continuing + new
    - **Validates: Requirements 1.5, 4.3, 4.4, 4.5**

  - [x]* 2.5 Property 2: 重要性状态分类属性测试
    - **Property 2: Materiality status classification**
    - 随机生成 (cumulative, pm, sat) 元组
    - 验证 green/yellow/red 边界正确
    - 验证 fraud_count > 0 时 fraud_flag 始终 True
    - **Validates: Requirements 3.1, 3.2, 3.7**

  - [x]* 2.6 Property 6: Prior_Year_Status 不变式属性测试
    - **Property 6: Prior_Year_Status invariant**
    - 随机生成 misstatement (is_carried_forward, prior_year_status) 组合
    - 验证 is_carried_forward=True → status ∈ {continuing, reversed}
    - 验证 is_carried_forward=False → status == "new"
    - **Validates: Requirements 4.1**

  - [x]* 2.7 Property 12: 聚合持久化往返一致性属性测试
    - **Property 12: Aggregation persistence round-trip**
    - 随机生成 aggregation result dict
    - 验证写入后读取等价于原值
    - **Validates: Requirements 1.6**

- [x] 3. Checkpoint - 聚合核心逻辑验证
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. 后端：EventBus handler + debounce 机制
  - [x] 4.1 实现 `_on_a13_sheet_saved` event handler
    - 创建 handler 注册到 EventType.WORKPAPER_SAVED
    - 过滤 wp_code 匹配 A13-2/A13-3/A13-4/A13-5
    - 从 EventPayload 提取 project_id 和 year
    - 异步调用 Aggregation_Resolver（不阻塞 save response）
    - 完成后 broadcast_raw SSE 事件 `a13_summary_updated`
    - _Requirements: 2.1, 2.2, 2.3, 2.5, 2.6_

  - [x] 4.2 实现 debounce 逻辑（2 秒窗口）
    - 多个 A13 子 tab 在 2 秒内连续保存时仅执行一次聚合
    - 使用 asyncio.Task + cancel 模式或 Redis key TTL
    - debounce 以 project_id + year 为 key
    - _Requirements: 2.4_

  - [x]* 4.3 Property 4: Debounce 合并属性测试
    - **Property 4: Debounce consolidation**
    - 随机生成 N 个事件 + 时间间隔
    - 验证 2 秒窗口内仅执行一次 resolver
    - **Validates: Requirements 2.4**

  - [x]* 4.4 Property 5: Event payload 契约属性测试
    - **Property 5: Event payload contract**
    - 随机 sheet_id ∈ {A13-2, A13-3, A13-4, A13-5}
    - 验证 EventPayload 包含 event_type/project_id/year/wp_code
    - **Validates: Requirements 2.1, 2.6**

- [x] 5. 后端：上年结转状态追踪
  - [x] 5.1 改造 carry_forward 逻辑
    - carry_forward 创建新记录时设置 `prior_year_status = "continuing"`
    - 设置 `is_carried_forward = True` + `prior_year_id` 指向原记录
    - _Requirements: 4.2_

  - [x] 5.2 实现 "标记已转回" 接口
    - 新增或复用端点支持将 carried-forward 记录的 prior_year_status 更新为 "reversed"
    - 更新后从 cumulative 中排除该记录
    - _Requirements: 4.3_

  - [x] 5.3 B15 重要性变更时重评估
    - 监听 B15 更新事件（或 A13 聚合时实时查询最新 PM）
    - PM 变化时重新评估所有 carried-forward 记录
    - _Requirements: 4.6_

  - [x]* 5.4 Property 7: Carry_forward 状态赋值属性测试
    - **Property 7: Carry_forward status assignment**
    - 随机生成上年 misstatement 集合
    - 验证 carry_forward 后全部 status="continuing" + is_carried_forward=True
    - **Validates: Requirements 4.2**

- [x] 6. Checkpoint - EventBus + 上年结转验证
  - Ensure all tests pass, ask the user if questions arise.

- [x] 7. 后端：沟通函草稿生成
  - [x] 7.1 实现 `POST /workpapers/{pid}/{year}/communication-draft` 端点
    - 查询 prior_year_status IN ('continuing', 'new') 的未更正错报
    - 无未更正错报时返回 empty 标志
    - 生成 Communication_Draft JSON (items + summary + conclusion_text)
    - _Requirements: 5.1, 5.2, 5.3, 5.5_

  - [x] 7.2 实现结论模板选择逻辑
    - Template A: cumulative < PM × 0.75
    - Template B: PM × 0.75 ≤ cumulative < PM
    - Template C: cumulative ≥ PM
    - _Requirements: 5.6_

  - [x] 7.3 持久化草稿到 A13-5 sheet data
    - 生成后写入 `parsed_data.html_data['communication_draft']`
    - 再次打开时直接展示，无需重新生成
    - _Requirements: 5.7_

  - [x]* 7.4 Property 8: 沟通函过滤与完整性属性测试
    - **Property 8: Communication draft filtering and completeness**
    - 随机生成 mixed status misstatement 集合
    - 验证仅包含 continuing + new 的条目
    - 验证每条包含 seq/description/affected_account/amount/misstatement_type/management_reason
    - **Validates: Requirements 5.1, 5.2, 5.3**

  - [x]* 7.5 Property 9: 沟通函模板选择属性测试
    - **Property 9: Communication draft template selection**
    - 随机生成 (cumulative, pm) 对
    - 验证 A/B/C 模板选择边界正确
    - **Validates: Requirements 5.6**

- [x] 8. 后端：错报来源 ref_chip 支持
  - [x] 8.1 改造 create_from_rejected_aje 自动填充 source_wp_code
    - rejected AJE 创建 misstatement 时，从 adjustment 的 originating_wp_code 填入 source_wp_code
    - _Requirements: 6.4_

  - [x] 8.2 注册 cross_wp_references 条目
    - A13 → 源底稿 (D~N cycles) 双向导航引用注册
    - _Requirements: 6.7_

  - [x]* 8.3 Property 10: Source_Ref_Chip 可见性属性测试
    - **Property 10: Source_Ref_Chip visibility**
    - 随机生成 misstatement (source_wp_code, source_adjustment_id)
    - 验证 chip 显示当且仅当任一非 null
    - **Validates: Requirements 6.1**

  - [x]* 8.4 Property 11: rejected AJE source_wp_code 自动填充属性测试
    - **Property 11: Source_wp_code auto-population from rejected AJE**
    - 随机生成带 originating_wp_code 的 adjustment
    - 验证创建的 misstatement.source_wp_code == adjustment.originating_wp_code
    - **Validates: Requirements 6.4**

- [x] 9. Checkpoint - 后端全功能验证
  - Ensure all tests pass, ask the user if questions arise.

- [x] 10. 前端：MisstatementSummaryView 增强
  - [x] 10.1 实现 Materiality_Indicator 组件
    - 在 MisstatementSummaryView 顶部新增 el-alert 组件
    - 三色状态映射: success (green) / warning (yellow) / error (red)
    - 显示: 累计未更正金额、PM 值、比率百分比
    - PM 未确定时显示 info 类型 + "重要性水平未确定" + 跳转 B15 链接
    - fraud_count > 0 时额外显示红色 badge
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.6, 3.7_

  - [x] 10.2 实现 SSE 监听自动刷新
    - 监听 `a13_summary_updated` SSE 事件
    - 收到事件时自动 reload summary 数据
    - SSE 断开降级: tab 切换时主动 fetch 最新 summary
    - _Requirements: 1.7, 2.5_

  - [x] 10.3 实现 Prior_Year_Status 分类展示
    - A13-1 汇总分别展示: 上年延续金额、上年转回金额、本年新增金额、净累计
    - _Requirements: 4.4_

  - [x] 10.4 实现阈值跨越通知
    - 聚合结果显示累计从 < PM 跨越到 ≥ PM 时，el-notification warning
    - _Requirements: 3.5_

  - [x]* 10.5 Property 3: 阈值跨越检测属性测试 (fast-check)
    - **Property 3: Materiality threshold transition detection**
    - 随机生成 (old_cumulative, new_cumulative, pm)
    - 验证仅在 old < PM 且 new ≥ PM 时触发通知
    - **Validates: Requirements 3.5**

- [x] 11. 前端：A13-2 错报明细增强
  - [x] 11.1 新增 "来源底稿" 列 + Source_Ref_Chip
    - A13-2 tab 新增列渲染 Source_Ref_Chip (el-tag type="info" + link icon)
    - source_wp_code 非空时显示可点击 chip
    - 点击通过 cross_wp_references 路由跳转源底稿
    - source_wp_code 为空时该行不显示 chip
    - _Requirements: 6.1, 6.2, 6.3, 6.5, 6.6_

  - [x] 11.2 新增 Prior_Year_Status 标签列
    - 每行显示 el-tag: blue="new", orange="continuing", gray="reversed"
    - _Requirements: 4.7_

- [x] 12. 前端：A13-5 沟通函草稿面板
  - [x] 12.1 实现 CommunicationDraftPanel.vue
    - "生成沟通函草稿" 按钮调用 POST communication-draft 端点
    - 无未更正错报时按钮禁用 + 提示 "当前无未更正错报，无需生成沟通函"
    - 展示草稿内容: 条目列表 + 汇总 + 结论
    - 支持复制到 A10-1 或导出
    - 已有持久化草稿时直接展示
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.7_

- [x] 13. 集成联调：保存→聚合→刷新全链路
  - 在 GtMisstatementWorkpaper.vue 中确认 A13-2~5 保存时后端发布 WORKPAPER_SAVED
  - 验证 SSE 推送到前端触发 summary 刷新
  - 验证 Materiality_Indicator 实时更新
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 2.1, 2.5_

- [x] 14. Final checkpoint - 全功能集成验证
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- 后端属性测试使用 hypothesis (max_examples=100)，前端属性测试使用 fast-check
- V092 迁移需注意与 cross-workpaper-dispatch-persistence spec 的 V092 编号冲突，实际编号需协调
- EventBus 发布仅传 EventPayload（踩坑铁律），轻量 SSE 推送用 broadcast_raw
- Aggregation_Resolver 异常时保留旧 summary 不变（Req 1.8）
- 前端 SSE 断开时降级为 tab 切换主动 fetch
