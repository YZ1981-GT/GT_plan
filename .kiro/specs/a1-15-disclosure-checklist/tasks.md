# Tasks — A1-15 企业会计准则财务报表列报及披露核对表

## 1. 注册与配置

- [x] 1.1 更新 `wp_code_overrides.json`：`"A1-15": "a1-15-disclosure-checklist"`（替换当前 `skip`）
- [x] 1.2 后端 `VALID_COMPONENT_TYPES` 新增 `"a1-15-disclosure-checklist"`
- [x] 1.3 后端 `RENDERER_DISPATCH` 新增 `"a1-15-disclosure-checklist": render_a115_disclosure`
- [x] 1.4 `htmlRendererRegistry.ts` 注册 `a1-15-disclosure-checklist`（lazy import GtA115DisclosureChecklist.vue）
- [x] 1.5 `useA1SubWorkpapers.ts` A1-15 componentType → `'a1-15-disclosure-checklist'`
- [x] 1.6 `GtA1Dashboard.vue` 新增 v-else-if 渲染分支识别 `a1-15-disclosure-checklist`
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6_

## 2. 后端渲染策略

- [x] 2.1 创建 `backend/app/routers/wp_render_strategies/_a115_disclosure.py` — render 函数
  - 调用现有 `_parse_a1_15(docx_path)` 获取模板数据（不重写解析器）
  - 从 `checklist_responses` 查询用户 responses（wp_id 过滤）
  - 从 `field_overrides` 查询 toc_applicability（scope=`a115_disclosure:{wp_id}`）
  - 组装 `CROSS_REFERENCE_MAP` 静态映射（10+ 条目）
  - 返回 `{template, responses, cross_reference_map}` 结构
  - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6_

- [x] 2.2 实现 `format_a115_to_summary(parse_output)` 可读文本摘要方法
  - 输出各章节标题 + 条目数量 + 总计
  - 用于 round-trip 验证
  - _Requirements: 10.1, 10.2_

## 3. 前端 composables

- [x] 3.1 创建 `useA115Checklist.ts` — 数据管理 + 持久化
  - loadData(): 自加载 render-config?force_component_type=a1-15-disclosure-checklist
  - updateItemResponse(itemId, field, value): debounce 2s 批量保存
  - setTocApplicability(sectionId, applicable): 级联 NA + 保存 field_overrides
  - globalProgress: computed（y/n/na/unfilled 各数量）
  - sectionProgress(sectionId): {filled, total}
  - searchQuery + conclusionFilter + filteredSections: 搜索与筛选
  - saving/lastSavedAt 状态指示
  - 保存失败重试 3 次 + ElMessage.warning
  - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 8.1, 8.2, 8.3, 8.4, 8.5, 11.1, 11.2, 11.3_

- [x] 3.2 创建 `useA115Navigation.ts` — 章节导航 + section-based lazy rendering
  - activeSectionId: IntersectionObserver 驱动高亮
  - visibleSections: Set<string>（当前 ±1 章节渲染，其余占位 div）
  - scrollToSection(sectionId): 先设 visible 再 scrollIntoView
  - initObserver(): 绑定各章节 sentinel
  - _Requirements: 4.1, 4.2, 4.3, 4.5_

## 4. 前端主组件

- [x] 4.1 创建 `GtA115DisclosureChecklist.vue` — 顶层编排
  - Props: wpId, readonly
  - el-segmented 模式切换（「结构化视图」/「Word 编辑」），默认结构化视图
  - 骨架屏（loading 态）/ 错误提示 + 重试按钮
  - 全局进度环 + Y/N/NA/未填统计
  - 搜索框 + 结论状态筛选下拉
  - "已保存 X秒前" 状态指示
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 8.1, 8.2, 8.3, 8.5, 11.2, 11.3, 11.4_

- [x] 4.2 实现 HTML 模式 — SectionNav 左侧章节导航
  - 35 章节列表，按 TOC 顺序排列
  - 每章节显示 icon（■已完成/◐进行中/□未开始/▧不适用）+ 进度数
  - 点击→scrollToSection
  - TOC_Applicability 标记：不适用章节灰色禁用 + 切换开关
  - 标记不适用时级联所有 actionable→NA
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7_

- [x] 4.3 实现 HTML 模式 — ChecklistBody 核查卡片
  - section-based lazy rendering（仅渲染 visibleSections，其余占位 div）
  - 章节顶部：标题 + 进度统计条（Y/N/NA/未填 + 百分比进度条）+ 建议关联底稿
  - Actionable 卡片：CAS_Ref 左上标签 + content 描述 + Y/N/NA 按钮组 + 备注 + wp_ref 索引
  - 卡片视觉：Y=绿色左边框、N=红色左边框、NA=灰色半透明、未填=白底无边框
  - Header 条目：渲染为章节内小节分隔标题（无交互按钮）
  - Guidance 子项：折叠展开（默认折叠），展开显示只读文本
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7_

- [x] 4.4 实现 HTML 模式 — 科目跳转联动
  - Ref_Index_Chip：渲染为 GtIndexChip，点击跳转对应循环底稿
  - Cross_Reference_Map 建议：未填 wp_ref 时显示虚线边框 suggested chip
  - 点击建议 chip→确认保存为正式关联
  - el-autocomplete 手动输入/修改关联索引号（联想已有 wp_code）
  - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6_

- [x] 4.5 实现 DOCX 模式 — OnlyOffice 渲染
  - activeMode='docx' 时加载 GtOnlyOfficeSheet（sheet-name="A1-15", whole-workbook=true）
  - OnlyOffice 不可用时 disabled + tooltip 提示
  - docx→html 切换时重新请求 render-config 获取最新数据
  - 切换期间 loading=true 防重复操作
  - _Requirements: 2.5, 2.6, 3.1, 3.2, 3.3_

## 5. Checkpoint

- [x] 5. Checkpoint — 注册正确 + 自加载渲染 + 章节导航 + 卡片填写 + 模式切换 + 自动保存
  - Ensure all tests pass, ask the user if questions arise.

## 6. Property-Based Tests — 前端（fast-check）

- [x] 6. 前端 PBT
  - [x]* 6.1 Property 1: 模式互斥渲染 — 任意 mode state 只渲染一个子视图（HTML 或 OnlyOffice）
    - **Property 1: 模式互斥渲染**
    - **Validates: Requirements 2.2, 2.3**
  - [x]* 6.2 Property 2: DOCX→HTML 切换触发刷新 — mode 从 docx→html 必触发 render-config API
    - **Property 2: DOCX→HTML 切换触发刷新**
    - **Validates: Requirements 2.6**
  - [x]* 6.3 Property 3: 章节导航完整有序 — SectionNav 显示 N 个 entry 与 template.sections 顺序一致
    - **Property 3: 章节导航完整有序**
    - **Validates: Requirements 4.2**
  - [x]* 6.4 Property 4: 章节进度计算正确 — filled = 非null结论数, total = actionable数
    - **Property 4: 章节进度计算正确**
    - **Validates: Requirements 4.4, 5.7**
  - [x]* 6.5 Property 5: TOC 适用性级联 — toc_applicability=false 时该章节所有 actionable conclusion='NA'
    - **Property 5: TOC 适用性级联**
    - **Validates: Requirements 4.7**
  - [x]* 6.6 Property 6: Actionable 卡片字段完整 — type=actionable 卡片必含 standard_ref/content/Y-N-NA/remark/wp_ref
    - **Property 6: Actionable 卡片字段完整**
    - **Validates: Requirements 5.1, 5.2, 6.1**
  - [x]* 6.7 Property 7: 结论状态→视觉映射 — Y→green-border, N→red-border, NA→gray, null→no-border
    - **Property 7: 结论状态→视觉映射**
    - **Validates: Requirements 5.3**
  - [x]* 6.8 Property 8: Header 条目渲染为分隔标题 — type=header 无交互按钮
    - **Property 8: Header 条目渲染为分隔标题**
    - **Validates: Requirements 5.6**
  - [x]* 6.9 Property 9: Cross_Reference_Map 建议显示 — 有映射且无 wp_ref 时显示 suggested chip
    - **Property 9: Cross_Reference_Map 建议显示**
    - **Validates: Requirements 6.3**
  - [x]* 6.10 Property 10: 全局进度不变量 — y+n+na+unfilled = total_actionable
    - **Property 10: 全局进度不变量**
    - **Validates: Requirements 8.1, 8.2**
  - [x]* 6.11 Property 11: 筛选正确性 — 可见条目满足 query+filter 条件
    - **Property 11: 筛选正确性**
    - **Validates: Requirements 8.4, 8.5**

## 7. Property-Based Tests — 后端（hypothesis）

- [x] 7. 后端 PBT
  - [x]* 7.1 Property 12: render-config 响应结构完整 — 含 template/responses/cross_reference_map 且字段齐全
    - **Property 12: render-config 响应结构完整**
    - **Validates: Requirements 9.3, 9.4, 9.5**
  - [x]* 7.2 Property 13: 解析器内容保真 — actionable item 的 standard_ref 非空 + content 非空不截断
    - **Property 13: 解析器内容保真**
    - **Validates: Requirements 10.3, 10.4**
  - [x]* 7.3 Property 14: 解析-格式化 Round Trip — format_a115_to_summary 保留章节标题+条目数+total
    - **Property 14: 解析-格式化 Round Trip**
    - **Validates: Requirements 10.2**
  - [x]* 7.4 Property 15: 持久化 Round Trip — save responses→reload→等价
    - **Property 15: 持久化 Round Trip**
    - **Validates: Requirements 7.5, 7.6**

## 8. Unit Tests（vitest）

- [x] 8. vitest 单元测试
  - [x]* 8.1 注册契约 — htmlRendererRegistry 含 a1-15-disclosure-checklist, VALID_COMPONENT_TYPES 含该值, wp_code_overrides 映射正确
  - [x]* 8.2 useA115Checklist 行为 — loadData/updateItemResponse/setTocApplicability/globalProgress/sectionProgress/searchQuery/conclusionFilter
  - [x]* 8.3 useA115Navigation 行为 — scrollToSection/activeSectionId/visibleSections
  - [x]* 8.4 GtA115DisclosureChecklist 组件 — 默认 html 模式、模式切换、骨架屏、错误重试、卡片渲染、结论按钮交互
  - [x]* 8.5 Cross_Reference_Map — 至少覆盖 10 个映射、suggested chip 渲染、确认保存

## 9. 集成与 E2E 测试

- [x] 9. 集成测试
  - [x]* 9.1 后端 `test_render_config_a115.py` — render-config 返回正确 A115RenderConfigResponse 结构
  - [x]* 9.2 Playwright E2E — A1→A1-15 Tab→章节导航→填写 Y/N/NA→自动保存→TOC 标记不适用→切 DOCX→切回→验证数据不丢失

## 10. Final Checkpoint

- [x] 10. Final — 全部测试通过，前后端注册一致，A1 Dashboard 内 A1-15 Tab 正常渲染
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- **复用现有 `_parse_a1_15` 解析器**：后端已完整实现 35 章节解析，仅包装为渲染策略
- **不复用 GtChecklistTable**：通用 UI 无法支持左侧导航、科目跳转联动、章节适用性级联
- 后端 hypothesis PBT 使用 `@settings(max_examples=5)`
- 新增 componentType 必须同步更新 VALID_COMPONENT_TYPES
- OnlyOffice 开发环境 JWT_ENABLED=false，使用 GtOnlyOfficeSheet 组件
- Cross_Reference_Map 静态配置于前端 composable（不从后端动态计算）
- section-based lazy rendering：仅渲染可视区 ±1 章节（IntersectionObserver）
- Tasks marked with `*` are optional and can be skipped for faster MVP
- A1 Dashboard 仅传 wpId，组件自加载 render-config
